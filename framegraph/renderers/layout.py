"""Compositional renderers: `group`, `container`, `component`, `chip_row`.

`container` implements stack-direction auto-layout (horizontal or
vertical) with gap, padding, justify, and align controls. `group`
wraps a list of children under a single `<g>`. `component`
instantiates a template from `r.component_defs`. `chip_row` lays out
a horizontal sequence of pill-style items.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from framegraph._helpers import (
    Box,
    attrs,
    box,
    deep_get,
    esc,
    fmt,
    fnum,
    pt,
)
from framegraph._types import RendererContext
from framegraph.renderers.text_objects import text_svg as _text_svg_raw


def _text_svg_helper(
    r: RendererContext, content: Any, b: Box, style: Mapping[str, Any], **kwargs: Any
) -> str:
    """Thin shim so layout module can call text_svg without circular import issues."""
    return _text_svg_raw(r, content, b, style, **kwargs)


def render_group(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Wrap a list of children in an SVG `<g>`.

    Children may be supplied via either `objects` or `children`.
    Optional `transform` attribute is forwarded as-is to the `<g>`.
    """
    ga = r.group_attrs(obj)
    if obj.get("transform"):
        ga["transform"] = obj["transform"]
    out = [f"<g {attrs(ga)}>"]
    for child in obj.get("objects", []) or obj.get("children", []) or []:
        if isinstance(child, Mapping):
            out.append(r.render_object(child))
    out.append("</g>")
    return "\n".join(out)


def _layout_stack(
    r,
    container_box: Box,
    children_raw: list[Mapping[str, Any]],
    layout: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Compute absolute boxes for children of a stack container.

    Returns a list of shallow-copy child dicts with resolved 'box'
    fields.
    """
    cx, cy, cw, ch = container_box
    direction = str(layout.get("direction", "vertical")).lower()
    horiz = direction in ("horizontal", "h", "row")
    gap = fnum(layout.get("gap"), 0)
    align = str(layout.get("align", "stretch")).lower()
    justify = str(layout.get("justify", "start")).lower()

    # Padding: scalar or [horizontal, vertical]
    pad_raw = layout.get("padding", 0)
    if isinstance(pad_raw, (list, tuple)) and len(pad_raw) == 2:
        pad_h, pad_v = fnum(pad_raw[0]), fnum(pad_raw[1])
    else:
        pad_h = pad_v = fnum(pad_raw)

    # Content area
    content_x = cx + pad_h
    content_y = cy + pad_v
    content_w = cw - 2 * pad_h
    content_h = ch - 2 * pad_v

    n = len(children_raw)
    if n == 0:
        return []

    # Determine preferred main-axis size for each child
    # Priority: explicit box → 0 (auto)
    def preferred_main(child: Mapping[str, Any]) -> float:
        b = child.get("box")
        if b and len(b) == 4:
            return fnum(b[3]) if not horiz else fnum(b[2])  # h or w
        return 0.0

    def flex_weight(child: Mapping[str, Any]) -> float:
        return fnum(child.get("flex"), 0.0)

    prefs = [preferred_main(c) for c in children_raw]
    flexes = [flex_weight(c) for c in children_raw]

    total_gap = gap * max(0, n - 1)
    main_size = content_h if not horiz else content_w  # total main-axis space

    # Distribute space:
    # 1. Items with explicit preferred size take that space.
    # 2. Items with flex > 0 share remaining space proportionally.
    # 3. Items with neither get equal share of remaining space.
    fixed_total = sum(p for p in prefs if p > 0)
    auto_indices = [i for i, p in enumerate(prefs) if p == 0]
    flex_total = sum(flexes[i] for i in auto_indices)
    remaining = max(0.0, main_size - total_gap - fixed_total)

    resolved_sizes: list[float] = list(prefs)
    for i in auto_indices:
        if flex_total > 0:
            resolved_sizes[i] = remaining * flexes[i] / flex_total
        else:
            resolved_sizes[i] = remaining / len(auto_indices) if auto_indices else 0.0

    # Justify: shift start offset
    total_content = sum(resolved_sizes) + total_gap
    if justify == "center":
        start_offset = (main_size - total_content) / 2
    elif justify == "end":
        start_offset = main_size - total_content
    elif justify == "space_between" and n > 1:
        gap = (main_size - sum(resolved_sizes)) / (n - 1)
        start_offset = 0.0
    else:
        start_offset = 0.0

    # Build resolved children
    resolved: list[Mapping[str, Any]] = []
    cursor = start_offset
    for i, child in enumerate(children_raw):
        main_sz = resolved_sizes[i]
        cross_sz = content_w if not horiz else content_h

        # Cross-axis position and size
        if align == "stretch":
            cross_pos = 0.0
            child_cross = cross_sz
        elif align == "center":
            existing_cross = fnum((child.get("box") or [0, 0, 0, 0])[2 if not horiz else 3])
            child_cross = existing_cross if existing_cross > 0 else cross_sz
            cross_pos = (cross_sz - child_cross) / 2
        elif align == "end":
            existing_cross = fnum((child.get("box") or [0, 0, 0, 0])[2 if not horiz else 3])
            child_cross = existing_cross if existing_cross > 0 else cross_sz
            cross_pos = cross_sz - child_cross
        else:  # start
            existing_cross = fnum((child.get("box") or [0, 0, 0, 0])[2 if not horiz else 3])
            child_cross = existing_cross if existing_cross > 0 else cross_sz
            cross_pos = 0.0

        # Compute absolute box
        if horiz:
            abs_box = [content_x + cursor, content_y + cross_pos, main_sz, child_cross]
        else:
            abs_box = [content_x + cross_pos, content_y + cursor, child_cross, main_sz]

        child_copy = dict(child)
        child_copy["box"] = abs_box
        # Register resolved box in object_index for connector targeting
        if child_copy.get("id"):
            cid = str(child_copy["id"])
            cb = r.object_box(child_copy)
            cpts = r.object_ports(child_copy, cb)
            r.object_index[cid] = {"box": cb, "ports": cpts, "raw": child_copy}
        resolved.append(child_copy)
        cursor += main_sz + gap

    return resolved


def render_container(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render an auto-layout container.

    Currently supports `kind: stack` (vertical or horizontal). The
    `grid` and `row` kinds are reserved for v2.0 — the schema is
    forward-compatible.
    """
    layout = dict(obj.get("layout") or {})
    kind = str(layout.get("kind", "stack")).lower()

    if kind not in ("stack",):
        return (
            f"<g {attrs(r.group_attrs(obj))}>"
            + f'<!-- container kind="{esc(kind)}" not yet implemented --></g>'
        )

    container_b = box(obj.get("box", [0, 0, 0, 0]))
    children_raw = list(obj.get("children") or obj.get("objects") or [])
    resolved_children = _layout_stack(r, container_b, children_raw, layout)

    ga = r.group_attrs(obj)
    out = [f"<g {attrs(ga)}>"]
    for child in resolved_children:
        if isinstance(child, Mapping):
            try:
                out.append("  " + r.render_object(child).replace("\n", "\n  "))
            except Exception as exc:
                out.append(f"  <!-- container child error: {esc(str(exc))} -->")
    out.append("</g>")
    return "\n".join(out)


def eval_length(r: RendererContext, value: Any, total: float) -> float:
    """Resolve a length expression against a total magnitude.

    Accepts a number (returned as float), a percent string like
    `"40%"`, or a `calc(P% +/- N)` expression. Anything else is
    coerced via `fnum`.
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.endswith("%"):
        return total * fnum(s[:-1]) / 100.0
    m = re.fullmatch(r"calc\(\s*([0-9.]+)%\s*([-+])\s*([0-9.]+)\s*\)", s)
    if m:
        base = total * fnum(m.group(1)) / 100.0
        return base + fnum(m.group(3)) if m.group(2) == "+" else base - fnum(m.group(3))
    return fnum(s)


def offset_box(r: RendererContext, parent: Box, offset: Any) -> Box:
    """Resolve a 4-element offset spec against a parent box.

    Each element of `offset` is resolved through `eval_length` —
    elements 0 and 2 against the parent width, 1 and 3 against the
    parent height — producing the `(x, y, w, h)` of the inner frame.
    """
    x, y, w, h = parent
    return (
        x + r.eval_length(offset[0], w),
        y + r.eval_length(offset[1], h),
        r.eval_length(offset[2], w),
        r.eval_length(offset[3], h),
    )


def render_component(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Instantiate a component template from `r.component_defs`.

    `obj.component` selects a template; `obj.params` supplies
    parameter overrides; `obj.box` supplies the placement frame the
    template is positioned within (using `eval_length` for percent /
    `calc()` offsets).
    """
    comp_name = str(obj.get("component"))
    comp = r.component_defs.get(comp_name)
    if not isinstance(comp, Mapping):
        raise ValueError(f"unknown component '{comp_name}'")
    x, y, w, h = box(obj.get("box", [0, 0, 0, 0]))
    variant_name = obj.get("variant")
    variant: Mapping[str, Any] = (
        (comp.get("variants", {}) or {}).get(str(variant_name), {}) if variant_name else {}
    )
    fill = obj.get("fill", variant.get("fill", comp.get("fill", "none")))
    radius = fnum(obj.get("radius", deep_get(comp, ["geometry", "radius"], 0)), 0)
    st = None
    ss_name = obj.get("stroke_style") or variant.get("stroke_style") or comp.get("stroke_style")
    if ss_name:
        st = r.stroke_style(ss_name)
    elif isinstance(variant.get("stroke"), Mapping):
        st = r.stroke_style(inline=variant["stroke"])
    elif isinstance(comp.get("stroke"), Mapping):
        st = r.stroke_style(inline=comp["stroke"])
    out = [f"<g {attrs(r.group_attrs(obj, {'data-component': comp_name}))}>"]
    ra: dict[str, Any] = {
        "x": fmt(x),
        "y": fmt(y),
        "width": fmt(w),
        "height": fmt(h),
        "fill": r.fill_value(fill),
    }
    if radius:
        ra.update({"rx": fmt(radius), "ry": fmt(radius)})
    ra.update(r.stroke_attrs(st))
    out.append(f"<rect {attrs(ra)}/>")
    internal = comp.get("internal_layout", {}) or {}
    for slot in comp.get("slots", list(internal.keys())) or []:
        if slot not in obj:
            continue
        layout = internal.get(slot, {}) or {}
        slot_box = offset_box(r, (x, y, w, h), layout.get("box_offset", [0, 0, w, h]))
        out.append(
            _text_svg_helper(
                r,
                obj[slot],
                slot_box,
                r.text_style(layout.get("style") or comp.get("text_style")),
                extra={"data-slot": slot},
            )
        )
    out.append("</g>")
    return "\n".join(out)


def render_chip_row(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a horizontal row of pill-shaped chips.

    `obj.origin` sets the top-left corner; each item is laid out
    left-to-right with `obj.gap` pixels of spacing. Items may be
    plain strings (auto-sized) or mappings with explicit `width`.
    """
    chip = r.component_defs.get("chip", {}) or {}
    x, y = pt(obj.get("origin", [0, 0]))
    gap = fnum(obj.get("gap"), 0)
    height = fnum(obj.get("height"), 16)
    radius = fnum(deep_get(chip, ["geometry", "radius"], 0), 0)
    fill = obj.get("fill", chip.get("fill", "none"))
    stroke = obj.get("stroke", chip.get("stroke"))
    st = r.stroke_style(inline=stroke) if isinstance(stroke, Mapping) else None
    ts = r.text_style(obj.get("style", chip.get("text_style", "tiny")))
    out = [f"<g {attrs(r.group_attrs(obj, {'data-component': 'chip_row'}))}>"]
    cursor = x
    for item in obj.get("items", []) or []:
        label = str(item.get("text", "")) if isinstance(item, Mapping) else str(item)
        width = (
            fnum(item.get("width"), max(20, len(label) * 6 + 12))
            if isinstance(item, Mapping)
            else max(20.0, len(label) * 6.0 + 12.0)
        )
        ra: dict[str, Any] = {
            "x": fmt(cursor),
            "y": fmt(y),
            "width": fmt(width),
            "height": fmt(height),
            "fill": r.fill_value(fill),
            "rx": fmt(radius),
            "ry": fmt(radius),
        }
        ra.update(r.stroke_attrs(st))
        out.append(f"<rect {attrs(ra)}/>")
        out.append(_text_svg_helper(r, label, (cursor, y, width, height), ts))
        cursor += width + gap
    out.append("</g>")
    return "\n".join(out)


RENDERERS = {
    "group": render_group,
    "container": render_container,
    "component": render_component,
    "chip_row": render_chip_row,
}
