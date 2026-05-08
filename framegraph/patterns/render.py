"""Renderer bridge — pattern + fill + layout → SVG.

Phase 4 of the fill-and-render roadmap. This module composes a
FrameGraph `Document` from a pattern, a validated fill, and a
computed layout, then drives the existing `FrameGraphRenderer`
to produce SVG.

The composition rule per zone:

  - Look up the zone's `content_type`.
  - Read the corresponding fill content (a Pydantic model
    instance whose attribute name is the zone's role).
  - Emit one or more FrameGraph visual objects with the zone's
    `[x, y, w, h]` box from the layout.

Per-content_type → object emitter map:

  | content_type | object type   | source fields |
  |--------------|---------------|----------------|
  | title_body   | text (spans)  | title (bold) + body |
  | metric       | text (spans)  | value (large bold) + label |
  | list_items   | bullet_list   | items as strings (or "label: metric") |
  | key_value    | bullet_list   | "k: v" pairs |
  | comparison   | text          | "left  |  right" |
  | chart_data   | bar_chart     | series passed through |
  | table_data   | table         | headers + rows passed through |
  | image        | image         | src, alt |
  | axis_label   | text          | "{title} ({units})" |
  | decorative   | rect          | empty bordered box (placeholder) |

Per the roadmap, this bridge does *not* re-implement SVG; it
delegates to the existing renderer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from framegraph._patterns import SlidePattern
from framegraph.patterns.layout import Box

__all__ = [
    "compose_document",
    "render_pattern_svg",
]


# ─────────────────────────────────────────────────────────────────
# Per-content_type emitters
# ─────────────────────────────────────────────────────────────────


def _content_value(content_obj: Any, role: str) -> Any:
    """Extract the per-role content from a fill object.

    The fill `content` is a Pydantic model with one attribute per
    role. We use `getattr` to read it.
    """
    return getattr(content_obj, role, None)


def _emit_title_body(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    title = getattr(value, "title", None) or ""
    body = getattr(value, "body", None) or ""
    spans: list[dict[str, Any]] = []
    if title:
        spans.append({"text": title, "weight": "bold"})
    if body:
        # Two-line approximation: title bold, body plain. Real
        # multi-line layout is the renderer's job; here we just
        # supply the spans.
        if title:
            spans.append({"text": "\n"})
        spans.append({"text": body})
    return [
        {
            "id": f"zone_{role}",
            "type": "text",
            "box": list(box),
            "spans": spans or [{"text": ""}],
        }
    ]


def _emit_metric(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    val = getattr(value, "value", None) or ""
    label = getattr(value, "label", None) or ""
    trend = getattr(value, "trend", None)
    spans: list[dict[str, Any]] = [
        {"text": val, "weight": "bold", "size": 32}
    ]
    if label:
        spans.append({"text": "\n"})
        spans.append({"text": label, "size": 14})
    if trend:
        spans.append({"text": " "})
        spans.append({"text": trend, "size": 14, "italic": True})
    return [
        {
            "id": f"zone_{role}",
            "type": "text",
            "box": list(box),
            "spans": spans,
        }
    ]


def _stringify_item(item: Any) -> str:
    """Reduce a list-item entry to a single string for bullet_list rendering.

    Strings pass through unchanged. Pydantic objects with `label`
    and `metric` attributes (the BMC sidecar override shape)
    render as ``"label: metric"``. Other objects fall back to
    ``str(item)``.
    """
    if isinstance(item, str):
        return item
    label = getattr(item, "label", None)
    metric = getattr(item, "metric", None)
    if label is not None and metric is not None:
        return f"{label}: {metric}"
    if isinstance(item, dict) and "label" in item and "metric" in item:
        return f"{item['label']}: {item['metric']}"
    return str(item)


def _emit_list_items(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    if value is None:
        items: list[Any] = []
    else:
        items = list(value)
    return [
        {
            "id": f"zone_{role}",
            "type": "bullet_list",
            "box": list(box),
            "items": [_stringify_item(it) for it in items],
        }
    ]


def _emit_key_value(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    if value is None:
        items: list[str] = []
    else:
        items = [f"{k}: {v}" for k, v in value.items()]
    return [
        {
            "id": f"zone_{role}",
            "type": "bullet_list",
            "box": list(box),
            "items": items,
            "marker": "–",
        }
    ]


def _emit_comparison(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    left = getattr(value, "left", "")
    right = getattr(value, "right", "")
    return [
        {
            "id": f"zone_{role}",
            "type": "text",
            "box": list(box),
            "spans": [
                {"text": left, "weight": "bold"},
                {"text": "  |  "},
                {"text": right, "weight": "bold"},
            ],
        }
    ]


def _emit_chart_data(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    chart_type = getattr(value, "type", None) or "bar"
    series_raw = getattr(value, "series", None) or []
    series = list(series_raw) if series_raw else []
    obj_type = "bar_chart" if chart_type != "line" else "line_chart"
    return [
        {
            "id": f"zone_{role}",
            "type": obj_type,
            "box": list(box),
            "series": series,
        }
    ]


def _emit_table_data(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    headers = getattr(value, "headers", None) or []
    rows = getattr(value, "rows", None) or []
    return [
        {
            "id": f"zone_{role}",
            "type": "table",
            "box": list(box),
            "header": list(headers) if headers else None,
            "rows": [list(r) for r in rows],
        }
    ]


def _emit_image(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    src = getattr(value, "src", "") or ""
    alt = getattr(value, "alt", None)
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "image",
        "box": list(box),
        "href": src,
    }
    if alt:
        obj["alt"] = alt
    return [obj]


def _emit_axis_label(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    title = getattr(value, "title", "") or ""
    units = getattr(value, "units", None)
    text = f"{title} ({units})" if units else title
    return [
        {
            "id": f"zone_{role}",
            "type": "text",
            "box": list(box),
            "text": text,
        }
    ]


def _emit_decorative(role: str, value: Any, box: Box) -> list[dict[str, Any]]:
    return [
        {
            "id": f"zone_{role}",
            "type": "rect",
            "box": list(box),
            "decorative": True,
        }
    ]


_EMITTERS = {
    "title_body": _emit_title_body,
    "metric": _emit_metric,
    "list_items": _emit_list_items,
    "key_value": _emit_key_value,
    "comparison": _emit_comparison,
    "chart_data": _emit_chart_data,
    "table_data": _emit_table_data,
    "image": _emit_image,
    "axis_label": _emit_axis_label,
    "decorative": _emit_decorative,
}


# ─────────────────────────────────────────────────────────────────
# Document composer
# ─────────────────────────────────────────────────────────────────


def compose_document(
    pattern: SlidePattern,
    fill: BaseModel,
    layout: dict[str, Box],
    canvas_w: float,
    canvas_h: float,
) -> dict[str, Any]:
    """Build a FrameGraph `Document` (as a dict) from pattern + fill + layout.

    Args:
        pattern: The catalog pattern being rendered.
        fill: A validated fill — typically the result of
            ``derive_fill_schema_with_sidecar(pattern, sidecar)
            .model_validate(...)``. Must expose one attribute per
            zone role.
        layout: A mapping from zone role → ``(x, y, w, h)``.
            Typically the result of
            ``compute_boxes(pattern, canvas_w, canvas_h)``.
        canvas_w: Canvas width in pixels.
        canvas_h: Canvas height in pixels.

    Returns:
        A `Document`-shaped dict ready for
        ``Document.model_validate`` and consumption by
        ``FrameGraphRenderer``.

    Raises:
        KeyError: If `layout` is missing a box for any zone in the
            pattern, or if a zone's `content_type` is unknown.
        ValueError: If a zone has no `content_type` (the pattern
            must be fully annotated or the sidecar must override
            every un-annotated zone).
    """
    objects: list[dict[str, Any]] = []
    for zone in pattern.zones:
        if zone.role not in layout:
            raise KeyError(
                f"layout missing box for role {zone.role!r} in pattern "
                f"{pattern.id} ({pattern.name!r})"
            )
        ct = zone.content_type
        if ct is None:
            raise ValueError(
                f"pattern {pattern.id} ({pattern.name!r}): zone "
                f"{zone.role!r} has no content_type; cannot emit"
            )
        emitter = _EMITTERS[ct]
        value = _content_value(fill, zone.role)
        objects.extend(emitter(zone.role, value, layout[zone.role]))

    return {
        "dsl": "FrameGraph",
        "version": 2.0,
        "scene": {
            "id": f"pattern_{pattern.id}",
            "name": pattern.name,
            "canvas": {
                "size": [canvas_w, canvas_h],
                "units": "px",
            },
        },
        "visual": {
            "layers": [
                {
                    "id": "content",
                    "objects": objects,
                }
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


def render_pattern_svg(
    pattern: SlidePattern,
    fill: BaseModel,
    layout: dict[str, Box],
    canvas_w: float,
    canvas_h: float,
) -> str:
    """Render a pattern + fill + layout to SVG.

    Composes a Document and drives the existing
    `FrameGraphRenderer`. The renderer is the source of truth for
    visual output; this function exists only as the bridge from
    pattern-fill semantics to renderer input.

    Args:
        pattern: The catalog pattern.
        fill: Validated fill object (one attribute per zone role).
        layout: Zone-role → ``(x, y, w, h)`` mapping.
        canvas_w: Canvas width in pixels.
        canvas_h: Canvas height in pixels.

    Returns:
        The SVG document as a string.
    """
    from framegraph import FrameGraphRenderer

    doc = compose_document(pattern, fill, layout, canvas_w, canvas_h)
    return FrameGraphRenderer(doc).render_svg()
