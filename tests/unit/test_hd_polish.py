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
        _doc_with_rect(
            {"shadow": {"preset": "medium", "dx": 5, "dy": 7, "color": "#FF0000"}}
        )
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
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10],
                         "shadow": "medium"},
                        {"type": "rect", "id": "b", "box": [20, 0, 10, 10],
                         "shadow": "medium"},
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
    rect_line = [
        line for line in svg.split("\n") if 'id="r1"' in line and "filter=" in line
    ]
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
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10],
                         "stroke_style": "thin"},
                        {"type": "rect", "id": "b", "box": [20, 0, 10, 10],
                         "stroke_style": "thick"},
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
        "scene": {
            "rendering_contract": {"hairline_guard": True, "hairline_min": 1.25}
        },
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
    assert svg.index("<defs>") < svg.index("<g id=\"layer_L\"")


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
                        {"type": "rect", "id": "a", "box": [0, 0, 10, 10],
                         "shadow": "medium", "stroke_style": "hair"},
                        {"type": "ellipse", "id": "b", "box": [20, 0, 10, 10],
                         "glow": "small"},
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
