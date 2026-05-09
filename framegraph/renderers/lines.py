"""Line geometry renderers: line, polyline, path, connector, legend.

`connector` differs from `line` in that endpoints are resolved
through the document's object index (`r.endpoint`), so they can be
expressed as object references like `"my_box.east"`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framegraph._helpers import (
    attrs,
    box,
    fmt,
    pt,
)
from framegraph._types import RendererContext


def render_line_object(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a two-point `line` object via `r.line_svg`."""
    return r.line_svg(
        obj, [pt(obj.get("from", [0, 0])), pt(obj.get("to", [0, 0]))], obj.get("stroke_style")
    )


def render_polyline(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a multi-point `polyline` object as an SVG `<polyline>`."""
    return r.line_svg(
        obj,
        [pt(p) for p in (obj.get("points", []) or [])],
        obj.get("stroke_style"),
        force_poly=True,
    )


def render_path(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a raw SVG `path` object — the `d` attribute is taken verbatim."""
    st = r.stroke_style(obj.get("stroke_style"), obj.get("stroke"))
    a: dict[str, Any] = {"d": obj.get("d", ""), "fill": r.fill_value(obj.get("fill"), "none")}
    a.update(r.stroke_attrs(st, arrows=True))
    a.update(r.opacity_attrs(obj))
    a.update(r.effect_filter_attrs(obj))
    return f"<g {attrs(r.group_attrs(obj))}><path {attrs(a)}/></g>"


def render_connector(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `connector` — two endpoints joined by a routed path.

    `from` and `to` accept any form `r.endpoint` understands:
    object-id strings, `"id.port"`, `{object: …, side: …}`, raw
    coordinate pairs, etc. `route` selects the path style:
    `straight` (default), `orthogonal`, or `bezier`.

    Emits an inner label via `r.text_svg` when `obj.label` is a mapping.
    """
    start = r.endpoint(obj.get("from"))
    end = r.endpoint(obj.get("to"))
    route = obj.get("route", {}) or {"type": "straight"}
    rtype = str(route.get("type", "straight"))
    if rtype == "straight":
        points = [start, end]
    elif rtype in ("orthogonal", "polyline"):
        if route.get("points"):
            points = [pt(p) for p in route["points"]]
            if points and points[0] != start:
                points.insert(0, start)
            if points and points[-1] != end:
                points.append(end)
        else:
            mid_x = (start[0] + end[0]) / 2
            points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
    elif rtype == "bezier":
        c1 = pt(route.get("control1", route.get("c1", start)))
        c2 = pt(route.get("control2", route.get("c2", end)))
        d = f"M {fmt(start[0])} {fmt(start[1])} C {fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} {fmt(end[0])} {fmt(end[1])}"
        points = []
    else:
        raise ValueError(f"unsupported route type '{rtype}'")
    if rtype != "bezier":
        d = r.path_d(points)
    st = r.stroke_style(
        obj.get("stroke_style"),
        obj.get("stroke") if isinstance(obj.get("stroke"), Mapping) else None,
    )
    a: dict[str, Any] = {"d": d, "fill": "none"}
    a.update(r.stroke_attrs(st, arrows=True))
    # Connectors carry stroke only; skip fill_opacity emission.
    a.update(r.opacity_attrs(obj, has_fill=False))
    # Shadow / glow on connectors is uncommon but enables effects like
    # "highlighted critical path"; emitted here so it's available on
    # parity with rect/ellipse.
    a.update(r.effect_filter_attrs(obj))
    out = [f"<g {attrs(r.group_attrs(obj))}>", f"<path {attrs(a)}/>"]
    label = obj.get("label")
    if isinstance(label, Mapping):
        out.append(
            r.text_svg(
                label.get("text", ""),
                box(label.get("box", [0, 0, 0, 0])),
                r.text_style(label.get("style", "tiny")),
            )
        )
    out.append("</g>")
    return "\n".join(out)


def render_legend(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `legend` — a list of items, each a sample swatch + label.

    Each item's `sample` describes either a `line` (rendered via
    `r.line_svg`) or a `rect`/`rounded_rect` swatch (rendered via
    `r.render_rect`) followed by a label rendered via `r.text_svg`.
    """
    out = [f"<g {attrs(r.group_attrs(obj))}>"]
    for item in obj.get("items", []) or []:
        if not isinstance(item, Mapping):
            continue
        sample = item.get("sample", {}) or {}
        item_id = item.get("id", "legend_item")
        if sample.get("type") == "line":
            pseudo = {
                "id": str(item_id) + ".sample",
                "type": "legend_sample",
                "bind": item.get("bind"),
                "stroke_style": sample.get("stroke_style"),
            }
            out.append(
                r.line_svg(
                    pseudo,
                    [pt(sample.get("from", [0, 0])), pt(sample.get("to", [0, 0]))],
                    sample.get("stroke_style"),
                )
            )
        elif sample.get("type") in ("rounded_rect", "rect"):
            pseudo = {
                "id": str(item_id) + ".sample",
                "type": "legend_sample",
                "bind": item.get("bind"),
                "box": sample.get("box", [0, 0, 0, 0]),
                "radius": sample.get("radius", 0),
                "fill": sample.get("fill", "none"),
                "stroke": sample.get("stroke"),
            }
            out.append(r.render_rect(pseudo))
        label = item.get("label")
        if isinstance(label, Mapping):
            out.append(
                r.text_svg(
                    label.get("text", ""),
                    box(label.get("box", [0, 0, 0, 0])),
                    r.text_style(label.get("style", "legend")),
                )
            )
    out.append("</g>")
    return "\n".join(out)


RENDERERS = {
    "line": render_line_object,
    "polyline": render_polyline,
    "path": render_path,
    "connector": render_connector,
    "legend": render_legend,
}
