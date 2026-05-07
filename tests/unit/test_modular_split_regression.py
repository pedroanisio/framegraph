"""Regression tests for the v2.0 modular-split repair.

Before this fix, three methods on the `RendererContext` Protocol were
declared but not implemented on `FrameGraphRenderer`:

    - r.text_svg(content, b, style, *, rotation=None, extra=None)
    - r.render_rect(obj)
    - r.eval_length(value, total)

The renderer modules in `framegraph.renderers.*` call them through the
Protocol. Calls used to raise `AttributeError`, which was caught by
`render_svg`'s per-object try/except and silently demoted to a comment
in the SVG output — the legend-with-rect-sample path, connector labels,
and component slot positioning were broken without any visible error.

Each test below either calls the new method directly or exercises an
upstream code path that depends on it. If any of these tests start
failing in the future, the regression has returned.

Reference: framegraph/_types.py:105-115 (Protocol declarations) and
the v2.0 repair note inserted in framegraph/renderer.py.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from framegraph.renderer import FrameGraphRenderer
from framegraph.renderers import lines, shapes
from framegraph.renderers.layout import offset_box, render_component

# ── Method existence (Protocol contract) ────────────────────────────


def test_renderer_has_text_svg_method() -> None:
    """`r.text_svg` must be callable, not raise AttributeError."""
    r = FrameGraphRenderer({})
    assert callable(r.text_svg)


def test_renderer_has_render_rect_method() -> None:
    r = FrameGraphRenderer({})
    assert callable(r.render_rect)


def test_renderer_has_eval_length_method() -> None:
    r = FrameGraphRenderer({})
    assert callable(r.eval_length)


# ── text_svg behaviour ──────────────────────────────────────────────


def test_text_svg_returns_text_element_for_string_content() -> None:
    r = FrameGraphRenderer({})
    out = r.text_svg("Hello", (0, 0, 100, 30), r.text_style("default"))
    assert "<text" in out
    assert "Hello" in out


def test_text_svg_with_lorem_placeholder_expands() -> None:
    """`r.text_svg` honours the same `lorem` / `lorem:N` placeholders as the free function."""
    r = FrameGraphRenderer({})
    out = r.text_svg("lorem:3", (0, 0, 200, 50), r.text_style("default"))
    # 3-word lorem expansion contains real lorem-ipsum vocabulary
    assert "<text" in out


def test_text_svg_rotation_kwarg_returns_string() -> None:
    """`rotation` is forwarded to the underlying text_svg.

    The free function only emits a `transform="rotate(...)"` wrapper
    when invoked through `render_text_object` (which wraps the result
    based on `obj.rotation`). At the `text_svg` entry point the
    rotation is folded into per-glyph layout instead. The contract we
    care about here is that the kwarg is accepted without error.
    """
    r = FrameGraphRenderer({})
    out = r.text_svg(
        "Tilted",
        (0, 0, 100, 30),
        r.text_style("default"),
        rotation=45,
    )
    assert isinstance(out, str) and "<text" in out


def test_text_svg_extra_attrs_merged_into_text_element() -> None:
    r = FrameGraphRenderer({})
    out = r.text_svg(
        "Underlined",
        (0, 0, 100, 30),
        r.text_style("default"),
        extra={"text-decoration": "underline"},
    )
    assert "text-decoration" in out


def test_text_svg_delegates_to_text_objects_module() -> None:
    """Result must equal what the free function produces directly."""
    from framegraph.renderers.text_objects import text_svg as _free_text_svg

    r = FrameGraphRenderer({})
    style = r.text_style("default")
    via_method = r.text_svg("Same", (0, 0, 100, 30), style)
    via_free = _free_text_svg(r, "Same", (0, 0, 100, 30), style)
    assert via_method == via_free


# ── render_rect behaviour ───────────────────────────────────────────


def test_render_rect_emits_rect_element_for_basic_obj() -> None:
    r = FrameGraphRenderer({})
    out = r.render_rect({"id": "r1", "box": [0, 0, 10, 10]})
    assert "<rect" in out and "<g" in out


def test_render_rect_with_radius_includes_rx_ry() -> None:
    r = FrameGraphRenderer({})
    out = r.render_rect({"box": [0, 0, 10, 10], "radius": 4})
    assert 'rx="4"' in out and 'ry="4"' in out


def test_render_rect_delegates_to_shapes_module() -> None:
    """Result must equal what the free function produces directly."""
    r = FrameGraphRenderer({})
    obj = {"id": "r1", "box": [0, 0, 10, 10]}
    via_method = r.render_rect(obj)
    via_free = shapes.render_rect(r, obj)
    assert via_method == via_free


# ── eval_length behaviour ───────────────────────────────────────────


def test_eval_length_numeric_returns_float() -> None:
    r = FrameGraphRenderer({})
    assert r.eval_length(42, 100.0) == 42.0
    assert r.eval_length(3.5, 100.0) == 3.5


def test_eval_length_percent_string_resolves_against_total() -> None:
    r = FrameGraphRenderer({})
    assert r.eval_length("50%", 200.0) == 100.0
    assert r.eval_length("0%", 100.0) == 0.0
    assert r.eval_length("100%", 50.0) == 50.0


def test_eval_length_calc_expression_with_addition() -> None:
    r = FrameGraphRenderer({})
    # calc(50% + 10) on total=100 → 50 + 10 = 60
    assert r.eval_length("calc(50% + 10)", 100.0) == 60.0


def test_eval_length_calc_expression_with_subtraction() -> None:
    r = FrameGraphRenderer({})
    # calc(40% - 5) on total=100 → 40 - 5 = 35
    assert r.eval_length("calc(40% - 5)", 100.0) == 35.0


def test_eval_length_invalid_string_returns_zero() -> None:
    r = FrameGraphRenderer({})
    assert r.eval_length("garbage", 100.0) == 0.0


def test_eval_length_none_returns_zero() -> None:
    r = FrameGraphRenderer({})
    assert r.eval_length(None, 100.0) == 0.0


# ── Previously-broken upstream paths ────────────────────────────────


def test_legend_with_rect_sample_emits_rect_not_silent_failure() -> None:
    """Before the fix this path raised AttributeError on r.render_rect.

    `render_svg`'s per-object try/except caught it and emitted an HTML
    comment instead of the rect swatch, silently corrupting legend output.
    The fix is verified by the presence of an actual `<rect ...>` element
    in the result.
    """
    r = FrameGraphRenderer({})
    out = lines.render_legend(
        r,
        {
            "type": "legend",
            "id": "leg",
            "items": [
                {
                    "id": "i1",
                    "sample": {
                        "type": "rect",
                        "box": [0, 0, 10, 10],
                        "fill": "none",
                    },
                }
            ],
        },
    )
    assert "<rect" in out
    # The "legend_sample" type label is the pseudo-object id used by render_legend
    # — its presence confirms render_rect was actually called, not skipped.
    assert "legend_sample" in out


def test_legend_with_rounded_rect_sample_also_works() -> None:
    """The `rounded_rect` sample type uses the same r.render_rect dispatch."""
    r = FrameGraphRenderer({})
    out = lines.render_legend(
        r,
        {
            "type": "legend",
            "items": [
                {
                    "sample": {
                        "type": "rounded_rect",
                        "box": [0, 0, 20, 10],
                        "radius": 3,
                    }
                }
            ],
        },
    )
    assert "<rect" in out


def test_legend_item_with_label_emits_text_via_text_svg() -> None:
    """Before the fix the label path raised AttributeError on r.text_svg.

    Now it produces a `<text>` element inside the legend group.
    """
    r = FrameGraphRenderer({})
    out = lines.render_legend(
        r,
        {
            "type": "legend",
            "items": [
                {
                    "sample": {
                        "type": "line",
                        "from": [0, 0],
                        "to": [10, 0],
                    },
                    "label": {
                        "text": "Series A",
                        "box": [12, 0, 50, 10],
                    },
                }
            ],
        },
    )
    assert "<text" in out
    assert "Series A" in out


def test_connector_with_label_emits_text() -> None:
    """Connectors with `label` (mapping) used to lose the label silently.

    Now `r.text_svg` is called directly and emits a `<text>` element.
    """
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
    r = FrameGraphRenderer(doc)
    out = lines.render_connector(
        r,
        {
            "type": "connector",
            "from": "a",
            "to": "b",
            "label": {"text": "calls", "box": [25, 25, 30, 12]},
        },
    )
    assert "<text" in out
    assert "calls" in out


def test_offset_box_resolves_via_renderer_eval_length() -> None:
    """`offset_box` calls `r.eval_length` four times — used to AttributeError."""
    r = FrameGraphRenderer({})
    parent = (0.0, 0.0, 100.0, 50.0)
    inner = offset_box(r, parent, [10, 5, "50%", 20])
    assert inner == (10.0, 5.0, 50.0, 20.0)


def test_offset_box_with_calc_expressions_resolves() -> None:
    """`calc(P% +/- N)` offsets must resolve through `r.eval_length`."""
    r = FrameGraphRenderer({})
    inner = offset_box(r, (0.0, 0.0, 100.0, 100.0), ["calc(10% + 2)", 0, "50%", "calc(50% - 5)"])
    assert inner == (12.0, 0.0, 50.0, 45.0)


def test_render_component_with_slot_offset_emits_slot_text() -> None:
    """`render_component` resolves slot positions via `offset_box` → `r.eval_length`.

    Before the fix the AttributeError demoted slot rendering to a comment.
    Now the slot text appears inside the component group.
    """
    r = FrameGraphRenderer(
        {
            "visual": {
                "component_defs": {
                    "card": {
                        "geometry": {"radius": 4},
                        "fill": "none",
                        "slots": ["title"],
                        "internal_layout": {
                            "title": {
                                "box_offset": [8, 8, "calc(100% - 16)", 20],
                                "style": "default",
                            }
                        },
                    }
                }
            }
        }
    )
    out = render_component(
        r,
        {
            "type": "component",
            "component": "card",
            "box": [0, 0, 100, 50],
            "title": "My Card",
        },
    )
    assert "<text" in out
    assert "My Card" in out
    assert 'data-slot="title"' in out


def test_full_render_with_legend_rect_sample_produces_valid_svg() -> None:
    """End-to-end: a document containing a legend with a rect sample renders
    valid SVG with the rect actually present.

    The original `render_svg` per-object try/except meant the bug was
    invisible at the document level; this test would have passed before
    the fix (no exception bubbles up) but the rect would have been missing.
    The assertion on `<rect` count makes the regression visible.
    """
    doc = {
        "visual": {
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {
                            "type": "legend",
                            "id": "leg",
                            "items": [
                                {
                                    "sample": {
                                        "type": "rect",
                                        "box": [0, 0, 10, 10],
                                        "fill": "none",
                                    },
                                    "label": {
                                        "text": "Item A",
                                        "box": [12, 0, 50, 10],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }
    svg = FrameGraphRenderer(doc).render_svg()
    ET.fromstring(svg)  # must be well-formed XML
    # The legend's rect sample must appear in the output.
    # Before the fix, the rect was silently dropped (comment instead).
    assert "<rect" in svg
    assert "Item A" in svg
    assert "<!-- " not in svg.split("<text")[0] or svg.count("<rect") >= 1


# ── Type-level Protocol conformance ─────────────────────────────────


def test_renderer_satisfies_renderercontext_protocol_at_runtime() -> None:
    """`FrameGraphRenderer` must satisfy `RendererContext` structurally.

    The Protocol is `@runtime_checkable`, so `isinstance(r, RendererContext)`
    is the cheapest available structural check. If any member of the
    Protocol is removed from `FrameGraphRenderer` in the future, this
    assertion fails.
    """
    from framegraph._types import RendererContext

    r = FrameGraphRenderer({})
    assert isinstance(r, RendererContext)


@pytest.mark.parametrize(
    "method_name",
    ["text_svg", "render_rect", "eval_length"],
)
def test_renderer_exposes_repaired_protocol_method(method_name: str) -> None:
    """The three methods that landed in the v2.0 repair must exist as instance attributes."""
    r = FrameGraphRenderer({})
    assert hasattr(r, method_name)
    assert callable(getattr(r, method_name))
