"""Phase 2 of ADR 0001 — render-graph dispatch tests.

Phase 2 makes FrameSet traversal the authoritative iteration spine
for `FrameGraphDeckRenderer.render_all` and lifts deck-merge
enrichments (`build_frame_doc` in `framegraph._frameset`) for native
FrameSet YAML.

These tests pin two contracts:

1. **Byte-identical deck render parity**: every deck fixture under
   `tests/fixtures/*deck*.yml` and `static/fixture/*deck*.yml`
   produces byte-identical SVG via the post-Phase-2 path
   (`coerce_to_frameset` + frame-by-frame `build_slide_doc`) that
   the pre-Phase-2 path (direct `self.slides_raw` iteration)
   would have produced. The pre-Phase-2 baseline is reconstructed
   in-test by replaying the legacy iteration logic against
   `self.slides_raw` so the test is self-contained.

2. **Native-FrameSet enrichment**: `build_frame_doc` correctly
   merges `frameset.tokens` < `frame.visual.tokens` (deep_merge),
   carries `frameset.symbols` ∪ `frame.visual.symbols`, resolves
   `frame.extends` chains, and injects the canonical
   `rendering_contract` defaults when the Frame doesn't declare
   its own — matching `library.build_slide_doc`'s contract for
   the deck path.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from framegraph._frameset import (
    FrameTarget,
    _resolve_extends_chain,
    build_frame_doc,
    render_frameset,
    validate_frameset,
)
from framegraph.library import FrameGraphDeckRenderer
from framegraph.renderer import FrameGraphRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────
# Deck render parity — every deck fixture renders byte-identically
# ─────────────────────────────────────────────────────────────────


def _deck_fixtures() -> list[Path]:
    """Discover every deck YAML fixture in the corpus."""
    out: list[Path] = []
    for d in (REPO_ROOT / "tests" / "fixtures", REPO_ROOT / "static" / "fixture"):
        if d.exists():
            out.extend(sorted(p for p in d.glob("*.yml") if "deck" in p.name))
    return out


def _render_legacy_deck_path(deck_data: dict, tmp_path: Path) -> list[str]:
    """Replay the *pre-Phase-2* deck render path explicitly.

    Iterates `self.slides_raw` directly (the path Phase 2 retired in
    favour of the FrameSet spine) and returns the per-slide SVG
    strings. This is the baseline against which the post-Phase-2
    path must be byte-identical.
    """
    deck = FrameGraphDeckRenderer(deck_data)
    svgs: list[str] = []
    for slide in deck.slides_raw:
        doc = deck.build_slide_doc(slide)
        renderer = FrameGraphRenderer(doc)
        svgs.append(renderer.render_svg())
    return svgs


def _render_post_phase2_deck_path(deck_data: dict, tmp_path: Path) -> list[str]:
    """Run the post-Phase-2 `render_all` path and read back per-slide SVGs."""
    deck = FrameGraphDeckRenderer(deck_data)
    out_dir = tmp_path / "post_phase2"
    paths = deck.render_all(out_dir)
    return [p.read_text(encoding="utf-8") for p in paths]


@pytest.mark.parametrize("fixture_path", _deck_fixtures(), ids=lambda p: p.name)
def test_deck_render_byte_identical_through_frameset_spine(
    fixture_path: Path, tmp_path: Path
) -> None:
    """Every deck fixture renders byte-identically post-Phase-2.

    Pre-fix, the slide loop iterated `self.slides_raw` directly.
    Post-Phase-2, the loop drives off the FrameSet view of
    `self.raw`. This test asserts the SVG bytes are identical
    across both paths so the rewire is purely structural.
    """
    deck_data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(deck_data, dict) or "slides" not in deck_data:
        pytest.skip(f"{fixture_path.name} is not a deck YAML")

    legacy_svgs = _render_legacy_deck_path(deck_data, tmp_path)
    post_phase2_svgs = _render_post_phase2_deck_path(deck_data, tmp_path)

    assert len(post_phase2_svgs) == len(legacy_svgs), (
        f"{fixture_path.name}: post-Phase-2 produced "
        f"{len(post_phase2_svgs)} SVGs, legacy produced {len(legacy_svgs)}"
    )
    for i, (a, b) in enumerate(zip(legacy_svgs, post_phase2_svgs, strict=False)):
        assert a == b, (
            f"{fixture_path.name} slide #{i + 1}: "
            f"SVG bytes differ between legacy and post-Phase-2 paths "
            f"(legacy len={len(a)}, post-Phase-2 len={len(b)})"
        )


# ─────────────────────────────────────────────────────────────────
# Native-FrameSet enrichment — build_frame_doc semantics
# ─────────────────────────────────────────────────────────────────


class TestBuildFrameDoc:
    def _basic_frameset(self, **kwargs):
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {"targets": [{"name": "x", "canvas": [200, 100]}]},
                **kwargs,
            },
            "frames": [{"id": "f", "visual": {"layers": []}}],
        }
        return validate_frameset(spec)

    def test_canonical_rendering_contract_injected_when_absent(self) -> None:
        """Native FrameSets without a `scene.rendering_contract`
        receive the four canonical contracts that
        `library.build_slide_doc` always injects on deck slides."""
        fs = self._basic_frameset()
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        contract = doc["scene"]["rendering_contract"]
        assert contract["coordinate_mode"] == "absolute"
        assert contract["preserve_manual_line_breaks"] is True
        assert contract["text"]["min_font_size"] == 7
        assert contract["text"]["overflow"] == "shrink_to_fit"
        assert contract["semantics"]["decorative_objects_may_omit_bind"] is True

    def test_existing_rendering_contract_preserved(self) -> None:
        """When a Frame declares its own `scene.rendering_contract`,
        `build_frame_doc` does not override it."""
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {
                    "id": "f",
                    "scene": {
                        "rendering_contract": {
                            "coordinate_mode": "absolute",
                            "text": {"min_font_size": 12},
                        }
                    },
                }
            ],
        }
        fs = validate_frameset(spec)
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        assert doc["scene"]["rendering_contract"]["text"]["min_font_size"] == 12

    def test_canvas_from_target(self) -> None:
        fs = self._basic_frameset()
        target = FrameTarget(name="custom", canvas=[640, 480])
        doc = build_frame_doc(fs, fs.frames[0], target)
        assert doc["scene"]["canvas"]["size"] == [640.0, 480.0]
        assert doc["scene"]["canvas"]["units"] == "px"

    def test_token_deep_merge_frame_wins_on_conflict(self) -> None:
        """`frameset.tokens` < `frame.visual.tokens` — Frame-local
        tokens win on scalar conflicts; nested tokens deep-merge."""
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]},
                "tokens": {
                    "colors": {
                        "brand": "#0000FF",  # frameset says blue
                        "ink": "#000000",
                    }
                },
            },
            "frames": [
                {
                    "id": "f",
                    "visual": {
                        "tokens": {
                            "colors": {"brand": "#FF0000"}  # frame says red
                        }
                    },
                }
            ],
        }
        fs = validate_frameset(spec)
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        colors = doc["visual"]["tokens"]["colors"]
        assert colors["brand"] == "#FF0000"  # frame wins
        assert colors["ink"] == "#000000"  # frameset preserved (deep_merge)

    def test_symbol_shallow_merge(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]},
                "symbols": {"shared": {"shape": "rect"}},
            },
            "frames": [
                {
                    "id": "f",
                    "visual": {"symbols": {"local": {"shape": "ellipse"}}},
                }
            ],
        }
        fs = validate_frameset(spec)
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        symbols = doc["visual"]["symbols"]
        assert "shared" in symbols
        assert "local" in symbols

    def test_component_def_shallow_merge(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]},
                "component_defs": {"card": {"slots": [{"role": "label"}]}},
            },
            "frames": [
                {
                    "id": "f",
                    "visual": {"component_defs": {"badge": {"slots": [{"role": "text"}]}}},
                }
            ],
        }
        fs = validate_frameset(spec)
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        cdefs = doc["visual"]["component_defs"]
        assert "card" in cdefs
        assert "badge" in cdefs

    def test_canonical_empty_semantic_when_absent(self) -> None:
        fs = self._basic_frameset()
        doc = build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])
        sem = doc["semantic"]
        assert sem == {
            "ontology": {"node_types": {}, "edge_types": {}},
            "nodes": [],
            "edges": [],
        }

    def test_pattern_composition_raises_until_phase_7(self) -> None:
        """Pattern-composed Frames (`use:` set) need
        `FrameGraphLibrary` access for theme + stylesheet
        resolution. Phase 2 doesn't ship that — Phase 7 will. The
        FrameSet path raises a clear NotImplementedError so the
        legacy deck path stays the authoritative composer until
        then.
        """
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [{"id": "f", "use": 10, "fill": {}}],
        }
        fs = validate_frameset(spec)
        with pytest.raises(NotImplementedError, match="Phase 2 doesn't yet support patterns"):
            build_frame_doc(fs, fs.frames[0], fs.frameset.defaults.targets[0])


# ─────────────────────────────────────────────────────────────────
# extends — recursive token / symbol / layer merge
# ─────────────────────────────────────────────────────────────────


class TestExtendsResolution:
    def test_extends_inherits_tokens(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {
                    "id": "base",
                    "visual": {"tokens": {"colors": {"bg": "#FFFFFF"}}},
                },
                {
                    "id": "derived",
                    "extends": "base",
                    "visual": {"tokens": {"colors": {"fg": "#000000"}}},
                },
            ],
        }
        fs = validate_frameset(spec)
        derived = fs.frames[1]
        resolved = _resolve_extends_chain(derived, fs)
        colors = (resolved.visual or {}).get("tokens", {}).get("colors", {})
        assert colors == {"bg": "#FFFFFF", "fg": "#000000"}

    def test_extends_layer_id_replacement(self) -> None:
        """Same-id derived layer replaces the base's layer of that id."""
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {
                    "id": "base",
                    "visual": {
                        "layers": [
                            {"id": "bg", "objects": [{"type": "rect", "fill": "white"}]},
                            {"id": "content", "objects": []},
                        ]
                    },
                },
                {
                    "id": "derived",
                    "extends": "base",
                    "visual": {
                        "layers": [
                            {
                                "id": "bg",
                                "objects": [{"type": "rect", "fill": "black"}],
                            }
                        ]
                    },
                },
            ],
        }
        fs = validate_frameset(spec)
        resolved = _resolve_extends_chain(fs.frames[1], fs)
        layers = (resolved.visual or {}).get("layers", [])
        layer_map = {lyr["id"]: lyr for lyr in layers}
        assert layer_map["bg"]["objects"][0]["fill"] == "black"  # derived wins
        assert "content" in layer_map  # base layer preserved

    def test_extends_chain_three_deep(self) -> None:
        """Token deep-merge propagates through a 3-frame chain."""
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {"id": "a", "visual": {"tokens": {"colors": {"a": "1"}}}},
                {
                    "id": "b",
                    "extends": "a",
                    "visual": {"tokens": {"colors": {"b": "2"}}},
                },
                {
                    "id": "c",
                    "extends": "b",
                    "visual": {"tokens": {"colors": {"c": "3"}}},
                },
            ],
        }
        fs = validate_frameset(spec)
        resolved = _resolve_extends_chain(fs.frames[2], fs)
        colors = (resolved.visual or {}).get("tokens", {}).get("colors", {})
        assert colors == {"a": "1", "b": "2", "c": "3"}

    def test_extends_cycle_detected(self) -> None:
        """Cycles in the extends chain raise — the FrameSet
        validator already rejects dangling references; this guards
        the in-resolution detection of cycles introduced by hand-
        constructed `Frame` instances.
        """
        from framegraph._frameset import Frame, FrameSetMeta

        # Build a FrameSet by hand bypassing the validator (to test
        # the runtime detection path).
        a = Frame(id="a", extends="b")
        b = Frame(id="b", extends="a")
        # The validator would reject these dangling refs, but our
        # cycle test bypasses it with construct().
        from framegraph._frameset import FrameSetDocument

        fs = FrameSetDocument.model_construct(
            dsl="FrameGraph",
            version=2.0,
            kind="frameset",
            frameset=FrameSetMeta(),
            frames=[a, b],
        )
        with pytest.raises(ValueError, match="Cycle"):
            _resolve_extends_chain(a, fs)


# ─────────────────────────────────────────────────────────────────
# render_frameset end-to-end with native-FrameSet enrichment
# ─────────────────────────────────────────────────────────────────


class TestRenderFramesetEnriched:
    def test_native_frameset_renders_with_token_inheritance(self) -> None:
        """A native FrameSet whose `frameset.tokens` carries colours
        and whose Frame references those colours by name renders
        correctly — proving the token deep-merge reaches the
        renderer."""
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {
                "defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]},
                "tokens": {"colors": {"brand": "#FF0000"}},
            },
            "frames": [
                {
                    "id": "f",
                    "visual": {
                        "layers": [
                            {
                                "id": "L",
                                "objects": [
                                    {
                                        "type": "rect",
                                        "id": "r",
                                        "decorative": True,
                                        "box": [0, 0, 100, 100],
                                        "fill": "brand",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ],
        }
        fs = validate_frameset(spec)
        out = render_frameset(fs)
        assert len(out) == 1
        # The frameset-level brand colour reaches the SVG fill.
        assert "#FF0000" in out[0].svg

    def test_native_frameset_chain_renders_each_frame(self) -> None:
        spec = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "x", "canvas": [100, 100]}]}},
            "frames": [
                {"id": "a", "next": "b"},
                {"id": "b", "prev": "a", "next": "c"},
                {"id": "c", "prev": "b"},
            ],
        }
        fs = validate_frameset(spec)
        out = render_frameset(fs)
        assert [r.frame_id for r in out] == ["a", "b", "c"]
        # Each output is a well-formed SVG document.
        for r in out:
            ET.fromstring(r.svg)
