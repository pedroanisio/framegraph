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
from framegraph._routing import normalize_side, route_orthogonal, simplify_polyline
from framegraph._types import RendererContext


def _endpoint_side(ep: Any) -> str | None:
    """Extract the cardinal `side` declaration from a connector endpoint.

    Endpoints like ``{object: "x", side: "east"}`` or
    ``"x.east"`` advertise which way the line should leave/enter the
    object. Returns the canonical side or None when no side was
    declared (literal coordinate pairs, centred references, etc.).
    """
    if isinstance(ep, str):
        if "." in ep:
            return normalize_side(ep.split(".", 1)[1])
        return None
    if isinstance(ep, Mapping):
        return normalize_side(ep.get("side") or ep.get("port"))
    return None


def _collect_obstacle_boxes(
    r: RendererContext,
    skip_ids: set[str],
) -> list[tuple[float, float, float, float]]:
    """Gather classifier-grade obstacle boxes from the renderer's index.

    Only types that represent solid visual containers contribute
    (UML classifier boxes today; future shape kinds can extend the
    list). Decorative / packaging containers are excluded so the
    router doesn't refuse to enter the package band that hosts its
    own endpoints.
    """
    obstacle_types = {"uml.classifier_box"}
    out: list[tuple[float, float, float, float]] = []
    for oid, rec in r.object_index.items():
        if oid in skip_ids:
            continue
        raw = rec.get("raw") or {}
        if raw.get("type") not in obstacle_types:
            continue
        if raw.get("decorative") is True:
            continue
        b = rec.get("box")
        if b is None:
            continue
        out.append(tuple(float(v) for v in b))
    return out


def _endpoint_object_id(ep: Any) -> str | None:
    """Return the object id referenced by an endpoint, or None."""
    if isinstance(ep, str):
        return ep.split(".", 1)[0].strip() or None
    if isinstance(ep, Mapping):
        oid = ep.get("object")
        return None if oid is None else str(oid)
    return None


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
    conn_id = obj.get("id")
    start = r.endpoint(obj.get("from"), _connector_id=conn_id, _end_label="from")
    end = r.endpoint(obj.get("to"), _connector_id=conn_id, _end_label="to")
    from_ep = obj.get("from")
    to_ep = obj.get("to")
    route = obj.get("route", {}) or {}
    # Default routing: straight when no sides are declared; orthogonal
    # when at least one endpoint specifies a cardinal side. The
    # side-aware orthogonal router knows how to leave each box
    # perpendicular to its declared face and how to detour around
    # other classifier boxes — the legacy straight default would draw
    # through anything between the two anchors.
    if "type" not in route:
        route = dict(route)
        route["type"] = (
            "orthogonal"
            if (_endpoint_side(from_ep) or _endpoint_side(to_ep))
            else "straight"
        )
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
            start_side = _endpoint_side(from_ep)
            end_side = _endpoint_side(to_ep)
            if start_side or end_side:
                # Side-aware obstacle-avoiding routing. Route around
                # other classifier boxes; never around the connector's
                # own anchor objects.
                skip: set[str] = set()
                for ep in (from_ep, to_ep):
                    oid = _endpoint_object_id(ep)
                    if oid:
                        skip.add(oid)
                obstacles = _collect_obstacle_boxes(r, skip)
                stub = float(route.get("stub", 16.0))
                clearance = float(route.get("clearance", 4.0))
                points = route_orthogonal(
                    start,
                    end,
                    start_side=start_side,
                    end_side=end_side,
                    obstacles=obstacles,
                    stub=stub,
                    clearance=clearance,
                )
            else:
                # Legacy Z routing — preserved for endpoints declared
                # as raw coordinate pairs or centred references.
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
        # Simplify the polyline before emission. Collapses author-supplied
        # waypoints that produce micro-zigzags after stub addition (e.g.
        # `M A L B L A' L B' L C` where A/A' and B/B' differ by 4 px),
        # and merges collinear runs into single segments. Pure visual
        # polish — endpoints and bend semantics are preserved.
        points = simplify_polyline(points)
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
        # Box: explicit `box` wins; otherwise compute a position that
        # sits beside the path's longest segment so the text never
        # overprints the line. The path simplifier above means
        # `points` is the polyline that actually gets drawn.
        label_box = label.get("box")
        if label_box is None:
            label_box = _auto_label_box(points, label)
        out.append(
            r.text_svg(
                label.get("text", ""),
                box(label_box),
                r.text_style(label.get("style", "tiny")),
            )
        )
    out.append("</g>")
    return "\n".join(out)


def _auto_label_box(
    points: list[tuple[float, float]],
    label: Mapping[str, Any],
) -> list[float]:
    """Compute an [x, y, w, h] for a connector label that does not
    overlap the connector's own path.

    Strategy: pick the longest segment of the polyline. For a
    horizontal segment, place the label above it (or below if the
    caller passed `placement: below`); for a vertical segment, place
    the label to the right (or left). The offset is computed from
    the label's text-style font size so descenders/ascenders never
    cross the path. Falls back to the start point when the polyline
    is empty.
    """
    if len(points) < 2:
        x, y = (points[0] if points else (0.0, 0.0))
        return [float(x), float(y), 100.0, 16.0]

    # Find the longest segment.
    longest_idx = 0
    longest_len = 0.0
    for i in range(len(points) - 1):
        seg_len = abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1])
        if seg_len > longest_len:
            longest_len = seg_len
            longest_idx = i
    p0 = points[longest_idx]
    p1 = points[longest_idx + 1]

    # Best-effort font-size lookup; any sane default works.
    style = label.get("style") or {}
    font_size = float(style.get("size", 11)) if isinstance(style, Mapping) else 11.0
    placement = str(label.get("placement", "auto")).lower()
    horizontal = abs(p0[1] - p1[1]) < 0.5
    label_w = float(label.get("width", 200))
    label_h = float(label.get("height", font_size + 4))
    pad = max(6.0, font_size * 0.5)  # gap between line and label baseline

    if horizontal:
        cx = (p0[0] + p1[0]) / 2.0
        if placement == "below":
            y = p0[1] + pad
        else:
            y = p0[1] - pad - label_h
        return [cx - label_w / 2.0, y, label_w, label_h]
    # Vertical segment.
    cy = (p0[1] + p1[1]) / 2.0
    if placement == "left":
        x = p0[0] - pad - label_w
    else:
        x = p0[0] + pad
    return [x, cy - label_h / 2.0, label_w, label_h]


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
