"""Pydantic v2 models — normative document schema for FrameGraph.

This module is the executable contract for what a FrameGraph YAML
document must look like. It supersedes the prior EBNF specification.
A complete, always-current human-readable field reference is generated
from these models into the documentation portal (``framegraph._docsite``),
with a CI gate guaranteeing every object type and model is documented.

Design notes:
  - Used as a validation gate at the public entry points
    (`FrameGraphRenderer.__init__`, `FrameGraphLibrary` loaders, the
    deck loader). The renderer pipeline still consumes plain dicts;
    validated objects are not destructured into typed attributes
    when handed downstream.
  - `extra="allow"` is the default on every object-type model. The
    EBNF advertised an open property bag on semantic nodes/edges, and
    the visual-object types accept arbitrary extras both for
    forward-compat (HD-effect filters added in v3.0) and for slot
    pass-through on `use` objects. Tightening to `extra="forbid"` on
    these would violate PURPOSE.md's v1.x backward-compatibility
    commitment.
  - Discriminated union on visual-object `type` covers the 16 first-
    class object types. Unknown types fall through to a permissive
    `_UnknownObject` model rather than failing — so third-party
    `register(type_name, fn)` plug-ins don't break ingestion.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, RootModel

# ─────────────────────────────────────────────────────────────────
# Common type aliases
# ─────────────────────────────────────────────────────────────────

Box = Annotated[list[float], Field(min_length=4, max_length=4)]
"""Bounding box `[x, y, w, h]` — exactly four numbers."""

Point = Annotated[list[float], Field(min_length=2, max_length=2)]
"""Point `[x, y]` — exactly two numbers."""

# Color: a hex literal (#RRGGBB / #RGB) OR a token id OR "none". The
# token-substitution invariant means we cannot validate the value
# beyond "is a string"; the renderer resolves at paint time.
Color = str

# Stroke spec: either a single COLOR string or a full StrokeInline mapping.
StrokeInlineLike = str | dict[str, Any]

# Connector / line endpoint: a bare semantic-node or object id, OR a full
# endpoint spec mapping (`{object, port, side, offset, …}`) resolved by the
# renderer's `endpoint()`.
EndpointSpec = str | dict[str, Any]


# ─────────────────────────────────────────────────────────────────
# Scene
# ─────────────────────────────────────────────────────────────────


class Canvas(BaseModel):
    """Scene canvas — required for standalone documents."""

    model_config = ConfigDict(extra="allow")
    size: Annotated[list[float], Field(min_length=2, max_length=2)]
    units: Literal["px", "pt"] | None = None


class TextContract(BaseModel):
    """`rendering_contract.text` — scene-wide text-layout policy.

    `min_font_size` is the floor for shrink-to-fit; `overflow` selects
    how text exceeding its box is handled.
    """

    model_config = ConfigDict(extra="allow")
    min_font_size: float | None = None
    overflow: Literal["visible", "clip", "shrink_to_fit"] | None = None


class SemanticsContract(BaseModel):
    """`rendering_contract.semantics` — semantic-binding policy.

    When `decorative_objects_may_omit_bind` is true, objects flagged
    `decorative` are exempt from the bind-to-semantic-node requirement.
    """

    model_config = ConfigDict(extra="allow")
    decorative_objects_may_omit_bind: bool | None = None


class RenderingContract(BaseModel):
    """`rendering_contract` block — scene-wide rendering policy.

    Bundles the coordinate mode (only `absolute` is implemented), the
    nested `text` and `semantics` contracts, and the debug toggles
    `debug_boxes` and `preserve_manual_line_breaks`.
    """

    model_config = ConfigDict(extra="allow")
    coordinate_mode: Literal["absolute"] | None = None
    text: TextContract | None = None
    semantics: SemanticsContract | None = None
    debug_boxes: bool | None = None
    preserve_manual_line_breaks: bool | None = None


class Scene(BaseModel):
    """`scene` block — canvas plus contracts."""

    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    description: str | None = None
    canvas: Canvas
    rendering_contract: RenderingContract | None = None
    source_image: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────
# Semantic
# ─────────────────────────────────────────────────────────────────


class TypeDef(BaseModel):
    """Node-type or edge-type declaration in the ontology.

    Property schemas are renderer/consumer-defined; this grammar
    layer accepts arbitrary extras.

    Note: `directionality` accepts `bidirectional` in addition to
    the EBNF's original `directed | undirected`. Production fixtures
    have used `bidirectional` since at least v1.x and the renderer
    has never enforced the binary set; widening here matches reality
    and preserves v1.x backward compatibility per PURPOSE.md.
    """

    model_config = ConfigDict(extra="allow")
    meaning: str | None = None
    directionality: Literal["directed", "undirected", "bidirectional"] | None = None


class Ontology(BaseModel):
    """`semantic.ontology` — node-type and edge-type declarations.

    `node_types` and `edge_types` each map a type name to its `TypeDef`.
    """

    model_config = ConfigDict(extra="allow")
    node_types: dict[str, TypeDef] = Field(default_factory=dict)
    edge_types: dict[str, TypeDef] = Field(default_factory=dict)


class NodeEntry(BaseModel):
    """Semantic node — `id` + `type` required; arbitrary user properties allowed."""

    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    label: str | None = None


class EdgeEntry(BaseModel):
    """Semantic edge — `id`, `type`, `from`, `to` required; arbitrary user properties allowed.

    `from` and `to` accept either a single id (the EBNF default) or a
    list of ids (multi-target / multi-source edges). Production
    fixtures use list-valued endpoints for cross-cutting control
    flows (e.g. governance applies to N target groups); widening
    here matches reality.
    """

    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    from_: str | list[str] = Field(alias="from")
    to: str | list[str]
    label: str | None = None


class Semantic(BaseModel):
    """`semantic` block — the ontology plus node and edge instances."""

    model_config = ConfigDict(extra="allow")
    ontology: Ontology | None = None
    nodes: list[NodeEntry] = Field(default_factory=list)
    edges: list[EdgeEntry] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Visual — tokens
# ─────────────────────────────────────────────────────────────────


class TextStyle(BaseModel):
    """Text style — every field optional; resolved with renderer defaults."""

    model_config = ConfigDict(extra="allow")
    font: str | None = None
    size: float | None = None
    weight: int | str | None = None
    color: Color | None = None
    align: Literal["left", "center", "right"] | None = None
    v_align: Literal["top", "middle", "bottom"] | None = None
    line_height: float | None = None
    italic: bool | None = None
    wrap: bool | None = None
    overflow: Literal["visible", "clip"] | None = None


class StrokeStyle(BaseModel):
    """Named stroke style — colour, width, dash, arrowheads, and opacity.

    Registered under `tokens.stroke_styles` and referenced by
    `stroke_style` on `line`, `connector`, and `path` objects.
    """

    model_config = ConfigDict(extra="allow")
    color: Color | None = None
    width: float | None = None
    dash: list[float] | None = None
    arrow_start: bool | None = None
    arrow_end: bool | None = None
    linecap: str | None = None
    linejoin: str | None = None
    # Channel transparency for the stroke. Either field accepted;
    # `opacity` here means stroke-opacity (group-level opacity is
    # carried on the object base). Range: 0.0 (transparent) – 1.0.
    opacity: float | None = None
    stroke_opacity: float | None = None


class Tokens(BaseModel):
    """Token tables. Every section is optional; absent sections render with defaults."""

    model_config = ConfigDict(extra="allow")
    colors: dict[str, str] = Field(default_factory=dict)
    fonts: dict[str, str] = Field(default_factory=dict)
    text_styles: dict[str, TextStyle] = Field(default_factory=dict)
    stroke_styles: dict[str, StrokeStyle] = Field(default_factory=dict)
    fill_styles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    glyph_map: dict[str, str] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
# Visual — symbols and components
# ─────────────────────────────────────────────────────────────────


class SymbolDef(BaseModel):
    """SVG `<use>`-style stamp — free-form objects with named slots and ports."""

    model_config = ConfigDict(extra="allow")
    box: Box
    slots: list[str] = Field(default_factory=list)
    ports: dict[str, Point] = Field(default_factory=dict)
    objects: list[dict[str, Any]] = Field(default_factory=list)


class ComponentVariant(BaseModel):
    """Theme override for a `ComponentDef` — swaps `fill` / `stroke_style`.

    Selected by variant name so one component geometry can paint in
    several palettes.
    """

    model_config = ConfigDict(extra="allow")
    fill: Color | None = None
    stroke_style: str | None = None


class SlotLayout(BaseModel):
    """Slot positioning inside a component's `internal_layout`.

    `box_offset` elements may be numbers, percent strings (`"100%"`),
    or `calc()` expressions (`"calc(100% - 16)"`). The renderer's
    `eval_length` resolves them against the parent box at paint time.
    """

    model_config = ConfigDict(extra="allow")
    box_offset: Annotated[list[float | str], Field(min_length=4, max_length=4)]
    style: str | TextStyle | None = None


class ComponentDef(BaseModel):
    """Styled product widget — single geometry, theme variants."""

    model_config = ConfigDict(extra="allow")
    fill: Color | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None
    radius: float | None = None
    text_style: str | None = None
    geometry: dict[str, Any] | None = None
    variants: dict[str, ComponentVariant] = Field(default_factory=dict)
    internal_layout: dict[str, SlotLayout] = Field(default_factory=dict)
    slots: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Visual — objects (the discriminated union)
# ─────────────────────────────────────────────────────────────────
#
# Per-type models are deliberately permissive: every recognized field
# is optional with `extra="allow"` so that:
#   - HD-effect fields like `shadow`/`glow` (added in v3.0 outside
#     the EBNF) flow through unchallenged,
#   - slot pass-through on `use` objects works,
#   - third-party `register(type_name, fn)` types are not rejected at
#     ingest (they fall into `_UnknownObject` below).
#
# The discriminator is the `type` field. Every common-fields entry
# (`id`, `decorative`, `bind`, `box`, `rotation`, `ports`, `opacity`,
# `class`) is allowed on every object via `extra="allow"`.


class OuterRing(BaseModel):
    """Halo border emitted as a concentric stroke around a rect/ellipse.

    Drawn before the primary geometry so the inner fill paints over the
    ring's interior — leaving only the ring band visible. Honoured by
    every rect-shaped renderer (`rect`, `image`, `component`) and by
    `ellipse` (which uses `offset` instead of `gap`, accepted as a
    synonym).
    """

    model_config = ConfigDict(extra="allow")
    color: Color | None = None
    width: float | None = None
    # rect convention; `offset` is accepted as a synonym for ellipses.
    gap: float | None = None
    offset: float | None = None
    dash: list[float] | str | None = None
    opacity: float | None = None


# `shadow` / `glow` accept three forms at the YAML surface:
#   - a preset name string ("small" | "medium" | "large")
#   - a mapping with optional `preset` plus dx/dy/blur/color/opacity overrides
#   - the literal "none" / false to disable
# Declared as a permissive alias so the schema documents the contract
# without rejecting any of the legitimate input shapes.
ShadowSpec = str | dict[str, Any] | bool | None
GlowSpec = str | dict[str, Any] | bool | None


class _ObjectBase(BaseModel):
    """Common fields shared by every concrete visual-object model.

    Carries identity/binding (`id`, `decorative`, `bind`), geometry
    (`box`, `rotation`, `ports`), the three opacity channels, and the
    HD-effect decorations (`shadow`, `glow`, `outer_ring`). Concrete
    object models add only their `type` discriminator; all other
    paint/geometry fields flow through via `extra="allow"`.
    """

    model_config = ConfigDict(extra="allow")
    id: str | None = None
    decorative: bool | None = None
    bind: str | None = None
    box: Box | None = None
    rotation: Any = None  # accepts number or [deg, cx, cy] list
    ports: dict[str, Point] | None = None
    # `opacity` applies to the wrapping <g>; channel-specific opacity
    # composes with it on the inner geometry without forcing rgba colour
    # literals. All three are optional and default to "fully opaque".
    opacity: float | None = None
    fill_opacity: float | None = None
    stroke_opacity: float | None = None
    # Visual decoration available on every renderer that paints primary
    # geometry. `shadow` / `glow` resolve to <filter> defs (mutually
    # exclusive — glow wins when both are set). `outer_ring` is a
    # concentric border used for halo / status-ring effects.
    shadow: ShadowSpec = None
    glow: GlowSpec = None
    outer_ring: OuterRing | dict[str, Any] | None = None


class RectObject(_ObjectBase):
    """Visual object `type: rect` — an axis-aligned, optionally rounded rectangle."""

    type: Literal["rect"]
    fill: Color | None = None
    radius: float | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class EllipseObject(_ObjectBase):
    """Visual object `type: ellipse` — an ellipse from `box` or `center` + radii."""

    type: Literal["ellipse"]
    center: Point | None = None
    rx: float | None = None
    ry: float | None = None
    fill: Color | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class TextObject(_ObjectBase):
    """Visual object `type: text` — a styled, box-bounded text block."""

    type: Literal["text"]
    text: str | None = None
    # `value` is a raw fallback for `text` (coerced to a string at render time).
    value: str | float | None = None
    # Rich inline runs: a list of `{text, weight?, color?, italic?, size?}` maps.
    spans: list[dict[str, Any]] | None = None
    style: str | TextStyle | None = None


class BulletListObject(_ObjectBase):
    """Visual object `type: bullet_list` — a vertical list of `items` with markers."""

    type: Literal["bullet_list"]
    # Each item is a string or a `{text, indent?, …}` mapping.
    items: list[Any] | None = None
    marker: str | None = None
    marker_color: Color | None = None
    gap: float | None = None
    indent: float | None = None
    style: str | TextStyle | None = None


class LineObject(_ObjectBase):
    """Visual object `type: line` — a straight segment between two endpoints."""

    type: Literal["line"]
    from_: EndpointSpec | None = Field(default=None, alias="from")
    to: EndpointSpec | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class PolylineObject(_ObjectBase):
    """Visual object `type: polyline` — a connected multi-point open path."""

    type: Literal["polyline"]
    points: list[Point] | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class PathObject(_ObjectBase):
    """Visual object `type: path` — a raw SVG path (`d`) primitive."""

    type: Literal["path"]
    d: str | None = None
    fill: Color | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class ImageObject(_ObjectBase):
    """Visual object `type: image` — an embedded or referenced image."""

    type: Literal["image"]
    # Image source; `href` / `src` / `uri` are accepted synonyms.
    href: str | None = None
    src: str | None = None
    uri: str | None = None
    placeholder: bool | None = None
    preserve_aspect_ratio: str | None = None
    clip: bool | dict[str, Any] | None = None
    label: str | None = None
    fill: Color | None = None
    radius: float | None = None


class IconObject(_ObjectBase):
    """Visual object `type: icon` — a glyph selected by `glyph` (or `code`)."""

    type: Literal["icon"]
    glyph: str | None = None
    color: Color | None = None
    font: str | None = None
    size: float | None = None


class UseObject(_ObjectBase):
    """Symbol instantiation — accepts arbitrary slot pass-through fields."""

    type: Literal["use"]
    symbol: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectorObject(_ObjectBase):
    """Visual object `type: connector` — a routed edge between `from` and `to`."""

    type: Literal["connector"]
    from_: EndpointSpec | None = Field(default=None, alias="from")
    to: EndpointSpec | None = None
    route: dict[str, Any] | None = None
    label: str | None = None
    stroke: StrokeInlineLike | None = None
    stroke_style: str | None = None


class LegendObject(_ObjectBase):
    """Visual object `type: legend` — a key of `sample` / `label` entries."""

    type: Literal["legend"]
    # Each item is a `{sample/color, label}` mapping.
    items: list[Any] | None = None


class GroupObject(_ObjectBase):
    """Visual object `type: group` — a transform/opacity wrapper over children."""

    type: Literal["group"]
    # Nested objects; `children` / `objects` are accepted synonyms.
    children: list[dict[str, Any]] | None = None
    objects: list[dict[str, Any]] | None = None
    transform: str | None = None


class ContainerObject(_ObjectBase):
    """Visual object `type: container` — auto-lays out `children` via its `layout`."""

    type: Literal["container"]
    # Nested objects; `children` / `objects` are accepted synonyms.
    children: list[dict[str, Any]] | None = None
    objects: list[dict[str, Any]] | None = None
    layout: dict[str, Any] | None = None


class ComponentObject(_ObjectBase):
    """Visual object `type: component` — an instance of the named `ComponentDef`."""

    type: Literal["component"]
    component: str | None = None
    variant: str | None = None
    fill: Color | None = None
    radius: float | None = None
    stroke_style: str | None = None


class ChipRowObject(_ObjectBase):
    """Visual object `type: chip_row` — a horizontal row of labelled chips."""

    type: Literal["chip_row"]
    items: list[Any] | None = None
    origin: Point | None = None
    height: float | None = None
    gap: float | None = None
    fill: Color | None = None
    stroke: StrokeInlineLike | None = None
    style: str | TextStyle | None = None


class BarChartObject(_ObjectBase):
    """Visual object `type: bar_chart` — a bar chart from `data` (built-in primitive)."""

    type: Literal["bar_chart"]
    # `{labels, values | series, note}` — see the renderer for the series shape.
    data: dict[str, Any] | None = None
    style: dict[str, Any] | None = None


class LineChartObject(_ObjectBase):
    """Visual object `type: line_chart` — a line chart from `data` (built-in primitive)."""

    type: Literal["line_chart"]
    # `{labels, values | series, note}` — see the renderer for the series shape.
    data: dict[str, Any] | None = None
    style: dict[str, Any] | None = None


class TableObject(_ObjectBase):
    """Tabular grid of cells with optional header and zebra-striping.

    `columns` declares column-width hints (numbers in document units, or
    percent strings, or `null` for auto-equal distribution). `header`
    is a list of strings for the title row; `rows` is a list of row
    lists, each cell is a string or a mapping `{text, style, align}`.
    """

    type: Literal["table"]
    columns: list[Any] | None = None
    header: list[Any] | None = None
    rows: list[list[Any]] | None = None
    row_height: float | None = None
    header_height: float | None = None
    zebra: bool | None = None
    cell_padding: float | list[float] | None = None
    style: dict[str, Any] | None = None


class UMLClassifierBoxObject(_ObjectBase):
    """UML classifier box — three-compartment notation primitive.

    Phase A.2 of the UML support architecture. The composer
    (Phase A.3) generates instances of this from typed UML model
    elements; authors may also instantiate it directly to hand-place
    a classifier outside the composer's auto-layout.

    `attributes` and `operations` accept the same field shapes as
    `framegraph._uml.UMLAttribute` / `UMLOperation` — the renderer
    is permissive on unknown extras, so feeding in raw model objects
    via `model_dump()` works.
    """

    type: Literal["uml.classifier_box"]
    name: str
    stereotype: str | None = None
    abstract: bool | None = None
    attributes: list[dict[str, Any]] | None = None
    operations: list[dict[str, Any]] | None = None
    style: dict[str, Any] | None = None


class UMLActorObject(_ObjectBase):
    """UML Actor — stick-figure glyph with a label below.

    Phase B.2 of the UML support architecture. The use-case-diagram
    composer emits these for `UMLActor` semantic elements; authors
    may also instantiate directly.
    """

    type: Literal["uml.actor"]
    name: str
    style: dict[str, Any] | None = None


class UMLComponentBoxObject(_ObjectBase):
    """UML Component box — rectangle with the component icon glyph.

    Phase C.1 of the UML support architecture. The component-diagram
    composer emits these for `UMLComponent` semantic elements.

    `provided_interfaces` and `required_interfaces` are accepted at
    primitive level so authors can hand-place a component without
    needing the composer.
    """

    type: Literal["uml.component_box"]
    name: str
    stereotype: str | None = None
    provided_interfaces: list[str] | None = None
    required_interfaces: list[str] | None = None
    style: dict[str, Any] | None = None


class UMLMarkerGlyphObject(_ObjectBase):
    """Inline UML marker glyph (diamond/triangle/arrow) for legends.

    Renders the same shape used by a connector's `arrow_end_kind` as a
    free-standing glyph at a chosen position. The motivating use case
    is the legend block of a class diagram: `◇ hollow diamond` and
    `◆ filled diamond` rendered as text characters fall back to the
    missing-glyph box on rasterisers whose default font lacks
    U+25C7 / U+25C6. This object emits the actual SVG polygon, so the
    legend always matches the diagram's markers byte-for-byte.
    """

    type: Literal["uml.marker_glyph"]
    kind: Literal[
        "hollow_diamond",
        "filled_diamond",
        "hollow_triangle",
        "filled_triangle",
        "open_arrow",
    ]
    position: list[float]
    size: float | None = None
    color: str | None = None
    rotation: float | None = None


class UMLLollipopObject(_ObjectBase):
    """UML provided-interface lollipop — circle on a stem.

    Phase C.1 primitive. `attach` is one of `north|south|east|west`
    and indicates which face of the parent component the stem
    extends from. The label sits beyond the circle.
    """

    type: Literal["uml.lollipop"]
    name: str
    attach: Literal["north", "south", "east", "west"] | None = None
    style: dict[str, Any] | None = None


class UMLSocketObject(_ObjectBase):
    """UML required-interface socket — half-circle on a stem.

    Phase C.1 primitive. `attach` selects the parent face the stem
    extends from. The arc opens away from the parent so it can
    visually mate with a lollipop.
    """

    type: Literal["uml.socket"]
    name: str
    attach: Literal["north", "south", "east", "west"] | None = None
    style: dict[str, Any] | None = None


class UMLNodeBoxObject(_ObjectBase):
    """UML deployment Node — 3D-box (cuboid) with name + stereotype.

    Phase C.2 of the UML support architecture. The deployment-diagram
    composer emits these for `UMLDeploymentNode` semantic elements.
    """

    type: Literal["uml.node_box"]
    name: str
    kind: Literal["device", "execution_environment"] | None = None
    stereotype: str | None = None
    depth: float | None = None
    style: dict[str, Any] | None = None


class UMLArtifactBoxObject(_ObjectBase):
    """UML Artifact — rectangle with «artifact» keyword + folded-document icon.

    Phase C.2 primitive.
    """

    type: Literal["uml.artifact_box"]
    name: str
    stereotype: str | None = None
    style: dict[str, Any] | None = None


class UMLActivityNodeObject(_ObjectBase):
    """UML activity node — initial / final / decision / fork / etc.

    Phase C.3 of the UML support architecture. The activity-diagram
    composer emits these for non-action nodes; actions use
    `uml.action` (a rounded rectangle). The renderer dispatches
    on `kind` to draw the appropriate glyph.
    """

    type: Literal["uml.activity_node"]
    kind: Literal[
        "initial",
        "final",
        "flow_final",
        "decision",
        "merge",
        "fork",
        "join",
    ]
    name: str | None = None
    orientation: Literal["horizontal", "vertical"] | None = None
    style: dict[str, Any] | None = None


class UMLActionObject(_ObjectBase):
    """UML Action — rounded rectangle with a name label.

    Phase C.3 primitive.
    """

    type: Literal["uml.action"]
    name: str
    style: dict[str, Any] | None = None


class UMLSwimlaneObject(_ObjectBase):
    """UML swim-lane (ActivityPartition) — column with header band.

    Phase C.3 primitive.
    """

    type: Literal["uml.swimlane"]
    name: str
    style: dict[str, Any] | None = None


class UMLStateBoxObject(_ObjectBase):
    """UML simple/composite state — rounded rectangle with optional internal-actions compartment.

    Phase C.4 of the UML support architecture. The state-machine
    composer emits these for `UMLState` semantic elements; authors
    may instantiate directly.
    """

    type: Literal["uml.state_box"]
    name: str
    entry: str | None = None
    exit: str | None = None
    do: str | None = None
    composite: bool | None = None
    style: dict[str, Any] | None = None


class UMLPseudostateObject(_ObjectBase):
    """UML pseudostate glyph (initial / choice / history / etc.).

    Phase C.4 primitive.
    """

    type: Literal["uml.pseudostate"]
    kind: Literal[
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
    name: str | None = None
    style: dict[str, Any] | None = None


class UMLLifelineObject(_ObjectBase):
    """UML sequence-diagram lifeline — head box with dashed line below.

    Phase D of the UML support architecture. The sequence-diagram
    composer emits these for `UMLLifeline` semantic elements.
    """

    type: Literal["uml.lifeline"]
    name: str
    type_name: str | None = None
    actor: bool | None = None
    head_height: float | None = None
    style: dict[str, Any] | None = None


class UMLActivationBarObject(_ObjectBase):
    """UML execution-specification activation bar — thin filled rectangle.

    Phase D primitive.
    """

    type: Literal["uml.activation_bar"]
    style: dict[str, Any] | None = None


class UMLFragmentFrameObject(_ObjectBase):
    """UML CombinedFragment frame — labelled rectangle with operator tag.

    Phase D primitive. `dividers` is the list of absolute y-coordinates
    where dashed inter-operand dividers should be drawn (composer
    supplies these).
    """

    type: Literal["uml.fragment_frame"]
    kind: Literal[
        "alt",
        "opt",
        "loop",
        "par",
        "break",
        "critical",
        "neg",
        "strict",
        "seq",
        "ignore",
        "consider",
        "assert",
        # Interaction-overview-only operators (Phase E.3): `ref` for
        # an interaction use, `sd` for an inline sequence fragment.
        "ref",
        "sd",
    ]
    operands: list[str] | None = None
    dividers: list[float] | None = None
    style: dict[str, Any] | None = None


class UMLTimingLaneObject(_ObjectBase):
    """UML timing-diagram lane — labelled rectangle with state ticks.

    Phase E.1 primitive. The composer overlays state-change step lines
    on top of this lane in a separate layer.
    """

    type: Literal["uml.timing_lane"]
    name: str
    states: list[str]
    label_width: float | None = None
    style: dict[str, Any] | None = None


class _UnknownObject(_ObjectBase):
    """Fall-through for third-party `register(type_name, fn)` types.

    The renderer dispatches by `type` at runtime; ingest must not
    reject types it has never heard of, otherwise plug-in authors
    would be locked out.
    """

    type: str


KnownObject = Annotated[
    RectObject
    | EllipseObject
    | TextObject
    | BulletListObject
    | LineObject
    | PolylineObject
    | PathObject
    | ImageObject
    | IconObject
    | UseObject
    | ConnectorObject
    | LegendObject
    | GroupObject
    | ContainerObject
    | ComponentObject
    | ChipRowObject
    | BarChartObject
    | LineChartObject
    | TableObject
    | UMLClassifierBoxObject
    | UMLActorObject
    | UMLComponentBoxObject
    | UMLLollipopObject
    | UMLSocketObject
    | UMLMarkerGlyphObject
    | UMLNodeBoxObject
    | UMLArtifactBoxObject
    | UMLActivityNodeObject
    | UMLActionObject
    | UMLSwimlaneObject
    | UMLStateBoxObject
    | UMLPseudostateObject
    | UMLLifelineObject
    | UMLActivationBarObject
    | UMLFragmentFrameObject
    | UMLTimingLaneObject,
    Field(discriminator="type"),
]


class _ObjectAdapter(RootModel["KnownObject | _UnknownObject"]):
    """Discriminated-union adapter that falls through to `_UnknownObject`."""


# Type alias used in `Layer.objects` so each entry is validated via
# the discriminated union below (with `_UnknownObject` fall-through
# for plug-in types).
ObjectUnion = KnownObject | _UnknownObject


# ─────────────────────────────────────────────────────────────────
# Visual — layers
# ─────────────────────────────────────────────────────────────────


class Layer(BaseModel):
    """A z-ordered stack of objects.

    `objects` validates each entry through the discriminated union on
    `type`. Unknown discriminators fall through to `_UnknownObject`
    so third-party plug-in types are not rejected at ingest.
    """

    model_config = ConfigDict(extra="allow")
    id: str
    z: float | None = None
    opacity: float | None = None
    objects: list[ObjectUnion] = Field(default_factory=list)


class Visual(BaseModel):
    """`visual` block — tokens, symbols, components, layers."""

    model_config = ConfigDict(extra="allow")
    tokens: Tokens = Field(default_factory=Tokens)
    symbols: dict[str, SymbolDef] = Field(default_factory=dict)
    component_defs: dict[str, ComponentDef] = Field(default_factory=dict)
    layers: list[Layer] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────────


class Document(BaseModel):
    """Standalone diagram document.

    Validates `dsl: FrameGraph`, a numeric `version`, and presence of
    the three structural blocks (scene + semantic + visual). The deck
    document model lives in `DeckDocument` below.
    """

    model_config = ConfigDict(extra="allow")
    dsl: Literal["FrameGraph"]
    version: float
    kind: str | None = None
    scene: Scene
    semantic: Semantic = Field(default_factory=Semantic)
    visual: Visual = Field(default_factory=Visual)


class ChromeConfig(BaseModel):
    """Master-slide chrome — auto-prepended layer on every slide.

    Declared at deck level via `deck.chrome:`. The slide may opt out
    via `chrome: false` or override per-instance via `chrome: {…}`.
    `extra="allow"` permits arbitrary slot pass-through fields, the
    same convention used on `use` objects.
    """

    model_config = ConfigDict(extra="allow")
    symbol: str
    params: dict[str, Any] | None = None
    z: float | None = None


# A slide's `chrome:` field accepts either:
#   - false / null  → opt out
#   - a mapping     → per-instance overrides
# We accept Any here and resolve at the deck-renderer level.
SlideChrome = bool | dict[str, Any] | None


class SlideEntry(BaseModel):
    """Single slide in a deck. Every field is optional except `id`."""

    model_config = ConfigDict(extra="allow")
    slide: int | None = None
    id: str
    title: str | None = None
    description: str | None = None
    notes: str | None = None
    extends: str | None = Field(default=None, alias="$extends")
    tokens: Tokens | None = None
    symbols: dict[str, SymbolDef] | None = None
    semantic: Semantic | None = None
    visual: Visual | None = None
    chrome: SlideChrome = None


class DeckConfig(BaseModel):
    """`deck:` block in a presentation-deck document."""

    model_config = ConfigDict(extra="allow")
    canvas: Canvas | None = None
    tokens: Tokens | None = None
    symbols: dict[str, SymbolDef] | None = None
    component_defs: dict[str, ComponentDef] | None = None
    # `chrome` accepts a string (symbol id) or a full ChromeConfig mapping.
    chrome: str | ChromeConfig | None = None


class DeckDocument(BaseModel):
    """Multi-slide deck document."""

    model_config = ConfigDict(extra="allow")
    dsl: Literal["FrameGraph"]
    version: float
    kind: str | None = None
    deck: DeckConfig = Field(default_factory=DeckConfig)
    slides: list[SlideEntry] = Field(default_factory=list)
    theme: str | None = Field(default=None, alias="$theme")


# ─────────────────────────────────────────────────────────────────
# Validation helpers — public entry points
# ─────────────────────────────────────────────────────────────────


def validate_document(data: dict[str, Any]) -> Document:
    """Validate a parsed YAML mapping as a standalone FrameGraph document.

    Args:
        data: The result of `yaml.safe_load(...)` on a FrameGraph YAML
            file. Must have a top-level `scene` key.

    Returns:
        A validated `Document` model. The renderer continues to read
        the original `data` dict; this call's job is to fail loudly
        on malformed input so silent skips in `render_svg` do not
        mask schema drift.

    Raises:
        pydantic.ValidationError: If the input violates the schema.
    """
    return Document.model_validate(data)


def validate_any(data: dict[str, Any]) -> Any:
    """Validate any FrameGraph document — dispatches by `kind:`.

    Phase 1 of ADR 0001 ("Collapse `Document` and `Deck` into a
    `FrameSet` graph") introduces `kind: frameset` alongside the
    existing `kind: hybrid-semantic-visual-diagram` and
    `kind: presentation-deck`. This helper centralizes the dispatch
    so callers don't have to inspect `kind:` themselves.

    Args:
        data: A parsed YAML mapping with `dsl: FrameGraph`.

    Returns:
        Either a `Document`, `DeckDocument`, or `FrameSetDocument`,
        depending on `data["kind"]` (or the presence of `slides:`).

    Raises:
        pydantic.ValidationError: If the input fails the matching
            schema.
        ValueError: If `data` is not a mapping or lacks
            `dsl: FrameGraph`.
    """
    if not isinstance(data, dict):
        raise ValueError(f"FrameGraph document root must be a mapping; got {type(data).__name__}")
    if data.get("dsl") != "FrameGraph":
        raise ValueError(
            f"FrameGraph document must declare `dsl: FrameGraph`; got {data.get('dsl')!r}"
        )

    # Lazy import — `_frameset` imports types from this module only via
    # the public surface, so a top-level import would not cause a cycle,
    # but defer to keep import-time latency low.
    from framegraph._frameset import validate_frameset as _vfs

    kind = data.get("kind")
    if kind == "frameset":
        return _vfs(data)
    if kind == "presentation-deck" or isinstance(data.get("slides"), list):
        return validate_deck(data)
    return validate_document(data)


def validate_deck(data: dict[str, Any]) -> DeckDocument:
    """Validate a parsed YAML mapping as a multi-slide deck.

    Args:
        data: The result of `yaml.safe_load(...)` on a deck YAML
            file. Must have a top-level `slides` key.

    Returns:
        A validated `DeckDocument`.

    Raises:
        pydantic.ValidationError: If the input violates the schema.
    """
    return DeckDocument.model_validate(data)


def validate_object(obj: dict[str, Any]) -> Any:
    """Validate a single visual-object mapping.

    Useful for ad-hoc fixture authoring tests. Unknown `type`
    discriminators fall through to `_UnknownObject` rather than
    raising — see the module docstring for why.
    """
    return _ObjectAdapter.model_validate(obj).root


# ─────────────────────────────────────────────────────────────────
# Strict authoring check — unknown / mistyped object keys
# ─────────────────────────────────────────────────────────────────
#
# PALS's Law (CLAUDE.md): LLM-authored YAML statistically carries typos
# and hallucinated field names. The ingestion models are `extra="allow"`
# for v1.x backward-compat (PURPOSE.md) and slot pass-through, so those
# bad keys validate clean and render silently wrong. This SEPARATE,
# opt-in layer flags any top-level object key not declared on the object's
# model — catching `radious`/`colour`/`algin` before they ship — without
# tightening the permissive ingestion contract.

# Object types that legitimately accept arbitrary top-level keys:
#   - `use` pulls symbol-slot values from arbitrary top-level fields
#     (`obj[slot_name]`), so its key set is open by design.
#   - `component` does the same for its `ComponentDef.slots` (the renderer
#     reads `obj[slot]` for each declared slot).
#   - unknown / third-party `register(type, fn)` types validate via
#     `_UnknownObject` and have no declared contract to check against.
_OPEN_OBJECT_TYPES: frozenset[str] = frozenset({"use", "component"})

# Keys permitted on every object regardless of `type`:
#   - `class`  — documented common pass-through (CSS-style hook).
#   - `flex`   — container-child layout hint read by the layout engine from
#                any child object, not by the child's own renderer.
_UNIVERSAL_OBJECT_KEYS: frozenset[str] = frozenset({"class", "flex"})


@dataclass(frozen=True)
class StrictViolation:
    """One unknown top-level key found on a visual object in strict mode."""

    object_type: str
    key: str
    path: str
    suggestion: str | None

    def __str__(self) -> str:
        """Render the violation as a `path (type): unknown key 'k'` diagnostic."""
        hint = f" — did you mean '{self.suggestion}'?" if self.suggestion else ""
        return f"{self.path} ({self.object_type}): unknown key '{self.key}'{hint}"


def _object_models() -> dict[str, type[BaseModel]]:
    """Map each first-class object `type` literal to its concrete model."""
    union = get_args(KnownObject)[0]  # KnownObject = Annotated[<union>, Field(...)]
    out: dict[str, type[BaseModel]] = {}
    for member in get_args(union):
        lits = get_args(member.model_fields["type"].annotation)
        if lits and isinstance(lits[0], str):
            out[lits[0]] = member
    return out


def _allowed_keys(model: type[BaseModel]) -> set[str]:
    keys: set[str] = set(_UNIVERSAL_OBJECT_KEYS)
    for name, field in model.model_fields.items():
        keys.add(name)
        if field.alias:
            keys.add(field.alias)
    return keys


_ALLOWED_OBJECT_KEYS: dict[str, set[str]] = {
    type_name: _allowed_keys(model) for type_name, model in _object_models().items()
}


def _check_object(obj: dict[str, Any], path: str, out: list[StrictViolation]) -> None:
    type_name = obj.get("type")
    if not isinstance(type_name, str) or type_name in _OPEN_OBJECT_TYPES:
        return
    allowed = _ALLOWED_OBJECT_KEYS.get(type_name)
    if allowed is None:
        return  # unknown / plug-in type → no declared contract to check
    for key in obj:
        if not isinstance(key, str) or key in allowed:
            continue
        match = difflib.get_close_matches(key, allowed, n=1, cutoff=0.7)
        out.append(StrictViolation(type_name, key, path, match[0] if match else None))


def iter_strict_violations(data: Any) -> list[StrictViolation]:
    """Report every unknown top-level key on a visual object in a document.

    Walks the whole document and inspects each object found in an `objects`
    or `children` list (layers, groups, containers, symbol bodies),
    comparing its top-level keys against the keys declared on the object's
    Pydantic model. Open types (`use`) and unknown plug-in types are exempt.

    This is an opt-in authoring-strictness layer (`framegraph render
    --strict`, `framegraph validate --strict`) on top of the permissive,
    backward-compatible ingestion schema — it never changes what
    `validate_*` accepts.
    """
    out: list[StrictViolation] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("objects", "children") and isinstance(value, list):
                    for i, item in enumerate(value):
                        item_path = f"{path}.{key}[{i}]"
                        if isinstance(item, dict) and isinstance(item.get("type"), str):
                            _check_object(item, item_path, out)
                        walk(item, item_path)
                else:
                    walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(data, "")
    return out


__all__ = [
    "ComponentDef",
    "DeckDocument",
    "Document",
    "Layer",
    "Scene",
    "Semantic",
    "StrictViolation",
    "SymbolDef",
    "Tokens",
    "Visual",
    "iter_strict_violations",
    "validate_any",
    "validate_deck",
    "validate_document",
    "validate_object",
]
