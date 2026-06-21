"""framegraph._types — Public typing contracts.

`RendererContext` is the structural type of the `r` argument that every
free-function renderer in `framegraph.renderers.*` receives. It also
defines the third-party plug-in contract used by
`FrameGraphRenderer.register(type_name, fn)`.

The Protocol intentionally describes the **observed** plug-in surface —
every attribute and method that any built-in renderer module reads from
its `r` parameter. `FrameGraphRenderer` is expected to satisfy this
Protocol structurally; mypy will flag drift in either direction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from framegraph._helpers import Box, Point

RenderFn = Callable[["RendererContext", Mapping[str, Any]], str]


@runtime_checkable
class RendererContext(Protocol):
    """Surface that built-in and third-party renderers expect from `r`.

    Stability: this Protocol is the v2.0 plug-in contract. Adding
    members is a minor change; removing or renaming them is a major
    schema break under the project's semver policy.
    """

    # ── Document state ────────────────────────────────────────────────
    # All five attributes are typed as concrete `dict` to match what
    # `FrameGraphRenderer` constructs in `__init__`. Mypy's Protocol
    # attribute matching is invariant, so widening to `Mapping` here
    # would force the implementing class to declare the same — losing
    # mutability that `renderers/layout.py` relies on (it writes
    # resolved child boxes into `object_index`). Read-only consumers
    # can still treat these as Mappings structurally.
    scene: dict[str, Any]
    object_index: dict[str, dict[str, Any]]
    symbols: dict[str, Any]
    component_defs: dict[str, dict[str, Any]]
    glyph_map: dict[str, str]

    # `_uses_icon_font` is mutated by plug-ins that emit icon-font glyphs;
    # `defs_svg()` reads it to decide whether to inject the Tabler webfont.
    _uses_icon_font: bool

    # `yaml_source_dir` is the absolute directory of the source YAML
    # document. `renderers/image.py` reads it to resolve relative
    # `<image>` `href`s; the CLI / deck renderer set it after
    # construction. Empty string when no source path is known.
    yaml_source_dir: str

    # ── Token resolution ──────────────────────────────────────────────
    def color(self, v: Any, default: str = ...) -> str:
        """Resolve a color reference to a hex/CSS string."""
        ...

    def font(self, v: Any) -> str:
        """Resolve a font reference to a CSS `font-family` string."""
        ...

    def fill_value(self, v: Any, default: str = ...) -> str:
        """Resolve a fill value to an SVG paint string."""
        ...

    def text_style(self, ref: Any) -> dict[str, Any]:
        """Resolve a text-style reference to a fully-defaulted style mapping."""
        ...

    def stroke_style(self, ref: Any = ..., inline: Any = ...) -> dict[str, Any] | None:
        """Resolve a stroke-style reference, optionally overlaid with inline overrides."""
        ...

    def rect_stroke(self, obj: Mapping[str, Any]) -> dict[str, Any] | None:
        """Resolve the stroke for a `rect`/`ellipse`-style object."""
        ...

    def stroke_attrs(
        self,
        st: Mapping[str, Any] | None,
        *,
        arrows: bool = ...,
    ) -> dict[str, Any]:
        """Convert a resolved stroke style into SVG attribute key/value pairs."""
        ...

    def opacity_attrs(
        self,
        obj: Mapping[str, Any],
        *,
        has_fill: bool = ...,
        has_stroke: bool = ...,
    ) -> dict[str, Any]:
        """Build per-shape `fill-opacity` / `stroke-opacity` SVG attrs."""
        ...

    def group_attrs(
        self,
        obj: Mapping[str, Any],
        extra: Mapping[str, Any] | None = ...,
    ) -> dict[str, Any]:
        """Build the SVG `<g>` attribute dict for a wrapped object."""
        ...

    # ── Object-index queries ──────────────────────────────────────────
    def object_box(self, obj: Mapping[str, Any]) -> Box | None:
        """Return the canvas-space bounding box `(x, y, w, h)` for an object."""
        ...

    def object_ports(self, obj: Mapping[str, Any], b: Box | None) -> dict[str, Point]:
        """Return the named anchor points exposed by an object."""
        ...

    # ── Connector / line geometry ─────────────────────────────────────
    def endpoint(
        self, ep: Any, *, _connector_id: str | None = None, _end_label: str | None = None
    ) -> Point:
        """Resolve a connector endpoint to a canvas-space (x, y) point."""
        ...

    def path_d(self, points: Sequence[Point]) -> str:
        """Build an SVG `path` `d` attribute from a polyline point list."""
        ...

    def line_svg(
        self,
        obj: Mapping[str, Any],
        points: Sequence[Point],
        style_name: Any = ...,
        force_poly: bool = ...,
    ) -> str:
        """Render a line or polyline object to an SVG fragment."""
        ...

    # ── Text metrics ──────────────────────────────────────────────────
    def _str_width(self, text: str, fs: float, bold: bool, font: str | None = None) -> float: ...

    # ── Object dispatch ───────────────────────────────────────────────
    def render_object(self, obj: Mapping[str, Any]) -> str:
        """Dispatch a single object to its registered renderer."""
        ...

    def register(self, type_name: str, fn: RenderFn) -> None:
        """Register a custom object-type renderer."""
        ...

    # ── Plug-in helpers ────────────────────────────────────────────────
    # `text_svg`, `render_rect`, `eval_length` are the "modular-split"
    # delegates: they live as free functions in `framegraph.renderers.*`
    # and are wired onto `FrameGraphRenderer` as thin methods so plug-ins
    # can call them as `r.text_svg(...)`, `r.render_rect(...)`, etc.
    #
    # `effect_filter_attrs` is the v3.0 HD-effects Protocol member:
    # shape renderers call it to receive the SVG `filter="url(#…)"`
    # attribute (or `{}`) for the requested effect chain.
    # ──────────────────────────────────────────────────────────────────
    def text_svg(
        self,
        content: Any,
        b: Box,
        style: Mapping[str, Any],
        *,
        rotation: Any = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> str:
        """Render `content` as text inside box `b` using the resolved `style`."""
        ...

    def render_rect(self, obj: Mapping[str, Any]) -> str:
        """Render a single `rect` object."""
        ...

    def eval_length(self, value: Any, total: float) -> float:
        """Resolve a length expression against `total`."""
        ...

    def effect_filter_attrs(self, obj: Mapping[str, Any]) -> dict[str, Any]:
        """Return SVG attributes wiring `shadow` / `glow` fields on an object."""
        ...
