"""Regression tests for slide auto-numbering in `framegraph deck`.

Before this fix, decks that omitted the per-slide `slide:` field rendered
every pattern slide with `slide=0`, producing:

  * `slide_00_<id>.svg` filenames for every pattern slide (collision risk)
  * No page numbers in the chrome (the page-number renderer skips slides
    where `slide` is None)

The fix assigns declaration-order indices (1-based) when `slide:` is
absent. Explicit `slide:` values are preserved so operators can still
use sparse / out-of-order numbering when they want it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary

ROOT = Path(__file__).resolve().parents[2]
LIB_PATH = ROOT / "framegraph" / "lib"


def _deck(slides: list[dict]) -> dict:
    """Minimal pattern-composed deck factory."""
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {"canvas": {"size": [1920, 1080]}},
        "slides": slides,
    }


def _fill_swot() -> dict:
    return {
        "strengths": ["s1"],
        "weaknesses": ["w1"],
        "opportunities": ["o1"],
        "threats": ["t1"],
    }


@pytest.fixture(scope="module")
def lib() -> FrameGraphLibrary:
    return FrameGraphLibrary(LIB_PATH)


def test_slides_without_explicit_number_get_declaration_order(lib: FrameGraphLibrary) -> None:
    """Slides omitting `slide:` are auto-numbered 1, 2, 3, … in declaration order.

    Catches the original defect: every pattern slide was emitted as
    `slide_00_<id>.svg` because the renderer defaulted missing `slide:`
    fields to 0.
    """
    deck = _deck(
        [
            {"id": "alpha", "use": 10, "fill": _fill_swot()},
            {"id": "bravo", "use": 10, "fill": _fill_swot()},
            {"id": "charlie", "use": 10, "fill": _fill_swot()},
        ]
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assigned = [s.get("slide") for s in renderer.slides_raw]
    assert assigned == [1, 2, 3]


def test_explicit_slide_numbers_are_preserved(lib: FrameGraphLibrary) -> None:
    """Operators can still set explicit (sparse / out-of-order) numbers.

    The auto-numbering only fills in *missing* `slide:` fields — it
    must not overwrite ones the operator declared. This preserves the
    sparse-numbering use case (e.g. handouts numbered to match a deck).
    """
    deck = _deck(
        [
            {"id": "a", "slide": 5, "use": 10, "fill": _fill_swot()},
            {"id": "b", "slide": 99, "use": 10, "fill": _fill_swot()},
        ]
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assigned = [s.get("slide") for s in renderer.slides_raw]
    assert assigned == [5, 99]


def test_mixed_explicit_and_implicit_numbering(lib: FrameGraphLibrary) -> None:
    """Explicit numbers anchor; gaps fill from declaration order.

    A deck mixing some explicit `slide:` values and some missing ones
    should keep the explicit ones unchanged and assign missing ones
    from their *declaration index* (not from "next unused number" —
    that's a different policy worth not silently implementing).
    """
    deck = _deck(
        [
            {"id": "a", "use": 10, "fill": _fill_swot()},  # → 1
            {"id": "b", "slide": 42, "use": 10, "fill": _fill_swot()},  # → 42
            {"id": "c", "use": 10, "fill": _fill_swot()},  # → 3
        ]
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assigned = [s.get("slide") for s in renderer.slides_raw]
    assert assigned == [1, 42, 3]


def test_rendered_filenames_use_auto_numbers(lib: FrameGraphLibrary, tmp_path: Path) -> None:
    """End-to-end: rendered filenames reflect auto-numbering.

    Before the fix every file landed as `slide_00_<id>.svg`. After the
    fix the filenames are `slide_01_<id>.svg`, `slide_02_<id>.svg`, etc.
    """
    deck = _deck(
        [
            {"id": "alpha", "use": 10, "fill": _fill_swot()},
            {"id": "bravo", "use": 10, "fill": _fill_swot()},
        ]
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    paths = renderer.render_all(tmp_path)
    names = sorted(p.name for p in paths)
    assert names == ["slide_01_alpha.svg", "slide_02_bravo.svg"], (
        f"Auto-numbering did not flow to filenames; got {names}"
    )


def test_chrome_page_number_renders_on_auto_numbered_slides(
    lib: FrameGraphLibrary, tmp_path: Path
) -> None:
    """The chrome page-number renders when `slide:` is auto-assigned.

    The page-number renderer skips slides where `slide` is None. Auto-
    assignment must populate it so page numbers show up by default.
    """
    deck = _deck(
        [
            {"id": "a", "use": 10, "fill": _fill_swot()},
            {"id": "b", "use": 10, "fill": _fill_swot()},
        ]
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    paths = renderer.render_all(tmp_path)
    svgs = {p.name: p.read_text(encoding="utf-8") for p in paths}

    assert "_chrome.page_num" in svgs["slide_01_a.svg"], (
        "Page-number chrome did not render on the first auto-numbered slide"
    )
    # Page number formatted as zero-padded 2-digit string (default format
    # "{n:02d}" in the bundled stylesheet's `slide_chrome.page_number.format`).
    assert ">01<" in svgs["slide_01_a.svg"]
    assert ">02<" in svgs["slide_02_b.svg"]


def test_auto_numbering_handles_empty_slides_list(lib: FrameGraphLibrary) -> None:
    """A deck with zero slides constructs cleanly (no off-by-one on empty list)."""
    deck = _deck([])
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assert renderer.slides_raw == []
