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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """Validate a multiplicity string against the UML 2.5 grammar.

    Args:
        value: The multiplicity literal (e.g. `"1"`, `"0..1"`, `"1..*"`,
            `"*"`).

    Returns:
        The input unchanged on success.

    Raises:
        ValueError: If the value does not match the
            `lower(..upper)?` pattern with `*` allowed for upper or
            as a shorthand for `0..*`.
    """
    if not _MULTIPLICITY_RE.match(value):
        raise ValueError(
            f"invalid UML multiplicity {value!r}; expected forms like '1', '0..1', '1..*', or '*'"
        )
    return value


Multiplicity = Annotated[str, Field(pattern=_MULTIPLICITY_RE.pattern)]
"""A UML multiplicity literal, validated at parse time."""


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


__all__ = [
    "AssociationKind",
    "Classifier",
    "ParamDirection",
    "Position",
    "UMLAssociation",
    "UMLAssociationEnd",
    "UMLAttribute",
    "UMLClass",
    "UMLClassDiagramModel",
    "UMLDependency",
    "UMLEnumeration",
    "UMLGeneralization",
    "UMLInterface",
    "UMLNote",
    "UMLOperation",
    "UMLPackage",
    "UMLParameter",
    "UMLRealization",
    "Visibility",
    "validate_class_diagram",
]
