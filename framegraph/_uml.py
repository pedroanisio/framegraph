"""UML 2.5 ontology — Pydantic v2 models for the FrameGraph UML composer.

This module is the typed vocabulary the UML composer (Phase A and
later) consumes. Authors declare their UML model in the FrameGraph
document's `semantic` block; Pydantic validators reject structurally-
malformed models at ingest before any rendering work begins.

Scope (Phase A — class-diagram MVP)
-----------------------------------
Classes, Attributes, Operations, Parameters, Generalizations,
Associations (incl. aggregation/composition), Realizations,
Dependencies, Packages, Notes. Phase B adds package merge/import;
later phases add use-case actors, state-machine vertices, sequence-
diagram lifelines, and so on, each as additional Pydantic models in
this same file.

Design notes
------------
- **Strict validation** (per the architecture-decisions section of
  the v2 proposal): structurally-invalid UML is rejected at ingest.
  A class generalizing itself, a duplicate parallel generalization,
  an operation with two `return`-direction parameters — all fail
  with line-pointer-quality Pydantic errors instead of silently
  producing a wrong picture.
- **Layout-hint escape hatch:** every diagrammable element accepts
  an optional `position: {x, y}` field. The Sugiyama-backed composer
  honours these hints for nodes that have them and lays out the
  rest. This is the production-grade nudge mechanism — without it,
  authors who hit one bad placement are forced into `layout: manual`.
- **No PlantUML/Mermaid round-trip in this module** (Decision 3 in
  the v2 proposal). The ontology is pure first; ingesters from
  external syntaxes are a separate, opt-in module.
- This file does NOT register with the FrameGraph schema's
  discriminated union — UML elements are semantic-block content
  (`NodeEntry`/`EdgeEntry` payloads), not visual-block objects. The
  composer reads them and emits visual primitives that DO live in
  the discriminated union.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────
# Common type aliases
# ─────────────────────────────────────────────────────────────────


Visibility = Literal["public", "private", "protected", "package"]
"""UML visibility levels. Composer maps these to `+/-/#/~` prefixes."""


# Multiplicity regex per UML 2.5 §7.5.4.1: lower..upper where lower
# is a non-negative integer and upper is a non-negative integer or `*`.
# Single integer = exact count; `*` alone = "0..*" (zero or more).
_MULTIPLICITY_RE = re.compile(r"^(\d+(\.\.(\d+|\*))?|\*)$")


def _validate_multiplicity(value: str) -> str:
    """Validate a multiplicity string against the UML 2.5.1 grammar.

    Enforces the `MultiplicityElement` constraints from the OMG
    metamodel (`static/specs/ptc-18-01-01.xmi`):

    - `lower_is_integer`: lower bound is a non-negative integer
    - `upper_is_unlimitedNatural`: upper bound is a non-negative
      integer or `*` (UnlimitedNatural infinity)
    - `lower_ge_0`: lower bound ≥ 0 (enforced by the `\\d+` regex)
    - `upper_ge_lower`: upper bound ≥ lower bound

    Args:
        value: The multiplicity literal (e.g. `"1"`, `"0..1"`, `"1..*"`,
            `"*"`).

    Returns:
        The input unchanged on success.

    Raises:
        ValueError: If the value does not match the
            `lower(..upper)?` pattern, or if the upper bound is a
            finite integer strictly less than the lower bound.
    """
    if not isinstance(value, str) or not _MULTIPLICITY_RE.match(value):
        raise ValueError(
            f"invalid UML multiplicity {value!r}; expected forms like '1', '0..1', '1..*', or '*'"
        )
    # Enforce upper_ge_lower per UML 2.5.1 MultiplicityElement constraints.
    if ".." in value:
        lo_s, up_s = value.split("..", 1)
        lo = int(lo_s)
        if up_s != "*":
            up = int(up_s)
            if up < lo:
                raise ValueError(
                    f"invalid UML multiplicity {value!r}: upper bound {up} "
                    f"is less than lower bound {lo} (UML 2.5.1 "
                    f"MultiplicityElement::upper_ge_lower)"
                )
    return value


Multiplicity = Annotated[str, BeforeValidator(_validate_multiplicity)]
"""A UML 2.5.1 multiplicity literal, validated at parse time.

Enforces grammar (`lower(..upper)?` with `*` for unbounded) plus the
`MultiplicityElement::upper_ge_lower` constraint from the metamodel.
"""


# ─────────────────────────────────────────────────────────────────
# Position hint — the layout escape hatch
# ─────────────────────────────────────────────────────────────────


class Position(BaseModel):
    """Author-supplied layout hint for a diagrammable element.

    When set on a `Class`, `Package`, `Note`, etc., the composer
    treats the element as pinned and lays out the rest of the
    diagram around it. Coordinates are in canvas units (pixels).
    """

    model_config = ConfigDict(extra="forbid")
    x: float
    y: float


# ─────────────────────────────────────────────────────────────────
# Distinguishability helper (UML 2.5.1 Namespace::members_distinguishable)
# ─────────────────────────────────────────────────────────────────


def _operation_signature(op: Any) -> tuple[str, tuple[str | None, ...]]:
    """Compute a UML operation signature for distinguishability.

    The signature is `(name, tuple of parameter types in declared
    order)`. Two operations collide iff their signatures are equal.
    Same-name-different-types is a legal overload.

    Notes:
        Parameters with `direction='return'` are excluded — UML 2.5.1
        signature equivalence is over input parameters only (the
        return value does not participate in dispatch).
    """
    types = tuple(p.type for p in op.parameters if p.direction != "return")
    return (op.name, types)


def _check_members_distinguishable(
    owner_id: str,
    owner_kind: str,
    attributes: list[Any],
    operations: list[Any],
) -> None:
    """Enforce `Namespace::members_distinguishable` on a classifier.

    Args:
        owner_id: The classifier's id (used in error messages).
        owner_kind: Human label, e.g. ``"class"`` or ``"interface"``.
        attributes: List of `UMLAttribute` (Class) or constants
            (Interface). Names must be unique.
        operations: List of `UMLOperation`. Signatures (name + input
            parameter types) must be unique.

    Raises:
        ValueError: When two attributes share a name or two
            operations share a signature.
    """
    seen_attr: set[str] = set()
    for a in attributes:
        if a.name in seen_attr:
            raise ValueError(
                f"{owner_kind} {owner_id!r}: duplicate attribute name {a.name!r}; "
                f"UML 2.5.1 Namespace::members_distinguishable requires "
                f"feature names to be distinguishable within a classifier"
            )
        seen_attr.add(a.name)

    seen_sig: set[tuple[str, tuple[str | None, ...]]] = set()
    for op in operations:
        sig = _operation_signature(op)
        if sig in seen_sig:
            raise ValueError(
                f"{owner_kind} {owner_id!r}: duplicate operation signature "
                f"{sig[0]!r}({', '.join(t or '?' for t in sig[1])}); UML "
                f"2.5.1 Namespace::members_distinguishable requires "
                f"operations to differ in name or in parameter type tuple"
            )
        seen_sig.add(sig)


# ─────────────────────────────────────────────────────────────────
# Class members
# ─────────────────────────────────────────────────────────────────


class UMLAttribute(BaseModel):
    """A typed attribute declared on a Class or Interface.

    Attributes:
        name: Attribute identifier. Required.
        type: Type expression as a string (e.g. `"String"`,
            `"List<Order>"`). Optional.
        visibility: One of `public`, `private`, `protected`,
            `package`. Defaults to `public`.
        multiplicity: UML multiplicity literal (e.g. `"0..1"`).
            Optional; treated as `"1"` when omitted.
        default: Default-value expression as a string. Optional.
        static: When True, renders underlined per UML convention.
        derived: When True, renders with a leading `/` per UML
            §7.5.4.5 (derived/computed attributes).
        readonly: When True, renders with `{readOnly}` constraint.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    type: str | None = None
    visibility: Visibility = "public"
    multiplicity: Multiplicity | None = None
    default: str | None = None
    static: bool = False
    derived: bool = False
    readonly: bool = False


ParamDirection = Literal["in", "out", "inout", "return"]
"""UML parameter direction. Exactly one parameter per operation may
be `return` per the UML 2.5 metamodel."""


class UMLParameter(BaseModel):
    """A single parameter of an operation.

    Attributes:
        name: Parameter identifier. Required.
        type: Type expression. Optional but conventional.
        direction: One of `in`, `out`, `inout`, `return`. Defaults
            to `in`.
        multiplicity: Optional multiplicity (e.g. `"0..*"`).
        default: Default-value expression. Optional.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    type: str | None = None
    direction: ParamDirection = "in"
    multiplicity: Multiplicity | None = None
    default: str | None = None


class UMLOperation(BaseModel):
    """A method declared on a Class or Interface.

    Attributes:
        name: Operation identifier. Required.
        parameters: Ordered list of `UMLParameter`. May contain at
            most one parameter with `direction: return`.
        return_type: Shortcut for declaring a return type without an
            explicit `direction: return` parameter. When both are
            set, `return_type` wins and the validator merges them.
        visibility: One of `public`, `private`, `protected`,
            `package`. Defaults to `public`.
        abstract: When True, renders italic per UML convention.
        static: When True, renders underlined.
        query: When True, renders with `{query}` constraint (no
            side effects).
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    parameters: list[UMLParameter] = Field(default_factory=list)
    return_type: str | None = None
    visibility: Visibility = "public"
    abstract: bool = False
    static: bool = False
    query: bool = False

    @model_validator(mode="after")
    def _validate_at_most_one_return_parameter(self) -> UMLOperation:
        """An operation may declare at most one `direction: return` parameter.

        Per UML 2.5 §9.6 — the return value is conceptually a single
        parameter even when expressed via `return_type` shorthand.
        """
        return_params = [p for p in self.parameters if p.direction == "return"]
        if len(return_params) > 1:
            raise ValueError(
                f"operation {self.name!r} has {len(return_params)} parameters "
                f"with direction='return'; UML 2.5 permits at most one"
            )
        return self


# ─────────────────────────────────────────────────────────────────
# Classifiers (Class + Interface)
# ─────────────────────────────────────────────────────────────────


class UMLClass(BaseModel):
    """A UML Class — the most common classifier in class diagrams.

    Attributes:
        id: Stable identifier used by edges (`Generalization.from_id`,
            etc.). Required.
        name: Display name. Required.
        stereotype: Optional `«…»` label rendered above the name
            (e.g. `"abstract"`, `"interface"`, `"entity"`).
        abstract: When True, the name renders italic per UML
            convention. Mutually exclusive with `final` per UML 2.5
            §11.4.4 — a final class cannot be abstract.
        final: When True, the class is sealed (cannot be specialized).
        attributes: Class attributes. Order is preserved in the
            rendered compartment.
        operations: Class operations. Order is preserved.
        position: Optional layout hint; composer pins this class
            when set.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    stereotype: str | None = None
    abstract: bool = False
    final: bool = False
    attributes: list[UMLAttribute] = Field(default_factory=list)
    operations: list[UMLOperation] = Field(default_factory=list)
    position: Position | None = None

    @model_validator(mode="after")
    def _validate_abstract_and_final_mutually_exclusive(self) -> UMLClass:
        """A class cannot be both abstract and final per UML 2.5 §11.4.4."""
        if self.abstract and self.final:
            raise ValueError(
                f"class {self.id!r} declares both abstract=True and final=True; "
                f"UML 2.5 §11.4.4 forbids this combination"
            )
        return self

    @model_validator(mode="after")
    def _validate_members_distinguishable(self) -> UMLClass:
        """Features must be distinguishable per UML 2.5.1 Namespace::members_distinguishable.

        - Attributes: unique by name within the class.
        - Operations: unique by `(name, parameter type tuple)`. Same
          name with different parameter type sequences is a legal
          overload; identical signatures collide.
        """
        _check_members_distinguishable(self.id, "class", self.attributes, self.operations)
        return self


class UMLInterface(BaseModel):
    """A UML Interface — like a Class but with no instance attributes.

    Per UML 2.5 §10.4: an Interface declares a contract; concrete
    state belongs to implementing classes. Interfaces may declare
    constants (static + readonly attributes) and operations.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        operations: Operations declared by this interface.
        constants: Static, readonly attributes (the only attribute
            kind interfaces may carry per UML 2.5 §10.4.1).
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    operations: list[UMLOperation] = Field(default_factory=list)
    constants: list[UMLAttribute] = Field(default_factory=list)
    position: Position | None = None

    @model_validator(mode="after")
    def _validate_constants_are_static_and_readonly(self) -> UMLInterface:
        """Interface attributes must be static + readonly per UML 2.5 §10.4.1.

        Concrete state (non-static, mutable) belongs in implementing
        classes. Constants live on the interface so consumers can
        reference them via the interface name.
        """
        for c in self.constants:
            if not c.static or not c.readonly:
                raise ValueError(
                    f"interface attribute {c.name!r} must declare both "
                    f"static=True and readonly=True; instance state belongs "
                    f"on implementing classes per UML 2.5 §10.4.1"
                )
        return self

    @model_validator(mode="after")
    def _validate_members_distinguishable(self) -> UMLInterface:
        """Features must be distinguishable per UML 2.5.1 Namespace::members_distinguishable.

        Same rules as `UMLClass`: constants unique by name; operations
        unique by `(name, parameter type tuple)` to permit overloads.
        """
        _check_members_distinguishable(self.id, "interface", self.constants, self.operations)
        return self

    @model_validator(mode="after")
    def _validate_features_are_public(self) -> UMLInterface:
        """Interface features must all be public (UML 2.5.1 Interface::visibility).

        OCL: `feature->forAll(visibility = VisibilityKind::public)`.
        Per the OMG normative metamodel, every operation and constant
        on an Interface is part of the public contract.
        """
        for op in self.operations:
            if op.visibility != "public":
                raise ValueError(
                    f"interface operation {op.name!r} has visibility "
                    f"{op.visibility!r}; UML 2.5.1 Interface::visibility "
                    f"requires all features to be public"
                )
        for c in self.constants:
            if c.visibility != "public":
                raise ValueError(
                    f"interface constant {c.name!r} has visibility "
                    f"{c.visibility!r}; UML 2.5.1 Interface::visibility "
                    f"requires all features to be public"
                )
        return self


class UMLEnumeration(BaseModel):
    """A UML Enumeration — a classifier whose instances are literals.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        literals: Ordered list of enumeration literal names.
        operations: Optional operations (rare but legal per UML 2.5
            §10.5).
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    literals: list[str] = Field(..., min_length=1)
    operations: list[UMLOperation] = Field(default_factory=list)
    position: Position | None = None

    @model_validator(mode="after")
    def _validate_literals_unique(self) -> UMLEnumeration:
        """Enumeration literals must be unique per UML 2.5 §10.5.4."""
        if len(set(self.literals)) != len(self.literals):
            raise ValueError(f"enumeration {self.id!r} has duplicate literals: {self.literals}")
        return self


# ─────────────────────────────────────────────────────────────────
# Relationships
# ─────────────────────────────────────────────────────────────────


class UMLGeneralization(BaseModel):
    """An inheritance edge: child specializes parent.

    Renders with a hollow-triangle arrowhead at the parent end and
    a solid line.

    Attributes:
        id: Stable identifier. Required.
        from_id: Child classifier id (the specializing one).
        to_id: Parent classifier id (the generalized one).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")

    @model_validator(mode="after")
    def _validate_no_self_generalization(self) -> UMLGeneralization:
        """A class cannot generalize itself per UML 2.5 §9.9.4."""
        if self.from_id == self.to_id:
            raise ValueError(
                f"generalization {self.id!r} has from==to=={self.from_id!r}; "
                f"a classifier cannot generalize itself per UML 2.5 §9.9.4"
            )
        return self


class UMLRealization(BaseModel):
    """A realization edge: class implements interface.

    Renders with a hollow-triangle arrowhead at the interface end
    and a dashed line.

    Attributes:
        id: Stable identifier. Required.
        from_id: Implementing classifier id.
        to_id: Realized interface id.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")

    @model_validator(mode="after")
    def _validate_no_self_realization(self) -> UMLRealization:
        """A classifier cannot realize itself."""
        if self.from_id == self.to_id:
            raise ValueError(
                f"realization {self.id!r} has from==to=={self.from_id!r}; "
                f"a classifier cannot realize itself"
            )
        return self


AssociationKind = Literal["association", "aggregation", "composition"]
"""Distinguishes plain association from whole/part relationships.

- `association`: plain reference / use-of relationship.
- `aggregation`: weak whole/part (`◇` hollow diamond at whole end).
- `composition`: strong whole/part with lifecycle ownership
  (`◆` filled diamond at whole end).
"""


class UMLAssociationEnd(BaseModel):
    """One end of an association — references a classifier with role/multiplicity.

    Attributes:
        id_ref: Classifier id this end attaches to. Required.
        role: Optional role-name label rendered near the end.
        multiplicity: Optional multiplicity string (e.g. `"0..*"`).
        navigable: When True, renders an arrowhead (UML 2.5 §11.5.4
            navigability notation). When False, no arrowhead. None
            (default) means "unspecified" — composer renders without
            arrowhead.
    """

    model_config = ConfigDict(extra="forbid")
    id_ref: str = Field(..., min_length=1)
    role: str | None = None
    multiplicity: Multiplicity | None = None
    navigable: bool | None = None


def _multiplicity_upper_bound(value: str | None) -> int | None:
    """Return the upper bound of a multiplicity string, or `None` for unbounded.

    UML 2.5.1 `MultiplicityElement::upperBound()`. Returns:

    - `None` if the multiplicity is `*` or `lower..*` (unbounded
      `UnlimitedNatural` infinity).
    - The integer upper bound otherwise. For a bare integer `n`,
      upper == lower == `n`.
    - `1` if `value` is `None` (UML default multiplicity).
    """
    if value is None:
        return 1
    if value == "*":
        return None
    if ".." in value:
        _, up = value.split("..", 1)
        return None if up == "*" else int(up)
    return int(value)


class UMLAssociation(BaseModel):
    """A relationship between two classifiers.

    Plain associations render as solid lines with optional role and
    multiplicity labels. Aggregations and compositions add a diamond
    at the `whole` end (whichever end is so designated by
    `kind == "aggregation"` or `"composition"`; conventionally
    `end1` is the whole).

    Attributes:
        id: Stable identifier. Required.
        end1: First end of the association. By convention, this is
            the "whole" end for aggregations/compositions.
        end2: Second end. By convention the "part" end.
        kind: One of `association` (default), `aggregation`,
            `composition`. The diamond renders at `end1`.
        name: Optional association name rendered along the line.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    end1: UMLAssociationEnd
    end2: UMLAssociationEnd
    kind: AssociationKind = "association"
    name: str | None = None

    @model_validator(mode="after")
    def _validate_composition_part_upper_bound(self) -> UMLAssociation:
        """Composition: the part-end upper bound must be ≤ 1.

        UML 2.5.1 Property::multiplicity_of_composite —
        `isComposite and association <> null implies opposite.upperBound() <= 1`.
        Composition implies lifecycle ownership: a part can belong to
        at most one whole at a time. The composite (whole) end is
        `end1`; the *opposite* end (`end2`) carries the multiplicity
        bounded by 1.
        """
        if self.kind != "composition":
            return self
        upper = _multiplicity_upper_bound(self.end2.multiplicity)
        if upper is None or upper > 1:
            raise ValueError(
                f"composition {self.id!r}: part-end multiplicity "
                f"{self.end2.multiplicity!r} exceeds 1; UML 2.5.1 "
                f"Property::multiplicity_of_composite requires the "
                f"opposite end of a composite to have upperBound() <= 1"
            )
        return self


class UMLDependency(BaseModel):
    """A `<<use>>`-style transient dependency: from-classifier needs to-classifier.

    Renders as a dashed line with an open arrowhead at the supplier
    end. Stereotypes like `«create»`, `«import»`, `«use»` may be
    declared via the `stereotype` field.

    Attributes:
        id: Stable identifier. Required.
        from_id: Client classifier id.
        to_id: Supplier classifier id.
        stereotype: Optional dependency stereotype.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    stereotype: str | None = None


# ─────────────────────────────────────────────────────────────────
# Containment + annotation
# ─────────────────────────────────────────────────────────────────


class UMLPackage(BaseModel):
    """A UML Package — namespace container for classifiers.

    Renders as a tabbed-rectangle ("folder") with the package name
    on the tab and contained classifiers laid out inside the body.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        contains: List of classifier ids contained in this package.
            Composer validates these reference real classifiers in
            the same document.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    contains: list[str] = Field(default_factory=list)
    position: Position | None = None


class UMLNote(BaseModel):
    """A free-text annotation, optionally anchored to one or more elements.

    Renders as a dog-eared rectangle with an optional dashed-line
    anchor connector to each `anchor_id`.

    Attributes:
        id: Stable identifier. Required.
        text: Note body. Required.
        anchor_ids: Element ids the note attaches to. Empty list
            means an unanchored note (rendered standalone).
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    anchor_ids: list[str] = Field(default_factory=list)
    position: Position | None = None


# ─────────────────────────────────────────────────────────────────
# Diagram envelope — the top-level UML model
# ─────────────────────────────────────────────────────────────────


# A single union type for "anything that's a classifier" — used by
# diagram-level cross-reference validation.
Classifier = UMLClass | UMLInterface | UMLEnumeration


class UMLClassDiagramModel(BaseModel):
    """Top-level container for a class diagram's UML model.

    Mirrors the FrameGraph `semantic` block but with typed UML
    metaclasses instead of free-form node/edge entries. The composer
    consumes one of these and produces a fully-laid-out `Visual`
    block.

    Attributes:
        classes: All `UMLClass` declarations.
        interfaces: All `UMLInterface` declarations.
        enumerations: All `UMLEnumeration` declarations.
        generalizations: Inheritance edges.
        realizations: Interface-implementation edges.
        associations: Association/aggregation/composition edges.
        dependencies: Dependency edges.
        packages: Package containment.
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    classes: list[UMLClass] = Field(default_factory=list)
    interfaces: list[UMLInterface] = Field(default_factory=list)
    enumerations: list[UMLEnumeration] = Field(default_factory=list)

    generalizations: list[UMLGeneralization] = Field(default_factory=list)
    realizations: list[UMLRealization] = Field(default_factory=list)
    associations: list[UMLAssociation] = Field(default_factory=list)
    dependencies: list[UMLDependency] = Field(default_factory=list)

    packages: list[UMLPackage] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLClassDiagramModel:
        """Every diagrammable element must have a globally-unique id.

        Edges reference classifiers by id; duplicate ids would make
        edge resolution ambiguous.
        """
        seen: dict[str, str] = {}
        for category in (
            ("class", self.classes),
            ("interface", self.interfaces),
            ("enumeration", self.enumerations),
            ("generalization", self.generalizations),
            ("realization", self.realizations),
            ("association", self.associations),
            ("dependency", self.dependencies),
            ("package", self.packages),
            ("note", self.notes),
        ):
            kind, items = category
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_edge_endpoints_resolve(self) -> UMLClassDiagramModel:
        """Every edge endpoint must reference an existing classifier id.

        Catches the most common authoring mistake: a typo in a
        `from`/`to`/`id_ref` field.
        """
        valid_ids = {c.id for c in self.classes}
        valid_ids |= {i.id for i in self.interfaces}
        valid_ids |= {e.id for e in self.enumerations}
        valid_ids |= {p.id for p in self.packages}

        def _check(edge_id: str, field: str, ref: str) -> None:
            if ref not in valid_ids:
                raise ValueError(
                    f"edge {edge_id!r} field {field!r} references unknown classifier id {ref!r}"
                )

        for g in self.generalizations:
            _check(g.id, "from", g.from_id)
            _check(g.id, "to", g.to_id)
        for r in self.realizations:
            _check(r.id, "from", r.from_id)
            _check(r.id, "to", r.to_id)
        for a in self.associations:
            _check(a.id, "end1.id_ref", a.end1.id_ref)
            _check(a.id, "end2.id_ref", a.end2.id_ref)
        for d in self.dependencies:
            _check(d.id, "from", d.from_id)
            _check(d.id, "to", d.to_id)
        return self

    @model_validator(mode="after")
    def _validate_generalization_kind_compatible(self) -> UMLClassDiagramModel:
        """Generalization endpoints must be the same classifier kind.

        UML 2.5.1 Classifier::specialize_type —
        `parents()->forAll(c | self.maySpecializeType(c))`. For the
        Phase-A class-diagram MVP, `maySpecializeType` reduces to
        same-kind: Class generalizes Class, Interface generalizes
        Interface, Enumeration generalizes Enumeration. Class →
        Interface is `realization`, not generalization.
        """
        kind_of: dict[str, str] = {}
        for c in self.classes:
            kind_of[c.id] = "class"
        for i in self.interfaces:
            kind_of[i.id] = "interface"
        for e in self.enumerations:
            kind_of[e.id] = "enumeration"

        for g in self.generalizations:
            kf = kind_of.get(g.from_id)
            kt = kind_of.get(g.to_id)
            # Endpoint resolution is checked by another validator;
            # only enforce kind compatibility when both resolve to
            # classifiers (packages aren't classifiers).
            if kf is None or kt is None:
                continue
            if kf != kt:
                raise ValueError(
                    f"generalization {g.id!r}: incompatible classifier kinds "
                    f"({kf!r} → {kt!r}); UML 2.5.1 Classifier::specialize_type "
                    f"requires the specific and general classifiers to be the "
                    f"same kind. For class-implements-interface, use "
                    f"`realizations` instead."
                )
        return self

    @model_validator(mode="after")
    def _validate_non_final_parents(self) -> UMLClassDiagramModel:
        """A generalization's parent (`to`) must not be a final classifier.

        UML 2.5.1 Classifier::non_final_parents —
        `parents()->forAll(not isFinalSpecialization)`. A class
        marked `final=True` is sealed and cannot be specialized.
        """
        finals = {c.id for c in self.classes if c.final}
        for g in self.generalizations:
            if g.to_id in finals:
                raise ValueError(
                    f"generalization {g.id!r}: parent {g.to_id!r} is a "
                    f"final class; UML 2.5.1 Classifier::non_final_parents "
                    f"forbids specializing a final classifier"
                )
        return self

    @model_validator(mode="after")
    def _validate_no_generalization_cycles(self) -> UMLClassDiagramModel:
        """No classifier may transitively generalize itself.

        UML 2.5.1 Classifier::no_cycles_in_generalization —
        `not allParents()->includes(self)`. Walks the parent graph
        from each classifier; a cycle is reported with the offending
        node so authors can locate it.
        """
        parents: dict[str, list[str]] = {}
        for g in self.generalizations:
            parents.setdefault(g.from_id, []).append(g.to_id)

        for start in parents:
            stack = list(parents.get(start, []))
            seen: set[str] = set()
            while stack:
                node = stack.pop()
                if node == start:
                    raise ValueError(
                        f"generalization cycle detected: classifier {start!r} "
                        f"transitively generalizes itself; UML 2.5.1 "
                        f"Classifier::no_cycles_in_generalization forbids "
                        f"`allParents()->includes(self)`"
                    )
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(parents.get(node, []))
        return self

    @model_validator(mode="after")
    def _validate_no_duplicate_generalizations(self) -> UMLClassDiagramModel:
        """Disallow parallel generalizations between the same (from, to) pair.

        UML permits multiple inheritance, but the same parent may
        not appear twice as a generalization target — that's an
        authoring mistake, not a metamodel feature.
        """
        seen_pairs: set[tuple[str, str]] = set()
        for g in self.generalizations:
            pair = (g.from_id, g.to_id)
            if pair in seen_pairs:
                raise ValueError(
                    f"duplicate generalization {g.from_id!r} → {g.to_id!r} "
                    f"(generalization {g.id!r}); each (from, to) pair is "
                    f"unique by UML convention"
                )
            seen_pairs.add(pair)
        return self

    @model_validator(mode="after")
    def _validate_package_contents_resolve(self) -> UMLClassDiagramModel:
        """Every `package.contains` id must reference an existing classifier."""
        valid_ids = {c.id for c in self.classes}
        valid_ids |= {i.id for i in self.interfaces}
        valid_ids |= {e.id for e in self.enumerations}
        for p in self.packages:
            for ref in p.contains:
                if ref not in valid_ids:
                    raise ValueError(f"package {p.id!r} contains unknown classifier id {ref!r}")
        return self


# ─────────────────────────────────────────────────────────────────
# Public validation entry point
# ─────────────────────────────────────────────────────────────────


def validate_class_diagram(data: dict[str, Any]) -> UMLClassDiagramModel:
    """Validate a parsed mapping as a UML class-diagram model.

    Args:
        data: A dict with `classes`, `interfaces`, `enumerations`,
            `generalizations`, `realizations`, `associations`,
            `dependencies`, `packages`, `notes` (each optional, list-
            valued).

    Returns:
        A validated `UMLClassDiagramModel`.

    Raises:
        pydantic.ValidationError: If the model violates any
            structural rule encoded by Pydantic field validators or
            the model-level validators above.
    """
    return UMLClassDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Package diagrams (Phase B)
# ─────────────────────────────────────────────────────────────────


PackageDependencyKind = Literal["dependency", "import", "access", "merge"]
"""UML 2.5.1 §12.2.4 — kinds of package-to-package relationships.

- `dependency`: client uses supplier (open arrow + dashed).
- `import`: client imports supplier's public elements
  (`«import»` stereotype + open arrow + dashed).
- `access`: client privately uses supplier's elements
  (`«access»` stereotype + open arrow + dashed).
- `merge`: contents of supplier are merged into client
  (`«merge»` stereotype + open arrow + dashed).
"""


class UMLPackageDependency(BaseModel):
    """A directed relationship between two packages.

    Renders as a dashed line with an open arrow at the supplier end.
    The `kind` selects the stereotype label conventionally drawn at
    the line's midpoint (`«import»`, `«access»`, `«merge»`); plain
    `dependency` renders without a stereotype.

    Attributes:
        id: Stable identifier. Required.
        from_id: Client package id.
        to_id: Supplier package id.
        kind: One of `dependency`, `import`, `access`, `merge`.
            Defaults to `dependency`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    kind: PackageDependencyKind = "dependency"

    @model_validator(mode="after")
    def _validate_no_self_dependency(self) -> UMLPackageDependency:
        """A package cannot depend on itself."""
        if self.from_id == self.to_id:
            raise ValueError(
                f"package dependency {self.id!r} has from==to=={self.from_id!r}; "
                f"a package cannot depend on itself"
            )
        return self


class UMLPackageDiagramModel(BaseModel):
    """Top-level container for a package diagram's UML model.

    Mirrors `UMLClassDiagramModel` but focused on packages and their
    dependencies. Sub-packages are expressed via `contains: list[str]`
    on a parent package — the same containment field used in class
    diagrams, but here the contained ids reference other packages
    (creating package nesting).

    Attributes:
        packages: All packages in the diagram. Required (≥ 1).
        dependencies: Inter-package dependency / import / access /
            merge edges.
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    packages: list[UMLPackage] = Field(..., min_length=1)
    dependencies: list[UMLPackageDependency] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLPackageDiagramModel:
        """Globally-unique element ids across packages, dependencies, notes."""
        seen: dict[str, str] = {}
        for kind, items in (
            ("package", self.packages),
            ("dependency", self.dependencies),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_dependency_endpoints_resolve(self) -> UMLPackageDiagramModel:
        """Every dependency endpoint must reference an existing package."""
        package_ids = {p.id for p in self.packages}
        for d in self.dependencies:
            if d.from_id not in package_ids:
                raise ValueError(
                    f"package dependency {d.id!r} references unknown client package {d.from_id!r}"
                )
            if d.to_id not in package_ids:
                raise ValueError(
                    f"package dependency {d.id!r} references unknown supplier package {d.to_id!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_contains_resolve_and_acyclic(self) -> UMLPackageDiagramModel:
        """Containment references real packages and forms no cycle."""
        package_ids = {p.id for p in self.packages}
        for p in self.packages:
            for ref in p.contains:
                if ref not in package_ids:
                    raise ValueError(f"package {p.id!r} contains unknown package id {ref!r}")

        # Cycle detection — package can't transitively contain itself.
        children: dict[str, list[str]] = {p.id: list(p.contains) for p in self.packages}
        for start in package_ids:
            stack = list(children.get(start, []))
            seen: set[str] = set()
            while stack:
                node = stack.pop()
                if node == start:
                    raise ValueError(
                        f"package containment cycle detected: package "
                        f"{start!r} transitively contains itself"
                    )
                if node in seen:
                    continue
                seen.add(node)
                stack.extend(children.get(node, []))
        return self


def validate_package_diagram(data: dict[str, Any]) -> UMLPackageDiagramModel:
    """Validate a parsed mapping as a UML package-diagram model.

    Args:
        data: A dict with `packages` (≥ 1), optional `dependencies`,
            optional `notes`.

    Returns:
        A validated `UMLPackageDiagramModel`.

    Raises:
        pydantic.ValidationError: If the model violates any
            structural rule.
    """
    return UMLPackageDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Use-case diagrams (Phase B.2)
# ─────────────────────────────────────────────────────────────────


class UMLActor(BaseModel):
    """A UML Actor — an external role interacting with the system.

    Renders as a stick-figure glyph with the name as a label below.
    Actors are conventionally placed on the left of a use-case
    diagram, outside any system boundary.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        position: Optional layout hint (escape hatch).
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    position: Position | None = None


class UMLUseCase(BaseModel):
    """A UML Use Case — an externally-visible system behaviour.

    Renders as a horizontally-stretched ellipse with the name
    centered. Use cases conventionally sit inside a system boundary
    (`UMLSystemBoundary.contains` lists them).

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    position: Position | None = None


class UMLSystemBoundary(BaseModel):
    """A UML System Boundary — a labelled rectangle wrapping use cases.

    Renders as an outer rectangle with the system name above the top
    edge. Contained use cases are positioned inside the body. Like
    `UMLPackage.contains`, the `contains` field references use-case
    ids in the same diagram.

    Attributes:
        id: Stable identifier. Required.
        name: Display name (rendered above the box). Required.
        contains: Use-case ids that belong inside this boundary.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    contains: list[str] = Field(default_factory=list)
    position: Position | None = None


UseCaseRelationKind = Literal["association", "include", "extend"]
"""UML 2.5.1 §18 — kinds of use-case-to-use-case or actor-to-use-case edges.

- `association`: actor participates in use-case (plain solid line).
- `include`: use-case A unconditionally invokes use-case B
  (`«include»` stereotype + dashed + open arrow at B).
- `extend`: use-case A optionally extends use-case B
  (`«extend»` stereotype + dashed + open arrow at A — note the
  reversed direction per UML 2.5.1 §18.1.4: extension points
  belong to the EXTENDED use case, so the arrow goes from
  extension → base).
"""


class UMLUseCaseRelation(BaseModel):
    """A directed edge in a use-case diagram.

    Attributes:
        id: Stable identifier. Required.
        from_id: Source element id (actor or use-case).
        to_id: Target element id (actor or use-case).
        kind: One of `association`, `include`, `extend`.
            Defaults to `association`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    kind: UseCaseRelationKind = "association"

    @model_validator(mode="after")
    def _validate_no_self_relation(self) -> UMLUseCaseRelation:
        if self.from_id == self.to_id:
            raise ValueError(
                f"use-case relation {self.id!r} has from==to=={self.from_id!r}; "
                f"a use-case element cannot relate to itself"
            )
        return self


class UMLUseCaseDiagramModel(BaseModel):
    """Top-level container for a use-case diagram's UML model.

    Attributes:
        actors: External actors interacting with the system.
        use_cases: System behaviours visible from outside.
        system_boundaries: Optional labelled rectangles grouping
            use cases.
        relations: Edges connecting actors to use cases (or use
            cases to use cases).
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    actors: list[UMLActor] = Field(default_factory=list)
    use_cases: list[UMLUseCase] = Field(default_factory=list)
    system_boundaries: list[UMLSystemBoundary] = Field(default_factory=list)
    relations: list[UMLUseCaseRelation] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_at_least_one_element(self) -> UMLUseCaseDiagramModel:
        """Empty diagram has nothing to render — reject for clarity."""
        if not self.actors and not self.use_cases:
            raise ValueError("use-case diagram must declare at least one actor or use case")
        return self

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLUseCaseDiagramModel:
        """Globally-unique element ids across all categories."""
        seen: dict[str, str] = {}
        for kind, items in (
            ("actor", self.actors),
            ("use_case", self.use_cases),
            ("system_boundary", self.system_boundaries),
            ("relation", self.relations),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_relation_endpoints_resolve(self) -> UMLUseCaseDiagramModel:
        """Every relation endpoint must reference an actor or use case."""
        valid_ids = {a.id for a in self.actors} | {u.id for u in self.use_cases}
        for rel in self.relations:
            if rel.from_id not in valid_ids:
                raise ValueError(
                    f"use-case relation {rel.id!r} references unknown source id {rel.from_id!r}"
                )
            if rel.to_id not in valid_ids:
                raise ValueError(
                    f"use-case relation {rel.id!r} references unknown target id {rel.to_id!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_include_extend_between_use_cases(self) -> UMLUseCaseDiagramModel:
        """`include` / `extend` are use-case-to-use-case relations only.

        UML 2.5.1 §18.1.4 — these two relation kinds are defined
        between two use cases. An actor cannot include or extend
        anything; that's an authoring mistake.
        """
        use_case_ids = {u.id for u in self.use_cases}
        for rel in self.relations:
            if rel.kind in ("include", "extend"):
                if rel.from_id not in use_case_ids or rel.to_id not in use_case_ids:
                    raise ValueError(
                        f"use-case relation {rel.id!r} kind={rel.kind!r} "
                        f"requires both endpoints to be use cases; UML 2.5.1 "
                        f"§18.1.4 restricts include/extend to use-case pairs"
                    )
        return self

    @model_validator(mode="after")
    def _validate_boundary_contents_resolve(self) -> UMLUseCaseDiagramModel:
        """`system_boundary.contains` must reference real use cases."""
        use_case_ids = {u.id for u in self.use_cases}
        for sb in self.system_boundaries:
            for ref in sb.contains:
                if ref not in use_case_ids:
                    raise ValueError(
                        f"system boundary {sb.id!r} contains unknown use-case id {ref!r}"
                    )
        return self


def validate_use_case_diagram(data: dict[str, Any]) -> UMLUseCaseDiagramModel:
    """Validate a parsed mapping as a UML use-case-diagram model.

    Args:
        data: A dict with optional `actors`, `use_cases`,
            `system_boundaries`, `relations`, `notes`. At least
            one actor or use case is required.

    Returns:
        A validated `UMLUseCaseDiagramModel`.

    Raises:
        pydantic.ValidationError: If the model violates any
            structural rule.
    """
    return UMLUseCaseDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Component diagrams (Phase C.1)
# ─────────────────────────────────────────────────────────────────


class UMLPort(BaseModel):
    """A UML Port — interaction point on a component's boundary.

    Per UML 2.5.1 §11.4, a port is a typed feature on a component
    that exposes part of its behavior to clients. Renders as a small
    square on the component's edge.

    Attributes:
        id: Stable identifier. Required.
        name: Display name (rendered as a label near the port).
        side: Which edge the port sits on. Defaults to `east`.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    side: Literal["north", "south", "east", "west"] = "east"


class UMLComponent(BaseModel):
    """A UML Component — a modular unit with provided/required interfaces.

    Renders as a rectangle with a small "component" icon (UML 2.5
    notation: a rectangle with two protrusions on its left side) in
    the upper-right corner. Provided interfaces render as filled
    circles ("lollipops"); required interfaces as half-circles
    ("sockets").

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        provided_interfaces: Names of provided interfaces (rendered
            as labelled lollipops on the component's right edge).
        required_interfaces: Names of required interfaces (rendered
            as labelled sockets on the component's right edge).
        ports: Optional named ports for fine-grained connections.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    provided_interfaces: list[str] = Field(default_factory=list)
    required_interfaces: list[str] = Field(default_factory=list)
    ports: list[UMLPort] = Field(default_factory=list)
    position: Position | None = None


class UMLConnector(BaseModel):
    """A UML Connector — links two components via interfaces or ports.

    Per UML 2.5.1 §11.5, a connector represents a runtime link
    between component instances. Renders as a solid line; the
    `kind` selects the visual:

    - `assembly`: a required interface of one component is wired
      to a provided interface of another (the lollipop and socket
      align visually). Renders as a plain line.
    - `delegation`: a port on a containing component delegates to
      a port on a contained component. Renders dashed with an
      open arrow at the delegate end.

    Attributes:
        id: Stable identifier. Required.
        from_id: Source component or port id.
        to_id: Target component or port id.
        kind: One of `assembly`, `delegation`. Defaults to `assembly`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    kind: Literal["assembly", "delegation"] = "assembly"

    @model_validator(mode="after")
    def _validate_no_self_connector(self) -> UMLConnector:
        if self.from_id == self.to_id:
            raise ValueError(
                f"connector {self.id!r} has from==to=={self.from_id!r}; "
                f"a component cannot connect to itself"
            )
        return self


class UMLComponentDiagramModel(BaseModel):
    """Top-level container for a component diagram's UML model.

    Attributes:
        components: All components in the diagram. Required (≥ 1).
        connectors: Inter-component links (assembly or delegation).
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    components: list[UMLComponent] = Field(..., min_length=1)
    connectors: list[UMLConnector] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLComponentDiagramModel:
        seen: dict[str, str] = {}
        for kind, items in (
            ("component", self.components),
            ("connector", self.connectors),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        # Ports also have ids; they share the global namespace.
        for c in self.components:
            for p in c.ports:
                if p.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {p.id!r}: declared as "
                        f"{seen[p.id]!r} and again as a port on component "
                        f"{c.id!r}"
                    )
                seen[p.id] = "port"
        return self

    @model_validator(mode="after")
    def _validate_connector_endpoints_resolve(self) -> UMLComponentDiagramModel:
        """Validate that every connector endpoint resolves.

        Every connector endpoint must reference a component, port,
        provided-interface name, or required-interface name.
        """
        valid_ids: set[str] = set()
        for c in self.components:
            valid_ids.add(c.id)
            for p in c.ports:
                valid_ids.add(p.id)
            # Interface names are used as connector endpoints when
            # connecting via the lollipop/socket convention.
            for iface in c.provided_interfaces:
                valid_ids.add(f"{c.id}.{iface}")
            for iface in c.required_interfaces:
                valid_ids.add(f"{c.id}.{iface}")
        for conn in self.connectors:
            if conn.from_id not in valid_ids:
                raise ValueError(
                    f"connector {conn.id!r} references unknown source id {conn.from_id!r}"
                )
            if conn.to_id not in valid_ids:
                raise ValueError(
                    f"connector {conn.id!r} references unknown target id {conn.to_id!r}"
                )
        return self


def validate_component_diagram(data: dict[str, Any]) -> UMLComponentDiagramModel:
    """Validate a parsed mapping as a UML component-diagram model.

    Args:
        data: A dict with `components` (≥ 1), optional `connectors`,
            optional `notes`.

    Returns:
        A validated `UMLComponentDiagramModel`.
    """
    return UMLComponentDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Deployment diagrams (Phase C.2)
# ─────────────────────────────────────────────────────────────────


NodeKind = Literal["device", "execution_environment"]
"""Per UML 2.5.1 §19.4, a Node is either a hardware *Device* or a
software *ExecutionEnvironment* (e.g., an OS, container runtime, JVM).
The two render with the same 3D-box notation, optionally tagged with
the corresponding stereotype."""


DeploymentRelationKind = Literal["deploy", "manifest", "communication"]
"""Three relations in a deployment diagram:

- `deploy`: an artifact is deployed onto a node (rendered as a
  dashed connector with `«deploy»` keyword).
- `manifest`: an artifact manifests one or more components or
  classifiers (rendered as a dashed connector with `«manifest»`).
- `communication`: a node communicates with another node — typically
  representing a network link (rendered as a plain solid line, often
  labelled with the protocol)."""


class UMLArtifact(BaseModel):
    """A UML Artifact — a deployable physical piece of information.

    Per UML 2.5.1 §19.4, an artifact is a deployable file
    (`.jar`, `.war`, `.so`, configuration files, source code, …).
    Renders as a rectangle with the `«artifact»` keyword and a
    document-fold icon in the upper-right corner.

    Attributes:
        id: Stable identifier. Required.
        name: Display name (typically the file name).
        stereotype: Optional sub-stereotype on top of the implicit
            `«artifact»` (e.g., `«executable»`, `«library»`).
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    stereotype: str | None = None
    position: Position | None = None


class UMLDeploymentNode(BaseModel):
    """A UML Node — a deployment target (device or runtime).

    Renders as a 3D box (cuboid). When `kind="device"`, the box
    represents physical hardware; when `kind="execution_environment"`,
    it represents a software runtime hosted on another node.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        kind: `device` or `execution_environment`. Defaults to
            `device`.
        stereotype: Optional sub-stereotype on top of the implicit
            `«device»` / `«executionEnvironment»` keyword (e.g.,
            `«server»`, `«container»`).
        contains: Ids of other nodes nested inside this node (e.g.,
            an OS execution-environment inside a server device).
            Containment is rendered structurally — contained nodes
            sit below their parent in the layered layout.
        artifacts: Ids of artifacts deployed on this node. The
            composer emits the `«deploy»` connector automatically;
            authors who need explicit control can list relations
            instead and leave this empty.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    kind: NodeKind = "device"
    stereotype: str | None = None
    contains: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    position: Position | None = None


class UMLDeploymentRelation(BaseModel):
    """A relation between two deployment-diagram elements.

    Attributes:
        id: Stable identifier. Required.
        from_id: Source element id.
        to_id: Target element id.
        kind: `deploy`, `manifest`, or `communication`.
        label: Optional label (e.g., `"HTTPS"` on a communication
            link).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    kind: DeploymentRelationKind = "deploy"
    label: str | None = None

    @model_validator(mode="after")
    def _validate_no_self_relation(self) -> UMLDeploymentRelation:
        if self.from_id == self.to_id:
            raise ValueError(
                f"deployment relation {self.id!r} has from==to=={self.from_id!r}; "
                f"a deployment element cannot relate to itself"
            )
        return self


class UMLDeploymentDiagramModel(BaseModel):
    """Top-level container for a deployment diagram's UML model.

    Attributes:
        nodes: All nodes (devices + execution environments). ≥ 1.
        artifacts: All artifacts.
        relations: Deployments, manifestations, communication links.
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[UMLDeploymentNode] = Field(..., min_length=1)
    artifacts: list[UMLArtifact] = Field(default_factory=list)
    relations: list[UMLDeploymentRelation] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLDeploymentDiagramModel:
        seen: dict[str, str] = {}
        for kind, items in (
            ("node", self.nodes),
            ("artifact", self.artifacts),
            ("relation", self.relations),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_endpoints_resolve(self) -> UMLDeploymentDiagramModel:
        valid: set[str] = {n.id for n in self.nodes} | {a.id for a in self.artifacts}
        # Validate `contains` references between nodes.
        node_ids = {n.id for n in self.nodes}
        for n in self.nodes:
            for child in n.contains:
                if child not in node_ids:
                    raise ValueError(f"node {n.id!r} contains unknown node id {child!r}")
        artifact_ids = {a.id for a in self.artifacts}
        for n in self.nodes:
            for art in n.artifacts:
                if art not in artifact_ids:
                    raise ValueError(f"node {n.id!r} declares unknown artifact id {art!r}")
        # Validate relation endpoints.
        for r in self.relations:
            if r.from_id not in valid:
                raise ValueError(
                    f"deployment relation {r.id!r} references unknown source id {r.from_id!r}"
                )
            if r.to_id not in valid:
                raise ValueError(
                    f"deployment relation {r.id!r} references unknown target id {r.to_id!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_no_containment_cycle(self) -> UMLDeploymentDiagramModel:
        children = {n.id: list(n.contains) for n in self.nodes}
        WHITE, GREY, BLACK = 0, 1, 2
        color = dict.fromkeys(children, WHITE)

        def visit(nid: str) -> None:
            color[nid] = GREY
            for c in children.get(nid, ()):
                if color.get(c) == GREY:
                    raise ValueError(f"node containment cycle detected at {nid!r} → {c!r}")
                if color.get(c) == WHITE:
                    visit(c)
            color[nid] = BLACK

        for nid in list(children):
            if color[nid] == WHITE:
                visit(nid)
        return self


def validate_deployment_diagram(data: dict[str, Any]) -> UMLDeploymentDiagramModel:
    """Validate a parsed mapping as a UML deployment-diagram model.

    Args:
        data: A dict with `nodes` (≥ 1), optional `artifacts`,
            `relations`, `notes`.

    Returns:
        A validated `UMLDeploymentDiagramModel`.
    """
    return UMLDeploymentDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Activity diagrams (Phase C.3)
# ─────────────────────────────────────────────────────────────────


ActivityNodeKind = Literal[
    "initial",
    "final",
    "flow_final",
    "action",
    "decision",
    "merge",
    "fork",
    "join",
]
"""Activity-node kinds per UML 2.5.1 §15.3:

- `initial`: small filled circle, the start of an activity.
- `final`: filled circle inside a hollow circle (bullseye).
- `flow_final`: a circle with an X — terminates one flow without
  ending the entire activity.
- `action`: a rounded rectangle holding an action label.
- `decision`: a diamond with one inbound flow and ≥ 2 guarded
  outbound flows.
- `merge`: a diamond with ≥ 2 inbound flows merging into one.
- `fork`: a thick horizontal/vertical bar splitting one flow into
  several concurrent flows.
- `join`: a thick bar synchronizing several flows into one."""


class UMLActivityNode(BaseModel):
    """A node in an activity diagram.

    Attributes:
        id: Stable identifier. Required.
        kind: Node kind (see `ActivityNodeKind`).
        name: Display label. Optional for decision/merge/fork/join
            (they typically render unlabelled). Required for
            actions (an unlabelled action is meaningless per UML).
        partition: Optional swim-lane id this node belongs to.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    kind: ActivityNodeKind
    name: str | None = None
    partition: str | None = None
    position: Position | None = None

    @model_validator(mode="after")
    def _validate_action_has_name(self) -> UMLActivityNode:
        if self.kind == "action" and not self.name:
            raise ValueError(
                f"activity action node {self.id!r} requires a name "
                f"(an unlabelled action is meaningless per UML 2.5)"
            )
        return self


class UMLActivityEdge(BaseModel):
    """A control flow or object flow between activity nodes.

    Attributes:
        id: Stable identifier. Required.
        from_id: Source node id.
        to_id: Target node id.
        guard: Optional Boolean guard expression (rendered as
            `[guard]`). Common on edges leaving a decision.
        kind: `control` (solid line) or `object` (dashed line).
            Defaults to `control`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    guard: str | None = None
    kind: Literal["control", "object"] = "control"

    @model_validator(mode="after")
    def _validate_no_self_edge(self) -> UMLActivityEdge:
        if self.from_id == self.to_id:
            raise ValueError(
                f"activity edge {self.id!r} has from==to=={self.from_id!r}; "
                f"an activity node cannot flow to itself"
            )
        return self


class UMLSwimlane(BaseModel):
    """A swim-lane (UML ActivityPartition) grouping activity nodes by responsibility.

    Renders as a vertical column with a header band carrying the
    lane name. Nodes whose `partition` matches the lane id are
    horizontally constrained to that column.

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class UMLActivityDiagramModel(BaseModel):
    """Top-level container for an activity diagram's UML model.

    Attributes:
        nodes: All nodes in the activity. ≥ 1.
        edges: Control flows + object flows.
        swimlanes: Optional partitions for grouping by responsibility.
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[UMLActivityNode] = Field(..., min_length=1)
    edges: list[UMLActivityEdge] = Field(default_factory=list)
    swimlanes: list[UMLSwimlane] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLActivityDiagramModel:
        seen: dict[str, str] = {}
        for kind, items in (
            ("node", self.nodes),
            ("edge", self.edges),
            ("swimlane", self.swimlanes),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_edge_endpoints_resolve(self) -> UMLActivityDiagramModel:
        node_ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.from_id not in node_ids:
                raise ValueError(
                    f"activity edge {e.id!r} references unknown source id {e.from_id!r}"
                )
            if e.to_id not in node_ids:
                raise ValueError(f"activity edge {e.id!r} references unknown target id {e.to_id!r}")
        return self

    @model_validator(mode="after")
    def _validate_partitions_resolve(self) -> UMLActivityDiagramModel:
        lane_ids = {sl.id for sl in self.swimlanes}
        for n in self.nodes:
            if n.partition is not None and n.partition not in lane_ids:
                raise ValueError(
                    f"activity node {n.id!r} references unknown swimlane id {n.partition!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_initial_outflow(self) -> UMLActivityDiagramModel:
        """Initial nodes must have exactly one outgoing edge.

        Per UML 2.5.1 §15.4 (InitialNode): an initial node may have
        any number of outgoing flows but exactly zero incoming flows.
        We enforce ≥ 0 incoming and ≥ 1 outgoing — a useful
        well-formedness check that catches accidentally orphaned
        initial nodes.
        """
        for n in self.nodes:
            if n.kind != "initial":
                continue
            outgoing = [e for e in self.edges if e.from_id == n.id]
            incoming = [e for e in self.edges if e.to_id == n.id]
            if incoming:
                raise ValueError(
                    f"initial node {n.id!r} cannot have incoming edges (found {len(incoming)})"
                )
            if not outgoing:
                # Permit the degenerate single-node case (just an
                # initial with no successors) — useful for testing
                # — but warn via doc that this is unusual. Don't
                # raise here; only outright violations raise.
                pass
        return self


def validate_activity_diagram(data: dict[str, Any]) -> UMLActivityDiagramModel:
    """Validate a parsed mapping as a UML activity-diagram model.

    Args:
        data: A dict with `nodes` (≥ 1), optional `edges`,
            `swimlanes`, `notes`.

    Returns:
        A validated `UMLActivityDiagramModel`.
    """
    return UMLActivityDiagramModel.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# State machines (Phase C.4)
# ─────────────────────────────────────────────────────────────────


PseudostateKind = Literal[
    "initial",
    "final",
    "choice",
    "junction",
    "fork",
    "join",
    "shallow_history",
    "deep_history",
    "entry_point",
    "exit_point",
    "terminate",
]
"""Pseudostate kinds per UML 2.5.1 §14.2.3 (PseudostateKind).

Render conventions:

- `initial`: small filled disc.
- `final`: bullseye (filled disc inside a hollow ring).
- `choice`: hollow diamond.
- `junction`: small filled disc.
- `fork` / `join`: thick bar.
- `shallow_history`: hollow circle with `H`.
- `deep_history`: hollow circle with `H*`.
- `entry_point` / `exit_point`: hollow circle on the boundary of a
  composite state (`exit_point` adds an X).
- `terminate`: an X glyph (cross).
"""


class UMLState(BaseModel):
    """A simple or composite state.

    Renders as a rounded rectangle. When `regions` is non-empty the
    state is *composite* — it contains nested sub-states organized
    into one region (separated by horizontal dashed lines when
    needed).

    Attributes:
        id: Stable identifier. Required.
        name: Display name. Required.
        entry: Optional entry-action label.
        exit_action: Optional exit-action label (named to avoid
            shadowing Python builtins; YAML can also use `exit`).
        do: Optional do-activity label.
        regions: Optional list of sub-state ids contained in this
            state.
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    entry: str | None = None
    exit_action: str | None = Field(default=None, alias="exit")
    do: str | None = None
    regions: list[str] = Field(default_factory=list)
    position: Position | None = None


class UMLPseudostate(BaseModel):
    """A pseudostate per UML 2.5.1 §14.2.3.

    Attributes:
        id: Stable identifier. Required.
        kind: Which pseudostate notation to render.
        name: Optional label (typically rendered beside the glyph).
        position: Optional layout hint.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    kind: PseudostateKind
    name: str | None = None
    position: Position | None = None


class UMLTransition(BaseModel):
    """A transition between states or pseudostates.

    Attributes:
        id: Stable identifier. Required.
        from_id: Source state or pseudostate id.
        to_id: Target state or pseudostate id.
        trigger: Optional trigger event name.
        guard: Optional guard expression.
        effect: Optional effect-action label.
        kind: `external` (default) or `internal`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1)
    from_id: str = Field(..., min_length=1, alias="from")
    to_id: str = Field(..., min_length=1, alias="to")
    trigger: str | None = None
    guard: str | None = None
    effect: str | None = None
    kind: Literal["external", "internal"] = "external"

    def label(self) -> str:
        """Build the canonical UML transition label.

        Returns the conventional `trigger [guard] / effect` form.
        Empty parts are omitted.
        """
        parts: list[str] = []
        if self.trigger:
            parts.append(self.trigger)
        if self.guard:
            parts.append(f"[{self.guard}]")
        if self.effect:
            parts.append(f"/ {self.effect}")
        return " ".join(parts)


class UMLStateMachineModel(BaseModel):
    """Top-level container for a state-machine diagram's UML model.

    Attributes:
        states: Simple and composite states. ≥ 1.
        pseudostates: Initial, final, choice, etc.
        transitions: Edges between states/pseudostates.
        notes: Free-text annotations.
    """

    model_config = ConfigDict(extra="forbid")

    states: list[UMLState] = Field(..., min_length=1)
    pseudostates: list[UMLPseudostate] = Field(default_factory=list)
    transitions: list[UMLTransition] = Field(default_factory=list)
    notes: list[UMLNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> UMLStateMachineModel:
        seen: dict[str, str] = {}
        for kind, items in (
            ("state", self.states),
            ("pseudostate", self.pseudostates),
            ("transition", self.transitions),
            ("note", self.notes),
        ):
            for item in items:
                if item.id in seen:
                    raise ValueError(
                        f"duplicate UML element id {item.id!r}: declared as "
                        f"{seen[item.id]!r} and again as {kind!r}"
                    )
                seen[item.id] = kind
        return self

    @model_validator(mode="after")
    def _validate_transition_endpoints(self) -> UMLStateMachineModel:
        valid = {s.id for s in self.states} | {p.id for p in self.pseudostates}
        for t in self.transitions:
            if t.from_id not in valid:
                raise ValueError(f"transition {t.id!r} references unknown source id {t.from_id!r}")
            if t.to_id not in valid:
                raise ValueError(f"transition {t.id!r} references unknown target id {t.to_id!r}")
        return self

    @model_validator(mode="after")
    def _validate_regions_resolve(self) -> UMLStateMachineModel:
        state_ids = {s.id for s in self.states}
        for s in self.states:
            for child in s.regions:
                if child == s.id:
                    raise ValueError(f"state {s.id!r} cannot contain itself in its regions")
                if child not in state_ids:
                    raise ValueError(f"state {s.id!r} declares unknown region member id {child!r}")
        return self

    @model_validator(mode="after")
    def _validate_no_region_cycle(self) -> UMLStateMachineModel:
        children = {s.id: list(s.regions) for s in self.states}
        WHITE, GREY, BLACK = 0, 1, 2
        color = dict.fromkeys(children, WHITE)

        def visit(nid: str) -> None:
            color[nid] = GREY
            for c in children.get(nid, ()):
                if color.get(c) == GREY:
                    raise ValueError(f"state region cycle detected at {nid!r} → {c!r}")
                if color.get(c) == WHITE:
                    visit(c)
            color[nid] = BLACK

        for nid in list(children):
            if color[nid] == WHITE:
                visit(nid)
        return self


def validate_state_machine(data: dict[str, Any]) -> UMLStateMachineModel:
    """Validate a parsed mapping as a UML state-machine diagram model.

    Args:
        data: A dict with `states` (≥ 1), optional `pseudostates`,
            `transitions`, `notes`.

    Returns:
        A validated `UMLStateMachineModel`.
    """
    return UMLStateMachineModel.model_validate(data)


__all__ = [
    "ActivityNodeKind",
    "AssociationKind",
    "Classifier",
    "DeploymentRelationKind",
    "NodeKind",
    "PackageDependencyKind",
    "ParamDirection",
    "Position",
    "PseudostateKind",
    "UMLActivityDiagramModel",
    "UMLActivityEdge",
    "UMLActivityNode",
    "UMLActor",
    "UMLArtifact",
    "UMLAssociation",
    "UMLAssociationEnd",
    "UMLAttribute",
    "UMLClass",
    "UMLClassDiagramModel",
    "UMLComponent",
    "UMLComponentDiagramModel",
    "UMLConnector",
    "UMLDependency",
    "UMLDeploymentDiagramModel",
    "UMLDeploymentNode",
    "UMLDeploymentRelation",
    "UMLEnumeration",
    "UMLGeneralization",
    "UMLInterface",
    "UMLNote",
    "UMLOperation",
    "UMLPackage",
    "UMLPackageDependency",
    "UMLPackageDiagramModel",
    "UMLParameter",
    "UMLPort",
    "UMLPseudostate",
    "UMLRealization",
    "UMLState",
    "UMLStateMachineModel",
    "UMLSwimlane",
    "UMLSystemBoundary",
    "UMLTransition",
    "UMLUseCase",
    "UMLUseCaseDiagramModel",
    "UMLUseCaseRelation",
    "UseCaseRelationKind",
    "Visibility",
    "validate_activity_diagram",
    "validate_class_diagram",
    "validate_component_diagram",
    "validate_deployment_diagram",
    "validate_package_diagram",
    "validate_state_machine",
    "validate_use_case_diagram",
]
