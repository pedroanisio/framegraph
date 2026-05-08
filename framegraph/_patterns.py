"""Slide-pattern catalog — typed vocabulary of named slide compositions.

Loads and validates `static/refs/slides-patter-a.yml`, the catalog
of 50 canonical slide-template patterns. The schema is refined
(Phase 2): controlled vocabularies replace the loose strings the
file used to carry.

Refined surface
---------------
- ``size`` is a `Size` literal of nine controlled values:
  ``xs``, ``small``, ``medium``, ``large``, ``xl``, ``full``,
  ``equal``, ``variable``, ``contextual``.
- ``placement`` is a typed union of three mutually-exclusive
  placement kinds:

  - `Anchor` — one of nine grid cells (``left|center|right`` ×
    ``top|middle|bottom``) plus a ``fullbleed`` mode.
  - `RegionPlacement` — a named area inside a structured layout
    (``matrix_body``, ``swimlanes``, ``funnel_body``, …) used when
    9-cell anchoring doesn't map cleanly.
  - `RelativePlacement` — placement expressed relative to another
    zone in the same pattern, e.g. ``below(title)`` or
    ``inside(profile_cards)``.

- ``shape`` is an optional zone field that captures what a zone
  *is* (``card``, ``bar``, ``node``, ``connector``, …) when it
  isn't already obvious from ``role``. Pulled out of the previous
  size-leakage values during normalization.

The bundled YAML is normalized to this shape via
`scripts/normalize_patterns.py` and the consequent file is what
`load_pattern_catalog()` consumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "PATTERN_CATALOG_PATH",
    "Anchor",
    "ContentType",
    "PatternCatalog",
    "PatternCategory",
    "PatternZone",
    "Placement",
    "RegionPlacement",
    "RelativePlacement",
    "Size",
    "SlidePattern",
    "Span",
    "load_pattern_catalog",
]


PATTERN_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent.parent / "static" / "refs" / "slides-patter-a.yml"
)
"""Path to the canonical 50-pattern catalog shipped with the repo."""


# ─────────────────────────────────────────────────────────────────
# Size — controlled literal
# ─────────────────────────────────────────────────────────────────


Size = Literal[
    "xs",
    "small",
    "medium",
    "large",
    "xl",
    "full",
    "equal",
    "variable",
    "contextual",
]
"""Controlled vocabulary for zone size.

- ``xs``, ``small``, ``medium``, ``large``, ``xl`` — relative
  scale on the slide canvas.
- ``full`` — fills its row or column (``full_width`` / ``full_height``).
- ``equal`` — one cell of an equal-cell grid; the composer
  computes per-cell size from the count of equal-sibling zones.
- ``variable`` — composer chooses, no constraint expressed by the
  pattern.
- ``contextual`` — depends on content; only valid when authoring
  guidance is also present.
"""


# ─────────────────────────────────────────────────────────────────
# Placement — typed union
# ─────────────────────────────────────────────────────────────────


_HAxis = Literal["left", "center", "right"]
_VAxis = Literal["top", "middle", "bottom"]


class Anchor(BaseModel):
    """A 9-cell grid anchor on the slide canvas, or full-bleed.

    Either ``fullbleed`` is True (the zone covers the entire
    canvas) or ``h`` and ``v`` together select one of nine cells.

    Attributes:
        h: Horizontal axis: ``left``, ``center``, or ``right``.
            Required when ``fullbleed`` is False.
        v: Vertical axis: ``top``, ``middle``, or ``bottom``.
            Required when ``fullbleed`` is False.
        fullbleed: When True, ``h`` and ``v`` are ignored. Default
            False.
    """

    model_config = ConfigDict(extra="forbid")
    h: _HAxis | None = None
    v: _VAxis | None = None
    fullbleed: bool = False

    @model_validator(mode="after")
    def _validate_axes_present_when_not_fullbleed(self) -> Anchor:
        """Either fullbleed=True or (h and v) must be set."""
        if self.fullbleed:
            return self
        if self.h is None or self.v is None:
            raise ValueError("Anchor requires both `h` and `v` (or `fullbleed=True`)")
        return self


_Relation = Literal[
    "above",
    "below",
    "left_of",
    "right_of",
    "inside",
    "around",
    "between",
    "near",
    "on",
]


class RelativePlacement(BaseModel):
    """Placement expressed relative to another zone in the same pattern.

    Attributes:
        relation: One of nine canonical relations: ``above``,
            ``below``, ``left_of``, ``right_of``, ``inside``,
            ``around``, ``between``, ``near``, ``on``.
        target: Role name of the referenced zone. Must match a
            `PatternZone.role` declared elsewhere in the same
            `SlidePattern` (uniqueness is enforced at the pattern
            level, so the reference is unambiguous).
    """

    model_config = ConfigDict(extra="forbid")
    relation: _Relation
    target: str = Field(..., min_length=1)


class RegionPlacement(BaseModel):
    """Placement inside a named structured area.

    Used when 9-cell anchoring doesn't map cleanly: matrix bodies,
    swimlanes, funnel stages, map overlays, etc.

    Attributes:
        region: Name of the structured area. Free-form for now;
            tightening to an enum is a Phase-3 candidate once the
            full set of regions is curated.
    """

    model_config = ConfigDict(extra="forbid")
    region: str = Field(..., min_length=1)


# Discriminated by which key is present. Pydantic resolves the union
# by validating each shape; ``extra="forbid"`` on each variant means
# only one shape will match a given input.
Placement = Union[Anchor, RegionPlacement, RelativePlacement]
"""A zone's placement: 9-cell anchor, named region, or relative."""


def _coerce_placement(raw: Any) -> Any:
    """Normalize a placement payload to its discriminated variant.

    Accepts the three documented shapes:

    - ``{"anchor": {...}}`` or ``{"anchor": "fullbleed"}``
    - ``{"region": "..."}``
    - ``{"relative": {"relation": "...", "target": "..."}}``

    Returns the inner mapping (or `Anchor(fullbleed=True)`) so
    Pydantic can dispatch to the right model.
    """
    if not isinstance(raw, dict):
        return raw
    if "anchor" in raw and len(raw) == 1:
        inner = raw["anchor"]
        if inner == "fullbleed":
            return {"fullbleed": True}
        return inner
    if "region" in raw and len(raw) == 1:
        return {"region": raw["region"]}
    if "relative" in raw and len(raw) == 1:
        return raw["relative"]
    return raw


# ─────────────────────────────────────────────────────────────────
# Zone
# ─────────────────────────────────────────────────────────────────


_Shape = Literal[
    "card",
    "list",
    "text",
    "metric",
    "icon",
    "connector",
    "bar",
    "axis",
    "node",
    "marker",
    "container",
    "sequence",
    "button",
    # Catalog B additions
    "cell",
    "block",
    "chart",
    "table",
    "timeline",
    # Catalog C additions
    "box",
    "band",
    # Catalog D additions
    "progress",
]


ContentType = Literal[
    "title_body",  # heading + paragraph text
    "metric",  # large number + label + optional trend/delta
    "list_items",  # bullet/numbered list of strings or short objects
    "key_value",  # name:value pairs — legends, tags, status indicators
    "comparison",  # paired before/after, pros/cons text
    "chart_data",  # series data — chart subtype implied by shape
    "table_data",  # 2D rows×cols of values — for table/matrix bodies
    "image",  # raster/vector asset reference
    "axis_label",  # axis title + range/units (label only, no series)
    "decorative",  # background, divider, ornamental — no content
]
"""Typed-form contract for a zone's fillable content.

Distinct from ``shape`` (visual form). Two zones can share the same
shape (e.g. ``card``) but carry different content types (a card with
``title_body`` is filled differently than a card with ``metric``).
Used downstream by fill-and-render pipelines to know what payload
shape an agent must supply for each slot.
"""


class Span(BaseModel):
    """How many grid cells a zone claims along each axis.

    Round 2 Phase 1 addition. Default ``{h: 1, v: 1}`` — a single
    cell, matching pre-Round-2 behavior. A zone with ``span: {h: 2}``
    claims its anchor cell *plus the next cell to the right*; the
    layout engine (Phase 2) honors this when allocating boxes.

    Span is **identity-neutral** — it does not participate in the
    pattern's structural fingerprint. Two patterns whose zones
    differ only by ``span`` are still structural duplicates; this
    matches how ``shape`` and ``content_type`` are treated.

    Attributes:
        h: Horizontal cells claimed. Must be ≥ 1. Default 1.
        v: Vertical cells claimed. Must be ≥ 1. Default 1.
    """

    model_config = ConfigDict(extra="forbid")
    h: int = Field(default=1, ge=1)
    v: int = Field(default=1, ge=1)


class PatternZone(BaseModel):
    """A named region in a slide-pattern composition.

    Attributes:
        role: Semantic name of the zone (e.g. ``"title"``,
            ``"summary_cards"``). Unique within a pattern.
            Required, non-empty.
        size: One of the nine controlled `Size` values.
        placement: Typed placement — `Anchor`, `RegionPlacement`,
            or `RelativePlacement`. Accepts the wrapper-key forms
            (``{"anchor": {...}}``, ``{"region": "..."}``,
            ``{"relative": {...}}``) at parse time.
        shape: Optional shape vocabulary — ``card``, ``bar``,
            ``node``, ``connector``, etc. — when the zone's *type*
            isn't already implied by its ``role``.
        content_type: Optional typed-form contract — what payload
            shape an agent supplies to fill this zone. One of the
            ten `ContentType` literals. Identity-neutral (does not
            participate in structural fingerprinting). When unset,
            the zone is un-curated and downstream fill schemas
            cannot derive a contract for it automatically.
        span: How many grid cells the zone claims along each axis.
            Defaults to a single cell. Identity-neutral — span is
            layout, not structure. The layout engine consumes this
            value to size the zone's box.
    """

    model_config = ConfigDict(extra="forbid")
    role: str = Field(..., min_length=1)
    size: Size
    placement: Annotated[Placement, Field(union_mode="left_to_right")]
    shape: _Shape | None = None
    content_type: ContentType | None = None
    span: Span = Field(default_factory=Span)

    @model_validator(mode="before")
    @classmethod
    def _coerce_placement(cls, data: Any) -> Any:
        if isinstance(data, dict) and "placement" in data:
            data = {**data, "placement": _coerce_placement(data["placement"])}
        return data


# ─────────────────────────────────────────────────────────────────
# Pattern
# ─────────────────────────────────────────────────────────────────


def _zone_fingerprint(z: PatternZone) -> tuple[Any, ...]:
    """Canonical tuple identifying one zone's structural content.

    Captures `(role, size, placement, shape)`. Placement is reduced
    to a hashable tuple distinguishing the three placement variants.
    Used by `SlidePattern.structural_fingerprint()` to detect
    duplicate patterns regardless of id, name, layout_disposition,
    or zone order.
    """
    p = z.placement
    if isinstance(p, Anchor):
        place_key: tuple[str, ...] = ("anchor", p.h or "", p.v or "", str(p.fullbleed))
    elif isinstance(p, RegionPlacement):
        place_key = ("region", p.region)
    else:  # RelativePlacement
        place_key = ("relative", p.relation, p.target)
    return (z.role, z.size, place_key, z.shape or "")


PatternCategory = Literal["generic", "consulting", "expert"]
"""Origin tag for a pattern in a merged multi-source catalog.

- ``generic`` — generic slide-template patterns (catalog A).
- ``consulting`` — big-4 consulting patterns (catalogs B–F).
- ``expert`` — expert/methodological reasoning patterns (catalog G+):
  decision-traceability, epistemic-status, causal-identification,
  resilience, and other analyst/auditor-oriented templates.

Future source files extend this literal as new categories arrive.
"""


class SlidePattern(BaseModel):
    """One slide-template pattern in the catalog.

    Attributes:
        id: Stable positive integer identifier.
        name: Human-readable pattern name. Unique within a catalog.
        layout_disposition: One-line description of the spatial
            disposition. Authoring guidance for humans.
        zones: Ordered list of named regions. At least one zone
            required; role names are unique within the pattern.
        use_case: Optional one-line use case (e.g.
            ``"Classic executive storyline structure."``). Sourced
            from per-catalog metadata fields — ``consulting_use``
            on consulting catalogs, ``expert_use`` on expert
            catalogs — and unified into a single field by the
            merger. Documentation only — does not participate in
            structural identity.
        category: Origin tag for the pattern in a merged catalog.
            Defaults to ``"generic"``; set to ``"consulting"`` for
            big-4 patterns and ``"expert"`` for methodological /
            reasoning patterns. Identity-neutral.
    """

    model_config = ConfigDict(extra="forbid")
    id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1)
    layout_disposition: str = Field(..., min_length=1)
    zones: list[PatternZone] = Field(..., min_length=1)
    use_case: str | None = None
    category: PatternCategory = "generic"

    @model_validator(mode="after")
    def _validate_zone_roles_unique(self) -> SlidePattern:
        seen: set[str] = set()
        for z in self.zones:
            if z.role in seen:
                raise ValueError(
                    f"pattern {self.id} ({self.name!r}): duplicate role "
                    f"{z.role!r}; zone roles must be unique within a pattern"
                )
            seen.add(z.role)
        return self

    def structural_fingerprint(self) -> frozenset[tuple[Any, ...]]:
        """Return the order-independent structural identity of the pattern.

        Two patterns with the same fingerprint are structurally
        identical: same zone roles with the same sizes, placements,
        and shapes — regardless of id, name, ``layout_disposition``,
        or the order zones were declared in. The catalog uses this
        to detect a single pattern declared twice under different
        identifiers.
        """
        return frozenset(_zone_fingerprint(z) for z in self.zones)


# ─────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────


class PatternCatalog(BaseModel):
    """A collection of slide-template patterns.

    Attributes:
        slide_template_patterns: All patterns. Both ids and names
            must be unique across the list.
    """

    model_config = ConfigDict(extra="forbid")
    slide_template_patterns: list[SlidePattern] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_ids_and_names_unique(self) -> PatternCatalog:
        seen_ids: set[int] = set()
        seen_names: set[str] = set()
        for p in self.slide_template_patterns:
            if p.id in seen_ids:
                raise ValueError(f"duplicate pattern id {p.id} in catalog")
            seen_ids.add(p.id)
            if p.name in seen_names:
                raise ValueError(f"duplicate pattern name {p.name!r} in catalog")
            seen_names.add(p.name)
        return self

    @model_validator(mode="after")
    def _validate_no_structural_duplicates(self) -> PatternCatalog:
        """No two patterns may share a structural fingerprint.

        Pattern identity is the multiset of `(role, size, placement,
        shape)` tuples across zones — different ids, names, or
        layout_disposition do not make two structurally-equal
        patterns distinct. Catches the case where the same
        composition is registered twice by mistake.
        """
        seen: dict[frozenset[tuple[Any, ...]], SlidePattern] = {}
        for p in self.slide_template_patterns:
            fp = p.structural_fingerprint()
            if fp in seen:
                prior = seen[fp]
                raise ValueError(
                    f"patterns {prior.id} ({prior.name!r}) and {p.id} "
                    f"({p.name!r}) are structurally identical: same zone set "
                    f"under different identifiers. Either merge them or "
                    f"differentiate the zone composition."
                )
            seen[fp] = p
        return self

    def get(self, pattern_id: int) -> SlidePattern:
        """Return the pattern with the given id, or raise `KeyError`."""
        for p in self.slide_template_patterns:
            if p.id == pattern_id:
                return p
        raise KeyError(f"no pattern with id {pattern_id}")


# ─────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────


def load_pattern_catalog(path: Path | str | None = None) -> PatternCatalog:
    """Load and validate a pattern catalog from a YAML file.

    Args:
        path: Optional path override. When None (default), loads
            the canonical bundled catalog at `PATTERN_CATALOG_PATH`.

    Returns:
        A validated `PatternCatalog`.

    Raises:
        FileNotFoundError: If the path does not exist.
        pydantic.ValidationError: If the YAML does not satisfy the
            catalog schema.
    """
    src = Path(path) if path is not None else PATTERN_CATALOG_PATH
    data: dict[str, Any] = yaml.safe_load(src.read_text(encoding="utf-8"))
    return PatternCatalog.model_validate(data)
