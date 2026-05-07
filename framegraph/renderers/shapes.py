"""Shape primitives: rect, ellipse.

Both renderers honour the optional `outer_ring` schema for halo /
ring effects.

Exported via the `RENDERERS` registry consumed by
`FrameGraphRenderer._register_all`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from framegraph._helpers import (
    attrs,
    box,
    fmt,
    fnum,
    pt,
)
from framegraph._types import RendererContext


def render_rect(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `rect` object as an SVG `<g><rect/></g>`.

    Recognized keys: `box` (required), `radius`, `fill`, `stroke`,
    `stroke_style`, `outer_ring`, `id`, `class`, `bind`,
    `decorative`, `opacity`.

    When `outer_ring` is set, two stacked rectangles are emitted; the
    ring is drawn first so the inner fill paints over the ring's
    interior, leaving only the ring band visible.
    """
    x, y, w, h = box(obj.get("box", [0, 0, 0, 0]))
    radius = fnum(obj.get("radius"), 0)
    a: dict[str, Any] = {
        "x": fmt(x),
        "y": fmt(y),
        "width": fmt(w),
        "height": fmt(h),
        "fill": r.fill_value(obj.get("fill"), "none"),
    }
    if radius:
        a.update({"rx": fmt(radius), "ry": fmt(radius)})
    a.update(r.stroke_attrs(r.rect_stroke(obj)))
    # ── HD effect filter (shadow / glow) — attached to the primary
    # geometry only; outer_ring trim is intentionally unfiltered to
    # avoid double-shadow on composite shapes.
    a.update(r.effect_filter_attrs(obj))

    # ── outer_ring: concentric rect rendered BEFORE fill covers interior ──
    # Shares schema with ellipse outer_ring; adds gap field (default 4px).
    # The ring rect expands by (gap + width/2) on all sides so its inner
    # edge sits gap px away from the shape edge.
    ring = obj.get("outer_ring")
    if not ring:
        return f"<g {attrs(r.group_attrs(obj))}><rect {attrs(a)}/></g>"

    rc = r.color(ring.get("color"), "#000000")
    rw = fnum(ring.get("width"), 2)
    gap = fnum(ring.get("gap"), 4)
    expand = gap + rw / 2  # outset from shape edge to ring centre

    ra: dict[str, Any] = {
        "x": fmt(x - expand),
        "y": fmt(y - expand),
        "width": fmt(w + 2 * expand),
        "height": fmt(h + 2 * expand),
        "fill": "none",
        "stroke": rc,
        "stroke-width": fmt(rw),
    }
    # Corner radius: grow proportionally so the ring follows the rect corner.
    # Only apply when the inner rect is rounded — a square inner rect must
    # not get rounded outer corners.
    if radius:
        ra["rx"] = fmt(radius + expand)
        ra["ry"] = fmt(radius + expand)

    dash = ring.get("dash")
    if dash:
        if isinstance(dash, Sequence) and not isinstance(dash, str):
            ra["stroke-dasharray"] = " ".join(fmt(d) for d in dash)
        else:
            ra["stroke-dasharray"] = str(dash)

    opacity = ring.get("opacity")
    if opacity is not None:
        ra["opacity"] = fmt(opacity)

    out = [
        f"<g {attrs(r.group_attrs(obj))}>",
        f"  <rect {attrs(ra)}/>",
        f"  <rect {attrs(a)}/>",
        "</g>",
    ]
    return "\n".join(out)


def render_ellipse(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render an `ellipse` object as an SVG `<g><ellipse/></g>`.

    Geometry: either `box` (the ellipse is inscribed in it) or
    `center` + `rx` + `ry`. Like `rect`, supports the `outer_ring`
    schema.
    """
    if "box" in obj:
        x, y, w, h = box(obj["box"])
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
    else:
        cx, cy = pt(obj.get("center", [0, 0]))
        rx = fnum(obj.get("rx"), 0)
        ry = fnum(obj.get("ry"), rx)
    a: dict[str, Any] = {
        "cx": fmt(cx),
        "cy": fmt(cy),
        "rx": fmt(rx),
        "ry": fmt(ry),
        "fill": r.fill_value(obj.get("fill"), "none"),  # v3: fill_value
    }
    a.update(r.stroke_attrs(r.rect_stroke(obj)))
    a.update(r.effect_filter_attrs(obj))

    out = [f"<g {attrs(r.group_attrs(obj))}>"]

    # ── v3: outer_ring — rendered BEFORE main ellipse so fill covers interior ──
    ring = obj.get("outer_ring")
    if ring:
        rc = r.color(ring.get("color"), "#000000")
        rw = fnum(ring.get("width"), 2)
        ro = fnum(ring.get("offset"), 4)
        ra: dict[str, Any] = {
            "cx": fmt(cx),
            "cy": fmt(cy),
            "rx": fmt(rx + ro + rw / 2),
            "ry": fmt(ry + ro + rw / 2),
            "fill": "none",
            "stroke": rc,
            "stroke-width": fmt(rw),
        }
        dash = ring.get("dash")
        if dash:
            if isinstance(dash, Sequence) and not isinstance(dash, str):
                ra["stroke-dasharray"] = " ".join(fmt(d) for d in dash)
            else:
                ra["stroke-dasharray"] = str(dash)
        out.append(f"  <ellipse {attrs(ra)}/>")

    out.append(f"  <ellipse {attrs(a)}/>")
    out.append("</g>")
    return "\n".join(out)


# ── v3: icon object ────────────────────────────────────────────────


RENDERERS = {
    "rect": render_rect,
    "ellipse": render_ellipse,
}
