"""Unit tests for canonical canvas normalization."""

from __future__ import annotations

import pytest

from framegraph.canvas import (
    DEFAULT_SVG_CANVAS,
    CanvasSize,
    canvas_from_mapping,
    canvas_from_scene,
    canvas_size_list,
    parse_canvas_size,
    svg_canvas_size,
)


def test_canvas_size_exposes_tuple_and_list_shapes() -> None:
    canvas = CanvasSize(width=1920, height=1080)

    assert canvas.size == (1920.0, 1080.0)
    assert canvas.as_list() == [1920.0, 1080.0]
    assert canvas_size_list(canvas) == [1920.0, 1080.0]


def test_canvas_size_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        CanvasSize(float("nan"), 1080)


def test_parse_canvas_size_accepts_two_number_sequence() -> None:
    assert parse_canvas_size(["960", 540]).size == (960.0, 540.0)


def test_parse_canvas_size_rejects_wrong_arity_without_fallback() -> None:
    with pytest.raises(ValueError, match="exactly two"):
        parse_canvas_size([960, 540, 1])


def test_parse_canvas_size_rejects_non_sequence_without_fallback() -> None:
    with pytest.raises(ValueError, match="two-item sequence"):
        parse_canvas_size("bad")


def test_parse_canvas_size_rejects_non_numeric_values_without_fallback() -> None:
    with pytest.raises(ValueError, match="numeric"):
        parse_canvas_size([960, "bad"])


def test_parse_canvas_size_returns_fallback_for_malformed_value() -> None:
    fallback = CanvasSize(1000, 600)

    assert parse_canvas_size("bad", fallback=fallback) is fallback
    assert parse_canvas_size([960, "bad"], fallback=fallback) is fallback


def test_canvas_from_mapping_reads_size_and_units() -> None:
    canvas = canvas_from_mapping({"size": [595.276, 841.89], "units": "pt"})

    assert canvas == CanvasSize(595.276, 841.89, units="pt")


def test_canvas_from_mapping_rejects_bad_mapping_without_fallback() -> None:
    with pytest.raises(ValueError, match="canvas must be a mapping"):
        canvas_from_mapping(None)


def test_canvas_from_mapping_uses_fallback_for_absent_or_bad_mapping() -> None:
    fallback = CanvasSize(960, 540)

    assert canvas_from_mapping(None, fallback=fallback) is fallback
    assert canvas_from_mapping({"size": [1]}, fallback=fallback) is fallback


def test_canvas_from_scene_prefers_scene_canvas() -> None:
    scene = {
        "canvas": {"size": [400, 300]},
        "source_image": {"width": 1000, "height": 600},
    }

    assert canvas_from_scene(scene, fallback=CanvasSize(1, 1)).size == (400.0, 300.0)


def test_canvas_from_scene_can_fall_back_to_source_image() -> None:
    scene = {"source_image": {"width": 1000, "height": 600}}

    assert canvas_from_scene(scene, fallback=CanvasSize(1, 1), use_source_image=True).size == (
        1000.0,
        600.0,
    )


def test_canvas_from_scene_uses_fallback_when_source_image_is_malformed() -> None:
    fallback = CanvasSize(1, 1)
    scene = {"source_image": {"width": "bad", "height": 600}}

    assert canvas_from_scene(scene, fallback=fallback, use_source_image=True) is fallback


def test_svg_canvas_size_prefers_root_width_height() -> None:
    svg = '<svg width="1920px" height="1080" viewBox="0 0 10 10"></svg>'

    assert svg_canvas_size(svg).size == (1920.0, 1080.0)


def test_svg_canvas_size_falls_back_to_viewbox() -> None:
    assert svg_canvas_size('<svg viewBox="0 0 960 540"></svg>').size == (960.0, 540.0)


def test_svg_canvas_size_uses_fallback_for_short_viewbox() -> None:
    fallback = CanvasSize(10, 10)

    assert svg_canvas_size('<svg viewBox="0 0 960"></svg>', fallback=fallback) is fallback


def test_svg_canvas_size_uses_configured_fallback() -> None:
    assert svg_canvas_size("<svg></svg>") is DEFAULT_SVG_CANVAS
