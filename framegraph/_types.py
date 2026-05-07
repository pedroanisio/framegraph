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
    scene: Mapping[str, Any]
    object_index: Mapping[str, Mapping[str, Any]]
    symbols: Mapping[str, Any]
    component_defs: Mapping[str, Mapping[str, Any]]
    glyph_map: Mapping[str, str]

    # `_uses_icon_font` is mutated by plug-ins that emit icon-font glyphs;
    # `defs_svg()` reads it to decide whether to inject the Tabler webfont.
    _uses_icon_font: bool

    # ── Token resolution ──────────────────────────────────────────────
    def color(self, v: Any, default: str = ...) -> str: ...
    def font(self, v: Any) -> str: ...
    def fill_value(self, v: Any, default: str = ...) -> str: ...
    def text_style(self, ref: Any) -> dict[str, Any]: ...
    def stroke_style(self, ref: Any = ..., inline: Any = ...) -> dict[str, Any] | None: ...
    def rect_stroke(self, obj: Mapping[str, Any]) -> dict[str, Any] | None: ...
    def stroke_attrs(
        self,
        st: Mapping[str, Any] | None,
        *,
        arrows: bool = ...,
    ) -> dict[str, Any]: ...
    def group_attrs(
        self,
        obj: Mapping[str, Any],
        extra: Mapping[str, Any] | None = ...,
    ) -> dict[str, Any]: ...

    # ── Object-index queries ──────────────────────────────────────────
    def object_box(self, obj: Mapping[str, Any]) -> Box | None: ...
    def object_ports(self, obj: Mapping[str, Any], b: Box | None) -> dict[str, Point]: ...

    # ── Connector / line geometry ─────────────────────────────────────
    def endpoint(self, ep: Any) -> Point: ...
    def path_d(self, points: Sequence[Point]) -> str: ...
    def line_svg(
        self,
        obj: Mapping[str, Any],
        points: Sequence[Point],
        style_name: Any = ...,
        force_poly: bool = ...,
    ) -> str: ...

    # ── Text metrics ──────────────────────────────────────────────────
    def _str_width(self, text: str, fs: float, bold: bool) -> float: ...

    # ── Object dispatch ───────────────────────────────────────────────
    def render_object(self, obj: Mapping[str, Any]) -> str: ...
    def register(self, type_name: str, fn: RenderFn) -> None: ...

    # ── Plug-in helpers expected but currently MISSING from
    #    FrameGraphRenderer (v2.0 modular-split regression).
    #    They are declared here so mypy flags the gap; runtime calls
    #    raise AttributeError, which is silently caught by render_svg's
    #    per-object try/except and recorded in `self.warnings`.
    #
    #    Tracking: `text_svg` and `render_rect` are needed by the
    #    `connector` and `legend` paths in renderers/lines.py; in
    #    renderer.py the duplicate in-class `render_connector` /
    #    `render_legend` (lines ~1032+) is unreachable dead code from
    #    the pre-modular era.
    #    `eval_length` is needed by container offset resolution in
    #    renderers/layout.py.
    #
    #    These three should be implemented on FrameGraphRenderer (or
    #    moved to free helpers and the call sites updated) in a follow-
    #    up step. They are intentionally listed in the Protocol so that
    #    the contract is honest about what plug-ins assume.
    # ──────────────────────────────────────────────────────────────────
    def text_svg(
        self,
        content: Any,
        b: Box,
        style: Mapping[str, Any],
        *,
        rotation: Any = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> str: ...
    def render_rect(self, obj: Mapping[str, Any]) -> str: ...
    def eval_length(self, value: Any, total: float) -> float: ...
