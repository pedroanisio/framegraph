"""Data-viz primitives: `bar_chart` and `line_chart`.

Both share a common YAML surface — `data`, `style`, `box` — and
auto-place axis labels, optional grid lines, and an optional source
note. Single-series and multi-series inputs are accepted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framegraph._helpers import (
    Box,
    attrs,
    box,
    esc,
    fmt,
    fnum,
)
from framegraph._types import RendererContext


def _chart_area(r: RendererContext, b: Box, padding_raw: Any) -> Box:
    bx, by, bw, bh = b
    if isinstance(padding_raw, (list, tuple)) and len(padding_raw) == 4:
        pl, pt, pr, pb = [fnum(p) for p in padding_raw]
    elif isinstance(padding_raw, (list, tuple)) and len(padding_raw) == 2:
        pl = pr = fnum(padding_raw[0])
        pt = pb = fnum(padding_raw[1])
    else:
        pl = pt = pr = pb = fnum(padding_raw or 0)
    return bx + pl, by + pt, bw - pl - pr, bh - pt - pb


def _chart_color(r: RendererContext, v: Any, fallback: str = "#002060") -> str:
    if v is None:
        return fallback
    resolved = r.color(v, fallback)
    return resolved if resolved != "none" else fallback


def _svg_line(
    r: RendererContext,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str,
    width: str = "0.5",
    dash: Any = None,
) -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" stroke="{stroke}" stroke-width="{width}"{d}/>'


def _svg_text(
    r: RendererContext,
    x: float,
    y: float,
    text: str,
    size: float = 8,
    fill: str = "#AAAAAA",
    anchor: str = "middle",
    weight: int = 400,
    italic: bool = False,
) -> str:
    st = ' font-style="italic"' if italic else ""
    return f'<text x="{fmt(x)}" y="{fmt(y)}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{st}>{esc(text)}</text>'


def render_bar_chart(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `bar_chart` object.

    YAML surface: `box`, `data.{labels, values, series, note}`,
    `style.*`. Single-series and multi-series inputs are accepted.
    """
    b = box(obj.get("box", [0, 0, 100, 100]))
    data = obj.get("data") or {}
    style = obj.get("style") or {}

    px, py, pw, ph = _chart_area(r, b, style.get("padding", [40, 20, 16, 28]))

    # Series
    series_raw = data.get("series")
    if series_raw:
        series = [
            {
                "label": s.get("label", ""),
                "values": list(s.get("values", [])),
                "color": _chart_color(r, s.get("color"), "#002060"),
            }
            for s in series_raw
        ]
    else:
        col = _chart_color(r, style.get("bar_fill") or style.get("color"), "#002060")
        series = [{"label": "", "values": list(data.get("values", [])), "color": col}]

    labels = list(data.get("labels") or data.get("x_labels") or [])
    n_bars = max((len(s["values"]) for s in series), default=0)
    n_series = len(series)
    if n_bars == 0:
        return f"<g {attrs(r.group_attrs(obj))}><!-- bar_chart: no data --></g>"
    while len(labels) < n_bars:
        labels.append(str(len(labels) + 1))

    bar_width = min(0.95, max(0.1, fnum(style.get("bar_width"), 0.72)))
    show_vals = bool(style.get("value_labels", True))
    grid_col = style.get("grid_color", "#EEEEEE")
    axis_col = _chart_color(r, style.get("axis_color"), "#AAAAAA")
    baseline = fnum(style.get("baseline"), 0)
    note = str(data.get("note") or "")

    all_vals = [v for s in series for v in s["values"]]
    vmin = min(min(all_vals), baseline)
    vmax = max(max(all_vals), baseline)
    if vmax == vmin:
        vmax = vmin + 1
    vrange = vmax - vmin

    def vy(val: Any) -> float:
        return float(py + ph - (fnum(val) - vmin) / vrange * ph)

    baseline_y = vy(baseline)
    slot_w = pw / n_bars
    group_w = slot_w * bar_width
    bar_w = group_w / n_series

    out = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Grid
    for gi in range(5):
        out.append(_svg_line(r, px, py + ph * gi / 4, px + pw, py + ph * gi / 4, grid_col))
    # Axes
    out.append(_svg_line(r, px, baseline_y, px + pw, baseline_y, axis_col, "0.8"))
    out.append(_svg_line(r, px, py, px, py + ph, axis_col, "0.8"))
    # Y-axis labels
    for gi in range(5):
        gval = vmin + vrange * (4 - gi) / 4
        gy = py + ph * gi / 4
        lbl = str(int(round(gval))) if abs(gval - round(gval)) < 0.01 else f"{gval:.1f}"
        out.append(_svg_text(r, px - 4, gy + 3, lbl, fill=axis_col, anchor="end"))

    # Bars
    for bi in range(n_bars):
        slot_x = px + bi * slot_w
        group_x = slot_x + (slot_w - group_w) / 2
        for si, ser in enumerate(series):
            if bi >= len(ser["values"]):
                continue
            val = fnum(ser["values"][bi])
            bar_x = group_x + si * bar_w
            bar_y = min(vy(val), baseline_y)
            bar_h = max(0.5, abs(vy(val) - baseline_y))
            out.append(
                f'<rect x="{fmt(bar_x)}" y="{fmt(bar_y)}" width="{fmt(bar_w)}" height="{fmt(bar_h)}" fill="{ser["color"]}"/>'
            )
            if show_vals:
                lbl = str(int(round(val))) if abs(val - round(val)) < 0.01 else f"{val:.1f}"
                out.append(
                    _svg_text(
                        r, bar_x + bar_w / 2, bar_y - 3, lbl, size=9, fill=ser["color"], weight=700
                    )
                )
        # X label
        if bi < len(labels):
            out.append(
                _svg_text(r, slot_x + slot_w / 2, baseline_y + 14, str(labels[bi]), fill=axis_col)
            )

    # Multi-series legend
    if n_series > 1:
        for si, ser in enumerate(series):
            ly = py + 4 + si * 14
            out.append(
                f'<rect x="{fmt(px + pw - 62)}" y="{fmt(ly)}" width="10" height="8" fill="{ser["color"]}"/>'
            )
            out.append(
                _svg_text(r, px + pw - 48, ly + 7, ser["label"], fill=axis_col, anchor="start")
            )

    # Note
    if note:
        bx2, by2, bw2, bh2 = b
        out.append(
            _svg_text(r, bx2, by2 + bh2 - 2, note, fill=axis_col, anchor="start", italic=True)
        )

    out.append("</g>")
    return "\n".join(out)


def render_line_chart(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `line_chart` object.

    YAML surface: `box`, `data.{series, x_labels, note}`, `style.*`.
    Multi-series with optional point markers and a positioned legend.
    """
    b = box(obj.get("box", [0, 0, 100, 100]))
    data = obj.get("data") or {}
    style = obj.get("style") or {}

    px, py, pw, ph = _chart_area(r, b, style.get("padding", [40, 16, 16, 28]))

    series_raw = data.get("series") or []
    if not series_raw:
        return f"<g {attrs(r.group_attrs(obj))}><!-- line_chart: no series --></g>"

    series = [
        {
            "label": s.get("label", ""),
            "values": [fnum(v) for v in s.get("values", [])],
            "color": _chart_color(r, s.get("color"), "#002060"),
            "dash": bool(s.get("dash", False)),
        }
        for s in series_raw
    ]

    x_labels = list(data.get("x_labels") or data.get("labels") or [])
    n_pts = max((len(s["values"]) for s in series), default=0)
    if n_pts < 2:
        return f"<g {attrs(r.group_attrs(obj))}><!-- line_chart: need >=2 points --></g>"
    while len(x_labels) < n_pts:
        x_labels.append(str(len(x_labels) + 1))

    grid_col = style.get("grid_color", "#EEEEEE")
    axis_col = _chart_color(r, style.get("axis_color"), "#AAAAAA")
    sw = fnum(style.get("stroke_width"), 1.5)
    pr_ = fnum(style.get("point_radius"), 0)
    show_legend = bool(style.get("show_legend", True))
    note = str(data.get("note") or "")

    all_vals = [v for s in series for v in s["values"]]
    vmin = min(all_vals)
    vmax = max(all_vals)
    if vmax == vmin:
        vmax = vmin + 1
    vrange = vmax - vmin

    def vx(i: float) -> float:
        return float(px + i * pw / (n_pts - 1))

    def vy(v: float) -> float:
        return float(py + ph - (v - vmin) / vrange * ph)

    out = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Grid
    for gi in range(5):
        out.append(_svg_line(r, px, py + ph * gi / 4, px + pw, py + ph * gi / 4, grid_col))
    # Axes
    out.append(_svg_line(r, px, py + ph, px + pw, py + ph, axis_col, "0.8"))
    out.append(_svg_line(r, px, py, px, py + ph, axis_col, "0.8"))
    # Y labels
    for gi in range(5):
        gval = vmin + vrange * (4 - gi) / 4
        gy = py + ph * gi / 4
        lbl = str(int(round(gval))) if abs(gval - round(gval)) < 0.01 else f"{gval:.1f}"
        out.append(_svg_text(r, px - 4, gy + 3, lbl, fill=axis_col, anchor="end"))
    # X labels
    for i, lbl in enumerate(x_labels):
        out.append(_svg_text(r, vx(i), py + ph + 14, str(lbl), fill=axis_col))

    # Lines
    for ser in series:
        vals = ser["values"]
        pts = " ".join(f"{fmt(vx(i))},{fmt(vy(vals[i]))}" for i in range(len(vals)))
        dash = ' stroke-dasharray="5,3"' if ser["dash"] else ""
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{ser["color"]}" stroke-width="{sw}" stroke-linejoin="round"{dash}/>'
        )
        if pr_ > 0:
            for i in range(len(vals)):
                out.append(
                    f'<circle cx="{fmt(vx(i))}" cy="{fmt(vy(vals[i]))}" r="{fmt(pr_)}" fill="{ser["color"]}"/>'
                )

    # Legend
    if show_legend and any(s["label"] for s in series):
        for si, ser in enumerate(series):
            if not ser["label"]:
                continue
            ly = py + 8 + si * 16
            out.append(
                _svg_line(r, px + pw - 42, ly + 4, px + pw - 28, ly + 4, ser["color"], str(sw))
            )
            out.append(
                _svg_text(r, px + pw - 24, ly + 7, ser["label"], fill=axis_col, anchor="start")
            )

    if note:
        bx2, by2, bw2, bh2 = b
        out.append(
            _svg_text(r, bx2, by2 + bh2 - 2, note, fill=axis_col, anchor="start", italic=True)
        )

    out.append("</g>")
    return "\n".join(out)


RENDERERS = {
    "bar_chart": render_bar_chart,
    "line_chart": render_line_chart,
}
