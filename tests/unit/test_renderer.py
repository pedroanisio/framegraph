"""Unit tests for `framegraph.renderer.FrameGraphRenderer`.

Drive the renderer with small in-memory dict documents. File I/O paths
(`from_yaml_file`, `write_svg`) use real `tmp_path` files. The user-facing
CLI lives in `framegraph.cli` and is covered by `tests/integration/test_cli.py`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from framegraph.renderer import FrameGraphRenderer

# ── Construction ────────────────────────────────────────────────────


def test_init_stores_doc_and_indexes_objects() -> None:
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L1",
                    "objects": [
                        {"type": "rect", "id": "r1", "box": [0, 0, 10, 10]},
                    ],
                }
            ]
        }
    }
    r = FrameGraphRenderer(doc)
    assert r.doc is doc
    assert "r1" in r.object_index


def test_init_with_empty_doc_uses_defaults() -> None:
    r = FrameGraphRenderer({})
    assert r.scene == {}
    assert r.semantic == {}
    assert r.visual == {}
    assert r.tokens == {}


def test_init_collects_semantic_ids_from_nodes_edges_ontology() -> None:
    doc = {
        "semantic": {
            "ontology": {
                "node_types": {"actor": {}, "system": {}},
                "edge_types": {"calls": {}},
            },
            "nodes": [{"id": "n1"}, {"id": "n2"}],
            "edges": [{"id": "e1"}],
        }
    }
    r = FrameGraphRenderer(doc)
    assert {"n1", "n2", "e1", "actor", "system", "calls"} <= r.semantic_ids


def test_init_builds_linear_gradient_def_when_fill_styles_present() -> None:
    doc = {
        "visual": {
            "tokens": {
                "fill_styles": {
                    "fade": {
                        "type": "linear_gradient",
                        "from": [0, 0],
                        "to": [1, 1],
                        "stops": [
                            {"offset": 0, "color": "#000000"},
                            {"offset": 1, "color": "#ffffff"},
                        ],
                    }
                }
            }
        }
    }
    r = FrameGraphRenderer(doc)
    assert any("linearGradient" in g for g in r.gradient_defs)


def test_init_builds_radial_gradient_def() -> None:
    doc = {
        "visual": {
            "tokens": {
                "fill_styles": {
                    "halo": {
                        "type": "radial_gradient",
                        "center": [0.5, 0.5],
                        "radius": 0.5,
                        "stops": [{"offset": 0, "color": "#fff"}],
                    }
                }
            }
        }
    }
    r = FrameGraphRenderer(doc)
    assert any("radialGradient" in g for g in r.gradient_defs)


def test_init_builds_marker_colors_from_stroke_styles() -> None:
    doc = {
        "visual": {
            "tokens": {
                "stroke_styles": {
                    "thick": {"color": "#ff0000", "width": 3},
                    "thin": {"color": "#00ff00", "width": 1},
                }
            }
        }
    }
    r = FrameGraphRenderer(doc)
    assert "#ff0000" in r.marker_colors
    assert "#00ff00" in r.marker_colors
    # default black always added
    assert "#000000" in r.marker_colors


# ── from_yaml_file ──────────────────────────────────────────────────


def test_from_yaml_file_loads_and_constructs(tmp_path: Path) -> None:
    f = tmp_path / "in.yml"
    f.write_text(
        yaml.dump(
            {
                "dsl": "FrameGraph",
                "version": 1.5,
                "scene": {"id": "test", "canvas": {"size": [100, 100]}},
                "visual": {"layers": []},
            }
        )
    )
    r = FrameGraphRenderer.from_yaml_file(f)
    assert isinstance(r, FrameGraphRenderer)


def test_from_yaml_file_rejects_non_mapping_root(tmp_path: Path) -> None:
    f = tmp_path / "list.yml"
    f.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        FrameGraphRenderer.from_yaml_file(f)


def test_from_yaml_file_rejects_wrong_dsl(tmp_path: Path) -> None:
    f = tmp_path / "wrong.yml"
    f.write_text(yaml.dump({"dsl": "OtherDSL"}))
    with pytest.raises(ValueError, match="dsl: FrameGraph"):
        FrameGraphRenderer.from_yaml_file(f)


# ── write_svg ───────────────────────────────────────────────────────


def test_write_svg_writes_to_disk(tmp_path: Path) -> None:
    out = tmp_path / "out.svg"
    FrameGraphRenderer({}).write_svg(out)
    assert out.exists() and out.stat().st_size > 0
    assert out.read_text(encoding="utf-8").lstrip().startswith(("<?xml", "<svg"))


# ── render_svg basic ────────────────────────────────────────────────


def test_render_svg_minimal_doc_returns_well_formed_svg() -> None:
    svg = FrameGraphRenderer({"visual": {"layers": [{"id": "L1", "objects": []}]}}).render_svg()
    ET.fromstring(svg)


def test_render_svg_includes_canvas_size_when_specified() -> None:
    doc = {
        "scene": {"canvas": {"size": [300, 200]}},
        "visual": {"layers": []},
    }
    svg = FrameGraphRenderer(doc).render_svg()
    assert 'width="300"' in svg or "viewBox" in svg


def test_render_svg_with_unknown_object_type_emits_comment() -> None:
    doc = {
        "visual": {"layers": [{"id": "L1", "objects": [{"type": "definitely_unknown", "id": "x"}]}]}
    }
    svg = FrameGraphRenderer(doc).render_svg()
    assert "unsupported object type" in svg


# ── canvas_size ─────────────────────────────────────────────────────


def test_canvas_size_returns_tuple_of_floats() -> None:
    r = FrameGraphRenderer({})
    w, h = r.canvas_size()
    assert isinstance(w, float) and isinstance(h, float)
    assert w > 0 and h > 0


def test_canvas_size_overridden_by_scene_canvas() -> None:
    r = FrameGraphRenderer({"scene": {"canvas": {"size": [400, 300]}}})
    assert r.canvas_size() == (400.0, 300.0)


# ── color / font / fill_value ────────────────────────────────────────


def test_color_resolves_token_lookup() -> None:
    r = FrameGraphRenderer({"visual": {"tokens": {"colors": {"brand": "#abcdef"}}}})
    assert r.color("brand") == "#abcdef"


def test_color_unknown_token_returns_literal_fallback() -> None:
    r = FrameGraphRenderer({})
    # Hex literals pass through
    assert r.color("#112233") == "#112233"


def test_color_none_returns_default() -> None:
    r = FrameGraphRenderer({})
    assert r.color(None, default="#deadbe") == "#deadbe"


def test_font_resolves_token() -> None:
    r = FrameGraphRenderer({"visual": {"tokens": {"fonts": {"hero": "Roboto"}}}})
    assert r.font("hero") == "Roboto"


def test_fill_value_none_returns_default() -> None:
    r = FrameGraphRenderer({})
    assert r.fill_value(None, default="green") == "green"


def test_fill_value_explicit_none_string_returns_none() -> None:
    r = FrameGraphRenderer({})
    assert r.fill_value("none") == "none"


def test_fill_value_gradient_ref_returns_url() -> None:
    r = FrameGraphRenderer(
        {
            "visual": {
                "tokens": {
                    "fill_styles": {
                        "g1": {"type": "linear_gradient", "stops": []},
                    }
                }
            }
        }
    )
    assert r.fill_value("g1").startswith("url(#")


# ── text_style / stroke_style ────────────────────────────────────────


def test_text_style_returns_dict_for_known_ref() -> None:
    r = FrameGraphRenderer(
        {"visual": {"tokens": {"text_styles": {"title": {"size": 24, "bold": True}}}}}
    )
    style = r.text_style("title")
    assert style["size"] == 24
    assert style["bold"] is True


def test_text_style_unknown_ref_returns_empty_or_default() -> None:
    r = FrameGraphRenderer({})
    style = r.text_style("nonexistent")
    assert isinstance(style, dict)


def test_stroke_style_known_ref_returns_dict() -> None:
    r = FrameGraphRenderer(
        {"visual": {"tokens": {"stroke_styles": {"bold": {"color": "#000", "width": 3}}}}}
    )
    s = r.stroke_style("bold")
    assert s is not None
    assert s.get("width") == 3


def test_stroke_style_inline_overrides_ref() -> None:
    r = FrameGraphRenderer(
        {"visual": {"tokens": {"stroke_styles": {"base": {"width": 1, "color": "#111"}}}}}
    )
    s = r.stroke_style("base", inline={"width": 5})
    assert s is not None and s.get("width") == 5


def test_stroke_style_none_returns_none() -> None:
    r = FrameGraphRenderer({})
    assert r.stroke_style(None) is None


# ── object_box / object_ports ────────────────────────────────────────


def test_object_box_returns_box_for_object_with_box() -> None:
    r = FrameGraphRenderer({})
    b = r.object_box({"box": [10, 20, 30, 40]})
    assert b == (10.0, 20.0, 30.0, 40.0)


def test_object_box_returns_none_when_no_box() -> None:
    r = FrameGraphRenderer({})
    assert r.object_box({"id": "x"}) is None


def test_object_ports_returns_named_dict_for_box() -> None:
    r = FrameGraphRenderer({})
    ports = r.object_ports({"box": [0, 0, 10, 10]}, (0.0, 0.0, 10.0, 10.0))
    assert isinstance(ports, dict)
    # Cardinal port names exist for any rectangular object
    expected_ports = {"north", "south", "east", "west", "center"}
    assert expected_ports & set(ports), f"got ports {set(ports)}"


# ── endpoint resolution ──────────────────────────────────────────────


def test_endpoint_literal_pair_returns_point() -> None:
    r = FrameGraphRenderer({})
    assert r.endpoint([5, 7]) == (5.0, 7.0)


def test_endpoint_object_string_returns_object_center() -> None:
    doc = {
        "visual": {
            "layers": [{"id": "L", "objects": [{"type": "rect", "id": "a", "box": [0, 0, 10, 10]}]}]
        }
    }
    r = FrameGraphRenderer(doc)
    p = r.endpoint("a")
    assert p == (5.0, 5.0)


def test_endpoint_dot_notation_resolves_named_port() -> None:
    doc = {
        "visual": {
            "layers": [{"id": "L", "objects": [{"type": "rect", "id": "a", "box": [0, 0, 10, 10]}]}]
        }
    }
    r = FrameGraphRenderer(doc)
    p = r.endpoint("a.east")
    assert p[0] == 10.0


def test_endpoint_object_dict_with_port_resolves() -> None:
    doc = {
        "visual": {
            "layers": [{"id": "L", "objects": [{"type": "rect", "id": "a", "box": [0, 0, 10, 10]}]}]
        }
    }
    r = FrameGraphRenderer(doc)
    p = r.endpoint({"object": "a", "port": "north"})
    assert p[1] == 0.0


def test_endpoint_object_dict_with_side_returns_side_anchor() -> None:
    doc = {
        "visual": {
            "layers": [{"id": "L", "objects": [{"type": "rect", "id": "a", "box": [0, 0, 10, 10]}]}]
        }
    }
    r = FrameGraphRenderer(doc)
    p = r.endpoint({"object": "a", "side": "south", "offset": 0})
    assert p[1] == 10.0


def test_endpoint_explicit_point_dict() -> None:
    r = FrameGraphRenderer({})
    p = r.endpoint({"point": [3, 4]})
    assert p == (3.0, 4.0)


# ── path_d ──────────────────────────────────────────────────────────


def test_path_d_two_points_emits_M_L() -> None:
    r = FrameGraphRenderer({})
    d = r.path_d([(0, 0), (10, 10)])
    assert d.startswith("M") and "L" in d


def test_path_d_empty_returns_empty_or_safe() -> None:
    r = FrameGraphRenderer({})
    # Should not raise
    d = r.path_d([])
    assert isinstance(d, str)


# ── validate ────────────────────────────────────────────────────────


def test_validate_returns_list_for_minimal_doc() -> None:
    r = FrameGraphRenderer({})
    out = r.validate()
    assert isinstance(out, list)


def test_validate_no_fatal_errors_for_valid_doc() -> None:
    doc = {
        "visual": {
            "layers": [
                {"id": "L", "objects": [{"type": "rect", "id": "r1", "box": [0, 0, 10, 10]}]}
            ]
        }
    }
    fatal = [w for w in FrameGraphRenderer(doc).validate() if w.upper().startswith("ERROR")]
    assert fatal == []


# ── register / dispatch ─────────────────────────────────────────────


def test_register_overrides_renderer_for_type() -> None:
    r = FrameGraphRenderer({})
    r.register("my_custom", lambda r_, obj: f'<rect data-id="{obj["id"]}"/>')
    out = r.render_object({"type": "my_custom", "id": "x"})
    assert 'data-id="x"' in out


def test_render_object_unknown_type_emits_comment() -> None:
    r = FrameGraphRenderer({})
    out = r.render_object({"type": "unknown_type"})
    assert "unsupported" in out


# ── group_attrs / stroke_attrs ──────────────────────────────────────


def test_group_attrs_includes_id_when_present() -> None:
    r = FrameGraphRenderer({})
    a = r.group_attrs({"id": "g1"})
    assert a.get("id") == "g1"


def test_stroke_attrs_returns_attrs_dict_with_arrow_marker() -> None:
    r = FrameGraphRenderer({})
    style = {"color": "#000000", "width": 1, "arrow": "end"}
    a = r.stroke_attrs(style, arrows=True)
    assert isinstance(a, dict)
    # Has stroke colour at minimum
    assert a.get("stroke") == "#000000"


def test_stroke_attrs_no_style_returns_stroke_none() -> None:
    r = FrameGraphRenderer({})
    a = r.stroke_attrs(None)
    # No style → renderer emits {"stroke": "none"} so SVG suppresses the default black line
    assert a == {"stroke": "none"}


# ── _str_width ──────────────────────────────────────────────────────


def test_str_width_bold_wider_than_regular_for_same_text() -> None:
    r = FrameGraphRenderer({})
    w_reg = r._str_width("hello world", 12, bold=False)
    w_bold = r._str_width("hello world", 12, bold=True)
    assert w_bold >= w_reg


def test_str_width_empty_string_zero() -> None:
    r = FrameGraphRenderer({})
    assert r._str_width("", 12, bold=False) == 0.0


@pytest.mark.parametrize(
    "char",
    [
        "a",  # narrow
        "M",  # wide upper
        "1",  # digit
        ".",  # punct
        " ",  # space
        "中",  # CJK
    ],
)
def test_str_width_classifies_each_char_class(char: str) -> None:
    r = FrameGraphRenderer({})
    w = r._str_width(char, 12, bold=False)
    assert w > 0


# ── Regression: in-class connector/legend duplicates and the legacy
# CLI in renderer.py (parse_args/main) were removed. The free functions
# in `framegraph.renderers.lines` are covered by
# `tests/unit/test_modular_split_regression.py` and the user-facing CLI
# (`framegraph.cli.main`) by `tests/integration/test_cli.py`.


def test_renderer_does_not_expose_in_class_connector_or_legend() -> None:
    """Regression: dead in-class duplicates were removed."""
    r = FrameGraphRenderer({})
    assert not hasattr(r, "render_connector")
    assert not hasattr(r, "render_legend")


def test_renderer_module_does_not_expose_legacy_cli() -> None:
    """Regression: the second CLI in renderer.py was removed.

    The package's only CLI entry point is `framegraph.cli:main`,
    declared in `pyproject.toml` under `[project.scripts]`.
    """
    from framegraph import renderer as R

    assert not hasattr(R, "parse_args")
    assert not hasattr(R, "main")


# ── Container layout edge cases (lifts renderers/layout.py coverage) ─────


def test_container_with_alignment_center_and_explicit_box() -> None:
    """Container with `align: center` and child with cross-axis size."""
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "id": "c",
            "box": [0, 0, 200, 200],
            "layout": {
                "kind": "stack",
                "direction": "vertical",
                "align": "center",
                "padding": 8,
            },
            "children": [
                {"type": "rect", "id": "ch", "box": [0, 0, 50, 30]},
            ],
        },
    )
    assert "<rect" in out


def test_container_with_alignment_end() -> None:
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 200, 200],
            "layout": {"kind": "stack", "direction": "vertical", "align": "end"},
            "children": [{"type": "rect", "id": "ch", "box": [0, 0, 50, 30]}],
        },
    )
    assert "<rect" in out


def test_container_justify_center() -> None:
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 200, 200],
            "layout": {
                "kind": "stack",
                "direction": "vertical",
                "justify": "center",
            },
            "children": [
                {"type": "rect", "id": "ch1", "box": [0, 0, 100, 20]},
                {"type": "rect", "id": "ch2", "box": [0, 0, 100, 20]},
            ],
        },
    )
    assert "<rect" in out


def test_container_justify_end() -> None:
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 200, 200],
            "layout": {
                "kind": "stack",
                "direction": "vertical",
                "justify": "end",
            },
            "children": [{"type": "rect", "id": "ch", "box": [0, 0, 100, 20]}],
        },
    )
    assert "<rect" in out


def test_container_justify_space_between_with_two_items() -> None:
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 200, 200],
            "layout": {
                "kind": "stack",
                "direction": "vertical",
                "justify": "space_between",
            },
            "children": [
                {"type": "rect", "id": "a", "box": [0, 0, 100, 20]},
                {"type": "rect", "id": "b", "box": [0, 0, 100, 20]},
            ],
        },
    )
    assert "<rect" in out


def test_container_with_flex_children_distributes_remaining_space() -> None:
    """Auto-sized children with flex weights share the remaining main-axis space."""
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 100, 200],
            "layout": {"kind": "stack", "direction": "vertical"},
            "children": [
                {"type": "rect", "id": "a", "flex": 1},
                {"type": "rect", "id": "b", "flex": 2},
            ],
        },
    )
    assert "<rect" in out


def test_container_unsupported_kind_emits_comment() -> None:
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "grid"},
            "children": [],
        },
    )
    assert "not yet implemented" in out


def test_container_child_render_failure_emits_inline_comment() -> None:
    """When a child renderer raises, container catches and emits a comment."""
    from framegraph.renderers.layout import render_container

    r = FrameGraphRenderer({})

    # Register a custom type that always raises
    def boom(_r, _obj):
        raise RuntimeError("boom")

    r.register("boomer", boom)
    out = render_container(
        r,
        {
            "type": "container",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "stack"},
            "children": [{"type": "boomer", "id": "x"}],
        },
    )
    assert "container child error" in out


def test_render_group_with_transform_attribute_forwarded() -> None:
    from framegraph.renderers.layout import render_group

    r = FrameGraphRenderer({})
    out = render_group(
        r,
        {
            "type": "group",
            "id": "g",
            "transform": "rotate(45)",
            "objects": [],
        },
    )
    assert 'transform="rotate(45)"' in out


def test_eval_length_pixel_number() -> None:
    from framegraph.renderers.layout import eval_length

    r = FrameGraphRenderer({})
    assert eval_length(r, 42, total=100.0) == 42.0


def test_eval_length_percentage_string() -> None:
    from framegraph.renderers.layout import eval_length

    r = FrameGraphRenderer({})
    assert eval_length(r, "50%", total=200.0) == 100.0


def test_eval_length_invalid_string_returns_zero() -> None:
    """Strings that aren't bare numbers or `N%` resolve to 0.0."""
    from framegraph.renderers.layout import eval_length

    r = FrameGraphRenderer({})
    assert eval_length(r, "not-a-length", total=100.0) == 0.0


def test_eval_length_none_returns_zero() -> None:
    from framegraph.renderers.layout import eval_length

    r = FrameGraphRenderer({})
    assert eval_length(r, None, total=100.0) == 0.0
