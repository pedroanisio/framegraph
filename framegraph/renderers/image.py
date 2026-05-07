"""Raster image embedding.

Reads an image from disk relative to the rendering YAML (when the
caller has set `r.yaml_source_dir`) and emits an SVG `<image>` with
the file inlined as a `data:` URI base-64 payload.
"""

from __future__ import annotations

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


def render_image(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a raster image object.

    href / src / uri resolution order:
      1. "placeholder" (literal) or missing/empty href, or placeholder:true
         → renders a grey placeholder box with diagonal cross + label
      2. "data:..." — passed through unchanged (already embedded)
      3. "http://" / "https://" — passed through as URL reference
      4. Local file path — resolved relative to the document source dir,
         then read and base64-encoded as a data URI.
    """
    import base64
    import mimetypes
    from pathlib import Path

    x, y, w, h = box(obj.get("box", [0, 0, 0, 0]))
    href = str(obj.get("href") or obj.get("src") or obj.get("uri") or "")
    is_placeholder = bool(obj.get("placeholder")) or href.lower() == "placeholder" or href == ""

    # ── Placeholder rendering ─────────────────────────────────────────
    if is_placeholder:
        label = obj.get("label") or f"{int(w)}×{int(h)}"
        fill = obj.get("fill") or "#E8E8E8"
        line_c = "#BBBBBB"
        rx_ = fnum(obj.get("radius"), 0)
        lfs = max(9, min(14, h * 0.18))  # label font size, clamped
        svg_parts = [
            f"<g {attrs(r.group_attrs(obj))}>",
            # Background
            f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" ',
            f'fill="{fill}" rx="{fmt(rx_)}" ry="{fmt(rx_)}" ',
            f'stroke="{line_c}" stroke-width="1"/>',
            # Diagonal lines (X pattern)
            f'<line x1="{fmt(x)}" y1="{fmt(y)}" x2="{fmt(x + w)}" y2="{fmt(y + h)}" ',
            f'stroke="{line_c}" stroke-width="1" stroke-dasharray="4,3"/>',
            f'<line x1="{fmt(x + w)}" y1="{fmt(y)}" x2="{fmt(x)}" y2="{fmt(y + h)}" ',
            f'stroke="{line_c}" stroke-width="1" stroke-dasharray="4,3"/>',
            # Label centred in box
            f'<text x="{fmt(x + w / 2)}" y="{fmt(y + h / 2 + lfs * 0.36)}" ',
            f'font-family="Arial,Helvetica,sans-serif" font-size="{fmt(lfs)}" ',
            'fill="#888888" text-anchor="middle" font-weight="400">',
            esc(label),
            "</text></g>",
        ]
        return "".join(svg_parts)

    # ── Real image ────────────────────────────────────────────────────
    preserve_ratio = obj.get("preserve_aspect_ratio", "xMidYMid meet")

    if href and not href.startswith("data:") and not href.startswith("http"):
        p = Path(href)
        if not p.is_absolute():
            base = getattr(r, "yaml_source_dir", None) or Path.cwd()
            p = Path(base) / p
        if p.exists():
            mime = mimetypes.guess_type(str(p))[0] or "image/png"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            href = f"data:{mime};base64,{b64}"

    a = {
        "x": fmt(x),
        "y": fmt(y),
        "width": fmt(w),
        "height": fmt(h),
        "href": href,
        "preserveAspectRatio": preserve_ratio,
    }
    return f"<g {attrs(r.group_attrs(obj))}><image {attrs(a)}/></g>"


RENDERERS = {
    "image": render_image,
}
