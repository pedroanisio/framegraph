"""Tabular grid: `type: table`.

Renders a structured grid of cells with optional header row, optional
zebra-striping, and per-column width hints. Designed as the
"presentation table" primitive — most decks reinvent this with hand-
positioned rect+text constellations.

YAML surface
------------
Required:
    type:    table
    box:     [x, y, w, h]
    rows:    list of row lists; each cell is a string or mapping

Optional:
    columns:        list of column-width hints (px number, "%" string, or null for auto)
    header:         list of header-cell strings/mappings; renders as a stylized first row
    row_height:     uniform px (default: distribute remaining height evenly)
    header_height:  uniform px for the header row (default: row_height)
    zebra:          alternate row backgrounds when true
    cell_padding:   inset for cell content (number or [hpad, vpad]); default 8
    style:
        border_color:        token or hex (default: chrome_line equivalent)
        border_width:        px (default: 0.5)
        header_fill:         token or hex (default: panel)
        header_text_style:   text-style id (default: card_label-equivalent inline)
        body_text_style:     text-style id (default: body-equivalent inline)
        zebra_fill:           alt-row fill (default: subtle warm tint)
        cell_align:          left | center | right (default: left)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framegraph._helpers import attrs, box, esc, fmt, fnum
from framegraph._types import RendererContext


def _resolve_widths(cols: list[Any] | None, n_cols: int, total: float) -> list[float]:
    """Resolve column-width hints to absolute pixel widths.

    Args:
        cols: Per-column width hints. Each element is one of:
            number → fixed px width, string ending `%` → fraction of
            total, anything else (None / 0 / "auto") → auto-distributed.
        n_cols: Number of columns to produce widths for.
        total: Total horizontal space to distribute across.

    Returns:
        A list of `n_cols` non-negative floats summing to `total`.
    """
    if cols is None:
        cols = [None] * n_cols
    # Pad / truncate to n_cols
    cols = list(cols)
    while len(cols) < n_cols:
        cols.append(None)
    cols = cols[:n_cols]

    widths: list[float | None] = []
    consumed = 0.0
    auto_indices: list[int] = []
    for i, c in enumerate(cols):
        if c is None or c == 0 or c == "auto":
            widths.append(None)
            auto_indices.append(i)
        elif isinstance(c, str) and c.endswith("%"):
            try:
                w = total * float(c[:-1]) / 100.0
            except ValueError:
                w = 0.0
            widths.append(w)
            consumed += w
        else:
            w = fnum(c)
            widths.append(w)
            consumed += w

    remaining = max(0.0, total - consumed)
    auto_width = remaining / len(auto_indices) if auto_indices else 0.0
    for i in auto_indices:
        widths[i] = auto_width

    return [float(w or 0.0) for w in widths]


def _normalize_cell(cell: Any) -> dict[str, Any]:
    """Normalize a cell to a dict with `text` (and optional overrides)."""
    if isinstance(cell, Mapping):
        return dict(cell)
    return {"text": "" if cell is None else str(cell)}


def _resolve_text_style(r: RendererContext, ref: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Resolve a style reference (id or inline mapping) with a fallback.

    Falls back to `fallback` when `ref` is None. Returns a fully-
    resolved style dict (font + color already token-resolved).
    """
    if ref is None:
        return r.text_style(fallback)
    return r.text_style(ref)


def render_table(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `table` object — header + rows of text cells in a grid.

    Cells are right-padded if their declared column count is short of
    `len(columns)`. Empty `rows: []` renders only the header. Empty
    `rows: []` and no `header:` renders an empty bordered frame.
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 0, 0]))
    style = obj.get("style") or {}
    rows = obj.get("rows") or []
    header = obj.get("header")
    columns = obj.get("columns")

    # Determine column count: explicit `columns` declaration wins, else
    # the widest row (or header) sets it.
    if columns is not None:
        n_cols = len(columns)
    else:
        widths_from_rows = max((len(r_) for r_ in rows), default=0)
        widths_from_header = len(header) if header else 0
        n_cols = max(widths_from_rows, widths_from_header, 1)

    col_widths = _resolve_widths(columns, n_cols, bw)

    # Padding — single number or [hpad, vpad]
    pad_raw = obj.get("cell_padding", 8)
    if isinstance(pad_raw, (list, tuple)) and len(pad_raw) == 2:
        h_pad = fnum(pad_raw[0])
        v_pad = fnum(pad_raw[1])
    else:
        h_pad = v_pad = fnum(pad_raw)

    # Row heights — uniform, with optional override for the header.
    #
    # When no explicit `row_height` is given, the row height auto-sizes
    # to a content-driven natural value (≈ body font-size × 2.5) and
    # only stretches to fill `bh` when that natural value would leave
    # the rows shorter than the available space *and* there's a header.
    # This avoids the failure mode where 3 rows of short text get
    # 110px each on a tall card. Authors who want the "fill the box"
    # behavior can pass `row_height: <px>` explicitly.
    n_body_rows = len(rows)
    has_header = bool(header)
    row_h_explicit = obj.get("row_height")
    header_h_explicit = obj.get("header_height")

    # Row height is uniform when explicit; otherwise *per-row* heights
    # are derived from the measured number of wrapped lines each row
    # needs. This keeps short rows tight and grows tall rows enough
    # to contain wrapped content without colliding with the next row.
    # The renderer's `_str_width` is the wrap oracle; same 8% safety
    # margin as `_emit_cell_text`.
    body_size_default = fnum(
        (style.get("body_text_style") or {}).get("size")
        if isinstance(style.get("body_text_style"), Mapping)
        else None,
        11,
    )
    body_line_h = body_size_default * 1.3
    header_size_default = fnum(
        (style.get("header_text_style") or {}).get("size")
        if isinstance(style.get("header_text_style"), Mapping)
        else None,
        12,
    )
    header_line_h = header_size_default * 1.3

    def _measure_lines(text: str, font_size: float, col_w: float) -> int:
        """Count wrapped lines a cell's text needs at the given column width."""
        if not text:
            return 1
        avail = max(1.0, col_w - 2 * h_pad) * 0.92
        n = 0
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                n += 1
                continue
            line = ""
            for w in words:
                test = (line + " " + w).strip()
                if line and r._str_width(test, font_size, False) > avail:
                    n += 1
                    line = w
                else:
                    line = test
            if line:
                n += 1
        return max(1, n)

    def _row_height(cells: list[Any], font_size: float, line_h: float) -> float:
        max_lines = 1
        for i in range(n_cols):
            if i < len(cells):
                cell = _normalize_cell(cells[i])
                cell_text = str(cell.get("text", ""))
                max_lines = max(
                    max_lines, _measure_lines(cell_text, font_size, col_widths[i])
                )
        return max_lines * line_h + 2 * v_pad

    row_h_explicit = obj.get("row_height")
    header_h_explicit = obj.get("header_height")

    if row_h_explicit is not None:
        # Author-pinned uniform row height.
        uniform_h = fnum(row_h_explicit)
        body_row_heights = [uniform_h] * n_body_rows
    else:
        body_row_heights = [
            _row_height(row, body_size_default, body_line_h) for row in rows
        ]
    if header_h_explicit is not None:
        header_h = fnum(header_h_explicit)
    elif has_header:
        header_h = _row_height(list(header), header_size_default, header_line_h)
    else:
        header_h = 0.0

    row_h = (
        sum(body_row_heights) / len(body_row_heights) if body_row_heights else 0.0
    )

    # Style defaults
    border_color = r.color(style.get("border_color", "#D0CEC8"), "#D0CEC8")
    border_width = fnum(style.get("border_width"), 0.5)
    header_fill = r.fill_value(style.get("header_fill", "#F0EDE6"), "#F0EDE6")
    body_fill_default = r.fill_value(style.get("body_fill", "none"), "none")
    zebra_on = bool(obj.get("zebra"))
    zebra_fill = r.fill_value(style.get("zebra_fill", "#F7F4EE"), "#F7F4EE")
    cell_align = str(style.get("cell_align", "left"))

    header_text_style = _resolve_text_style(
        r,
        style.get("header_text_style"),
        {"size": 10, "weight": 700, "color": "#1A1A1A", "align": cell_align},
    )
    body_text_style = _resolve_text_style(
        r,
        style.get("body_text_style"),
        {"size": 11, "weight": 400, "color": "#1A1A1A", "align": cell_align},
    )

    # Render is faithful: rows draw at the styles the planner gave
    # us. No shrink, no truncation, no constraint reporting from
    # here. The layout planner is the sole decision-maker for
    # geometry and typography scale.

    out = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Track the running y cursor so cells, fills, and borders all align.
    y = by

    # ── Header row ──
    if has_header:
        # Background
        out.append(
            f'<rect x="{fmt(bx)}" y="{fmt(y)}" width="{fmt(bw)}" height="{fmt(header_h)}" '
            f'fill="{header_fill}"/>'
        )
        # Cell texts
        x_cursor = bx
        for i in range(n_cols):
            cw = col_widths[i]
            if i < len(header):
                cell = _normalize_cell(header[i])
                _emit_cell_text(
                    out,
                    cell,
                    x_cursor,
                    y,
                    cw,
                    header_h,
                    h_pad,
                    v_pad,
                    header_text_style,
                    estimate_width=r._str_width,
                )
            x_cursor += cw
        y += header_h

    # ── Body rows ──
    # Render every row the author declared. Auto-shrink above
    # already attempted to fit content via typography compression;
    # if rows still overflow the box, the constraint report has
    # been emitted and the operator can decide. The render itself
    # is faithful — no row is dropped.
    for row_idx, row in enumerate(rows):
        rh = body_row_heights[row_idx] if row_idx < len(body_row_heights) else row_h
        row_fill = zebra_fill if (zebra_on and row_idx % 2 == 1) else body_fill_default
        if row_fill and row_fill != "none":
            out.append(
                f'<rect x="{fmt(bx)}" y="{fmt(y)}" width="{fmt(bw)}" height="{fmt(rh)}" '
                f'fill="{row_fill}"/>'
            )
        x_cursor = bx
        for i in range(n_cols):
            cw = col_widths[i]
            if i < len(row):
                cell = _normalize_cell(row[i])
                _emit_cell_text(
                    out,
                    cell,
                    x_cursor,
                    y,
                    cw,
                    rh,
                    h_pad,
                    v_pad,
                    body_text_style,
                    estimate_width=r._str_width,
                )
            x_cursor += cw
        y += rh

    # ── Borders ──
    # Outer frame
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(y - by)}" '
        f'fill="none" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )
    # Header rule
    if has_header:
        ry = by + header_h
        out.append(
            f'<line x1="{fmt(bx)}" y1="{fmt(ry)}" x2="{fmt(bx + bw)}" y2="{fmt(ry)}" '
            f'stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
        )
    # Vertical column separators
    x_cursor = bx
    for i in range(n_cols - 1):
        x_cursor += col_widths[i]
        out.append(
            f'<line x1="{fmt(x_cursor)}" y1="{fmt(by)}" x2="{fmt(x_cursor)}" y2="{fmt(y)}" '
            f'stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
        )

    out.append("</g>")
    return "\n".join(out)


def _emit_cell_text(
    out: list[str],
    cell: dict[str, Any],
    x: float,
    y: float,
    cw: float,
    rh: float,
    h_pad: float,
    v_pad: float,
    base_style: dict[str, Any],
    estimate_width: Any = None,
) -> None:
    """Emit a single cell's `<text>` element honouring per-cell overrides.

    Per-cell `style` mapping merges over `base_style`. `align` may be
    `left` / `center` / `right`. Long text wraps to the cell's
    available width and the text block is vertically centered.
    """
    text = str(cell.get("text", ""))
    cell_style = dict(base_style)
    if isinstance(cell.get("style"), Mapping):
        cell_style.update(dict(cell["style"]))
    if cell.get("align"):
        cell_style["align"] = cell["align"]
    if cell.get("color"):
        cell_style["color"] = cell["color"]

    align = str(cell_style.get("align", "left"))
    if align == "center":
        tx = x + cw / 2
        anchor = "middle"
    elif align == "right":
        tx = x + cw - h_pad
        anchor = "end"
    else:
        tx = x + h_pad
        anchor = "start"

    size = fnum(cell_style.get("size"), 11)
    weight = str(cell_style.get("weight", 400))
    bold = weight in ("700", "bold", "bolder")
    line_h = fnum(cell_style.get("line_height"), size * 1.3)
    avail_w = max(1.0, cw - 2 * h_pad)

    # Wrap text into lines that fit `avail_w`. The width estimator
    # tends to undercount; trim 8% off avail_w as a safety margin so
    # rendered glyphs stay clear of the next column's separator.
    safe_w = avail_w * 0.92
    lines: list[str] = []
    if estimate_width is not None and text:
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            line = ""
            for w in words:
                test = (line + " " + w).strip()
                if line and estimate_width(test, size, bold) > safe_w:
                    lines.append(line)
                    line = w
                else:
                    line = test
            if line:
                lines.append(line)
    else:
        lines = [text]

    # Vertical centering: stack of N lines, total height = N * line_h,
    # first baseline = y + (rh - N * line_h) / 2 + size * 0.78.
    n = max(1, len(lines))
    block_h = n * line_h
    baseline_y = y + max(v_pad, (rh - block_h) / 2) + size * 0.78

    a_base: dict[str, Any] = {
        "font-family": str(cell_style.get("font", "Helvetica, Arial, sans-serif")),
        "font-size": fmt(size),
        "font-weight": weight,
        "fill": str(cell_style.get("color", "#1A1A1A")),
        "text-anchor": anchor,
    }
    if cell_style.get("italic"):
        a_base["font-style"] = "italic"

    for i, ln in enumerate(lines):
        a = dict(a_base)
        a["x"] = fmt(tx)
        a["y"] = fmt(baseline_y + i * line_h)
        out.append(f"<text {attrs(a)}>{esc(ln)}</text>")


RENDERERS = {
    "table": render_table,
}
