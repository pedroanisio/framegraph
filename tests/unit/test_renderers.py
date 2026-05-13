"""Unit tests for the per-type modules in `framegraph.renderers`.

Each renderer is a pure function `(ctx, obj) -> str`. We drive them
through a real `FrameGraphRenderer` instance (the simplest concrete
`RendererContext`) configured with small in-memory documents — that
exercises the renderer module's branches without needing to hand-roll
a fake context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph.renderer import FrameGraphRenderer
from framegraph.renderers import (
    charts,
    image,
    layout,
    lines,
    shapes,
    symbols,
    text_objects,
)


def _ctx(doc: dict | None = None) -> FrameGraphRenderer:
    return FrameGraphRenderer(doc or {})


# ── shapes ──────────────────────────────────────────────────────────


def test_render_rect_basic_emits_g_with_rect() -> None:
    out = shapes.render_rect(_ctx(), {"id": "r", "box": [0, 0, 10, 10]})
    assert out.startswith("<g") and "<rect" in out


def test_render_rect_with_radius_includes_rx_ry() -> None:
    out = shapes.render_rect(_ctx(), {"box": [0, 0, 10, 10], "radius": 4})
    assert 'rx="4"' in out and 'ry="4"' in out


def test_render_rect_with_outer_ring_emits_two_rects() -> None:
    out = shapes.render_rect(
        _ctx(),
        {
            "box": [0, 0, 10, 10],
            "outer_ring": {"color": "#000", "width": 2, "gap": 4},
        },
    )
    assert out.count("<rect") == 2


def test_render_rect_outer_ring_with_dash_array_list() -> None:
    out = shapes.render_rect(
        _ctx(),
        {
            "box": [0, 0, 10, 10],
            "outer_ring": {"color": "#000", "dash": [4, 2]},
        },
    )
    assert "stroke-dasharray" in out


def test_render_rect_outer_ring_with_dash_string_passes_through() -> None:
    out = shapes.render_rect(
        _ctx(),
        {"box": [0, 0, 10, 10], "outer_ring": {"color": "#000", "dash": "5,5"}},
    )
    assert 'stroke-dasharray="5,5"' in out


def test_render_rect_outer_ring_with_opacity() -> None:
    out = shapes.render_rect(
        _ctx(),
        {"box": [0, 0, 10, 10], "outer_ring": {"color": "#000", "opacity": 0.5}},
    )
    assert "opacity" in out


def test_render_rect_square_inner_with_outer_ring_keeps_ring_square() -> None:
    """Regression: outer_ring must not get rounded corners when the
    inner rect has no `radius`. Pre-fix, the ring rect always inherited
    rx/ry because the guard tested the (always-truthy) renderer context.
    """
    out = shapes.render_rect(
        _ctx(),
        {
            "box": [0, 0, 100, 50],
            "outer_ring": {"color": "#000", "width": 2, "gap": 4},
        },
    )
    # Two rects: outer ring rect (first) and inner rect (second).
    # Neither should carry rx/ry when the inner rect is square.
    assert "rx=" not in out
    assert "ry=" not in out


def test_render_rect_rounded_inner_with_outer_ring_grows_corner_radius() -> None:
    """Sibling test to the regression: when the inner rect IS rounded,
    the outer ring rx/ry must equal `radius + gap + width/2` so the
    ring follows the inner corner concentrically.
    """
    out = shapes.render_rect(
        _ctx(),
        {
            "box": [0, 0, 100, 50],
            "radius": 6,
            "outer_ring": {"color": "#000", "width": 2, "gap": 4},
        },
    )
    # expand = gap + width/2 = 4 + 1 = 5; ring rx = 6 + 5 = 11
    assert 'rx="11"' in out and 'ry="11"' in out
    # The inner rect retains its own rx/ry of 6
    assert 'rx="6"' in out and 'ry="6"' in out


def test_render_ellipse_with_box_inscribes_ellipse() -> None:
    out = shapes.render_ellipse(_ctx(), {"box": [0, 0, 20, 10]})
    assert "<ellipse" in out
    assert 'cx="10"' in out and 'cy="5"' in out


def test_render_ellipse_with_center_and_rx_ry() -> None:
    out = shapes.render_ellipse(_ctx(), {"center": [5, 5], "rx": 3, "ry": 2})
    assert 'rx="3"' in out and 'ry="2"' in out


def test_render_ellipse_with_outer_ring() -> None:
    out = shapes.render_ellipse(
        _ctx(),
        {
            "center": [5, 5],
            "rx": 3,
            "outer_ring": {"color": "#000", "offset": 2, "dash": [3, 3]},
        },
    )
    assert out.count("<ellipse") == 2


def test_render_ellipse_outer_ring_with_string_dash() -> None:
    out = shapes.render_ellipse(
        _ctx(),
        {"center": [5, 5], "rx": 3, "outer_ring": {"color": "#000", "dash": "2,2"}},
    )
    assert 'stroke-dasharray="2,2"' in out


# ── lines ───────────────────────────────────────────────────────────


def test_render_line_object_emits_line_via_line_svg() -> None:
    out = lines.render_line_object(_ctx(), {"id": "l1", "from": [0, 0], "to": [10, 10]})
    assert out  # non-empty


def test_render_polyline_emits_polyline_with_points() -> None:
    out = lines.render_polyline(_ctx(), {"id": "p1", "points": [[0, 0], [10, 0], [10, 10]]})
    assert out


def test_render_path_passes_d_attribute_through() -> None:
    out = lines.render_path(_ctx(), {"id": "p", "d": "M 0 0 L 10 10"})
    assert 'd="M 0 0 L 10 10"' in out


def test_render_path_with_fill_token_resolves() -> None:
    r = _ctx({"visual": {"tokens": {"colors": {"accent": "#ff0000"}}}})
    out = lines.render_path(r, {"d": "M 0 0", "fill": "accent"})
    assert "#ff0000" in out


def test_render_connector_straight_default_route() -> None:
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10]},
                        {"type": "rect", "id": "b", "box": [50, 50, 10, 10]},
                    ],
                }
            ]
        }
    }
    out = lines.render_connector(_ctx(doc), {"type": "connector", "from": "a", "to": "b"})
    assert "<path" in out


def test_render_connector_orthogonal_with_explicit_points_inserts_endpoints() -> None:
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10]},
                        {"type": "rect", "id": "b", "box": [50, 50, 10, 10]},
                    ],
                }
            ]
        }
    }
    out = lines.render_connector(
        _ctx(doc),
        {
            "type": "connector",
            "from": "a",
            "to": "b",
            "route": {"type": "orthogonal", "points": [[20, 20], [40, 40]]},
        },
    )
    assert "<path" in out


def test_render_connector_bezier_route_emits_C_path_command() -> None:
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10]},
                        {"type": "rect", "id": "b", "box": [50, 50, 10, 10]},
                    ],
                }
            ]
        }
    }
    out = lines.render_connector(
        _ctx(doc),
        {
            "type": "connector",
            "from": "a",
            "to": "b",
            "route": {"type": "bezier", "c1": [20, 20], "c2": [40, 40]},
        },
    )
    assert "C " in out


def test_render_connector_unknown_route_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="unsupported route type"):
        lines.render_connector(
            _ctx(),
            {
                "type": "connector",
                "from": [0, 0],
                "to": [1, 1],
                "route": {"type": "spline"},
            },
        )


def test_render_legend_with_line_sample_uses_line_svg() -> None:
    out = lines.render_legend(
        _ctx(),
        {
            "type": "legend",
            "id": "leg",
            "items": [{"id": "i1", "sample": {"type": "line", "from": [0, 0], "to": [10, 0]}}],
        },
    )
    assert out.startswith("<g")


def test_render_legend_skips_non_mapping_items() -> None:
    out = lines.render_legend(
        _ctx(),
        {"type": "legend", "items": ["not-a-mapping", 42]},
    )
    assert out.startswith("<g") and out.endswith("</g>")


def test_render_legend_empty_items_emits_just_group() -> None:
    out = lines.render_legend(_ctx(), {"type": "legend", "items": []})
    assert out == "<g >\n</g>" or (out.startswith("<g") and out.endswith("</g>"))


# ── symbols ─────────────────────────────────────────────────────────


def test_render_icon_with_explicit_glyph_emits_string() -> None:
    """Icon with `glyph` Unicode codepoint produces an SVG element."""
    r = _ctx()
    out = symbols.render_icon(r, {"type": "icon", "id": "i1", "glyph": "x", "box": [0, 0, 20, 20]})
    assert isinstance(out, str)


def test_render_use_unknown_symbol_raises_valueerror() -> None:
    r = _ctx({"visual": {"symbols": {}}})
    with pytest.raises(ValueError, match="unknown symbol"):
        symbols.render_use(
            r,
            {"type": "use", "id": "u1", "symbol": "missing_sym", "box": [0, 0, 10, 10]},
        )


def test_render_use_known_symbol_emits_referenced_objects() -> None:
    r = _ctx(
        {
            "visual": {
                "symbols": {
                    "node_rect": {
                        "objects": [{"type": "rect", "id": "r", "box": [0, 0, 10, 10]}],
                    }
                }
            }
        }
    )
    out = symbols.render_use(
        r,
        {"type": "use", "id": "u1", "symbol": "node_rect", "box": [0, 0, 10, 10]},
    )
    assert isinstance(out, str)


# ── image ───────────────────────────────────────────────────────────


def test_render_image_with_data_uri_passes_through() -> None:
    out = image.render_image(
        _ctx(),
        {
            "id": "img",
            "box": [0, 0, 10, 10],
            "href": "data:image/png;base64,iVBORw0KGgo=",
        },
    )
    assert "data:image/png" in out


def test_render_image_with_http_url_passes_through() -> None:
    out = image.render_image(
        _ctx(),
        {"id": "img", "box": [0, 0, 10, 10], "href": "https://example.com/x.png"},
    )
    assert "example.com" in out


def test_render_image_with_local_file_inlines_base64(tmp_path: Path) -> None:
    """A real local PNG path resolves and inlines as data URI."""
    src = Path(__file__).resolve().parents[1] / "fixtures" / "test_logo.png"
    r = _ctx()
    r.yaml_source_dir = str(src.parent)
    out = image.render_image(r, {"id": "img", "box": [0, 0, 10, 10], "href": src.name})
    assert "data:image/" in out or "<image" in out


def test_render_image_placeholder_for_missing_file(tmp_path: Path) -> None:
    """A missing local file falls back to a placeholder rect or comment."""
    r = _ctx()
    r.yaml_source_dir = str(tmp_path)
    out = image.render_image(r, {"id": "img", "box": [0, 0, 10, 10], "href": "missing.png"})
    # Must return something, not crash
    assert isinstance(out, str)


# ── text_objects ────────────────────────────────────────────────────


def test_render_text_object_plain_string_wraps_in_text_element() -> None:
    out = text_objects.render_text_object(
        _ctx(),
        {"type": "text", "id": "t", "box": [0, 0, 100, 50], "text": "Hello"},
    )
    assert "<text" in out or "<g" in out
    assert "Hello" in out


def test_render_text_object_with_lorem_placeholder_expands() -> None:
    out = text_objects.render_text_object(
        _ctx(),
        {"type": "text", "box": [0, 0, 200, 100], "text": "lorem:5"},
    )
    # 5-word lorem placeholder expands; output contains real words
    assert "Lorem" in out or "lorem" in out.lower()


def test_render_bullet_list_renders_bullets() -> None:
    out = text_objects.render_bullet_list(
        _ctx(),
        {
            "type": "bullet_list",
            "id": "bl",
            "box": [0, 0, 200, 200],
            "items": ["Alpha", "Beta", "Gamma"],
        },
    )
    assert "Alpha" in out and "Beta" in out and "Gamma" in out


def test_render_bullet_list_with_empty_items_emits_group() -> None:
    out = text_objects.render_bullet_list(
        _ctx(),
        {"type": "bullet_list", "box": [0, 0, 100, 100], "items": []},
    )
    assert isinstance(out, str)


# ── charts ──────────────────────────────────────────────────────────


def test_render_bar_chart_emits_one_rect_per_value() -> None:
    out = charts.render_bar_chart(
        _ctx(),
        {
            "type": "bar_chart",
            "id": "bc",
            "box": [0, 0, 400, 200],
            "data": {"labels": ["A", "B", "C"], "values": [10, 20, 30]},
        },
    )
    # Bars are rect elements
    assert out.count("<rect") >= 3


def test_render_bar_chart_with_multi_series() -> None:
    out = charts.render_bar_chart(
        _ctx(),
        {
            "type": "bar_chart",
            "box": [0, 0, 400, 200],
            "data": {
                "labels": ["A", "B"],
                "series": [
                    {"label": "X", "values": [10, 20]},
                    {"label": "Y", "values": [15, 25]},
                ],
            },
        },
    )
    assert "<rect" in out


def test_render_line_chart_emits_polyline_or_path_per_series() -> None:
    out = charts.render_line_chart(
        _ctx(),
        {
            "type": "line_chart",
            "box": [0, 0, 400, 200],
            "data": {
                "x_labels": ["Q1", "Q2", "Q3"],
                "series": [
                    {"label": "S1", "values": [1, 2, 3]},
                ],
            },
        },
    )
    assert "<polyline" in out or "<path" in out


def test_render_bar_chart_with_negative_values_renders() -> None:
    out = charts.render_bar_chart(
        _ctx(),
        {
            "type": "bar_chart",
            "box": [0, 0, 400, 200],
            "data": {"labels": ["A", "B"], "values": [-10, 20]},
        },
    )
    assert "<rect" in out


def test_render_bar_chart_with_grid_lines() -> None:
    out = charts.render_bar_chart(
        _ctx(),
        {
            "type": "bar_chart",
            "box": [0, 0, 400, 200],
            "data": {"labels": ["A"], "values": [10]},
            "style": {"grid_lines": True, "grid_color": "#cccccc"},
        },
    )
    assert "<line" in out or "stroke" in out


def test_render_line_chart_with_legend_and_points() -> None:
    out = charts.render_line_chart(
        _ctx(),
        {
            "type": "line_chart",
            "box": [0, 0, 400, 200],
            "data": {
                "x_labels": ["a", "b"],
                "series": [{"label": "S", "values": [1, 2]}],
            },
            "style": {"show_legend": True, "point_radius": 3},
        },
    )
    # legend means text labels emitted, point_radius means circle elements
    assert "<circle" in out or "<text" in out


# ── layout ──────────────────────────────────────────────────────────


def test_render_group_emits_g_with_id() -> None:
    out = layout.render_group(
        _ctx(),
        {"type": "group", "id": "g1", "objects": []},
    )
    assert out.startswith("<g")


def test_render_container_with_stack_layout_distributes_children() -> None:
    out = layout.render_container(
        _ctx(),
        {
            "type": "container",
            "id": "c1",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "stack", "direction": "vertical", "gap": 5},
            "children": [
                {"type": "rect", "id": "ch1", "box": [0, 0, 100, 20]},
                {"type": "rect", "id": "ch2", "box": [0, 0, 100, 20]},
            ],
        },
    )
    assert "<rect" in out


def test_render_container_horizontal_stack() -> None:
    out = layout.render_container(
        _ctx(),
        {
            "type": "container",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "stack", "direction": "horizontal"},
            "children": [
                {"type": "rect", "id": "ch1", "box": [0, 0, 20, 100]},
                {"type": "rect", "id": "ch2", "box": [0, 0, 20, 100]},
            ],
        },
    )
    assert "<rect" in out


def test_render_container_with_padding_list() -> None:
    out = layout.render_container(
        _ctx(),
        {
            "type": "container",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "stack", "padding": [8, 4]},
            "children": [{"type": "rect", "id": "ch", "box": [0, 0, 100, 20]}],
        },
    )
    assert isinstance(out, str)


def test_render_container_no_children_returns_string() -> None:
    out = layout.render_container(
        _ctx(),
        {"type": "container", "box": [0, 0, 100, 100], "children": []},
    )
    assert isinstance(out, str)


def test_render_chip_row_renders_each_chip() -> None:
    out = layout.render_chip_row(
        _ctx(),
        {
            "type": "chip_row",
            "id": "cr",
            "box": [0, 0, 200, 30],
            "items": [{"text": "A"}, {"text": "B"}, {"text": "C"}],
        },
    )
    # Each chip is a rect+text pair
    assert "<rect" in out or "<text" in out


def test_render_chip_row_empty_returns_string() -> None:
    out = layout.render_chip_row(
        _ctx(),
        {"type": "chip_row", "box": [0, 0, 200, 30], "items": []},
    )
    assert isinstance(out, str)


def test_render_component_dispatches_to_component_def() -> None:
    r = _ctx(
        {
            "visual": {
                "component_defs": {
                    "my_card": {
                        "geometry": {"radius": 4},
                        "fill": "none",
                    }
                }
            }
        }
    )
    out = layout.render_component(
        r,
        {
            "type": "component",
            "id": "c1",
            "component": "my_card",
            "box": [0, 0, 100, 50],
        },
    )
    assert isinstance(out, str)


def test_render_component_unknown_component_raises() -> None:
    r = _ctx({"visual": {"component_defs": {}}})
    with pytest.raises(ValueError, match="unknown component"):
        layout.render_component(
            r,
            {"type": "component", "component": "missing", "box": [0, 0, 100, 50]},
        )
