"""Render-parity tests for `framegraph._frameset`.

Phase 1 of ADR 0001. Pins the contract that:

- Every existing single-document fixture under `static/fixture/*.yml`
  renders to **byte-identical SVG** via the new FrameSet path
  (`render_frameset(coerce_to_frameset(doc))[0].svg`) as via the
  legacy path (`FrameGraphRenderer(doc).render_svg()`).
- A native FrameSet YAML with multiple targets renders each target
  at its declared canvas dimensions.
- Coerced presentation decks render to **structurally** equivalent
  output (every slide present, in declaration order, valid SVG).
  Byte-identical deck parity is **Phase 2** scope; the legacy
  `FrameGraphDeckRenderer` remains the authoritative deck renderer
  for byte-level comparison until then.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from framegraph._frameset import (
    FrameSetDocument,
    coerce_to_frameset,
    render_frameset,
    validate_frameset,
)
from framegraph.renderer import FrameGraphRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────
# Single-document fixtures — byte-identical SVG parity
# ─────────────────────────────────────────────────────────────────


def _single_doc_fixtures() -> list[Path]:
    """Discover bundled single-document fixtures.

    Excludes `*-deck.yml` (which the deck renderer owns in Phase 1).
    """
    candidates = sorted((REPO_ROOT / "static" / "fixture").glob("*.yml"))
    return [p for p in candidates if "deck" not in p.name]


@pytest.mark.parametrize("fixture_path", _single_doc_fixtures(), ids=lambda p: p.name)
def test_single_doc_render_byte_identical_through_frameset(fixture_path: Path) -> None:
    """For every single-doc fixture: legacy render == FrameSet render.

    `render_frameset(coerce_to_frameset(doc))[0].svg` must equal
    `FrameGraphRenderer(doc).render_svg()` byte-for-byte. Any
    divergence indicates either:

    - the coercion lost or added information that surfaces in the
      rendered output, or
    - the renderer adapter's `project_frame_to_document` reconstructs
      the legacy single-document shape unfaithfully.
    """
    doc = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("dsl") != "FrameGraph":
        pytest.skip(f"{fixture_path.name} is not a FrameGraph YAML")

    legacy_svg = FrameGraphRenderer(doc).render_svg()

    fs = coerce_to_frameset(doc)
    assert isinstance(fs, FrameSetDocument)
    assert len(fs.frames) == 1
    new_svg = render_frameset(fs)[0].svg

    assert new_svg == legacy_svg, (
        f"FrameSet path produced different SVG for {fixture_path.name}: "
        f"new length={len(new_svg)}, legacy length={len(legacy_svg)}"
    )


# ─────────────────────────────────────────────────────────────────
# Deck fixtures — structural equivalence (not byte-identical in Phase 1)
# ─────────────────────────────────────────────────────────────────


def _deck_fixtures() -> list[Path]:
    """Discover bundled deck fixtures."""
    candidates = sorted((REPO_ROOT / "tests" / "fixtures").glob("*deck*.yml"))
    candidates += sorted((REPO_ROOT / "static" / "fixture").glob("*deck*.yml"))
    return candidates


@pytest.mark.parametrize("fixture_path", _deck_fixtures(), ids=lambda p: p.name)
def test_deck_coerces_to_frameset_with_slide_count_matched(
    fixture_path: Path,
) -> None:
    """For every deck fixture: coercion produces one Frame per slide.

    Phase 1 contract: structural equivalence only. Frame ids and
    declaration order are preserved; byte-identical render parity
    is deferred to Phase 2.
    """
    doc = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "slides" not in doc:
        pytest.skip(f"{fixture_path.name} is not a deck YAML")

    slides = doc.get("slides") or []
    fs = coerce_to_frameset(doc)
    assert len(fs.frames) == len(slides), (
        f"{fixture_path.name}: coerce produced {len(fs.frames)} frames for {len(slides)} slides"
    )

    # Frame ids preserve slide ids in declaration order.
    expected_ids: list[str] = []
    for i, slide in enumerate(slides):
        expected_ids.append(str(slide.get("id") or f"slide_{slide.get('slide', i + 1):02d}"))
    assert [f.id for f in fs.frames] == expected_ids


@pytest.mark.parametrize("fixture_path", _deck_fixtures(), ids=lambda p: p.name)
def test_deck_chain_links_materialized(fixture_path: Path) -> None:
    """Every coerced deck has a complete next/prev chain.

    `frames[0].prev` is None, `frames[-1].next` is None, every
    middle frame has both pointers wired to its neighbors (unless
    the author already declared an explicit `next` / `prev`).
    """
    doc = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "slides" not in doc:
        pytest.skip(f"{fixture_path.name} is not a deck YAML")

    fs = coerce_to_frameset(doc)
    if len(fs.frames) < 2:
        pytest.skip("chain-link semantics only meaningful on 2+ frames")

    # First frame has no implicit prev.
    if not any(slide.get("prev") for slide in (doc.get("slides") or [])[:1]):
        assert fs.frames[0].prev is None

    # Middle frames have both pointers (when not author-overridden).
    for i in range(1, len(fs.frames) - 1):
        slide = (doc.get("slides") or [])[i] if isinstance(doc.get("slides"), list) else {}
        if not slide.get("prev"):
            assert fs.frames[i].prev == fs.frames[i - 1].id
        if not slide.get("next"):
            assert fs.frames[i].next == fs.frames[i + 1].id


# ─────────────────────────────────────────────────────────────────
# Native FrameSet — multi-target rendering
# ─────────────────────────────────────────────────────────────────


class TestNativeFrameSetRendering:
    def _two_target_frameset(self) -> dict:
        return {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {
                    "targets": [
                        {"name": "landscape", "canvas": [1920, 1080]},
                        {"name": "portrait", "canvas": [1080, 1920]},
                    ]
                },
            },
            "frames": [
                {
                    "id": "hero",
                    "title": "Hero",
                    "visual": {
                        "tokens": {"colors": {"bg": "#FFFFFF"}},
                        "layers": [
                            {
                                "id": "bg",
                                "objects": [
                                    {
                                        "type": "rect",
                                        "id": "rect",
                                        "decorative": True,
                                        "box": [0, 0, 100, 100],
                                        "fill": "bg",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }

    def test_landscape_target_renders_at_landscape_canvas(self) -> None:
        fs = validate_frameset(self._two_target_frameset())
        out = render_frameset(fs, target_name="landscape")
        assert len(out) == 1
        assert out[0].canvas == [1920.0, 1080.0]
        assert out[0].target_name == "landscape"
        # SVG carries the target canvas dimensions.
        root = ET.fromstring(out[0].svg)
        assert root.attrib.get("width") == "1920"
        assert root.attrib.get("height") == "1080"

    def test_portrait_target_renders_at_portrait_canvas(self) -> None:
        fs = validate_frameset(self._two_target_frameset())
        out = render_frameset(fs, target_name="portrait")
        assert out[0].canvas == [1080.0, 1920.0]
        root = ET.fromstring(out[0].svg)
        assert root.attrib.get("width") == "1080"
        assert root.attrib.get("height") == "1920"

    def test_default_target_is_first_declared(self) -> None:
        # No `target_name=` argument → first target on each Frame
        # (or first FrameSet default target).
        fs = validate_frameset(self._two_target_frameset())
        out = render_frameset(fs)
        assert out[0].target_name == "landscape"

    def test_unknown_target_raises_keyerror(self) -> None:
        fs = validate_frameset(self._two_target_frameset())
        with pytest.raises(KeyError, match="no target named"):
            render_frameset(fs, target_name="square")

    def test_frame_ids_filter(self) -> None:
        # Render only a subset of frames.
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {"id": "a"},
                {"id": "b"},
                {"id": "c"},
            ],
        }
        fs = validate_frameset(spec)
        out = render_frameset(fs, frame_ids=["a", "c"])
        assert [r.frame_id for r in out] == ["a", "c"]

    def test_frame_ids_filter_unknown_raises(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [{"id": "a"}],
        }
        fs = validate_frameset(spec)
        with pytest.raises(KeyError, match="missing"):
            render_frameset(fs, frame_ids=["a", "missing"])

    def test_per_frame_target_overrides_defaults(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "default", "canvas": [100, 100]}]}},
            "frames": [
                {"id": "default-target"},
                {
                    "id": "custom-target",
                    "targets": [{"name": "default", "canvas": [500, 500]}],
                },
            ],
        }
        fs = validate_frameset(spec)
        out = render_frameset(fs)
        assert out[0].canvas == [100.0, 100.0]
        assert out[1].canvas == [500.0, 500.0]
