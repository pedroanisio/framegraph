"""Integration: render every standalone YAML fixture via the public API.

This single parametrized test is the largest coverage multiplier in the
suite — it drives `FrameGraphRenderer.render_svg()` over real-world
schemas (7S frameworks, GenAI diagrams, charts, decks, themed tokens),
exercising the per-object dispatch path through every renderer module.

Boundaries respected:
- Reads YAML fixtures from disk (real I/O — fixtures are checked-in
  test inputs, not external state).
- Asserts on returned SVG strings; no rasterization (cairosvg / PIL
  are exercised only by the separate golden harness at
  tests/run_tests.py, which remains callable manually).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary, FrameGraphRenderer

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
LIB_DIR = Path(__file__).resolve().parents[2] / "framegraph" / "lib"

STANDALONE_FIXTURES = sorted(p for p in FIXTURE_DIR.glob("*.yml") if ".deck." not in p.name)
DECK_FIXTURES = sorted(FIXTURE_DIR.glob("*.deck.yml"))


def _is_deck(doc: object) -> bool:
    return isinstance(doc, dict) and ("deck" in doc or "slides" in doc)


@pytest.mark.parametrize("fixture", STANDALONE_FIXTURES, ids=lambda p: p.stem)
def test_fixture_renders_valid_svg(fixture: Path) -> None:
    """Each standalone YAML fixture renders to a non-empty, well-formed SVG."""
    doc = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    if _is_deck(doc):
        pytest.skip("deck fixture; covered by deck tests")

    renderer = FrameGraphRenderer(doc)
    renderer.yaml_source_dir = str(fixture.parent.resolve())
    svg = renderer.render_svg()

    assert isinstance(svg, str) and svg, f"{fixture.name}: empty SVG"
    # SVG may start with the XML prologue or with <svg directly
    head = svg.lstrip()
    assert head.startswith("<?xml") or head.startswith("<svg"), (
        f"{fixture.name}: unexpected prefix {head[:60]!r}"
    )
    assert svg.rstrip().endswith("</svg>"), f"{fixture.name}: unterminated SVG"

    # Well-formed XML
    ET.fromstring(svg)

    # No fatal validation errors (warnings are tolerated — fixtures may
    # reference symbols/tokens that intentionally exercise warning paths)
    fatal = [w for w in renderer.validate() if w.upper().startswith("ERROR")]
    assert fatal == [], f"{fixture.name}: fatal validation errors {fatal!r}"


def test_render_minimal_in_memory_doc_returns_svg() -> None:
    """A trivial in-memory dict produces valid SVG without any file I/O."""
    doc = {
        "canvas": {"w": 100, "h": 100},
        "objects": [{"type": "rect", "id": "r1", "box": [0, 0, 10, 10]}],
    }
    svg = FrameGraphRenderer(doc).render_svg()
    assert "<svg" in svg
    ET.fromstring(svg)


def test_render_empty_doc_returns_svg() -> None:
    """An empty dict still produces a valid (empty-canvas) SVG."""
    svg = FrameGraphRenderer({}).render_svg()
    assert svg.lstrip().startswith(("<?xml", "<svg"))
    ET.fromstring(svg)


@pytest.mark.parametrize("deck_fixture", DECK_FIXTURES, ids=lambda p: p.stem)
def test_deck_fixture_renders_all_slides(deck_fixture: Path, tmp_path: Path) -> None:
    """Each deck fixture renders one SVG per declared slide into the output dir."""
    data = yaml.safe_load(deck_fixture.read_text(encoding="utf-8"))
    lib = FrameGraphLibrary(LIB_DIR)
    deck = FrameGraphDeckRenderer(data, library=lib)
    paths = deck.render_all(tmp_path)

    assert len(paths) == len(deck.slides_raw), (
        f"{deck_fixture.name}: expected {len(deck.slides_raw)} slides, got {len(paths)}"
    )
    for p in paths:
        assert p.exists() and p.stat().st_size > 0
        assert p.suffix == ".svg"
        content = p.read_text(encoding="utf-8")
        assert content.lstrip().startswith(("<?xml", "<svg"))
        ET.fromstring(content)


def test_deck_collect_notes_returns_dict_per_slide() -> None:
    """`collect_notes()` returns a dict keyed by slide id with per-slide notes."""
    data = yaml.safe_load((FIXTURE_DIR / "ginga_one_full.deck.yml").read_text(encoding="utf-8"))
    lib = FrameGraphLibrary(LIB_DIR)
    deck = FrameGraphDeckRenderer(data, library=lib)
    notes = deck.collect_notes()
    assert isinstance(notes, dict)
    # Notes dict size is bounded by the slide count
    assert len(notes) <= len(deck.slides_raw)
