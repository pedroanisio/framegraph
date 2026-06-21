"""honeycomb_capability_map — data-driven generator.

Reads a compact input dict (see honeycomb_capability_map.schema.json),
computes per-cell positions on a flat-top hex tessellation, and emits a
complete FrameGraph presentation-deck dict ready to feed the renderer.

The deck inlines the three hex sub-symbols from honeycomb_cells.sym.yml
into `deck.symbols` so the standard `framegraph deck` pipeline can
expand them without depending on the `$symbols` directive (which the
deck composer does not yet auto-resolve).

CLI usage:
    python -m framegraph.lib.symbols.honeycomb.build IN_DATA.yml OUT_DECK.yml
    (e.g. examples/honeycomb-capability-map/{data,deck}.yml)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

# Defaults match the JSON schema's documented defaults.
DEFAULT_PALETTE: dict[str, str] = {
    "bg": "#FFFFFF",
    "title_color": "#1A2B3E",
    "kicker_color": "#9A9A9A",
    "dot_primary": "#E51A4C",
    "dot_secondary": "#1A2B3E",
    "dot_tertiary": "#C8C8C8",
    "header_fill": "#1A56B0",
    "leaf_fill": "#FFFFFF",
    "outline_core": "#1A56B0",
    "outline_extended": "#7FBA3A",
    "outline_future": "#7FBA3A",
    "header_text_color": "#FFFFFF",
    "leaf_text_color": "#1A2B3E",
    "page_number_color": "#9A9A9A",
}

DEFAULT_GEOMETRY: dict[str, float] = {
    "canvas_w": 1280,
    "canvas_h": 1000,
    "hex_w": 150,
    "hex_h": 130,
    "column_pitch_x": 130,
    "row_pitch_y": 135,
    "column_offset_y": 68,
    "left_margin": 60,
    "top_margin": 140,
}


def _load_cell_symbols() -> dict[str, Any]:
    """Load and return the hex sub-symbol bodies from the sym pack."""
    sym_path = Path(__file__).parent / "honeycomb_cells.sym.yml"
    pack = yaml.safe_load(sym_path.read_text(encoding="utf-8"))
    return dict(pack.get("symbols") or {})


def _column_offset(col_idx: int, declared: str) -> str:
    if declared == "auto":
        return "shifted" if col_idx % 2 == 1 else "top"
    return declared


def _variant_to_symbol(variant: str) -> str:
    return "hex_leaf_dashed" if variant == "future" else "hex_leaf_solid"


def _build_objects(
    data: dict[str, Any],
    pal: dict[str, str],
    geo: dict[str, float],
) -> list[dict[str, Any]]:
    """Compose the ordered list of slide objects (dots, title, kicker, cells, footer)."""
    objects: list[dict[str, Any]] = []
    hex_w, hex_h = geo["hex_w"], geo["hex_h"]

    # ── Decorator dots (top-left corner) ────────────────────────────
    objects.append(
        {
            "type": "ellipse",
            "id": "dot_primary",
            "box": [22, 14, 18, 18],
            "fill": "dot_primary",
        }
    )
    objects.append(
        {
            "type": "ellipse",
            "id": "dot_secondary",
            "box": [22, 44, 18, 18],
            "fill": "dot_secondary",
        }
    )
    objects.append(
        {
            "type": "ellipse",
            "id": "dot_tertiary",
            "box": [22, 92, 18, 18],
            "fill": "dot_tertiary",
        }
    )

    # ── Title + kicker ───────────────────────────────────────────────
    objects.append(
        {
            "type": "text",
            "id": "title",
            "box": [60, 12, geo["canvas_w"] - 80, 56],
            "text": data["title"],
            "style": "honeycomb_title",
        }
    )
    kicker = (data.get("kicker_label") or "").strip()
    if kicker:
        objects.append(
            {
                "type": "text",
                "id": "kicker",
                "box": [60, 88, geo["canvas_w"] - 80, 24],
                "text": kicker,
                "style": "honeycomb_kicker",
            }
        )

    # ── Honeycomb cells ──────────────────────────────────────────────
    for col_idx, col in enumerate(data["columns"]):
        offset = _column_offset(col_idx, col.get("offset") or "auto")
        col_x = geo["left_margin"] + col_idx * geo["column_pitch_x"]
        col_top_y = geo["top_margin"] + (geo["column_offset_y"] if offset == "shifted" else 0)

        # Header hex
        objects.append(
            {
                "type": "use",
                "id": f"col{col_idx}_header",
                "symbol": "hex_header",
                "box": [col_x, col_top_y, hex_w, hex_h],
                "label": col["header"],
                "params": {"header_fill": "header_fill"},
            }
        )

        # Leaf hexes — stacked below the header
        for item_idx, item in enumerate(col["items"]):
            cell_y = col_top_y + (item_idx + 1) * geo["row_pitch_y"]
            variant = (item.get("variant") or "core").lower()
            outline_token = {
                "core": "outline_core",
                "extended": "outline_extended",
                "future": "outline_future",
            }.get(variant, "outline_core")
            objects.append(
                {
                    "type": "use",
                    "id": f"col{col_idx}_item{item_idx}",
                    "symbol": _variant_to_symbol(variant),
                    "box": [col_x, cell_y, hex_w, hex_h],
                    "label": item["label"],
                    "params": {
                        "leaf_fill": "leaf_fill",
                        "outline_color": outline_token,
                    },
                }
            )

    # ── Optional footer page number ──────────────────────────────────
    page_num = data.get("page_number")
    if page_num not in (None, ""):
        objects.append(
            {
                "type": "text",
                "id": "page_number",
                "box": [0, geo["canvas_h"] - 28, geo["canvas_w"], 18],
                "text": str(page_num),
                "style": "honeycomb_page_number",
            }
        )

    return objects


def build_deck(data: dict[str, Any]) -> dict[str, Any]:
    """Map an input data dict to a complete FrameGraph deck dict."""
    pal: dict[str, str] = {**DEFAULT_PALETTE, **(data.get("palette") or {})}
    geo: dict[str, float] = {**DEFAULT_GEOMETRY, **(data.get("geometry") or {})}

    symbols = _load_cell_symbols()
    objects = _build_objects(data, pal, geo)

    text_styles: dict[str, Any] = {
        "honeycomb_title": {
            "font": "primary",
            "size": 32,
            "weight": 400,
            "color": "title_color",
            "align": "left",
            "v_align": "top",
            "line_height": 38,
            "wrap": True,
        },
        "honeycomb_kicker": {
            "font": "primary",
            "size": 18,
            "weight": 400,
            "color": "kicker_color",
            "align": "left",
            "v_align": "middle",
        },
        "honeycomb_header_text": {
            "font": "primary",
            "size": 13,
            "weight": 700,
            "color": "header_text_color",
            "align": "center",
            "v_align": "middle",
            "line_height": 16,
            "wrap": True,
        },
        "honeycomb_leaf_text": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "leaf_text_color",
            "align": "center",
            "v_align": "middle",
            "line_height": 14,
            "wrap": True,
        },
        "honeycomb_page_number": {
            "font": "primary",
            "size": 11,
            "weight": 400,
            "color": "page_number_color",
            "align": "center",
            "v_align": "middle",
        },
    }

    return {
        "dsl": "FrameGraph",
        "version": "1.2",
        "kind": "presentation-deck",
        "deck": {
            "canvas": {"size": [geo["canvas_w"], geo["canvas_h"]], "units": "px"},
            "tokens": {
                "colors": dict(pal),
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
                "id": "s_honeycomb",
                "title": data["title"],
                "description": (data.get("kicker_label") or "Honeycomb capability map."),
                "visual": {
                    "layers": [
                        {
                            "id": "honeycomb",
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
