"""Pydantic v2 models — normative document schema for FrameGraph.

This module is the executable contract for what a FrameGraph YAML
document must look like. It supersedes the prior EBNF specification.
The companion human-readable spec lives at `static/specs/SCHEMA.md`.

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

from typing import Annotated, Any, Literal

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


# ─────────────────────────────────────────────────────────────────
# Scene
# ─────────────────────────────────────────────────────────────────


class Canvas(BaseModel):
    """Scene canvas — required for standalone documents."""

    model_config = ConfigDict(extra="allow")
    size: Annotated[list[float], Field(min_length=2, max_length=2)]
    units: Literal["px", "pt"] | None = None


class TextContract(BaseModel):
    model_config = ConfigDict(extra="allow")
    min_font_size: float | None = None
    overflow: Literal["visible", "clip", "shrink_to_fit"] | None = None


class SemanticsContract(BaseModel):
    model_config = ConfigDict(extra="allow")
    decorative_objects_may_omit_bind: bool | None = None


class RenderingContract(BaseModel):
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
    model_config = ConfigDict(extra="allow")
    color: Color | None = None
    width: float | None = None
    dash: list[float] | None = None
    arrow_start: bool | None = None
    arrow_end: bool | None = None
    linecap: str | None = None
    linejoin: str | None = None


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


class _ObjectBase(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    decorative: bool | None = None
    bind: str | None = None
    box: Box | None = None
    rotation: Any = None  # accepts number or [deg, cx, cy] list
    ports: dict[str, Point] | None = None
    opacity: float | None = None


class RectObject(_ObjectBase):
    type: Literal["rect"]


class EllipseObject(_ObjectBase):
    type: Literal["ellipse"]


class TextObject(_ObjectBase):
    type: Literal["text"]


class BulletListObject(_ObjectBase):
    type: Literal["bullet_list"]


class LineObject(_ObjectBase):
    type: Literal["line"]


class PolylineObject(_ObjectBase):
    type: Literal["polyline"]


class PathObject(_ObjectBase):
    type: Literal["path"]


class ImageObject(_ObjectBase):
    type: Literal["image"]


class IconObject(_ObjectBase):
    type: Literal["icon"]


class UseObject(_ObjectBase):
    """Symbol instantiation — accepts arbitrary slot pass-through fields."""

    type: Literal["use"]
    symbol: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectorObject(_ObjectBase):
    type: Literal["connector"]


class LegendObject(_ObjectBase):
    type: Literal["legend"]


class GroupObject(_ObjectBase):
    type: Literal["group"]


class ContainerObject(_ObjectBase):
    type: Literal["container"]


class ComponentObject(_ObjectBase):
    type: Literal["component"]
    component: str | None = None


class ChipRowObject(_ObjectBase):
    type: Literal["chip_row"]


class BarChartObject(_ObjectBase):
    type: Literal["bar_chart"]


class LineChartObject(_ObjectBase):
    type: Literal["line_chart"]


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
    | UMLNodeBoxObject
    | UMLArtifactBoxObject,
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


__all__ = [
    "Document",
    "DeckDocument",
    "Scene",
    "Visual",
    "Tokens",
    "Semantic",
    "Layer",
    "SymbolDef",
    "ComponentDef",
    "validate_document",
    "validate_deck",
    "validate_object",
]
