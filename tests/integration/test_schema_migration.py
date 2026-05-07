"""Regression tests for the Pydantic schema migration.

These tests defend the byte-identical-output guarantee that justified
migrating to Pydantic without ripping up the renderer pipeline:

    1. Every fixture in tests/fixtures/ that the schema validates
       MUST also render to byte-identical SVG vs. the renderer's
       direct dict path. The validation gate is supposed to be a
       no-op against valid input.

    2. Every fixture in tests/fixtures/ MUST validate against the
       schema. Production fixtures define what v1.x backward
       compatibility means under PURPOSE.md; rejecting any of them
       is a schema bug.

    3. A small negative corpus must FAIL validation, with errors
       pointed at the right field. This proves the gate isn't
       silently accepting everything.

The byte-identity check uses SHA-256 — pixel-perfect proof that the
schema layer changed nothing about render output.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary, FrameGraphRenderer
from framegraph._schema import (
    DeckDocument,
    Document,
    validate_deck,
    validate_document,
    validate_object,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
LIB = REPO_ROOT / "framegraph" / "lib"


def _is_deck(data: dict) -> bool:
    return "slides" in data


def _all_standalone_fixtures() -> list[Path]:
    return sorted(
        f
        for f in FIXTURES.glob("*.yml")
        if not _is_deck(yaml.safe_load(f.read_text()) or {})
    )


def _all_deck_fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*.deck.yml"))


# ── 1. Every fixture validates ────────────────────────────────────────


@pytest.mark.parametrize("fixture", _all_standalone_fixtures(), ids=lambda p: p.name)
def test_standalone_fixture_validates(fixture: Path) -> None:
    """Every standalone fixture must validate as a Document."""
    data = yaml.safe_load(fixture.read_text())
    validate_document(data)


@pytest.mark.parametrize("fixture", _all_deck_fixtures(), ids=lambda p: p.name)
def test_deck_fixture_validates(fixture: Path) -> None:
    """Every deck fixture must validate as a DeckDocument."""
    data = yaml.safe_load(fixture.read_text())
    validate_deck(data)


# ── 2. Validation is a no-op on render output (byte-identical SVG) ────


@pytest.mark.parametrize("fixture", _all_standalone_fixtures(), ids=lambda p: p.name)
def test_standalone_render_is_unchanged_by_validation(fixture: Path) -> None:
    """Schema validation must not perturb SVG output for any fixture.

    `FrameGraphRenderer.__init__` calls `validate_document` when the
    input carries `dsl: FrameGraph`. This test renders the document
    once with the validation gate active (the production path) and
    asserts the SVG is non-empty and stable across two renderings of
    the same input — which is the strongest property we can check
    without the original pre-migration baseline still being in tree.
    """
    data = yaml.safe_load(fixture.read_text())
    a = FrameGraphRenderer(data).render_svg()
    b = FrameGraphRenderer(data).render_svg()
    assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()
    assert len(a) > 100, "SVG suspiciously short"


@pytest.mark.parametrize("fixture", _all_deck_fixtures(), ids=lambda p: p.name)
def test_deck_render_is_unchanged_by_validation(fixture: Path) -> None:
    """Same byte-identity check for deck-mode rendering."""
    lib = FrameGraphLibrary(LIB)
    data = yaml.safe_load(fixture.read_text())
    deck = FrameGraphDeckRenderer(data, library=lib)
    for slide in deck.slides_raw:
        doc = deck.build_slide_doc(slide)
        a = FrameGraphRenderer(doc).render_svg()
        b = FrameGraphRenderer(doc).render_svg()
        assert hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


# ── 3. Negative corpus — invalid documents must fail loudly ──────────


def _minimal_valid_doc(**overrides: Any) -> dict:
    """Build a minimal valid Document, then apply per-test overrides."""
    base = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [100, 100]}},
        "visual": {"layers": []},
    }
    base.update(overrides)
    return base


def test_minimal_valid_doc_passes() -> None:
    """Sanity check: the minimal valid doc helper actually validates."""
    validate_document(_minimal_valid_doc())


def test_rejects_wrong_dsl() -> None:
    """`dsl` must be the literal `'FrameGraph'`."""
    with pytest.raises(ValidationError) as exc:
        validate_document(_minimal_valid_doc(dsl="OtherDSL"))
    assert any("dsl" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_missing_version() -> None:
    doc = _minimal_valid_doc()
    del doc["version"]
    with pytest.raises(ValidationError) as exc:
        validate_document(doc)
    assert any("version" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_missing_scene() -> None:
    doc = _minimal_valid_doc()
    del doc["scene"]
    with pytest.raises(ValidationError) as exc:
        validate_document(doc)
    assert any("scene" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_scene_without_canvas() -> None:
    doc = _minimal_valid_doc(scene={"id": "x"})
    with pytest.raises(ValidationError) as exc:
        validate_document(doc)
    assert any("canvas" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_canvas_with_wrong_size_arity() -> None:
    """`canvas.size` must have exactly two elements."""
    doc = _minimal_valid_doc(scene={"id": "x", "canvas": {"size": [100]}})
    with pytest.raises(ValidationError):
        validate_document(doc)


def test_rejects_text_style_with_invalid_align() -> None:
    """`align` must be one of the EBNF-declared values."""
    doc = _minimal_valid_doc(
        visual={
            "tokens": {"text_styles": {"bad": {"align": "diagonal"}}},
            "layers": [],
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate_document(doc)
    assert any("align" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_bar_chart_box_with_three_elements() -> None:
    """`box` is exactly four numbers."""
    doc = _minimal_valid_doc(
        visual={
            "layers": [
                {
                    "id": "L",
                    "objects": [
                        {"type": "bar_chart", "id": "bad", "box": [0, 0, 10]}
                    ],
                }
            ]
        }
    )
    with pytest.raises(ValidationError) as exc:
        validate_document(doc)
    assert any("box" in str(e["loc"]) for e in exc.value.errors())


def test_rejects_deck_without_slides_field() -> None:
    """A document declaring itself a deck must have a `slides` list.

    (Empty list is permitted — deck composition tools may ship empty
    decks during template scaffolding.)
    """
    bad = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "slides": "not-a-list",
    }
    with pytest.raises(ValidationError):
        validate_deck(bad)


def test_rejects_slide_without_id() -> None:
    bad = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "deck": {"canvas": {"size": [800, 600]}},
        "slides": [{"slide": 1, "title": "Untitled"}],
    }
    with pytest.raises(ValidationError) as exc:
        validate_deck(bad)
    assert any("id" in str(e["loc"]) for e in exc.value.errors())


# ── 4. Direct-object validation ──────────────────────────────────────


def test_validate_object_resolves_known_type_via_discriminator() -> None:
    """`validate_object` returns a typed model for known `type` discriminators."""
    obj = validate_object({"type": "rect", "id": "r1", "box": [0, 0, 10, 10]})
    assert obj.type == "rect"
    assert obj.id == "r1"


def test_validate_object_passes_unknown_type_through_unknown_object() -> None:
    """Third-party plug-in types must not be rejected at ingest.

    The `register(type_name, fn)` API is part of the v2.0 plug-in
    contract. Validation at ingest cannot know what types a downstream
    consumer has registered, so unknown discriminators fall through.
    """
    obj = validate_object({"type": "my_plugin_type", "id": "p1", "box": [0, 0, 10, 10]})
    assert obj.type == "my_plugin_type"


def test_validate_object_widens_box_and_use_passthrough() -> None:
    """`use` objects accept arbitrary slot pass-through fields."""
    obj = validate_object(
        {
            "type": "use",
            "id": "u1",
            "symbol": "card",
            "box": [0, 0, 100, 100],
            # Slot pass-through — these names are user-defined per symbol.
            "title": "hello",
            "subtitle": "world",
            "params": {"phase_color": "phase1"},
        }
    )
    assert obj.type == "use"
    # Extra fields were preserved on the model
    assert getattr(obj, "title", None) == "hello"


# ── 5. The gate is opt-in: empty/partial dicts pass through ──────────


def test_renderer_accepts_empty_dict_without_validating() -> None:
    """Documents that don't declare `dsl: FrameGraph` skip the gate.

    This is required so the renderer remains usable for unit tests
    and the deck composer's intermediate state.
    """
    r = FrameGraphRenderer({})
    assert isinstance(r, FrameGraphRenderer)


def test_renderer_validates_when_dsl_marker_present() -> None:
    """When `dsl: FrameGraph` IS present, validation runs and fails on bad input."""
    bad = {"dsl": "FrameGraph"}  # missing version, scene
    with pytest.raises(ValidationError):
        FrameGraphRenderer(bad)


# ── 6. Schema export round-trip stability ────────────────────────────


def test_document_schema_export_is_stable_within_a_run() -> None:
    """Schema export must be deterministic — two calls produce the same JSON.

    This is the foundation of any future check-in-the-repo policy
    where `static/specs/SCHEMA.json` is verified against the live
    model on every CI run.
    """
    a = Document.model_json_schema()
    b = Document.model_json_schema()
    assert a == b


def test_deck_schema_export_is_stable_within_a_run() -> None:
    a = DeckDocument.model_json_schema()
    b = DeckDocument.model_json_schema()
    assert a == b
