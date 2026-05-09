"""Regression tests for HD render polish primitives.

Covers the additive renderer changes that lift output from wireframe to
slide-grade:

- Render hints on the `<svg>` root (`shape-rendering`,
  `text-rendering`)
- Shadow + glow filter primitives in `<defs>` and their per-object
  `filter="url(#…)"` wiring on rects/ellipses
- Hairline guard that promotes sub-px strokes when opted in via
  `scene.rendering_contract.hairline_guard`

Each primitive is opt-in or default-on-but-non-mutating-of-geometry,
so v1.x YAML keeps rendering with identical layout. These tests pin
both the new behaviour AND the back-compat path (`render_quality:
legacy`, no hairline_guard).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from framegraph.renderer import FrameGraphRenderer

# ── Render hints on <svg> root ──────────────────────────────────────


def _render(doc: dict) -> str:
    return FrameGraphRenderer(doc).render_svg()


def test_root_has_hd_render_hints_by_default() -> None:
    """Default `render_quality` is `hd`; hints attach to the root <svg>."""
    svg = _render({})
    # ElementTree to assert on the parsed root, not raw substring
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.attrib.get("shape-rendering") == "geometricPrecision"
    assert root.attrib.get("text-rendering") == "optimizeLegibility"


def test_root_omits_hd_hints_when_render_quality_is_legacy() -> None:
    """`render_quality: legacy` reverts to v1.x behaviour (no hints)."""
    svg = _render({"scene": {"rendering_contract": {"render_quality": "legacy"}}})
    root = ET.fromstring(svg)
    assert "shape-rendering" not in root.attrib
    assert "text-rendering" not in root.attrib


def test_root_hd_hints_case_insensitive() -> None:
    """`render_quality` is case-insensitive."""
    svg = _render({"scene": {"rendering_contract": {"render_quality": "HD"}}})
    assert 'shape-rendering="geometricPrecision"' in svg


# ── Shadow filter primitive ─────────────────────────────────────────


def _doc_with_rect(extra: dict) -> dict:
    """Build a minimal doc containing one rect with `extra` keys merged."""
    rect: dict = {"type": "rect", "id": "r1", "box": [10, 10, 80, 40]}
    rect.update(extra)
    return {"visual": {"layers": [{"id": "L", "objects": [rect]}]}}


def test_shadow_preset_emits_filter_def_and_object_attr() -> None:
    """A `shadow: small` rect gains a `filter=` attr referencing a `<filter>` in defs."""
    svg = _render(_doc_with_rect({"shadow": "small"}))
    assert "<defs>" in svg
    assert "<filter " in svg
    assert "feGaussianBlur" in svg
    assert "feOffset" in svg
    assert 'filter="url(#fg-fx-sh_' in svg


def test_shadow_inline_overrides_preset_params() -> None:
    """Inline mapping overrides preset: dx/dy/blur/color/opacity flow through."""
    svg = _render(
        _doc_with_rect({"shadow": {"preset": "medium", "dx": 5, "dy": 7, "color": "#FF0000"}})
    )
    # Filter id is content-addressed: the override values appear in the id
    assert "fg-fx-sh_5_7_4_FF0000_" in svg
    # The flood color is the override, not the preset default
    assert 'flood-color="#FF0000"' in svg


def test_shadow_none_emits_no_filter_attr() -> None:
    """`shadow: none` (or absent) keeps the rect filter-free."""
    svg_none = _render(_doc_with_rect({"shadow": "none"}))
    svg_absent = _render(_doc_with_rect({}))
    assert "filter=" not in svg_none
    assert "filter=" not in svg_absent


def test_shadow_unknown_preset_is_silent_noop() -> None:
    """Unknown preset names are tolerated (no error, no filter)."""
    svg = _render(_doc_with_rect({"shadow": "ginormous"}))
    assert "filter=" not in svg
    # And no <filter> emitted into defs either
    assert "<filter " not in svg


def test_identical_shadow_specs_share_one_filter_def() -> None:
    """Two rects with the same shadow spec collapse to one <filter> in defs."""
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10], "shadow": "medium"},
                        {"type": "rect", "id": "b", "box": [20, 0, 10, 10], "shadow": "medium"},
                    ],
                }
            ]
        }
    }
    svg = _render(doc)
    # One <filter> def, two filter= references
    assert svg.count("<filter ") == 1
    assert svg.count("filter=") == 2


# ── Glow filter primitive ───────────────────────────────────────────


def test_glow_preset_emits_filter_with_flood_color() -> None:
    """A `glow: medium` rect gains a glow filter (flood with default gold)."""
    svg = _render(_doc_with_rect({"glow": "medium"}))
    assert 'filter="url(#fg-fx-gl_' in svg
    # Default glow color is gold
    assert 'flood-color="#FFD700"' in svg


def test_glow_inline_color_override_flows_to_flood() -> None:
    """Inline glow mapping can recolor the halo."""
    svg = _render(_doc_with_rect({"glow": {"color": "#00FFAA", "blur": 6}}))
    assert 'flood-color="#00FFAA"' in svg
    # Blur override appears in the id
    assert "fg-fx-gl_6_00FFAA_" in svg


def test_glow_wins_when_both_shadow_and_glow_declared() -> None:
    """When both fields are present, glow is the dominant effect."""
    svg = _render(_doc_with_rect({"shadow": "small", "glow": "medium"}))
    # The rect's filter= refers to a glow id, not a shadow id
    # (glow filter def is still emitted only when chosen)
    rect_line = [line for line in svg.split("\n") if 'id="r1"' in line and "filter=" in line]
    assert rect_line, "rect should carry a filter= attribute"
    assert "fg-fx-gl_" in rect_line[0]
    assert "fg-fx-sh_" not in rect_line[0]


# ── Effect filters apply to ellipse too ─────────────────────────────


def test_ellipse_honours_shadow_field() -> None:
    """Effect filters work on ellipses, not just rects."""
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "ellipse",
                            "id": "e1",
                            "box": [0, 0, 100, 60],
                            "shadow": "large",
                        }
                    ],
                }
            ]
        }
    }
    svg = _render(doc)
    assert "<filter " in svg
    # Filter attribute lives on the ellipse element
    assert 'filter="url(#fg-fx-sh_' in svg


# ── Hairline guard ──────────────────────────────────────────────────


def test_hairline_guard_off_by_default_preserves_sub_px_stroke() -> None:
    """v1.x default: a 0.5px stroke renders as 0.5 (no promotion)."""
    doc = {
        "visual": {
            "tokens": {
                "stroke_styles": {"thin": {"color": "#000", "width": 0.5}},
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "rect",
                            "id": "r1",
                            "box": [0, 0, 10, 10],
                            "stroke_style": "thin",
                        }
                    ],
                }
            ],
        }
    }
    svg = _render(doc)
    assert 'stroke-width="0.5"' in svg


def test_hairline_guard_promotes_sub_px_stroke_when_opted_in() -> None:
    """With guard on, 0.5px → default min (0.75); 1.0px stays as-is."""
    doc = {
        "scene": {"rendering_contract": {"hairline_guard": True}},
        "visual": {
            "tokens": {
                "stroke_styles": {
                    "thin": {"color": "#000", "width": 0.5},
                    "thick": {"color": "#000", "width": 1.0},
                },
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10], "stroke_style": "thin"},
                        {
                            "type": "rect",
                            "id": "b",
                            "box": [20, 0, 10, 10],
                            "stroke_style": "thick",
                        },
                    ],
                }
            ],
        },
    }
    svg = _render(doc)
    assert 'stroke-width="0.75"' in svg
    assert 'stroke-width="1"' in svg
    # The 0.5px value MUST not appear anywhere in the output
    assert 'stroke-width="0.5"' not in svg


def test_hairline_guard_respects_custom_minimum() -> None:
    """`hairline_min` is configurable; sub-min strokes promote to it."""
    doc = {
        "scene": {"rendering_contract": {"hairline_guard": True, "hairline_min": 1.25}},
        "visual": {
            "tokens": {
                "stroke_styles": {"thin": {"color": "#000", "width": 1.0}},
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "rect",
                            "id": "r1",
                            "box": [0, 0, 10, 10],
                            "stroke_style": "thin",
                        }
                    ],
                }
            ],
        },
    }
    svg = _render(doc)
    assert 'stroke-width="1.25"' in svg
    assert 'stroke-width="1"' not in svg


def test_hairline_guard_does_not_mutate_zero_stroke() -> None:
    """A width of 0 (intentional no-stroke) is not promoted."""
    doc = {
        "scene": {"rendering_contract": {"hairline_guard": True}},
        "visual": {
            "tokens": {
                "stroke_styles": {"none": {"color": "#000", "width": 0}},
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "rect",
                            "id": "r1",
                            "box": [0, 0, 10, 10],
                            "stroke_style": "none",
                        }
                    ],
                }
            ],
        },
    }
    svg = _render(doc)
    assert 'stroke-width="0"' in svg


# ── defs_svg integration ────────────────────────────────────────────


def test_defs_block_emitted_when_only_effect_filters_present() -> None:
    """A doc whose only def-worthy content is an effect filter still gets <defs>."""
    # Trivial doc: empty visual, rect with shadow added below
    svg = _render(_doc_with_rect({"shadow": "small"}))
    assert "<defs>" in svg
    assert "</defs>" in svg
    # Defs block precedes the layer body
    assert svg.index("<defs>") < svg.index('<g id="layer_L"')


def test_well_formed_xml_with_all_primitives_active() -> None:
    """The combined output (hints + shadow + glow + hairline) is valid XML."""
    doc = {
        "scene": {
            "rendering_contract": {
                "render_quality": "hd",
                "hairline_guard": True,
            }
        },
        "visual": {
            "tokens": {
                "stroke_styles": {"hair": {"color": "#000", "width": 0.4}},
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "rect",
                            "id": "a",
                            "box": [0, 0, 10, 10],
                            "shadow": "medium",
                            "stroke_style": "hair",
                        },
                        {"type": "ellipse", "id": "b", "box": [20, 0, 10, 10], "glow": "small"},
                    ],
                }
            ],
        },
    }
    svg = _render(doc)
    # Must parse cleanly
    ET.fromstring(svg)
    # All four primitives represented
    assert "shape-rendering" in svg
    assert "fg-fx-sh_" in svg
    assert "fg-fx-gl_" in svg
    assert 'stroke-width="0.75"' in svg


# ── Shadow / glow coverage across renderers ─────────────────────────


def _doc_with_object(obj: dict) -> dict:
    return {"visual": {"layers": [{"id": "L", "objects": [obj]}]}}


def test_shadow_on_path_attaches_filter_to_path_element() -> None:
    """Path renderer must honour `shadow:` in addition to rect/ellipse."""
    svg = _render(
        _doc_with_object(
            {"type": "path", "id": "p1", "d": "M0 0 L 50 50", "shadow": "small"}
        )
    )
    assert "<filter " in svg
    # The path element itself carries the filter wiring.
    assert 'filter="url(#fg-fx-sh_' in svg
    assert "<path " in svg


def test_shadow_on_image_attaches_filter_to_image_element() -> None:
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img1",
                "box": [0, 0, 100, 80],
                "href": "https://example.com/x.png",
                "shadow": "medium",
            }
        )
    )
    assert "<image " in svg
    assert 'filter="url(#fg-fx-sh_' in svg


def test_shadow_on_line_attaches_filter() -> None:
    """Lines support shadow for highlighted-edge effects."""
    svg = _render(
        _doc_with_object(
            {
                "type": "line",
                "id": "edge",
                "from": [0, 0],
                "to": [100, 100],
                "stroke": "#000",
                "shadow": "small",
            }
        )
    )
    assert "<line " in svg
    assert 'filter="url(#fg-fx-sh_' in svg


def test_shadow_on_polyline_attaches_filter() -> None:
    svg = _render(
        _doc_with_object(
            {
                "type": "polyline",
                "id": "poly",
                "points": [[0, 0], [10, 10], [20, 0]],
                "stroke": "#000",
                "shadow": "small",
            }
        )
    )
    assert "<polyline " in svg
    assert 'filter="url(#fg-fx-sh_' in svg


def test_shadow_on_connector_attaches_filter_to_path() -> None:
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "rect", "id": "a", "box": [0, 0, 20, 20]},
                        {"type": "rect", "id": "b", "box": [80, 0, 20, 20]},
                        {
                            "type": "connector",
                            "id": "c",
                            "from": "a",
                            "to": "b",
                            "stroke": {"color": "#000"},
                            "shadow": "small",
                        },
                    ],
                }
            ]
        }
    }
    svg = _render(doc)
    # The connector emits a <path>; the filter rides on it.
    assert 'filter="url(#fg-fx-sh_' in svg


def test_shadow_on_component_primary_rect() -> None:
    doc = {
        "visual": {
            "component_defs": {
                "card": {
                    "fill": "#fff",
                    "geometry": {"radius": 8},
                }
            },
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "component",
                            "id": "c1",
                            "component": "card",
                            "box": [0, 0, 100, 60],
                            "shadow": "medium",
                        }
                    ],
                }
            ],
        }
    }
    svg = _render(doc)
    assert "<filter " in svg
    assert 'filter="url(#fg-fx-sh_' in svg


def test_glow_on_image_attaches_filter() -> None:
    """Glow must compose the same way shadow does on non-rect renderers."""
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img",
                "box": [0, 0, 50, 50],
                "href": "https://example.com/x.png",
                "glow": "small",
            }
        )
    )
    assert 'filter="url(#fg-fx-gl_' in svg


# ── Outer ring border coverage ──────────────────────────────────────


def test_outer_ring_on_image_emits_concentric_rect_before_image() -> None:
    """Image must accept the same `outer_ring` schema as rect."""
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img",
                "box": [10, 10, 100, 80],
                "href": "https://example.com/x.png",
                "radius": 6,
                "outer_ring": {"color": "#FF0000", "width": 2, "gap": 4},
            }
        )
    )
    # Ring rect appears before the <image> tag in document order so the
    # image overpaints the ring's interior.
    ring_pos = svg.find("<rect ")
    image_pos = svg.find("<image ")
    assert ring_pos != -1 and image_pos != -1 and ring_pos < image_pos
    # Ring is expanded by gap + width/2 = 5px on every side.
    assert 'x="5"' in svg and 'y="5"' in svg
    assert 'stroke="#FF0000"' in svg


def test_outer_ring_on_component_emits_concentric_rect_before_main() -> None:
    doc = {
        "visual": {
            "component_defs": {"card": {"fill": "#fff"}},
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "component",
                            "id": "c1",
                            "component": "card",
                            "box": [10, 10, 100, 60],
                            "outer_ring": {"color": "#00AA00", "width": 1.5, "gap": 3},
                        }
                    ],
                }
            ],
        }
    }
    svg = _render(doc)
    # Two <rect> elements: the outer ring and the primary geometry.
    assert svg.count("<rect ") >= 2
    assert 'stroke="#00AA00"' in svg


def test_outer_ring_dash_string_passed_through() -> None:
    """Dash arrays accept either a sequence or a raw SVG-formatted string."""
    svg = _render(
        _doc_with_object(
            {
                "type": "rect",
                "id": "r",
                "box": [0, 0, 50, 50],
                "outer_ring": {"color": "#000", "width": 1, "dash": "4 2 1 2"},
            }
        )
    )
    assert 'stroke-dasharray="4 2 1 2"' in svg


def test_outer_ring_offset_synonym_works_on_image() -> None:
    """`offset` (ellipse-style) is accepted on rect-shaped renderers too."""
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img",
                "box": [10, 10, 50, 50],
                "href": "https://example.com/x.png",
                "outer_ring": {"color": "#000", "width": 2, "offset": 6},
            }
        )
    )
    # offset 6 + width/2 = 7 → ring origin shifts by 7 from box origin.
    assert 'x="3"' in svg and 'y="3"' in svg


def test_outer_ring_absent_on_image_keeps_byte_identity() -> None:
    """Without outer_ring, image markup contains no extra rect."""
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img",
                "box": [0, 0, 50, 50],
                "href": "https://example.com/x.png",
            }
        )
    )
    assert "<rect " not in svg
    assert "<image " in svg


def test_shadow_and_outer_ring_on_image_compose() -> None:
    """Filter wires onto <image>; ring is drawn unfiltered as a sibling."""
    svg = _render(
        _doc_with_object(
            {
                "type": "image",
                "id": "img",
                "box": [10, 10, 80, 80],
                "href": "https://example.com/x.png",
                "shadow": "small",
                "outer_ring": {"color": "#000", "width": 1, "gap": 2},
            }
        )
    )
    # Filter on image
    assert 'filter="url(#fg-fx-sh_' in svg
    # Ring is a separate <rect> — should NOT also carry filter (avoids
    # double-shadow on the composite).
    rect_segment = svg[svg.find("<rect "): svg.find("/>", svg.find("<rect "))]
    assert "filter=" not in rect_segment
