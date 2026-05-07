"""Text rendering: `text` (single style or rich-text spans) and `bullet_list`.

`text_svg` and `spans_svg` are also imported by the layout module to
draw labels inside container/component decorations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framegraph._helpers import (
    Box,
    _expand_lorem,
    attrs,
    box,
    deep_get,
    esc,
    fmt,
    fnum,
    sid,
)
from framegraph._types import RendererContext


def render_text_object(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `text` object.

    Two modes:

    - **Plain text** (`text` key) — single resolved text style applied
      to one string; supports `wrap` and auto-shrink-to-fit.
    - **Rich spans** (`spans` key) — a list of inline span mappings,
      each with optional per-span `weight`, `color`, `italic`,
      `size` overrides; rendered through `spans_svg`.
    """
    b = box(obj.get("box", [0, 0, 0, 0]))
    rot = obj.get("rotation")
    base_style = r.text_style(obj.get("style"))
    spans_raw = obj.get("spans")  # list of {text, weight?, color?, italic?}
    if spans_raw:
        text_node = spans_svg(r, spans_raw, b, base_style, rotation=rot)
    else:
        raw = obj.get("text", obj.get("value", ""))
        text_node = text_svg(r, _expand_lorem(raw), b, base_style, rotation=rot)
    if rot is not None:
        x, y, w, h = b
        text_node = (
            f'<g transform="rotate({fmt(rot)} {fmt(x + w / 2)} {fmt(y + h / 2)})">{text_node}</g>'
        )

    # overflow: clip — wrap in a clipPath enforcing the declared box
    if str(base_style.get("overflow", "visible")).lower() == "clip" and b:
        cx2, cy2, cw2, ch2 = b
        clip_id = sid(f"clip_{obj.get('id', 't')}")
        clip_def = (
            f'<defs><clipPath id="{clip_id}">'
            f'<rect x="{fmt(cx2)}" y="{fmt(cy2)}" width="{fmt(cw2)}" height="{fmt(ch2)}"/>'
            f"</clipPath></defs>"
        )
        ga2 = dict(r.group_attrs(obj))
        ga2["clip-path"] = f"url(#{clip_id})"
        return f"{clip_def}<g {attrs(ga2)}>{text_node}</g>"

    return f"<g {attrs(r.group_attrs(obj))}>{text_node}</g>"


def text_svg(
    r: RendererContext,
    content: Any,
    b: Box,
    style: Mapping[str, Any],
    *,
    rotation: Any = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Render plain text laid out inside a box at the given style.

    Args:
        r: The active renderer context (used for token resolution
            and width estimation).
        content: The text payload. Strings starting with `lorem` /
            `lorem:N` are expanded to filler.
        b: The bounding box `(x, y, w, h)` the text must fit inside.
            Affects horizontal/vertical alignment and the auto-shrink
            decision when `style.wrap` is True.
        style: A pre-resolved text style mapping (output of
            `r.text_style`).
        rotation: Optional `[degrees, cx, cy]` tuple to rotate the
            emitted `<text>` block around `(cx, cy)`.
        extra: Extra attributes merged into the `<text>` element
            (e.g. `text-decoration`).

    Returns:
        SVG fragment containing one `<text>` element with one or more
        `<tspan>` children.

    """
    x, y, w, h = b
    raw_text = str(content) if content is not None else ""

    # ── weight-aware char-width via per-class tables ───────────────────
    weight = str(style.get("weight", 400))
    bold = weight in ("700", "bold", "bolder")
    # ─────────────────────────────────────────────────────────────────

    fs = fnum(style.get("size"), 12)
    min_fs = fnum(deep_get(r.scene, ["rendering_contract", "text", "min_font_size"], 7), 7)
    lh = fnum(style.get("line_height"), fs * 1.2)
    align = str(style.get("align", "left")).lower()
    v_align = str(style.get("v_align", "middle")).lower()  # NEW: top|middle|bottom
    do_wrap = bool(style.get("wrap", False))  # NEW: word-wrap flag

    ew = h if rotation is not None and 80 <= abs(fnum(rotation)) % 180 <= 100 else w

    # ── word-wrap ────────────────────────────────────────────────────
    def wrap_text(text: str, font_size: float) -> list:
        """Break text into lines that fit within ew pixels."""
        result = []
        for para in text.split("\n"):
            words = para.split()
            if not words:
                result.append("")
                continue
            line = ""
            for word in words:
                test = (line + " " + word).strip()
                if ew > 0 and r._str_width(test, font_size, bold) > ew and line:
                    result.append(line)
                    line = word
                else:
                    line = test
            if line:
                result.append(line)
        return result if result else [""]

    # ── shrink font to fit longest line ──────────────────────────────
    if do_wrap:
        lines = wrap_text(raw_text, fs)
        # After wrapping, longest line might still exceed box → shrink only if needed
        if ew > 0 and r._str_width(lines[lines.index(max(lines, key=len))], fs, bold) > ew:
            old = fs
            _lw = r._str_width(max(lines, key=len), fs, bold)
            fs = max(min_fs, fs * ew / max(_lw, 1))
            lh = max(fs * 1.05, lh * fs / max(old, 1))
        # Rewrap at new font size if it shrank
        lines = wrap_text(raw_text, fs)
    else:
        lines = raw_text.split("\n")
        if ew > 0 and r._str_width(lines[lines.index(max(lines, key=len))], fs, bold) > ew:
            old = fs
            _lw = r._str_width(max(lines, key=len), fs, bold)
            fs = max(min_fs, fs * ew / max(_lw, 1))
            lh = max(fs * 1.05, lh * fs / max(old, 1))

    # ── vertical alignment ───────────────────────────────────────────
    block_h = fs + max(0, len(lines) - 1) * lh
    if v_align == "top":
        baseline = y + fs * 0.78
    elif v_align == "bottom":
        baseline = y + h - block_h + fs * 0.78
    else:  # middle (default)
        baseline = y + (h - block_h) / 2 + fs * 0.78

    # ── anchor / x ───────────────────────────────────────────────────
    tx, anchor = (
        (x + w / 2, "middle")
        if align == "center"
        else (x + w, "end")
        if align == "right"
        else (x, "start")
    )

    a = {
        "x": fmt(tx),
        "y": fmt(baseline),
        "font-family": style.get("font"),
        "font-size": fmt(fs),
        "font-weight": style.get("weight", 400),
        "fill": style.get("color"),
        "text-anchor": anchor,
    }
    if style.get("italic"):
        a["font-style"] = "italic"
    if extra:
        a.update(extra)
    spans = "".join(
        f'<tspan x="{fmt(tx)}" dy="{fmt(0 if i == 0 else lh)}">{esc(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return f"<text {attrs(a)}>{spans}</text>"


def spans_svg(
    r: RendererContext,
    spans_raw: list,
    b: Box,
    base_style: dict,
    *,
    rotation: Any = None,
) -> str:
    """Render a text object built from inline styled spans.

    Each span: {text: str, weight?: int|str, color?: str, italic?: bool, size?: float}
    Base style provides font, size, align, v_align, wrap, line_height.

    Strategy:
      1. Collect all span texts with their per-character metrics.
      2. Word-wrap the concatenated text, preserving span boundaries.
      3. Emit one SVG <text> element; each line is a <tspan dy=lh> containing
         per-span <tspan> elements with attribute overrides.
    """
    x, y, w, h = b
    fs = fnum(base_style.get("size"), 12)
    lh = fnum(base_style.get("line_height"), fs * 1.2)
    align = str(base_style.get("align", "left")).lower()
    v_align = str(base_style.get("v_align", "middle")).lower()
    do_wrap = bool(base_style.get("wrap", False))
    ew = w

    # Resolve each span into (text, resolved_attrs_dict, estimated_char_width_fn)
    resolved: list[dict] = []
    for sp in spans_raw or []:
        sp_weight = str(sp.get("weight", base_style.get("weight", 400)))
        sp_bold = sp_weight in ("700", "bold", "bolder")
        sp_color = r.color(sp.get("color", base_style.get("color", "#000000")))
        sp_italic = bool(sp.get("italic", base_style.get("italic", False)))
        sp_size = fnum(sp.get("size"), fs)  # per-span size override
        resolved.append(
            {
                "text": str(sp.get("text", "")),
                "weight": sp_weight,
                "bold": sp_bold,
                "color": sp_color,
                "italic": sp_italic,
                "size": sp_size,
            }
        )

    def span_width(sp_dict: dict, text: str) -> float:
        return r._str_width(text, sp_dict["size"], sp_dict["bold"])

    # Flatten to words with span index for re-assembly
    # Each word: (word_text, span_idx, is_last_in_span, trailing_space)
    flat_words: list[tuple] = []
    for si, sp in enumerate(resolved):
        words = sp["text"].split(" ")
        for wi, word in enumerate(words):
            if not word:
                continue
            flat_words.append((word, si, wi == len(words) - 1))

    # Word-wrap: accumulate words measuring their width per-span
    if do_wrap and flat_words:
        lines: list[list[tuple]] = []  # list of list of (word, span_idx)
        cur_line: list[tuple] = []
        cur_w = 0.0
        for word, si, _ in flat_words:
            sp = resolved[si]
            word_w = span_width(sp, word)
            space_w = r._str_width(" ", sp["size"], sp["bold"])
            if cur_line and cur_w + space_w + word_w > ew:
                lines.append(cur_line)
                cur_line = [(word, si)]
                cur_w = word_w
            else:
                cur_line.append((word, si))
                cur_w += (space_w if cur_line else 0) + word_w
        if cur_line:
            lines.append(cur_line)
    else:
        # No wrap — one line per \n in concatenated text
        # Build lines by splitting on \n within each span, re-merging
        lines = [[]]
        for word, si, _ in flat_words:
            lines[-1].append((word, si))

    n_lines = len(lines) if lines else 1
    block_h = fs + max(0, n_lines - 1) * lh
    if v_align == "top":
        baseline = y + fs * 0.78
    elif v_align == "bottom":
        baseline = y + h - block_h + fs * 0.78
    else:
        baseline = y + (h - block_h) / 2 + fs * 0.78

    tx, anchor = (
        (x + w / 2, "middle")
        if align == "center"
        else (x + w, "end")
        if align == "right"
        else (x, "start")
    )

    # Build SVG
    fa = {
        "x": fmt(tx),
        "y": fmt(baseline),
        "font-family": base_style.get("font"),
        "font-size": fmt(fs),
        "font-weight": base_style.get("weight", 400),
        "fill": base_style.get("color", "#000000"),
        "text-anchor": anchor,
    }
    if base_style.get("italic"):
        fa["font-style"] = "italic"

    svg_lines = []
    for li, line_words in enumerate(lines):
        # Group consecutive words of same span
        groups: list[tuple] = []  # (span_idx, [words])
        for word, si in line_words:
            if groups and groups[-1][0] == si:
                groups[-1][1].append(word)
            else:
                groups.append((si, [word]))

        line_parts = []
        for gi, (si, words) in enumerate(groups):
            sp = resolved[si]
            txt = " ".join(words)
            # add leading space between groups (different spans on same line)
            if gi > 0:
                txt = " " + txt

            span_a: dict[str, Any] = {}
            if sp["weight"] != str(base_style.get("weight", 400)):
                span_a["font-weight"] = sp["weight"]
            if sp["color"] != base_style.get("color", "#000000"):
                span_a["fill"] = sp["color"]
            if sp["italic"] and not base_style.get("italic"):
                span_a["font-style"] = "italic"
            if abs(sp["size"] - fs) > 0.1:
                span_a["font-size"] = fmt(sp["size"])

            attr_str = (" " + attrs(span_a)) if span_a else ""
            line_parts.append(f"<tspan{attr_str}>{esc(txt)}</tspan>")

        line_attr = f'x="{fmt(tx)}" dy="{fmt(0 if li == 0 else lh)}"'
        svg_lines.append(f"<tspan {line_attr}>{' '.join(line_parts)}</tspan>")

    return f"<text {attrs(fa)}>{''.join(svg_lines)}</text>"


def render_bullet_list(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a bullet_list object.

    YAML surface:
      type: bullet_list
      id: my_list
      box: [x, y, w, h]
      style: body_text          # base text style
      items:                    # list of items
        - "Simple string item"
        - text: "Item with |bold| run"   # future: spans per item
        - {text: "Nested indent", indent: 1}
      marker: "•"               # default bullet. "1." for ordered lists. "–" etc.
      gap: 6                    # px between items (default: 0.3 * line_height)
      indent: 16                # px per indent level (default: 12)

    Implementation:
      - Resolves base style for font/size/color/line_height.
      - Each item is word-wrapped to (box_w - indent_offset) using _str_width.
      - Marker is placed at x + indent_offset - marker_width.
      - Items stack vertically from box top (v_align always top for lists).
    """
    b = box(obj.get("box", [0, 0, 0, 0]))
    x, y, w, h = b
    style = r.text_style(obj.get("style"))
    items_raw = obj.get("items") or []
    marker = str(obj.get("marker", "•"))
    indent_px = fnum(obj.get("indent"), 12)
    fs = fnum(style.get("size"), 12)
    lh = fnum(style.get("line_height"), fs * 1.35)
    gap = fnum(obj.get("gap"), lh * 0.3)
    weight = str(style.get("weight", 400))
    bold = weight in ("700", "bold", "bolder")
    is_ordered = marker.endswith(".")

    # Resolve marker width
    marker_w = r._str_width(marker + " ", fs, bold)
    text_x = x + indent_px

    fa = {
        "font-family": style.get("font"),
        "font-size": fmt(fs),
        "font-weight": weight,
        "fill": style.get("color", "#000000"),
        "text-anchor": "start",
    }
    if style.get("italic"):
        fa["font-style"] = "italic"

    parts: list[str] = []
    cur_y = y + fs * 0.78  # first baseline

    for idx, item in enumerate(items_raw):
        # Resolve item text and per-item indent
        if isinstance(item, str):
            item_text, item_indent = _expand_lorem(item), 0
        elif isinstance(item, Mapping):
            item_text = _expand_lorem(str(item.get("text", "")))
            item_indent = int(item.get("indent", 0))
        else:
            item_text, item_indent = _expand_lorem(str(item)), 0

        # Marker label
        mark_str = f"{idx + 1}." if is_ordered else marker

        extra_indent = item_indent * indent_px
        mark_x = text_x + extra_indent - marker_w
        body_x = text_x + extra_indent
        body_w = w - indent_px - extra_indent

        # Word-wrap body text to available width
        wrapped = []
        line_buf = ""
        for word in item_text.split():
            test = (line_buf + " " + word).strip()
            if line_buf and r._str_width(test, fs, bold) > body_w:
                wrapped.append(line_buf)
                line_buf = word
            else:
                line_buf = test
        if line_buf:
            wrapped.append(line_buf)
        if not wrapped:
            wrapped = [""]

        # Emit marker on first line
        mark_attrs = dict(fa)
        mark_attrs["x"] = fmt(max(x, mark_x))
        mark_attrs["y"] = fmt(cur_y)
        parts.append(f"<text {attrs(mark_attrs)}><tspan>{esc(mark_str)}</tspan></text>")

        # Emit body lines
        for li, line in enumerate(wrapped):
            line_y = cur_y + li * lh
            line_attrs = dict(fa)
            line_attrs["x"] = fmt(body_x)
            line_attrs["y"] = fmt(line_y)
            parts.append(f"<text {attrs(line_attrs)}><tspan>{esc(line)}</tspan></text>")

        # Advance cursor past this item
        cur_y += len(wrapped) * lh + gap

        # Clip if we've overrun the box
        if cur_y > y + h + lh:
            break

    return f"<g {attrs(r.group_attrs(obj))}>{''.join(parts)}</g>"


RENDERERS = {
    "text": render_text_object,
    "bullet_list": render_bullet_list,
}
