"""Normalization tables for `static/refs/slides-patter-a.yml`.

This module is the single source of truth for the controlled
vocabulary refinement of the slide-pattern catalog. It is consumed
by `scripts/normalize_patterns.py` to rewrite the YAML in place.

Two outputs per zone:

- `size` becomes a `Literal["xs", "small", "medium", "large", "xl",
  "full", "equal", "variable", "contextual"]`.
- `position` decomposes into a structured `placement` mapping with
  fields `anchor` (one of 9 grid cells + ``"fullbleed"``), and
  optionally `relative` (relation + target zone role) and
  `region` (a named area inside a structured layout).

Anything that was role-leakage in the original `size` field
(e.g. ``"cards"``, ``"bar"``, ``"nodes"``) becomes a value of a new
optional `shape` field on the zone.

The dictionaries below cover every distinct value present in the
canonical 50-pattern catalog. Adding a new pattern that uses a
value not in these tables is a deliberate vocabulary extension —
update this file rather than the YAML.
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────
# SIZE — old free string → new {size, shape?}
# ─────────────────────────────────────────────────────────────────
#
# Values that genuinely encode size collapse to the controlled
# Size literal. Values that encode shape/role move to a `shape`
# field. Both can be set: e.g. ``"equal_cards"`` → size=equal,
# shape=card.

SIZE_NORMALIZATION: dict[str, dict[str, str]] = {
    # Pure size — direct mapping
    "xs": {"size": "xs"},
    "small": {"size": "small"},
    "medium": {"size": "medium"},
    "large": {"size": "large"},
    "xl": {"size": "xl"},
    "very_large": {"size": "xl"},
    "dominant": {"size": "xl"},
    "tall_block": {"size": "large"},
    "wide_block": {"size": "large"},
    "vertical_block": {"size": "medium"},
    "block": {"size": "medium"},
    "large_list": {"size": "large"},
    "highlighted": {"size": "large"},
    "thin": {"size": "small"},
    # Layout-relative size
    "full_width": {"size": "full"},
    "full_height": {"size": "full"},
    "full_length": {"size": "full"},
    "half_width": {"size": "medium"},
    "horizontal_band": {"size": "full"},
    # Grid behaviour
    "equal": {"size": "equal"},
    "grid": {"size": "equal"},
    "matrix_body": {"size": "equal"},
    "rows": {"size": "equal"},
    "columns": {"size": "equal"},
    "quadrant": {"size": "equal"},
    "quadrants_or_cells": {"size": "equal"},
    "stacked_segments": {"size": "equal"},
    "horizontal_steps": {"size": "equal"},
    "decreasing_width": {"size": "equal"},
    # Composer-decided
    "variable": {"size": "variable"},
    "contextual": {"size": "contextual"},
    "optional": {"size": "contextual"},
    "equal_or_featured": {"size": "equal"},
    # Shape-leakage values: size→medium, shape→<value>
    "cards": {"size": "medium", "shape": "card"},
    "card": {"size": "medium", "shape": "card"},
    "equal_cards": {"size": "equal", "shape": "card"},
    "cards_or_lists": {"size": "medium", "shape": "card"},
    "list": {"size": "medium", "shape": "list"},
    "text": {"size": "medium", "shape": "text"},
    "numeric": {"size": "medium", "shape": "metric"},
    "icons": {"size": "small", "shape": "icon"},
    "lines": {"size": "small", "shape": "connector"},
    "arrows": {"size": "small", "shape": "connector"},
    "connectors": {"size": "small", "shape": "connector"},
    "bar": {"size": "medium", "shape": "bar"},
    "axis": {"size": "full", "shape": "axis"},
    "node": {"size": "medium", "shape": "node"},
    "nodes": {"size": "medium", "shape": "node"},
    "terminal_nodes": {"size": "medium", "shape": "node"},
    "markers": {"size": "small", "shape": "marker"},
    "dots_or_labels": {"size": "small", "shape": "marker"},
    "line_or_icons": {"size": "small", "shape": "icon"},
    "container": {"size": "large", "shape": "container"},
    "sequence": {"size": "large", "shape": "sequence"},
    "button_like": {"size": "small", "shape": "button"},
}


# ─────────────────────────────────────────────────────────────────
# POSITION — old free string → structured placement
# ─────────────────────────────────────────────────────────────────
#
# Each placement is a dict with one or more of:
#   - anchor: {h: left|center|right, v: top|middle|bottom} | "fullbleed"
#   - region: a named area inside a structured layout (matrix_body,
#     swimlanes, etc.) — for layouts where 9-cell anchoring doesn't
#     map cleanly
#   - relative: {relation, target} — for "below_title" style
#
# Disjunctive originals like "right_or_bottom" are resolved to a
# single canonical placement (the first listed alternative).

# Helper aliases for readability below.
def _A(h: str, v: str) -> dict[str, Any]:
    return {"anchor": {"h": h, "v": v}}


def _F() -> dict[str, Any]:
    return {"anchor": "fullbleed"}


def _R(relation: str, target: str) -> dict[str, Any]:
    return {"relative": {"relation": relation, "target": target}}


def _Reg(name: str) -> dict[str, Any]:
    return {"region": name}


POSITION_NORMALIZATION: dict[str, dict[str, Any]] = {
    # ── 9-cell anchors ──────────────────────────────────────────
    "top": _A("center", "top"),
    "bottom": _A("center", "bottom"),
    "left": _A("left", "middle"),
    "right_side": _A("right", "middle"),
    "center": _A("center", "middle"),
    "top_left": _A("left", "top"),
    "top_right": _A("right", "top"),
    "top_center": _A("center", "top"),
    "bottom_left": _A("left", "bottom"),
    "bottom_right": _A("right", "bottom"),
    "far_left": _A("left", "middle"),
    "far_right": _A("right", "middle"),
    # ── Column / axis aliases ────────────────────────────────────
    "left_column": _A("left", "middle"),
    "right_column": _A("right", "middle"),
    "center_column": _A("center", "middle"),
    "left_axis": _A("left", "middle"),
    "top_axis": _A("center", "top"),
    "vertical_axis": _A("left", "middle"),
    "horizontal_axis": _A("center", "bottom"),
    "edges": _A("left", "middle"),  # convention: rendered on all edges
    # ── Grid / row aliases ──────────────────────────────────────
    "top_row": _A("center", "top"),
    "bottom_row": _A("center", "bottom"),
    "row_1": _Reg("row_1"),
    "row_2": _Reg("row_2"),
    "row_3": _Reg("row_3"),
    "middle_grid": _A("center", "middle"),
    "center_grid": _A("center", "middle"),
    "center_horizontal": _A("center", "middle"),
    "center_vertical": _A("center", "middle"),
    "center_vertical_or_grid": _A("center", "middle"),
    "center_or_right": _A("center", "middle"),
    "center_or_full_bleed": _A("center", "middle"),
    "left_or_center": _A("left", "middle"),
    "left_or_top": _A("left", "top"),
    "left_or_bottom": _A("left", "bottom"),
    "right_or_bottom": _A("right", "bottom"),
    "bottom_or_left": _A("center", "bottom"),
    "bottom_or_right": _A("right", "bottom"),
    "side_or_bottom": _A("right", "bottom"),
    "stacked_or_grouped": _A("center", "middle"),
    # ── 9-block canvas (Business Model Canvas) ──────────────────
    "upper_left_center": _A("left", "top"),
    "upper_right_center": _A("right", "top"),
    "lower_left_center": _A("left", "bottom"),
    "lower_right_center": _A("right", "bottom"),
    "lower_section": _A("center", "bottom"),
    "lower_levels": _A("center", "bottom"),
    "lower_right": _A("right", "bottom"),
    "middle_levels": _A("center", "middle"),
    "middle_columns": _A("center", "middle"),
    "middle_bars": _A("center", "middle"),
    # ── Disjunctive corners — pick first ─────────────────────────
    "bottom_left_or_bottom_right": _A("left", "bottom"),
    "top_or_bottom_corner": _A("right", "top"),
    "left_panel_or_bottom": _A("left", "middle"),
    "side_panel_or_callouts": _A("right", "middle"),
    "background_or_edge": _A("center", "middle"),
    "left_or_background": _A("left", "middle"),
    "far_right_or_bottom": _A("right", "middle"),
    "left_to_right_or_top_to_bottom": _A("left", "middle"),
    "horizontal_sequence": _A("center", "middle"),
    # ── Region (named structured area) ──────────────────────────
    "matrix_body": _Reg("matrix_body"),
    "grid_body": _Reg("matrix_body"),
    "background_grid": _Reg("matrix_body"),
    "highlighted_quadrant": _Reg("quadrant"),
    "quadrant_space": _Reg("quadrant"),
    "swimlanes_or_columns": _Reg("swimlanes"),
    "canvas_or_matrix": _Reg("canvas"),
    "background": _Reg("background"),
    "table_cells": _Reg("matrix_body"),
    "leftmost_bar": _Reg("waterfall_start"),
    "rightmost_bar": _Reg("waterfall_end"),
    "on_map": _Reg("map_overlay"),
    "funnel_stages": _Reg("funnel_body"),
    # ── Relative — relation + target zone role ──────────────────
    "below_title": _R("below", "title"),
    "below_numbers": _R("below", "metric_numbers"),
    "below_photos": _R("below", "photos"),
    "below_message": _R("below", "thank_you_message"),
    "below_steps": _R("below", "process_steps"),
    "below_each_milestone": _R("below", "milestone_sequence"),
    "above_or_below_steps": _R("above", "demo_steps"),
    "above_and_below_axis": _R("around", "timeline_axis"),
    "around_center": _R("around", "central_system"),
    "around_screenshot": _R("around", "screenshot"),
    "around_chart_or_right": _R("around", "chart"),
    "around_system": _R("around", "central_system"),
    "around_circle": _R("around", "circular_flow"),
    "between_nodes": _R("between", "nodes"),
    "between_steps": _R("between", "process_steps"),
    "between_components": _R("between", "components"),
    "between_center_and_actors": _R("between", "central_system"),
    "inside_layers": _R("inside", "system_layers"),
    "inside_lanes": _R("inside", "actors"),
    "inside_phases": _R("inside", "phases"),
    "inside_steps": _R("inside", "demo_steps"),
    "inside_cards": _R("inside", "recommendation_cards"),
    "inside_or_near_circles": _R("inside", "circle_a"),
    "inside_or_right_of_stages": _R("inside", "funnel_stages"),
    "near_chart_highlight": _R("near", "chart"),
    "near_inflection_point": _R("near", "line_chart"),
    "near_largest_or_smallest_bar": _R("near", "bar_chart"),
    "near_numbers": _R("near", "metric_numbers"),
    "on_each_milestone": _R("on", "milestone_sequence"),
    "outward_from_root": _R("around", "root_decision"),
    "surrounding_or_below": _R("around", "solution_name"),
    "left_overlap": _R("left_of", "intersection"),
    "right_overlap": _R("right_of", "intersection"),
    "center_overlap": _R("inside", "intersection"),
    "left_of_each_card": _R("left_of", "recommendation_cards"),
    "top_of_each_card": _R("inside", "profile_cards"),
    "top_of_each_column": _R("inside", "pricing_columns"),
    "middle_of_each_column": _R("inside", "pricing_columns"),
    "bottom_of_each_column": _R("inside", "pricing_columns"),
    "center_of_donut_or_right_panel": _R("inside", "chart"),
    "bottom_or_near_image": _R("near", "persona_image"),
    "along_axis": _R("on", "timeline_axis"),
    "left_or_inside": _A("left", "middle"),
}
