"""Regression tests for canvas-aware default-stylesheet auto-selection.

Decks that omit `stylesheet:` get a default chosen by canvas width:

  * width ≥ 1600 px → `default-screen` (screen-grade: 16pt body)
  * width < 1600 px → `default` (print-density: 10pt body)

Explicit `stylesheet:` declarations always win. The breakpoint and
bundled stylesheet names are part of the public contract — changing
them silently would re-bless every pattern-rendered output downstream.

These tests pin:

  1. The two bundled stylesheets exist and load.
  2. The breakpoint at 1600 px (inclusive lower bound for screen).
  3. Auto-selection only fires when `stylesheet:` is absent.
  4. The screen stylesheet renders pattern slides at slide-grade sizes
     (≥ 14pt body) end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary
from framegraph.patterns.style import load_bundled_stylesheet

ROOT = Path(__file__).resolve().parents[2]
LIB_PATH = ROOT / "framegraph" / "lib"


def _deck(canvas_w: int, canvas_h: int = 1080, **extra) -> dict:
    deck: dict = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {"canvas": {"size": [canvas_w, canvas_h]}},
        "slides": [
            {
                "id": "a",
                "use": 10,
                "fill": {
                    "strengths": ["s"],
                    "weaknesses": ["w"],
                    "opportunities": ["o"],
                    "threats": ["t"],
                },
            }
        ],
    }
    deck.update(extra)
    return deck


@pytest.fixture(scope="module")
def lib() -> FrameGraphLibrary:
    return FrameGraphLibrary(LIB_PATH)


# ─────────────────────────────────────────────────────────────────
# Bundled stylesheets exist + load
# ─────────────────────────────────────────────────────────────────


def test_default_stylesheet_loads() -> None:
    """The print-density `default` stylesheet must load and have card_body=10pt.

    This is the existing letter-size print default — protected against
    accidental drift because re-blessing existing goldens depends on it
    staying at 10pt.
    """
    ss = load_bundled_stylesheet("default")
    assert ss.text_styles["card_body"]["size"] == 10


def test_default_screen_stylesheet_loads() -> None:
    """The new `default-screen` stylesheet must load and have screen-grade card_body."""
    ss = load_bundled_stylesheet("default-screen")
    # Screen-grade: card_body ≥ 14pt readable from presentation distance.
    assert ss.text_styles["card_body"]["size"] >= 14


def test_default_screen_keeps_default_chrome_and_treatments() -> None:
    """`default-screen` is the sibling of `default` — chrome / treatments / roles
    must be structurally identical (only `text_styles` diverges)."""
    base = load_bundled_stylesheet("default")
    scr = load_bundled_stylesheet("default-screen")

    # Roles / treatments / chrome structure is the contract.
    assert scr.treatments.keys() == base.treatments.keys()
    assert len(scr.roles) == len(base.roles)
    base_chrome = base.model_dump().get("slide_chrome") or {}
    scr_chrome = scr.model_dump().get("slide_chrome") or {}
    assert set(scr_chrome.keys()) == set(base_chrome.keys()), (
        f"slide_chrome keys diverged: base={sorted(base_chrome)} vs screen={sorted(scr_chrome)}"
    )


# ─────────────────────────────────────────────────────────────────
# Auto-selection by canvas width
# ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "canvas_w,expected_body_size",
    [
        (960, 10),  # legacy letter-size deck → print stylesheet
        (1280, 10),  # 720p screencast → still print (< 1600 breakpoint)
        (1599, 10),  # just below the breakpoint
        (1600, 16),  # exactly the breakpoint → screen
        (1920, 16),  # 1080p screen-slide → screen
        (2560, 16),  # 1440p → screen
    ],
)
def test_canvas_width_selects_stylesheet(
    lib: FrameGraphLibrary, canvas_w: int, expected_body_size: int
) -> None:
    """The auto-selection breakpoint is at 1600 px width (inclusive lower bound).

    Pins the breakpoint contract: ≥ 1600 → screen, < 1600 → print. The
    threshold matters because a deck a few pixels short of 1600 should
    still pick the same stylesheet as one a few pixels above it; the
    sizes in question (1280×720, 1920×1080) are the canonical
    breakpoints for screencast vs presentation.
    """
    deck = _deck(canvas_w=canvas_w)
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assert renderer._stylesheet.text_styles["card_body"]["size"] == expected_body_size, (
        f"canvas width {canvas_w} should select a stylesheet with "
        f"card_body={expected_body_size}, got "
        f"{renderer._stylesheet.text_styles['card_body']['size']}"
    )


def test_explicit_stylesheet_wins_over_auto_selection(lib: FrameGraphLibrary) -> None:
    """An explicit `stylesheet:` field always wins, regardless of canvas size.

    A 1920×1080 deck that explicitly says `stylesheet: default` must
    get the print-density default — operators sometimes want this
    (e.g. exporting a deck for letter-size print at a larger canvas).
    """
    deck = _deck(canvas_w=1920, stylesheet="default")
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assert renderer._stylesheet.text_styles["card_body"]["size"] == 10


def test_inline_stylesheet_dict_wins_over_auto_selection(lib: FrameGraphLibrary) -> None:
    """An inline stylesheet dict bypasses auto-selection too."""
    deck = _deck(
        canvas_w=1920,
        stylesheet={"text_styles": {"card_body": {"font": "primary", "size": 99}}},
    )
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assert renderer._stylesheet.text_styles["card_body"]["size"] == 99


def test_missing_canvas_falls_back_to_print_default(lib: FrameGraphLibrary) -> None:
    """A deck without a `canvas:` block falls back to print-density default.

    The width is 0 in that case, which is < 1600 — so the print
    stylesheet wins. This is the conservative choice (smaller text on
    an unknown canvas is more likely to fit than larger text).
    """
    deck: dict = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {},  # no canvas
        "slides": [
            {
                "id": "a",
                "use": 10,
                "fill": {
                    "strengths": ["s"],
                    "weaknesses": ["w"],
                    "opportunities": ["o"],
                    "threats": ["t"],
                },
            }
        ],
    }
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    assert renderer._stylesheet.text_styles["card_body"]["size"] == 10


# ─────────────────────────────────────────────────────────────────
# End-to-end: rendered pattern slide picks up the screen stylesheet
# ─────────────────────────────────────────────────────────────────


def test_screen_canvas_rendered_at_slide_grade_sizes(
    lib: FrameGraphLibrary, tmp_path: Path
) -> None:
    """A pattern-composed slide on a 1920×1080 canvas renders body text at ≥ 14pt.

    Closes the loop: stylesheet selection → emitter → rendered SVG. A
    new author who writes a 1920×1080 deck and omits `stylesheet:`
    should not get 10pt body text — the original cbm-deck defect.
    """
    deck = _deck(canvas_w=1920, canvas_h=1080)
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    paths = renderer.render_all(tmp_path)
    svg = paths[0].read_text(encoding="utf-8")

    import re

    sizes = {int(m) for m in re.findall(r'font-size="(\d+)"', svg)}
    # The body-text size must be present and ≥ 14pt.
    body_sizes = {s for s in sizes if 14 <= s <= 24}
    assert body_sizes, (
        f"No slide-grade body text (14–24pt) found in 1920×1080 pattern "
        f"slide; observed sizes: {sorted(sizes)}"
    )
    # The print-density 8pt label / 10pt body must NOT be present.
    assert 8 not in sizes, "8pt print-density text leaked into screen-canvas slide"


def test_print_canvas_rendered_at_print_sizes(lib: FrameGraphLibrary, tmp_path: Path) -> None:
    """A pattern-composed slide on a 960×540 canvas keeps the print stylesheet.

    Existing letter-size-print decks must not regress: card_body stays
    10pt; card_label stays 8pt; the previous goldens that depend on
    these sizes are unaffected.
    """
    deck = _deck(canvas_w=960, canvas_h=540)
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    paths = renderer.render_all(tmp_path)
    svg = paths[0].read_text(encoding="utf-8")

    import re

    sizes = {int(m) for m in re.findall(r'font-size="(\d+)"', svg)}
    assert 10 in sizes, "Print-density 10pt body did not render on legacy 960×540 canvas"
    assert 8 in sizes, "Print-density 8pt label did not render on legacy 960×540 canvas"
