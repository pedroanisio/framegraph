"""Reusable-template renderers: `icon` (font glyph) and `use` (`<symbol>` instantiation).

`icon` resolves a glyph_map alias or literal Unicode character to
text-rendered SVG; `use` deep-copies a symbol template, fills its
slots with per-instance parameters, and renders the resolved tree.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from framegraph._helpers import (
    attrs,
    box,
    esc,
    fmt,
    fnum,
)
from framegraph._types import RendererContext


def render_icon(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a glyph (icon-font codepoint or Unicode symbol) centred in box.

    Args:
        r: Active renderer context.
        obj: Object mapping. Recognized keys:

            - `font`: a fonts token key, a literal font-family string,
              or `"primary"`.
            - `glyph`: a glyph_map key OR a raw Unicode character /
              codepoint string.
            - `size`: font-size in px; defaults to 65% of box height.
    """
    x, y, w, h = box(obj.get("box", [0, 0, 0, 0]))
    font_ref = obj.get("font", "primary")
    font_name = r.font(font_ref)

    # Flag icon-font usage so defs_svg emits the @import
    known_icon_fonts = {
        "tabler",
        "tabler-icons",
        "material",
        "material symbols",
        "fontawesome",
        "phosphor",
        "remixicon",
    }
    if str(font_ref).lower() in known_icon_fonts:
        r._uses_icon_font = True

    glyph_ref = str(obj.get("glyph", ""))
    glyph = r.glyph_map.get(glyph_ref, glyph_ref)  # resolve alias
    color = r.color(obj.get("color"), "#000000")
    size = fnum(obj.get("size"), h * 0.65)
    cx, cy = x + w / 2, y + h / 2
    a: dict[str, Any] = {
        "x": fmt(cx),
        "y": fmt(cy),
        "font-family": font_name,
        "font-size": fmt(size),
        "fill": color,
        "text-anchor": "middle",
        "dominant-baseline": "central",
    }
    return f"<g {attrs(r.group_attrs(obj))}><text {attrs(a)}>{esc(glyph)}</text></g>"


# ── v3: use object ─────────────────────────────────────────────────


def render_use(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Stamp a symbol at obj's box, scaling its local coordinate space to fit.

    Slot values (`$slotname`) and params (`$paramname`) are resolved
    from the use object's fields and `params` sub-mapping
    respectively. Object ids inside the symbol are prefixed with the
    use instance's id to avoid collisions across multiple stampings.
    """
    sym_name = str(obj.get("symbol", ""))
    sym = r.symbols.get(sym_name)
    if not sym:
        raise ValueError(f"unknown symbol '{sym_name}'")

    ux, uy, uw, uh = box(obj.get("box", [0, 0, 0, 0]))
    _, _, sw, sh = box(sym.get("box", [0, 0, 1, 1]))
    scale_x = uw / sw if sw else 1.0
    scale_y = uh / sh if sh else 1.0
    transform = f"translate({fmt(ux)},{fmt(uy)}) scale({fmt(scale_x)},{fmt(scale_y)})"

    # Collect slot and param values from the use object
    slots: dict[str, Any] = {}
    for sname in sym.get("slots") or []:
        if sname in obj:
            slots[sname] = obj[sname]
    params: dict[str, Any] = dict(obj.get("params") or {})

    use_id = str(obj.get("id", "use"))
    out = [f"<g {attrs(r.group_attrs(obj))}>", f'  <g transform="{transform}">']

    for sym_obj in sym.get("objects") or []:
        resolved = _resolve_symbol_slots(r, sym_obj, slots, params, use_id)
        try:
            rendered = r.render_object(resolved)
            out.append("    " + rendered.replace("\n", "\n    "))
        except Exception as exc:
            out.append(f"    <!-- symbol obj error: {esc(str(exc))} -->")

    out.append("  </g>")
    out.append("</g>")
    return "\n".join(out)


def _resolve_symbol_slots(
    r: RendererContext, obj: Any, slots: dict, params: dict, prefix: str
) -> dict[str, Any]:
    """Deep-copy an object dict, replacing `$key` placeholders.

    `$key` string values are looked up in `slots` first, then
    `params`; ids are prefixed with `prefix` to avoid collisions
    across multiple `use` instances.
    """

    def resolve(v: Any) -> Any:
        if isinstance(v, str) and v.startswith("$"):
            k = v[1:]
            if k in slots:
                return slots[k]
            if k in params:
                return params[k]
        return v

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(resolve(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(resolve(item)) for item in node]
        return resolve(node)

    result = walk(copy.deepcopy(dict(obj)))
    if "id" in result:
        result["id"] = f"{prefix}__{result['id']}"
    return result


# Unchanged shape renderers from v2 ─────────────────────────────────


RENDERERS = {
    "icon": render_icon,
    "use": render_use,
}
