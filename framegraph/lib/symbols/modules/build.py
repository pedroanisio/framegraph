"""module_hub_radial — data-driven generator.

Reads a compact input dict (see module_hub_radial.schema.json) and
emits a complete FrameGraph presentation-deck dict. Lays out:

  * decorator dots + title + kicker (top-left header band)
  * connector edges (drawn first, so hexes sit on top)
  * the central hub hex (large, thick stroke)
  * a captioned bullet block under the hub (optional)
  * satellite hexes at explicit positions, each with its own outline
    color and icon variant
  * per-node labels positioned outside the hex (above / below / left /
    right of the hex by the satellite's label_anchor)
  * optional centered footer page number

Hex sub-symbols are inlined into deck.symbols from
honeycomb_cells.sym.yml's sibling pack at module_node_cells.sym.yml.

CLI usage:
    python -m framegraph.lib.symbols.modules.build \\
        examples/module-hub-radial/data.yml \\
        examples/module-hub-radial/deck.yml
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PALETTE: dict[str, str] = {
    "bg":                "#FFFFFF",
    "title_color":       "#1A2B3E",
    "kicker_color":      "#9A9A9A",
    "dot_primary":       "#E51A4C",
    "dot_secondary":     "#1A2B3E",
    "dot_tertiary":      "#C8C8C8",
    "edge_color":        "#C8C8C8",
    "page_number_color": "#9A9A9A",
}

DEFAULT_GEOMETRY: dict[str, float] = {
    "canvas_w":               1280,
    "canvas_h":               900,
    "satellite_default_size": 70,
    "label_gap":              6,
}

ICON_TO_SYMBOL = {
    "warning": "hex_node_warning",
    "excel":   "hex_node_excel",
    "money":   "hex_node_money",
    "none":    "hex_node_plain",
}


def _load_cell_symbols() -> dict[str, Any]:
    sym_path = Path(__file__).parent / "module_node_cells.sym.yml"
    pack = yaml.safe_load(sym_path.read_text(encoding="utf-8"))
    return dict(pack.get("symbols") or {})


def _hex_box(cx: float, cy: float, side: float) -> list[float]:
    """Return the [x, y, w, h] box for a flat-top hex centered at (cx, cy)."""
    w = 2.0 * side
    h = math.sqrt(3.0) * side
    return [cx - w / 2.0, cy - h / 2.0, w, h]


def _label_box(
    hex_box: list[float],
    anchor: str,
    gap: float,
) -> tuple[list[float], str]:
    """Return ([x, y, w, h], align) for a label placed outside a hex.

    The width/height pre-sized to allow two-line wrapped labels.
    """
    x, y, w, h = hex_box
    if anchor == "below":
        return [x - 40, y + h + gap, w + 80, 44], "center"
    if anchor == "left":
        return [x - 230, y + h / 2.0 - 22, 220, 44], "right"
    if anchor == "right":
        return [x + w + gap, y + h / 2.0 - 22, 220, 44], "left"
    # "above" (default)
    return [x - 40, y - 44 - gap, w + 80, 44], "center"


def _node_center(node: dict[str, Any], satellite_default_size: float) -> tuple[float, float]:
    px, py = node["position"]
    return float(px), float(py)


def _node_size(node: dict[str, Any], default: float) -> float:
    return float(node.get("size") or default)


def _build_objects(
    data: dict[str, Any],
    pal: dict[str, str],
    geo: dict[str, float],
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    # ── Decorator dots ──────────────────────────────────────────────
    objects.append({"type": "ellipse", "id": "dot_primary",   "box": [22, 14, 18, 18], "fill": "dot_primary"})
    objects.append({"type": "ellipse", "id": "dot_secondary", "box": [22, 44, 18, 18], "fill": "dot_secondary"})
    objects.append({"type": "ellipse", "id": "dot_tertiary",  "box": [22, 92, 18, 18], "fill": "dot_tertiary"})

    # ── Title + kicker ──────────────────────────────────────────────
    objects.append({
        "type": "text", "id": "title",
        "box": [60, 12, geo["canvas_w"] - 80, 56],
        "text": data["title"],
        "style": "module_title",
    })
    kicker = (data.get("kicker_label") or "").strip()
    if kicker:
        objects.append({
            "type": "text", "id": "kicker",
            "box": [60, 88, geo["canvas_w"] - 80, 24],
            "text": kicker,
            "style": "module_kicker",
        })

    # ── Build node registry (id → (cx, cy, size) ) ──────────────────
    sat_default = geo["satellite_default_size"]
    hub = data["hub"]
    hub_cx, hub_cy = _node_center(hub, sat_default)
    hub_size = _node_size(hub, 130)

    registry: dict[str, tuple[float, float, float]] = {
        hub["id"]: (hub_cx, hub_cy, hub_size),
    }
    for sat in data["satellites"]:
        cx, cy = _node_center(sat, sat_default)
        registry[sat["id"]] = (cx, cy, _node_size(sat, sat_default))

    # ── Edges (drawn FIRST so hexes paint over them) ────────────────
    for edge_idx, edge in enumerate(data.get("edges") or []):
        src = registry.get(edge["from"])
        tgt = registry.get(edge["to"])
        if not src or not tgt:
            continue
        line_obj: dict[str, Any] = {
            "type":   "line",
            "id":     f"edge_{edge_idx}",
            "from":   [src[0], src[1]],
            "to":     [tgt[0], tgt[1]],
            "stroke": {
                "color": edge.get("stroke_color") or "edge_color",
                "width": float(edge.get("stroke_width") or 1.5),
            },
        }
        if edge.get("dash"):
            line_obj["stroke"]["dash"] = list(edge["dash"])
        objects.append(line_obj)

    # ── Hub label (above the hub hex) ───────────────────────────────
    hub_box = _hex_box(hub_cx, hub_cy, hub_size)
    hub_label_box = [hub_box[0] - 40, hub_box[1] - 90, hub_box[2] + 80, 80]
    objects.append({
        "type": "text", "id": "hub_label",
        "box": hub_label_box,
        "text": hub["label"],
        "style": "module_hub_label",
    })

    # ── Hub hex ──────────────────────────────────────────────────────
    hub_icon = (hub.get("icon") or "warning").lower()
    objects.append({
        "type":   "use",
        "id":     f"node_{hub['id']}",
        "symbol": ICON_TO_SYMBOL.get(hub_icon, "hex_node_warning"),
        "box":    hub_box,
        "params": {
            "outline_color": hub.get("outline_color") or "#9E1A8C",
            "fill":          hub.get("fill") or "bg",
        },
    })

    # ── Hub detail block (optional) ─────────────────────────────────
    detail = hub.get("detail") or {}
    if detail:
        if detail.get("box"):
            d_box = list(detail["box"])
        else:
            d_box = [hub_box[0] - 60, hub_box[1] + hub_box[3] + 12, hub_box[2] + 120, 160]

        # Heading
        objects.append({
            "type":  "text",
            "id":    "hub_detail_heading",
            "box":   [d_box[0], d_box[1], d_box[2], 24],
            "text":  detail.get("heading") or "",
            "style": "module_hub_detail_heading",
        })
        # Bullets
        bullets = detail.get("bullets") or []
        if bullets:
            objects.append({
                "type":   "bullet_list",
                "id":     "hub_detail_bullets",
                "box":    [d_box[0] + 24, d_box[1] + 32, d_box[2] - 24, d_box[3] - 32],
                "items":  list(bullets),
                "marker": "•",
                "style":  "module_hub_detail_bullets",
            })

    # ── Satellites ──────────────────────────────────────────────────
    for sat in data["satellites"]:
        sat_size = _node_size(sat, sat_default)
        sat_cx, sat_cy = _node_center(sat, sat_default)
        sat_box = _hex_box(sat_cx, sat_cy, sat_size)
        icon = (sat.get("icon") or "warning").lower()
        objects.append({
            "type":   "use",
            "id":     f"node_{sat['id']}",
            "symbol": ICON_TO_SYMBOL.get(icon, "hex_node_warning"),
            "box":    sat_box,
            "params": {
                "outline_color": sat.get("outline_color") or "#1A56B0",
                "fill":          sat.get("fill") or "bg",
            },
        })
        # Label
        lab_box, lab_align = _label_box(sat_box, sat.get("label_anchor") or "above", geo["label_gap"])
        style_name = {
            "right": "module_sat_label_left",   # anchor right means text is left-aligned
            "left":  "module_sat_label_right",  # anchor left means text is right-aligned
        }.get(sat.get("label_anchor") or "above", "module_sat_label_center")
        objects.append({
            "type":  "text",
            "id":    f"label_{sat['id']}",
            "box":   lab_box,
            "text":  sat["label"],
            "style": style_name,
        })

    # ── Footer page number ─────────────────────────────────────────
    page_num = data.get("page_number")
    if page_num not in (None, ""):
        objects.append({
            "type":  "text",
            "id":    "page_number",
            "box":   [0, geo["canvas_h"] - 28, geo["canvas_w"], 18],
            "text":  str(page_num),
            "style": "module_page_number",
        })

    return objects


def build_deck(data: dict[str, Any]) -> dict[str, Any]:
    """Build a complete FrameGraph presentation-deck dict from input ``data``.

    Merges palette and geometry over defaults, registers per-node hex
    colors as deck tokens, inlines the hex cell symbols, builds the layer
    objects and text styles, and returns the single-slide deck.
    """
    pal: dict[str, str] = {**DEFAULT_PALETTE, **(data.get("palette") or {})}
    geo: dict[str, float] = {**DEFAULT_GEOMETRY, **(data.get("geometry") or {})}

    # Inject per-node colors as deck tokens so symbol params (which
    # resolve to token names) work consistently with hex literals.
    node_colors: dict[str, str] = {}
    for node in [data["hub"], *data["satellites"]]:
        for key in ("outline_color", "label_color", "fill"):
            v = node.get(key)
            if isinstance(v, str) and v.startswith("#"):
                token_name = f"_c_{abs(hash(v)) % 100000:05d}"
                node_colors[token_name] = v

    colors = {**pal, **node_colors}

    symbols = _load_cell_symbols()
    objects = _build_objects(data, pal, geo)

    text_styles: dict[str, Any] = {
        "module_title": {
            "font": "primary", "size": 32, "weight": 400,
            "color": "title_color", "align": "left", "v_align": "top",
            "line_height": 38, "wrap": True,
        },
        "module_kicker": {
            "font": "primary", "size": 18, "weight": 400,
            "color": "kicker_color", "align": "left", "v_align": "middle",
        },
        "module_hub_label": {
            "font": "primary", "size": 30, "weight": 400,
            "color": (data["hub"].get("label_color") or "#E58938"),
            "align": "center", "v_align": "middle",
            "line_height": 36, "wrap": True,
        },
        "module_hub_detail_heading": {
            "font": "primary", "size": 16, "weight": 700,
            "color": (data["hub"].get("detail") or {}).get("heading_color") or (data["hub"].get("outline_color") or "#9E1A8C"),
            "align": "left", "v_align": "top",
        },
        "module_hub_detail_bullets": {
            "font": "primary", "size": 13, "weight": 400,
            "color": "#1A2B3E", "align": "left", "v_align": "top",
            "line_height": 18,
        },
        "module_sat_label_center": {
            "font": "primary", "size": 14, "weight": 400,
            "color": "#1A2B3E", "align": "center", "v_align": "middle",
            "line_height": 18, "wrap": True,
        },
        "module_sat_label_left": {
            "font": "primary", "size": 14, "weight": 400,
            "color": "#1A2B3E", "align": "left", "v_align": "middle",
            "line_height": 18, "wrap": True,
        },
        "module_sat_label_right": {
            "font": "primary", "size": 14, "weight": 400,
            "color": "#1A2B3E", "align": "right", "v_align": "middle",
            "line_height": 18, "wrap": True,
        },
        "module_icon_warning": {
            "font": "primary", "size": 22, "weight": 700,
            "color": "#1A1A1A", "align": "center", "v_align": "middle",
        },
        "module_icon_excel": {
            "font": "primary", "size": 24, "weight": 700,
            "color": "#FFFFFF", "align": "center", "v_align": "middle",
        },
        "module_icon_money": {
            "font": "primary", "size": 22, "weight": 700,
            "color": "#1A2B3E", "align": "center", "v_align": "middle",
        },
        "module_page_number": {
            "font": "primary", "size": 11, "weight": 400,
            "color": "page_number_color", "align": "center", "v_align": "middle",
        },
    }

    return {
        "dsl": "FrameGraph",
        "version": "1.2",
        "kind": "presentation-deck",
        "deck": {
            "canvas": {"size": [geo["canvas_w"], geo["canvas_h"]], "units": "px"},
            "tokens": {
                "colors": colors,
                "fonts": {
                    "primary": "Century Gothic, Avenir Next, Avenir, Futura, Arial, sans-serif",
                },
                "text_styles": text_styles,
            },
            "symbols": symbols,
        },
        "slides": [
            {
                "slide": 1,
                "id": "s_module_hub",
                "title": data["title"],
                "description": data.get("kicker_label") or "Module hub-and-spoke diagram.",
                "visual": {
                    "layers": [
                        {
                            "id": "module_hub",
                            "z": 10,
                            "objects": objects,
                        }
                    ]
                },
            }
        ],
    }


def main(argv: list[str]) -> int:
    """Read input YAML, build the deck, and write it to the output path.

    Expects ``argv == [prog, in_path, out_path]``; prints usage and
    returns 2 on a wrong argument count, otherwise returns 0.
    """
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    in_path = Path(argv[1])
    out_path = Path(argv[2])
    data = yaml.safe_load(in_path.read_text(encoding="utf-8"))
    deck = build_deck(data)
    out_path.write_text(
        yaml.dump(deck, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
