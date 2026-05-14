"""Renderer bridge — pattern + fill + layout (+ stylesheet) → SVG.

The framework's universal "designed-by-default" promise lives here.
Every content_type's emitter delegates to one **structured card**
primitive that lays out its slots — accent_bar, number, label,
title, body — driven by the stylesheet's `treatments` block. Themes
swap freely; patterns swap freely; the visual language is constant.

Without a stylesheet the composed Document is bare and the renderer
falls back on its defaults (debug path used by
`framegraph patterns build`). With a stylesheet, every zone gets
typography, treatment, and palette resolved by
`framegraph.patterns.style.resolve_zone_style`.

Architecture
------------

  compose_document(pattern, fill, layout, canvas, stylesheet)
      │
      ├── for each pattern.zone:
      │       resolve style ← stylesheet.roles[]
      │       _emit_card(zone, value, layout-box, style, stylesheet)
      │            │
      │            ├── treatment background rect (+ accent bar)
      │            ├── slot grid: number / label / title / body
      │            └── body slot filled by content-type-specific
      │                 visual (text, bullet_list, table, chart, …)
      │
      └── chrome / synthesis layers handled by the deck loader
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from framegraph._patterns import SlidePattern
from framegraph.patterns.layout import Box
from framegraph.patterns.style import Stylesheet, resolve_zone_style

__all__ = [
    "compose_document",
    "render_pattern_svg",
]


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _content_value(content_obj: Any, role: str) -> Any:
    """Extract the per-role content from a fill object."""
    return getattr(content_obj, role, None)


def _humanize_role(role: str, case: str = "upper") -> str:
    """`key_partners` → `KEY PARTNERS` (upper) / `Key partners` (title)."""
    words = role.replace("_", " ").replace("-", " ").strip()
    if case == "upper":
        return words.upper()
    if case == "title":
        return words[:1].upper() + words[1:]
    return words


def _stringify_item(item: Any) -> str:
    """Reduce a list-item entry to a string for bullet rendering.

    Strings pass through. Pydantic models or dicts with `label` and
    `metric` render as ``"label: metric"``. Everything else falls
    back to ``str(item)``.
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


def _resolve_typography_ref(ref: Any, stylesheet: Stylesheet | None) -> dict[str, Any]:
    """Look up a typography reference (string id or inline mapping)."""
    if not ref:
        return {}
    if isinstance(ref, dict):
        return dict(ref)
    if isinstance(ref, str) and stylesheet is not None:
        return dict(stylesheet.text_styles.get(ref, {}))
    return {}


def _resolve_treatment(
    style: dict[str, Any] | None, stylesheet: Stylesheet | None
) -> dict[str, Any]:
    """Resolve the active treatment props from a zone style.

    Precedence (later wins): stylesheet lookup → inline
    ``treatment_props`` from the merged style. Inline props are
    populated by ``resolve_zone_style`` when the pattern's
    ``enterprise_layout`` carries a treatment, and again when a
    stylesheet ``RoleRule`` references a named treatment.
    """
    if not style:
        return {}
    inline_props = style.get("treatment_props")
    if isinstance(inline_props, dict) and inline_props:
        return dict(inline_props)
    treatment_name = style.get("treatment")
    if isinstance(treatment_name, str) and stylesheet is not None:
        treatments = stylesheet.model_dump().get("treatments", {})
        return dict(treatments.get(treatment_name, {}))
    return {}


def _padding_tuple(pad: Any) -> tuple[float, float, float, float]:
    """Normalize a padding spec to ``(top, right, bottom, left)``."""
    if pad is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(pad, (int, float)):
        v = float(pad)
        return (v, v, v, v)
    if isinstance(pad, (list, tuple)) and len(pad) == 4:
        return tuple(float(p) for p in pad)  # type: ignore[return-value]
    return (0.0, 0.0, 0.0, 0.0)


# ─────────────────────────────────────────────────────────────────
# Universal card primitive
# ─────────────────────────────────────────────────────────────────


def _emit_card(
    role: str,
    zone_box: Box,
    style: dict[str, Any],
    stylesheet: Stylesheet | None,
    *,
    label_text: str | None,
    number_text: str | None,
    title_text: str | None,
    body_emit: Any,
) -> list[dict[str, Any]]:
    """Render one structured card and return its visual objects.

    The card is a stylesheet-driven slot grid:

        ┌─────────────────────────────────────┐
        │┃                                    │  ← accent bar (left)
        │┃ 01   LABEL                          │  ← number, label
        │┃      Title (optional)               │  ← title
        │┃      Body content emitted by caller │  ← body
        │┃                                    │
        └─────────────────────────────────────┘

    Slots that have no content (e.g. no number was supplied) are
    skipped and their height is reclaimed by the body. Treatments
    that lack an ``accent_bar`` block render without one. The
    body slot is filled by ``body_emit(body_box) -> list[obj]`` —
    the caller decides what goes there (text, bullets, table, etc.).

    Args:
        role: Zone role (used in object IDs and as label fallback).
        zone_box: The full zone box ``(x, y, w, h)``.
        style: The role's resolved stylesheet rule (output of
            ``resolve_zone_style``). Carries the treatment name and
            any per-rule overrides.
        stylesheet: The active `Stylesheet`. Used to look up the
            treatment definition and named typography styles.
        label_text: Text for the LABEL slot (e.g. "STRENGTHS").
            None → slot omitted. Empty string → slot omitted.
        number_text: Text for the NUMBER slot (e.g. "01"). None →
            slot omitted unless the treatment forbids omission.
        title_text: Text for the TITLE slot. None → slot omitted.
        body_emit: Callable taking ``(body_box) → list[obj]`` that
            renders whatever fills the body slot.

    Returns:
        A list of visual objects (dicts) ready to drop into the
        Document.
    """
    treatment = _resolve_treatment(style, stylesheet)

    objects: list[dict[str, Any]] = []
    x, y, w, h = zone_box

    # ── 1. Background rect (the card body) ──
    fill_color = treatment.get("fill_color")
    stroke_color = treatment.get("stroke_color")
    stroke_width = float(treatment.get("stroke_width", 0) or 0)
    corner_radius = float(treatment.get("corner_radius", 0) or 0)
    has_fill = fill_color not in (None, "none")
    has_stroke = stroke_color not in (None, "none") and stroke_width > 0

    if has_fill or has_stroke:
        bg: dict[str, Any] = {
            "id": f"zone_{role}_bg",
            "type": "rect",
            "box": [x, y, w, h],
        }
        if has_fill:
            bg["fill"] = fill_color
        if has_stroke:
            bg["stroke"] = stroke_color
            bg["stroke_width"] = stroke_width
        if corner_radius:
            bg["corner_radius"] = corner_radius
        objects.append(bg)

    # ── 2. Accent bar ──
    accent_bar = treatment.get("accent_bar")
    if accent_bar:
        bar_w = float(accent_bar.get("width", 3))
        bar_color = accent_bar.get("color", "accent")
        side = accent_bar.get("side", "left")
        if side == "left":
            bar_box = [x, y, bar_w, h]
        elif side == "right":
            bar_box = [x + w - bar_w, y, bar_w, h]
        elif side == "top":
            bar_box = [x, y, w, bar_w]
        else:
            bar_box = [x, y + h - bar_w, w, bar_w]
        objects.append(
            {
                "id": f"zone_{role}_accent",
                "type": "rect",
                "box": bar_box,
                "fill": bar_color,
                "decorative": True,
            }
        )

    # ── 3. Slot grid inside the padded inner area ──
    pad_top, pad_right, pad_bottom, pad_left = _padding_tuple(treatment.get("padding"))
    inner_x = x + pad_left
    inner_y = y + pad_top
    inner_w = max(0.0, w - pad_left - pad_right)
    inner_h = max(0.0, h - pad_top - pad_bottom)

    slots: dict[str, Any] = treatment.get("slots") or {}
    cur_y = inner_y

    # Optional NUMBER slot — sits in its own column on the left so
    # label/title/body don't shift when present.
    number_slot = slots.get("number")
    body_left = inner_x
    body_right = inner_x + inner_w
    if number_slot and number_text:
        n_height = float(number_slot.get("height", 22))
        n_width = float(number_slot.get("width", 32))
        n_x_offset = float(number_slot.get("x_offset", 0))
        objects.append(
            {
                "id": f"zone_{role}_number",
                "type": "text",
                "box": [inner_x, inner_y, n_width, n_height],
                "text": str(number_text),
                "style": _resolve_typography_ref(number_slot.get("typography"), stylesheet),
            }
        )
        # Body content shifts to the right of the number column.
        body_left = inner_x + n_width + max(0.0, n_x_offset)

    # LABEL slot
    label_slot = slots.get("label")
    if label_slot is not None and label_text:
        lh = float(label_slot.get("height", 12))
        gap_below = float(label_slot.get("gap_below", 4))
        objects.append(
            {
                "id": f"zone_{role}_label",
                "type": "text",
                "box": [body_left, cur_y, body_right - body_left, lh],
                "text": label_text,
                "style": _resolve_typography_ref(label_slot.get("typography"), stylesheet),
            }
        )
        cur_y += lh + gap_below

    # TITLE slot
    title_slot = slots.get("title")
    if title_slot is not None and title_text:
        th = float(title_slot.get("height", 22))
        gap_below = float(title_slot.get("gap_below", 6))
        objects.append(
            {
                "id": f"zone_{role}_title",
                "type": "text",
                "box": [body_left, cur_y, body_right - body_left, th],
                "text": title_text,
                "style": _resolve_typography_ref(title_slot.get("typography"), stylesheet),
            }
        )
        cur_y += th + gap_below

    # BODY slot — caller fills it.
    body_box: Box = (
        body_left,
        cur_y,
        body_right - body_left,
        max(0.0, (inner_y + inner_h) - cur_y),
    )
    body_objs = body_emit(body_box) if callable(body_emit) else []
    objects.extend(body_objs)

    return objects


# ─────────────────────────────────────────────────────────────────
# Per-content_type body emitters — fill the card's body slot.
# Each takes (role, value, body_box, style, stylesheet) and returns
# a list of visual objects.
# ─────────────────────────────────────────────────────────────────


def _body_title_body(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    """`title_body` body slot: bold title + body text, both wrapped."""
    typography = _resolve_typography_ref(
        (style.get("slots") or {}).get("body", {}).get("typography") or "card_body",
        stylesheet,
    )
    title = getattr(value, "title", None) or ""
    body = getattr(value, "body", None) or ""
    spans: list[dict[str, Any]] = []
    if title:
        spans.append({"text": title, "weight": "bold"})
    if body:
        if title:
            spans.append({"text": "\n"})
        spans.append({"text": body})
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "text",
        "box": list(body_box),
        "spans": spans or [{"text": ""}],
    }
    if typography:
        obj["style"] = typography
    return [obj]


def _body_list_items(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    """`list_items` body slot.

    Two emission paths, decided by the runtime shape of the items:

    - **String items** → emit a `bullet_list` with theme-styled markers.
      This is the default for ``list_items`` zones whose effective
      schema kept the default ``list[str]`` shape.
    - **Object items** (e.g. ``list[{label, metric}]`` from a sidecar
      ``item_kind: object`` override) → emit a `table` whose header
      row is the field names and whose body rows are the field
      values, in declaration order. This honours the Round 2 Phase 3
      "list-of-objects renders as table" contract pinned by
      ``tests/integration/test_pattern_render.py``.

    Detection is purely runtime — the renderer doesn't need to thread
    the sidecar object through. A Pydantic model exposes
    ``model_dump``; a plain mapping exposes ``items()``; everything
    else is treated as a string.
    """
    items = list(value or [])
    typography = _resolve_typography_ref("card_body", stylesheet)

    # Detect object items by checking the first one. The fill schema
    # builder constrains a sidecar-overridden list zone to a single
    # uniform shape, so the first item's shape applies to all.
    has_object_items = bool(items) and (
        hasattr(items[0], "model_dump") or isinstance(items[0], Mapping)
    )

    if has_object_items:
        # Coerce to ordered list-of-dicts.
        rows_raw: list[Mapping[str, Any]] = [
            it.model_dump() if hasattr(it, "model_dump") else dict(it) for it in items
        ]
        # Header: union of keys preserving declaration order from the
        # first item (sidecar item_fields order is preserved by
        # Pydantic v2 model dumps).
        header: list[str] = list(rows_raw[0].keys())
        rows: list[list[str]] = [
            [_stringify_item(row.get(k, "")) for k in header] for row in rows_raw
        ]
        obj: dict[str, Any] = {
            "id": f"zone_{role}",
            "type": "table",
            "box": list(body_box),
            "header": header,
            "rows": rows,
        }
        if typography:
            obj["style"] = {"cell_text_style": typography}
        return [obj]

    obj = {
        "id": f"zone_{role}",
        "type": "bullet_list",
        "box": list(body_box),
        "items": [_stringify_item(it) for it in items],
    }
    if typography:
        obj["style"] = typography
    obj["marker_color"] = "accent"
    return [obj]


def _body_key_value(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    items = [] if value is None else [f"{k}: {v}" for k, v in value.items()]
    typography = _resolve_typography_ref("card_body_small", stylesheet)
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "bullet_list",
        "box": list(body_box),
        "items": items,
        "marker": "–",
    }
    if typography:
        obj["style"] = typography
    return [obj]


def _body_comparison(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    left = getattr(value, "left", "")
    right = getattr(value, "right", "")
    typography = _resolve_typography_ref("card_body", stylesheet)
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "text",
        "box": list(body_box),
        "spans": [
            {"text": left, "weight": "bold"},
            {"text": "  |  "},
            {"text": right, "weight": "bold"},
        ],
    }
    if typography:
        obj["style"] = typography
    return [obj]


def _body_chart_data(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    chart_type = getattr(value, "type", None) or "bar"
    series_raw = getattr(value, "series", None) or []
    series = list(series_raw) if series_raw else []
    obj_type = "bar_chart" if chart_type != "line" else "line_chart"
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": obj_type,
        "box": list(body_box),
        "series": series,
    }
    treatment = _resolve_treatment(style, stylesheet)
    palette = (treatment.get("slots") or {}).get("chart", {}).get("palette")
    if palette:
        obj["palette"] = palette
    return [obj]


def _body_table_data(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    headers = getattr(value, "headers", None) or []
    rows = getattr(value, "rows", None) or []
    treatment = _resolve_treatment(style, stylesheet)
    table_slot = (treatment.get("slots") or {}).get("table") or {}
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "table",
        "box": list(body_box),
        "header": list(headers) if headers else None,
        "rows": [list(r) for r in rows],
    }
    style_block: dict[str, Any] = {}
    if table_slot.get("header_typography"):
        style_block["header_text_style"] = _resolve_typography_ref(
            table_slot["header_typography"], stylesheet
        )
    if table_slot.get("cell_typography"):
        style_block["body_text_style"] = _resolve_typography_ref(
            table_slot["cell_typography"], stylesheet
        )
    if table_slot.get("header_fill"):
        style_block["header_fill"] = table_slot["header_fill"]
    if table_slot.get("border_color"):
        style_block["border_color"] = table_slot["border_color"]
    if style_block:
        obj["style"] = style_block
    return [obj]


def _body_image(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    src = getattr(value, "src", "") or ""
    alt = getattr(value, "alt", None)
    obj: dict[str, Any] = {
        "id": f"zone_{role}",
        "type": "image",
        "box": list(body_box),
        "href": src,
    }
    if alt:
        obj["alt"] = alt
    return [obj]


def _body_metric(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    """`metric` body slot: large KPI value above small label/trend."""
    treatment = _resolve_treatment(style, stylesheet)
    slots = treatment.get("slots") or {}
    value_typo = _resolve_typography_ref(
        (slots.get("kpi_value") or {}).get("typography") or "kpi_value", stylesheet
    )
    label_typo = _resolve_typography_ref("kpi_label", stylesheet)

    val = getattr(value, "value", None) or ""
    label = getattr(value, "label", None) or ""
    trend = getattr(value, "trend", None)

    bx, by, bw, bh = body_box
    value_h = float((slots.get("kpi_value") or {}).get("height", 40))
    objects: list[dict[str, Any]] = [
        {
            "id": f"zone_{role}_value",
            "type": "text",
            "box": [bx, by, bw, value_h],
            "text": val,
            "style": value_typo,
        }
    ]
    if label or trend:
        bottom_text = label
        if trend:
            bottom_text = f"{label}  {trend}" if label else trend
        objects.append(
            {
                "id": f"zone_{role}_label",
                "type": "text",
                "box": [bx, by + value_h, bw, max(0.0, bh - value_h)],
                "text": bottom_text,
                "style": label_typo,
            }
        )
    return objects


def _body_axis_label(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    title = getattr(value, "title", "") or ""
    units = getattr(value, "units", None)
    text = f"{title} ({units})" if units else title
    typography = _resolve_typography_ref(
        style.get("typography") if style else "axis_label", stylesheet
    )
    return [
        {
            "id": f"zone_{role}",
            "type": "text",
            "box": list(body_box),
            "text": text,
            "style": typography,
        }
    ]


def _body_decorative(
    role: str, value: Any, body_box: Box, style: dict[str, Any], stylesheet: Stylesheet | None
) -> list[dict[str, Any]]:
    bx, by, bw, bh = body_box
    return [
        {
            "id": f"zone_{role}",
            "type": "rect",
            "box": [bx, by + bh / 2 - 0.5, bw, 1],
            "fill": (style or {}).get("fill_color", "border"),
            "decorative": True,
        }
    ]


_BODY_EMITTERS = {
    "title_body": _body_title_body,
    "metric": _body_metric,
    "list_items": _body_list_items,
    "key_value": _body_key_value,
    "comparison": _body_comparison,
    "chart_data": _body_chart_data,
    "table_data": _body_table_data,
    "image": _body_image,
    "axis_label": _body_axis_label,
    "decorative": _body_decorative,
}


# ─────────────────────────────────────────────────────────────────
# Document composer
# ─────────────────────────────────────────────────────────────────


def _zone_label_text(
    role: str,
    label_overrides: dict[str, str] | None,
    label_cfg: dict[str, Any] | None,
) -> str | None:
    """Return the label text for a zone, or None to skip."""
    if label_overrides and role in label_overrides:
        return label_overrides[role]
    case = (label_cfg or {}).get("case", "upper")
    return _humanize_role(role, case)


def compose_document(
    pattern: SlidePattern,
    fill: BaseModel,
    layout: dict[str, Box],
    canvas_w: float,
    canvas_h: float,
    *,
    stylesheet: Stylesheet | None = None,
    label_overrides: dict[str, str] | None = None,
    numbers: dict[str, str] | None = None,
    titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a FrameGraph `Document` from pattern + fill + layout.

    With a stylesheet, every zone is rendered through the universal
    `_emit_card` primitive. The stylesheet's `treatments` block
    controls slot geometry; theme tokens supply colors and fonts.

    Args:
        pattern: The catalog pattern.
        fill: A validated fill object.
        layout: Per-zone box mapping.
        canvas_w / canvas_h: Canvas size in pixels.
        stylesheet: Active `Stylesheet`. Without one, the card
            primitive degrades to a single body emission and the
            renderer uses defaults.
        label_overrides: Optional ``{role: humanized label}`` map
            from the slide entry.
        numbers: Optional ``{role: number_string}`` to fill the
            card-number slot per zone.
        titles: Optional ``{role: title_string}`` to fill the
            card-title slot per zone.
    """
    objects: list[dict[str, Any]] = []
    label_cfg = stylesheet.model_dump().get("zone_labels", {}) if stylesheet else {}

    # Pattern-level enterprise polish presets — applied per-zone under
    # the active stylesheet (stylesheet still wins on conflict). When
    # the pattern declares no `enterprise_layout`, this dict is empty
    # and the code path is byte-identical to the pre-preset behavior.
    ent_layout = pattern.enterprise_layout
    ent_zones = ent_layout.zones if ent_layout is not None else {}

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

        zone_preset = ent_zones.get(zone.role)
        zone_box = layout[zone.role]
        # Coordinate override: when the preset hand-tunes a box (covers,
        # dividers, full-bleed treatments), it replaces the layout
        # planner's computed box. The planner result remains the
        # default — the preset opts in explicitly.
        if zone_preset is not None and zone_preset.box is not None:
            zone_box = tuple(zone_preset.box)  # type: ignore[assignment]

        zone_style: dict[str, Any] = {}
        if stylesheet is not None:
            zone_style = resolve_zone_style(
                zone, stylesheet, enterprise_preset=zone_preset
            )

        value = _content_value(fill, zone.role)
        body_emitter = _BODY_EMITTERS[ct]

        # Per-zone label, number, title — skip label for decorative
        # zones (they're chrome) and table_data when treatments
        # disable it.
        label_text: str | None = None
        if ct != "decorative":
            # Preset `label_text` overrides the humanized auto-label,
            # but a user-supplied `label_overrides[role]` still wins —
            # `_zone_label_text` checks `label_overrides` first.
            preset_label = (
                zone_preset.label_text if zone_preset is not None else None
            )
            if (label_overrides or {}).get(zone.role) is not None:
                label_text = _zone_label_text(zone.role, label_overrides, label_cfg)
            elif preset_label is not None:
                label_text = preset_label or None  # empty string suppresses
            else:
                label_text = _zone_label_text(zone.role, label_overrides, label_cfg)

        number_text = (numbers or {}).get(zone.role)
        title_text = (titles or {}).get(zone.role)

        if stylesheet is None:
            # Bare debug path — no card, just body.
            objects.extend(body_emitter(zone.role, value, zone_box, {}, None))
            continue

        def make_body_emit(
            _zone: Any = zone,
            _value: Any = value,
            _style: dict[str, Any] = zone_style,
        ) -> Any:
            def _emit(body_box: Box) -> list[dict[str, Any]]:
                return body_emitter(_zone.role, _value, body_box, _style, stylesheet)

            return _emit

        objects.extend(
            _emit_card(
                zone.role,
                zone_box,
                zone_style,
                stylesheet,
                label_text=label_text,
                number_text=number_text,
                title_text=title_text,
                body_emit=make_body_emit(),
            )
        )

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
    *,
    stylesheet: Stylesheet | None = None,
    label_overrides: dict[str, str] | None = None,
    numbers: dict[str, str] | None = None,
    titles: dict[str, str] | None = None,
) -> str:
    """Render a pattern + fill + layout (+ optional stylesheet) to SVG."""
    from framegraph import FrameGraphRenderer

    doc = compose_document(
        pattern,
        fill,
        layout,
        canvas_w,
        canvas_h,
        stylesheet=stylesheet,
        label_overrides=label_overrides,
        numbers=numbers,
        titles=titles,
    )
    return FrameGraphRenderer(doc).render_svg()
