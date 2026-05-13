"""Coercion tests for `framegraph._frameset.coerce_to_frameset`.

Phase 1 of ADR 0001. Pins that the coercion shim is **total** over
old YAML shapes (`hybrid-semantic-visual-diagram`, `presentation-deck`)
and produces structurally-correct FrameSets:

- Single docs become a one-Frame FrameSet with the doc's canvas.
- Decks become an N-Frame FrameSet with `next`/`prev` chain in
  declaration order.
- All inputs are validated by `FrameSetDocument.model_validate` so
  the resulting object passes every structural invariant.
"""

from __future__ import annotations

import pytest

from framegraph._frameset import (
    FrameSetDocument,
    coerce_to_frameset,
)

# ─────────────────────────────────────────────────────────────────
# Bad inputs
# ─────────────────────────────────────────────────────────────────


class TestCoerceErrors:
    def test_non_mapping_root_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a mapping"):
            coerce_to_frameset(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_missing_dsl_marker_raises(self) -> None:
        with pytest.raises(ValueError, match="dsl: FrameGraph"):
            coerce_to_frameset({"version": 1.0, "scene": {"id": "x"}})

    def test_wrong_dsl_marker_raises(self) -> None:
        with pytest.raises(ValueError, match="dsl: FrameGraph"):
            coerce_to_frameset({"dsl": "Other", "version": 1.0})


# ─────────────────────────────────────────────────────────────────
# Single-document path
# ─────────────────────────────────────────────────────────────────


class TestCoerceSingleDocument:
    def test_typical_single_doc(self) -> None:
        doc = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "kind": "hybrid-semantic-visual-diagram",
            "scene": {
                "id": "my_diagram",
                "name": "My Diagram",
                "canvas": {"size": [960, 540]},
            },
            "visual": {"layers": []},
        }
        fs = coerce_to_frameset(doc)
        assert isinstance(fs, FrameSetDocument)
        assert fs.kind == "frameset"
        assert len(fs.frames) == 1
        assert fs.frames[0].id == "my_diagram"
        assert fs.frames[0].title == "My Diagram"
        assert fs.frames[0].targets[0].canvas == [960.0, 540.0]
        # version flows through
        assert fs.version == 1.5

    def test_single_doc_without_canvas_uses_default(self) -> None:
        # Documents without an explicit canvas fall back to the
        # project's de-facto 1280x720 default.
        doc = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "scene": {"id": "no_canvas"},
            "visual": {"layers": []},
        }
        fs = coerce_to_frameset(doc)
        assert fs.frames[0].targets[0].canvas == [1280.0, 720.0]

    def test_single_doc_preserves_visual_and_semantic(self) -> None:
        doc = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "kind": "hybrid-semantic-visual-diagram",
            "scene": {"id": "x", "canvas": {"size": [200, 100]}},
            "semantic": {"nodes": [{"id": "n1", "type": "actor"}]},
            "visual": {
                "tokens": {"colors": {"brand": "#FF0000"}},
                "layers": [{"id": "L", "objects": []}],
            },
        }
        fs = coerce_to_frameset(doc)
        f = fs.frames[0]
        assert f.semantic == {"nodes": [{"id": "n1", "type": "actor"}]}
        assert f.visual is not None
        assert f.visual["tokens"]["colors"]["brand"] == "#FF0000"

    def test_theme_alias_lifted(self) -> None:
        doc = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "$theme": "mckinsey",
            "stylesheet": "default",
            "scene": {"id": "x", "canvas": {"size": [100, 100]}},
            "visual": {"layers": []},
        }
        fs = coerce_to_frameset(doc)
        assert fs.theme == "mckinsey"
        assert fs.stylesheet == "default"


# ─────────────────────────────────────────────────────────────────
# Deck path
# ─────────────────────────────────────────────────────────────────


class TestCoerceDeck:
    def _basic_deck(self) -> dict:
        return {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [1280, 720]}},
            "slides": [
                {"slide": 1, "id": "s1", "title": "Slide 1"},
                {"slide": 2, "id": "s2", "title": "Slide 2"},
                {"slide": 3, "id": "s3", "title": "Slide 3"},
            ],
        }

    def test_each_slide_becomes_a_frame(self) -> None:
        fs = coerce_to_frameset(self._basic_deck())
        assert len(fs.frames) == 3
        assert [f.id for f in fs.frames] == ["s1", "s2", "s3"]
        assert [f.title for f in fs.frames] == ["Slide 1", "Slide 2", "Slide 3"]

    def test_implicit_chain_materialized(self) -> None:
        fs = coerce_to_frameset(self._basic_deck())
        assert fs.frames[0].next == "s2"
        assert fs.frames[1].prev == "s1"
        assert fs.frames[1].next == "s3"
        assert fs.frames[2].prev == "s2"
        # First has no prev, last has no next.
        assert fs.frames[0].prev is None
        assert fs.frames[2].next is None

    def test_explicit_next_overrides_chain(self) -> None:
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [100, 100]}},
            "slides": [
                {"slide": 1, "id": "s1", "next": "s3"},
                {"slide": 2, "id": "s2"},
                {"slide": 3, "id": "s3"},
            ],
        }
        fs = coerce_to_frameset(deck)
        # s1 author-declared next='s3' wins over implicit chain.
        assert fs.frames[0].next == "s3"

    def test_deck_canvas_carries_to_frameset_default(self) -> None:
        fs = coerce_to_frameset(self._basic_deck())
        # Frames inherit deck canvas via FrameSet defaults; per-Frame
        # targets are empty unless a slide overrides.
        assert fs.frameset.defaults.targets[0].canvas == [1280.0, 720.0]
        assert fs.frames[0].targets == []  # falls back to defaults

    def test_per_slide_canvas_override(self) -> None:
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [1280, 720]}},
            "slides": [
                {
                    "slide": 1,
                    "id": "wide",
                    "scene": {"canvas": {"size": [1920, 1080]}},
                },
                {"slide": 2, "id": "default"},
            ],
        }
        fs = coerce_to_frameset(deck)
        # Wide slide carries an explicit per-Frame target.
        assert fs.frames[0].targets[0].canvas == [1920.0, 1080.0]
        # Default slide stays at FrameSet default.
        assert fs.frames[1].targets == []

    def test_no_kind_with_slides_routed_as_deck(self) -> None:
        # Some corpus YAML files declare `kind:` but most do not.
        # The presence of `slides:` is the discriminator.
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "deck": {"canvas": {"size": [800, 600]}},
            "slides": [{"slide": 1, "id": "a"}, {"slide": 2, "id": "b"}],
        }
        fs = coerce_to_frameset(deck)
        assert len(fs.frames) == 2
        assert fs.frames[0].next == "b"

    def test_empty_deck_produces_placeholder_frame(self) -> None:
        # Edge case: empty `slides:` list. The shim emits a single
        # "empty" placeholder Frame so downstream consumers always
        # have something to dispatch over.
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [100, 100]}},
            "slides": [],
        }
        fs = coerce_to_frameset(deck)
        assert len(fs.frames) == 1
        assert fs.frames[0].id == "empty"

    def test_slide_with_no_explicit_id_gets_default(self) -> None:
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [100, 100]}},
            "slides": [{"slide": 1}, {"slide": 2}],
        }
        fs = coerce_to_frameset(deck)
        # Default ids are zero-padded `slide_NN` for sortable filenames.
        assert fs.frames[0].id == "slide_01"
        assert fs.frames[1].id == "slide_02"


# ─────────────────────────────────────────────────────────────────
# Native frameset path (passthrough)
# ─────────────────────────────────────────────────────────────────


class TestCoerceNativeFrameSet:
    def test_native_frameset_passes_through(self) -> None:
        native = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frameset": {"defaults": {"targets": [{"name": "landscape", "canvas": [1920, 1080]}]}},
            "frames": [
                {"id": "a", "next": "b"},
                {"id": "b", "prev": "a"},
            ],
        }
        fs = coerce_to_frameset(native)
        assert isinstance(fs, FrameSetDocument)
        assert fs.kind == "frameset"
        assert len(fs.frames) == 2
        assert fs.frames[0].next == "b"

    def test_native_frameset_with_links(self) -> None:
        native = {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frames": [
                {
                    "id": "main",
                    "links": [
                        {"to": "appendix", "relation": "appendix"},
                        {
                            "to": "https://example.com",
                            "external": True,
                            "label": "Docs",
                        },
                    ],
                },
                {"id": "appendix"},
            ],
        }
        fs = coerce_to_frameset(native)
        main = fs.frames[0]
        assert len(main.links) == 2
        assert main.links[0].relation == "appendix"
        assert main.links[1].external is True
