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
    # ── Catalog B additions ──────────────────────────────────────
    # Card variants — size + shape=card (semantic in role)
    "metric_card": {"size": "medium", "shape": "card"},
    "metric_cards": {"size": "medium", "shape": "card"},
    "status_card": {"size": "medium", "shape": "card"},
    "comparison_cards": {"size": "medium", "shape": "card"},
    "highlighted_card": {"size": "medium", "shape": "card"},
    "value_cards": {"size": "medium", "shape": "card"},
    "small_cards": {"size": "small", "shape": "card"},
    # Tree/graph nodes — size + shape=node
    "large_node": {"size": "large", "shape": "node"},
    "large_nodes": {"size": "large", "shape": "node"},
    "medium_nodes": {"size": "medium", "shape": "node"},
    "small_nodes": {"size": "small", "shape": "node"},
    "smaller_nodes": {"size": "small", "shape": "node"},
    "tree_nodes": {"size": "medium", "shape": "node"},
    "branching_nodes": {"size": "medium", "shape": "node"},
    # Matrix cells — size + shape=cell (new shape)
    "cells": {"size": "equal", "shape": "cell"},
    "metric_cells": {"size": "equal", "shape": "cell"},
    "score_cells": {"size": "equal", "shape": "cell"},
    "text_cells": {"size": "equal", "shape": "cell"},
    "heatmap_cells": {"size": "equal", "shape": "cell"},
    "symbols": {"size": "small", "shape": "cell"},
    # Bar/chart variants
    "bars": {"size": "medium", "shape": "bar"},
    "horizontal_bars": {"size": "medium", "shape": "bar"},
    "waterfall_steps": {"size": "equal", "shape": "bar"},
    "wide_chart": {"size": "full", "shape": "chart"},
    "chart_or_blocks": {"size": "large", "shape": "chart"},
    "bars_or_cards": {"size": "medium", "shape": "bar"},
    # Block variants
    "blocks": {"size": "medium", "shape": "block"},
    "equal_block": {"size": "equal", "shape": "block"},
    "grouped_blocks": {"size": "equal", "shape": "block"},
    "wide_bands": {"size": "full", "shape": "block"},
    # Layout-grouping
    "grouped_sections": {"size": "equal"},
    "equal_columns": {"size": "equal"},
    "horizontal_levels": {"size": "equal"},
    "equal_or_progressive": {"size": "equal"},
    # Free-text on a card
    "labels": {"size": "small", "shape": "text"},
    "highlight": {"size": "medium", "shape": "card"},
    "highlighted_area": {"size": "medium"},
    "summary": {"size": "medium", "shape": "text"},
    # Tables / dashboards
    "table": {"size": "large", "shape": "table"},
    "table_or_equation_flow": {"size": "large", "shape": "table"},
    "timeline": {"size": "full", "shape": "timeline"},
    "metrics": {"size": "medium", "shape": "metric"},
    "metric": {"size": "medium", "shape": "metric"},
    # Markers
    "marker": {"size": "small", "shape": "marker"},
    "bubbles": {"size": "medium", "shape": "marker"},
    "callout": {"size": "medium", "shape": "card"},
    # Edge sizes
    "tiny": {"size": "xs"},
    "largest": {"size": "xl"},
    "smallest": {"size": "xs"},
    # ── Catalog C additions ──────────────────────────────────────
    # Box shape — distinct from block (boxes have outline emphasis)
    "box": {"size": "medium", "shape": "box"},
    "large_box": {"size": "large", "shape": "box"},
    # Card variants
    "medium_card": {"size": "medium", "shape": "card"},
    "large_card": {"size": "large", "shape": "card"},
    "action_cards": {"size": "medium", "shape": "card"},
    # Cell variants — extend the cell shape
    "action_cells": {"size": "equal", "shape": "cell"},
    "scale_cells": {"size": "equal", "shape": "cell"},
    "icon_cells": {"size": "equal", "shape": "cell"},
    # Chart variants
    "chart": {"size": "large", "shape": "chart"},
    "large_chart": {"size": "large", "shape": "chart"},
    "chart_or_tree": {"size": "large", "shape": "chart"},
    "table_or_chart": {"size": "large", "shape": "chart"},
    # Band shape — full-width strip (distinct from block)
    "band": {"size": "full", "shape": "band"},
    "banner": {"size": "full", "shape": "band"},
    "highlighted_band": {"size": "full", "shape": "band"},
    "vertical_band": {"size": "full", "shape": "band"},
    "horizontal_bands": {"size": "full", "shape": "band"},
    "stacked_bands": {"size": "full", "shape": "band"},
    # Waterfall — naming consistency with catalog B
    "waterfall_step": {"size": "equal", "shape": "bar"},
    # Node groupings
    "grouped_nodes": {"size": "medium", "shape": "node"},
    # Lists / labels
    "bullet_lists": {"size": "medium", "shape": "list"},
    "lists": {"size": "medium", "shape": "list"},
    "label": {"size": "small", "shape": "text"},
    "tags": {"size": "small", "shape": "text"},
    # Markers + composite
    "bubbles_or_logos": {"size": "medium", "shape": "marker"},
    "markers_or_rows": {"size": "medium", "shape": "marker"},
    "labeled_lines": {"size": "small", "shape": "connector"},
    # Layout-grouping additions
    "equal_blocks": {"size": "equal", "shape": "block"},
    "stacked_blocks": {"size": "equal", "shape": "block"},
    "connected_blocks": {"size": "equal", "shape": "block"},
    # Pattern-internal flow elements
    "callouts": {"size": "small", "shape": "card"},
    "highlighted_paths": {"size": "medium", "shape": "connector"},
    "metric_row": {"size": "full", "shape": "metric"},
    "small_labels": {"size": "small", "shape": "text"},
    "angled_groups": {"size": "medium", "shape": "node"},
    "arrows_or_table": {"size": "medium", "shape": "connector"},
    "bars_or_metrics": {"size": "medium", "shape": "bar"},
    "cube_or_matrix": {"size": "large", "shape": "chart"},
    "wedge_or_card": {"size": "medium", "shape": "card"},
    "emphasized": {"size": "large"},
    # ── Catalog D additions ──────────────────────────────────────
    # Card variants (continued proliferation — all collapse to shape=card)
    "grouped_cards": {"size": "equal", "shape": "card"},
    "wide_cards": {"size": "large", "shape": "card"},
    "smaller_cards": {"size": "small", "shape": "card"},
    "highlighted_cards": {"size": "medium", "shape": "card"},
    "sequence_cards": {"size": "equal", "shape": "card"},
    "status_cards": {"size": "medium", "shape": "card"},
    "cards_or_heatmap": {"size": "equal", "shape": "card"},
    # Band / pillar variants — all full-width strips
    "wide_band": {"size": "full", "shape": "band"},
    "dominant_band": {"size": "full", "shape": "band"},
    "top_band": {"size": "full", "shape": "band"},
    "base_band": {"size": "full", "shape": "band"},
    "bottom_band": {"size": "full", "shape": "band"},
    "vertical_bands": {"size": "full", "shape": "band"},
    "vertical_pillars": {"size": "equal", "shape": "band"},
    "explanation_band": {"size": "full", "shape": "band"},
    # Cell variants
    "status_cells": {"size": "equal", "shape": "cell"},
    "issue_cells": {"size": "equal", "shape": "cell"},
    "timeline_cells": {"size": "equal", "shape": "cell"},
    # Block variants
    "large_block": {"size": "large", "shape": "block"},
    "highlighted_block": {"size": "large", "shape": "block"},
    # List / text variants
    "highlighted_list": {"size": "medium", "shape": "list"},
    "ranked_list": {"size": "medium", "shape": "list"},
    "stacked_labels": {"size": "small", "shape": "text"},
    "short_text": {"size": "small", "shape": "text"},
    "text_snippets": {"size": "small", "shape": "text"},
    "small_notes": {"size": "small", "shape": "text"},
    "headline": {"size": "large", "shape": "text"},
    "tag": {"size": "small", "shape": "text"},
    # Chart / dashboard variants
    "charts": {"size": "equal", "shape": "chart"},
    "dashboard_grid": {"size": "large", "shape": "chart"},
    "horizontal_scale": {"size": "full", "shape": "axis"},
    "progress_bar": {"size": "full", "shape": "progress"},
    # Segment / ring shapes (framework wheels)
    "segments": {"size": "equal", "shape": "block"},
    "equal_segments": {"size": "equal", "shape": "block"},
    # Containers (agile-at-scale tribes/domains)
    "containers": {"size": "equal", "shape": "container"},
    # Mixed / variant grab-bag — keep semantics in role
    "action_box": {"size": "medium", "shape": "box"},
    "bubbles_or_rows": {"size": "medium", "shape": "marker"},
    "markers_or_blocks": {"size": "medium", "shape": "marker"},
    "labeled_arrows": {"size": "small", "shape": "connector"},
    "quotes_or_metrics": {"size": "medium", "shape": "text"},
    "flow": {"size": "large", "shape": "sequence"},
    # Backgrounds / decorative
    "subtle_large": {"size": "large"},
    "tall": {"size": "large"},
    # ── Catalog E additions ──────────────────────────────────────
    # Card variants (continued)
    "connected_cards": {"size": "equal", "shape": "card"},
    "flow_cards": {"size": "equal", "shape": "card"},
    "cards_or_bubbles": {"size": "equal", "shape": "card"},
    # Block / pillar variants
    "layered_blocks": {"size": "equal", "shape": "block"},
    "equal_pillars": {"size": "equal", "shape": "band"},
    # Cell / row variants
    "numeric_cells": {"size": "equal", "shape": "cell"},
    "symbols_or_cells": {"size": "equal", "shape": "cell"},
    "rows_or_markers": {"size": "equal", "shape": "cell"},
    "rows_or_cards": {"size": "equal", "shape": "card"},
    # List / text variants
    "notes": {"size": "small", "shape": "text"},
    "metric_labels": {"size": "small", "shape": "metric"},
    "rank_labels": {"size": "small", "shape": "text"},
    "note_band": {"size": "full", "shape": "band"},
    "summary_row": {"size": "full", "shape": "band"},
    "action_list": {"size": "medium", "shape": "list"},
    # Chart / composite variants
    "chart_or_table": {"size": "large", "shape": "chart"},
    "network_or_table": {"size": "large", "shape": "chart"},
    "mini_org_chart": {"size": "small", "shape": "chart"},
    "mini_roadmap": {"size": "small", "shape": "chart"},
    "profile": {"size": "medium", "shape": "chart"},
    # Funnel / sequence
    "decreasing_segments": {"size": "equal", "shape": "block"},
    "curve_or_icons": {"size": "medium", "shape": "chart"},
    # Hierarchy is a node tree
    "hierarchy": {"size": "large", "shape": "node"},
    # Highlighted variants
    "highlighted_metric": {"size": "large", "shape": "metric"},
    # Layout sizing
    "widest": {"size": "full"},
    "timeline_columns": {"size": "equal", "shape": "timeline"},
    "timeline_or_table": {"size": "large", "shape": "timeline"},
    "columns_or_bands": {"size": "equal", "shape": "band"},
    # Loop sizes
    "circular_flow": {"size": "large", "shape": "sequence"},
    # ── Catalog F additions ──────────────────────────────────────
    # Card variants (continued)
    "dominant_card": {"size": "xl", "shape": "card"},
    "wide_card": {"size": "large", "shape": "card"},
    "action_card": {"size": "medium", "shape": "card"},
    "compact_cards": {"size": "small", "shape": "card"},
    "muted_cards": {"size": "medium", "shape": "card"},
    # Block / band variants
    "highlighted_blocks": {"size": "equal", "shape": "block"},
    "medium_band": {"size": "medium", "shape": "band"},
    "narrow_band": {"size": "small", "shape": "band"},
    "label_band": {"size": "full", "shape": "band"},
    # Text variants
    "text_block": {"size": "medium", "shape": "text"},
    "short_labels": {"size": "small", "shape": "text"},
    "small_label": {"size": "small", "shape": "text"},
    "highlighted_label": {"size": "small", "shape": "text"},
    "warning_notes": {"size": "small", "shape": "text"},
    # Metric variant
    "dominant_metric": {"size": "xl", "shape": "metric"},
    # Node variants
    "highlighted_node": {"size": "large", "shape": "node"},
    "highlighted_nodes": {"size": "large", "shape": "node"},
    "small_node": {"size": "small", "shape": "node"},
    # Connector variants
    "directed_edges": {"size": "small", "shape": "connector"},
    "line": {"size": "small", "shape": "connector"},
    "vertical_line": {"size": "small", "shape": "connector"},
    "arrow_or_callout": {"size": "small", "shape": "connector"},
    # Composite shape variants
    "ladder": {"size": "large", "shape": "chart"},
    "horizontal_flow": {"size": "full", "shape": "sequence"},
    "funnel_or_rules": {"size": "large", "shape": "chart"},
    "status_table": {"size": "medium", "shape": "table"},
    # Layout grouping
    "grouped_areas": {"size": "equal", "shape": "container"},
    # Edge sizes
    "narrow": {"size": "small"},
    # ── Catalog G additions ──────────────────────────────────────
    # List / checklist / tree shapes
    "checklist": {"size": "medium", "shape": "list"},
    "tree": {"size": "large", "shape": "node"},
    "wide_tree": {"size": "full", "shape": "node"},
    "rule_cards": {"size": "equal", "shape": "card"},
    "scenario_cards": {"size": "equal", "shape": "card"},
    "shortlist_cards": {"size": "equal", "shape": "card"},
    # Chart / region variants
    "dominant_chart": {"size": "xl", "shape": "chart"},
    "large_region": {"size": "large"},
    "central_area": {"size": "large"},
    "surrounding_area": {"size": "large"},
    # Path / branch / sequence
    "branching_paths": {"size": "large", "shape": "node"},
    "sequential_filters": {"size": "equal", "shape": "sequence"},
    "parallel_rows": {"size": "equal"},
    "examples": {"size": "small", "shape": "card"},
    # Markers / highlighting
    "vertical_marker": {"size": "small", "shape": "marker"},
    "shaded_ranges": {"size": "medium"},
    "highlighted_cells": {"size": "equal", "shape": "cell"},
    "metric_band": {"size": "full", "shape": "band"},
    # Special compound shapes
    "dominant_node": {"size": "xl", "shape": "node"},
    "edges": {"size": "small", "shape": "connector"},
    "formula_or_statement": {"size": "medium", "shape": "text"},
    "full_area": {"size": "full"},
    "large_group": {"size": "large", "shape": "container"},
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
    # ── Catalog B additions ──────────────────────────────────────
    # Anchor synonyms
    "middle": _A("center", "middle"),
    "right": _A("right", "middle"),
    "top_or_left": _A("left", "top"),
    "outer_or_top": _A("center", "top"),
    "inner_or_bottom": _A("center", "bottom"),
    "center_or_top_right": _A("right", "top"),
    "leftmost": _A("left", "middle"),
    "rightmost": _A("right", "middle"),
    "footer": _A("center", "bottom"),
    "bottom_or_side": _A("center", "bottom"),
    "stacked_vertical": _A("center", "middle"),
    "columns_or_rows": _A("left", "middle"),
    "rows_or_columns": _A("left", "middle"),
    # Panels — semantic side anchors
    "left_panel": _A("left", "middle"),
    "right_panel": _A("right", "middle"),
    "side_panel": _A("right", "middle"),
    # Sub-grid anchors
    "center_left": _A("center", "middle"),
    "center_right": _A("center", "middle"),
    "middle_left": _A("left", "middle"),
    "middle_right": _A("right", "middle"),
    "right_center": _A("right", "middle"),
    "center_columns": _A("center", "middle"),
    # Axis anchors
    "bottom_axis": _A("center", "bottom"),
    "bottom_layer": _A("center", "bottom"),
    "chart_center": _A("center", "middle"),
    # Region — named structured areas
    "canvas": _Reg("canvas"),
    "roadmap_body": _Reg("roadmap_body"),
    "timeline_body": _Reg("timeline_body"),
    "center_timeline": _Reg("timeline_body"),
    "quadrant_labels": _Reg("quadrant"),
    "highlighted_nodes_or_links": _Reg("highlighted"),
    "near_largest_pools": _Reg("highlighted"),
    "across_pillars": _Reg("integration_layer"),
    "across_timeline": _Reg("timeline_body"),
    "on_scale": _Reg("scale_body"),
    # Relative — between
    "between_columns": _R("between", "columns"),
    "between_layers": _R("between", "layers"),
    "between_levels": _R("between", "levels"),
    "between_waves": _R("between", "wave_blocks"),
    # Relative — inside
    "inside_each_category": _R("inside", "mece_categories"),
    "inside_each_wave": _R("inside", "wave_blocks"),
    "inside_domains": _R("inside", "capability_domains"),
    "within_theme_sections": _R("inside", "strategic_themes"),
    # Relative — below / on
    "below_each_category": _R("below", "growth_categories"),
    "below_each_wave": _R("below", "wave_blocks"),
    "below_curve": _R("below", "adoption_curve"),
    "bottom_of_cards": _R("below", "principles"),
    "along_time_axis": _R("on", "time_periods"),
    # Card-internal anchors
    "card_top_or_corner": _R("inside", "initiative_cards"),
    "card_bottom": _R("inside", "initiative_cards"),
    "card_corner_or_right_column": _R("inside", "findings"),
    "block_color_or_label": _R("inside", "capabilities"),
    # ── Catalog C additions ──────────────────────────────────────
    # Anchor synonyms / disjunctions
    "upper_left": _A("left", "top"),
    "upper_right": _A("right", "top"),
    "below": _A("center", "bottom"),
    "columns": _A("center", "middle"),
    "connectors": _A("center", "middle"),
    "highlighted_area": _Reg("highlighted"),
    "highlighted_nodes": _Reg("highlighted"),
    "highlighted_step": _Reg("highlighted"),
    "top_or_side": _A("center", "top"),
    "right_panel_or_bottom": _A("right", "middle"),
    "labels_or_right_column": _A("right", "middle"),
    "matrix_body_or_left_axis": _Reg("matrix_body"),
    # Layered architecture anchors (catalog C #150 specifically)
    "top_layer": _A("center", "top"),
    "upper_middle_layer": _A("center", "top"),
    "lower_middle_layer": _A("center", "middle"),
    "side_or_cross_cutting_layer": _A("right", "middle"),
    "top_or_bottom_bands": _A("center", "top"),
    # Sequence / flow positions
    "horizontal_chain": _A("center", "middle"),
    "center_sequence": _A("center", "middle"),
    "center_vertical_stack": _A("center", "middle"),
    "center_grid_or_vertical_list": _A("center", "middle"),
    "middle_steps": _A("center", "middle"),
    "right_of_bars": _A("right", "middle"),
    # Region — named structured areas
    "surrounding_clusters": _Reg("ecosystem_outer"),
    # Relative — between
    "between_cards": _R("between", "narrative_steps"),
    # Relative — inside groups
    "inside_categories": _R("inside", "fact_categories"),
    "inside_segments": _R("inside", "industry_segments"),
    "inside_waves": _R("inside", "migration_waves"),
    # Relative — above/below structural elements
    "above_and_below_spine": _R("around", "main_spine"),
    "along_branches": _R("on", "cause_branches"),
    "below_segments": _R("below", "industry_segments"),
    "callouts_above_or_below": _R("around", "workflow_steps"),
    # Relative — on
    "on_callouts": _R("inside", "pain_points"),
    "on_chart": _R("on", "peer_distribution"),
    "on_curve": _R("on", "profitability_curve"),
    "on_process_map": _R("on", "process_map"),
    # Card-internal anchors (zone-internal subdivisions)
    "card_header": _R("inside", "segments"),
    "card_body": _R("inside", "segments"),
    "card_footer": _R("inside", "segments"),
    "card_corner": _R("inside", "debt_items"),
    "card_tags": _R("inside", "application_groups"),
    # ── Catalog D additions ──────────────────────────────────────
    # Layered-architecture anchor synonyms
    "upper_middle": _A("center", "top"),
    "lower_middle": _A("center", "middle"),
    "middle_layer": _A("center", "middle"),
    "top_layers": _A("center", "top"),
    "center_left_to_right": _A("center", "middle"),
    # Row / column synonyms
    "middle_row": _A("center", "middle"),
    "center_row": _A("center", "middle"),
    "top_of_columns": _A("center", "top"),
    "column_body": _A("center", "middle"),
    "right_column_or_bottom": _A("right", "middle"),
    "bottom_or_far_right": _A("right", "bottom"),
    # Callout / disjunctive anchors
    "top_or_bottom_callout": _A("center", "bottom"),
    "top_or_bottom_overlay": _A("center", "top"),
    "top_row_or_left_axis": _A("center", "top"),
    "left_or_side_panel": _A("left", "middle"),
    "center_or_bottom_band": _A("center", "bottom"),
    "background_or_center": _A("center", "middle"),
    # House diagram (#212) — semantic anchors
    "roof": _A("center", "top"),
    "bottom_band": _A("center", "bottom"),
    # Side / cross-cutting
    "side_or_cross_cutting": _A("right", "middle"),
    "side_vertical_band": _A("right", "middle"),
    # Region — named structured areas
    "surrounding_ring": _Reg("ring"),
    "surrounding_nodes": _Reg("ring"),
    "grouped_regions": _Reg("groupings"),
    "circular_flow": _Reg("ring"),
    "around_cycle_or_bottom": _Reg("ring"),
    "heatmap_body": _Reg("matrix_body"),
    "matrix_or_table_body": _Reg("matrix_body"),
    "matrix_body_or_timeline": _Reg("matrix_body"),
    "timeline_overlay": _Reg("timeline_body"),
    "map_or_canvas": _Reg("canvas"),
    "quadrant_or_label": _Reg("quadrant"),
    # Bubble / marker hybrid positions
    "bubble_color_or_tag": _Reg("highlighted"),
    "bubble_size_or_tag": _Reg("highlighted"),
    "marker_tag_or_side_panel": _Reg("highlighted"),
    # Relative — inside containers
    "inside_each_card": _R("inside", "imperative_cards"),
    "inside_columns": _R("inside", "lever_categories"),
    "inside_sections": _R("inside", "diligence_dimensions"),
    # Relative — below
    "below_each_pillar": _R("below", "pillars"),
    # Relative — on flow / map
    "on_flow_or_below": _R("on", "process_flow"),
    "on_nodes_or_routes": _R("on", "supply_nodes"),
    "above_flow": _R("above", "process_flow"),
    # Card-internal anchor (continued)
    "card_header_or_corner": _R("inside", "themes"),
    "card_tag": _R("inside", "value_levers"),
    # Axis variants
    "vertical_axis_or_metric": _A("left", "middle"),
    "horizontal_axis_or_tag": _A("center", "bottom"),
    # Bar-internal
    "inside_bars_or_tags": _R("inside", "modernization_timeline"),
    # ── Catalog E additions ──────────────────────────────────────
    # Timeline anchor synonyms
    "horizontal_timeline": _A("center", "middle"),
    "top_timeline": _A("center", "top"),
    "below_timeline": _A("center", "bottom"),
    "above_steps": _A("center", "top"),
    "highlighted_points": _Reg("highlighted"),
    "highlighted_stage_edges": _Reg("highlighted"),
    "highlighted_steps": _Reg("highlighted"),
    # Disjunctive anchors / panels
    "left_axis_or_matrix_body": _A("left", "middle"),
    "left_axis_or_labels": _A("left", "middle"),
    "matrix_body_or_table_rows": _Reg("matrix_body"),
    "quadrant_labels_or_right_panel": _A("right", "middle"),
    "bottom_or_right_panel": _A("right", "bottom"),
    "bottom_or_tag": _A("center", "bottom"),
    "rightmost_or_bottom": _A("right", "bottom"),
    "top_or_bottom": _A("center", "top"),
    "top_or_center": _A("center", "top"),
    "top_or_bottom_loop": _A("center", "bottom"),
    # Stage / pipeline positions
    "horizontal_pipeline_or_funnel": _A("center", "middle"),
    "between_stages": _R("between", "innovation_stages"),
    "right_of_stages": _R("right_of", "funnel_stages"),
    "inside_stages": _R("inside", "innovation_stages"),
    # Score / column positions
    "score_column_or_vertical_axis": _A("left", "middle"),
    "score_column_or_horizontal_axis": _A("center", "bottom"),
    "column_or_card_tag": _R("inside", "strategic_themes"),
    # Card / theme internals
    "card_top": _R("inside", "design_options"),
    "inside_themes": _R("inside", "strategic_themes"),
    "inside_groups": _R("inside", "criteria_groups"),
    "bubble_size_or_metric_column": _Reg("highlighted"),
    "columns_or_layers": _A("center", "middle"),
    # Swimlane / lane positions
    "upper_swimlanes": _A("center", "top"),
    "lower_swimlanes": _A("center", "bottom"),
    "bottom_lane": _A("center", "bottom"),
    "board_body": _Reg("matrix_body"),
    # Network / cascade positions
    "middle_network": _A("center", "middle"),
    "side_connectors": _A("right", "middle"),
    "side_panels": _A("right", "middle"),
    # Chart-axes positions
    "chart_axes_or_rows": _A("left", "middle"),
    "chart_or_left_column": _A("left", "middle"),
    "chart_or_right_column": _A("right", "middle"),
    # Standalone callouts
    "callouts": _Reg("highlighted"),
    "surrounding_cards": _R("around", "customer_promise"),
    # ── Catalog F additions ──────────────────────────────────────
    # Ladder anchors (#281, #304 — vertical ladder rungs)
    "top_rung": _A("center", "top"),
    "upper_middle_rung": _A("center", "top"),
    "lower_middle_rung": _A("center", "middle"),
    "bottom_rung": _A("center", "bottom"),
    "on_ladder_rungs": _R("on", "evidence_levels"),
    # Cluster / zone anchors
    "left_cluster": _A("left", "middle"),
    "right_cluster": _A("right", "middle"),
    "left_zone": _A("left", "middle"),
    "center_zone": _A("center", "middle"),
    "right_zone": _A("right", "middle"),
    "inside_zones": _R("inside", "trust_zones"),
    "between_zones": _R("between", "trust_zones"),
    # Tension / triangle anchors (#288)
    "inside_tension_space": _A("center", "middle"),
    "bottom_or_top": _A("center", "bottom"),
    # Graph / canvas regions
    "graph_canvas": _Reg("canvas"),
    "clustered_canvas": _Reg("canvas"),
    "background_regions": _Reg("background"),
    "chart_body": _Reg("matrix_body"),
    "loop_annotations": _Reg("highlighted"),
    # Highlighting positions
    "highlighted_marker": _Reg("highlighted"),
    "highlighted_rows": _Reg("highlighted"),
    "overlaid_curve": _Reg("highlighted"),
    # Flow-internal anchors
    "horizontal_flow": _A("center", "middle"),
    "above_or_below_flow": _R("above", "process_or_system_flow"),
    "inserted_between_steps": _R("between", "automated_steps"),
    "on_flow_nodes": _R("on", "system_or_process_flow"),
    "near_markers": _R("near", "control_points"),
    "on_crossings": _R("on", "boundary_crossings"),
    # Tile / cluster header positions
    "tile_footer": _R("inside", "insight_tiles"),
    "cluster_headers": _R("inside", "pattern_clusters"),
    # ── Catalog G additions ──────────────────────────────────────
    # Row-position synonyms (#327 Epistemic Status — 5-tier stack)
    "second_row": _A("center", "top"),
    "third_row": _A("center", "middle"),
    "fourth_row": _A("center", "middle"),
    # Path tree positions (#359 Exception Handling)
    "left_path": _A("left", "middle"),
    "center_path": _A("center", "middle"),
    "right_path": _A("right", "middle"),
    "on_paths": _R("on", "decision_paths"),
    # Header positions (#366 Interface Contract)
    "left_header": _A("left", "top"),
    "right_header": _A("right", "top"),
    "center_table": _Reg("matrix_body"),
    # Panel synonyms
    "center_panel": _A("center", "middle"),
    # Chart-axes / regions
    "chart_axes": _A("left", "middle"),
    "chart_overlay": _Reg("highlighted"),
    "highlighted_region": _Reg("highlighted"),
    "shaded_regions": _Reg("highlighted"),
    "boundary_lines": _Reg("highlighted"),
    "boundary_region": _Reg("highlighted"),
    "inside_feasible_region": _Reg("highlighted"),
    "outside_region": _Reg("background"),
    # Ring / cluster positions
    "adjacent_ring_or_column": _Reg("ring"),
    "next_ring_or_column": _Reg("ring"),
    "outer_ring_or_right_column": _A("right", "middle"),
    "middle_layers": _A("center", "middle"),
    # Counterfactual / aligned-marker positions
    "lower_timelines": _A("center", "bottom"),
    "aligned_markers": _Reg("highlighted"),
    "on_timeline": _R("on", "meaning_timeline"),
    # Entity / node-internal positions
    "between_entities": _R("between", "entities"),
    "inside_or_near_nodes": _R("inside", "entities"),
}
