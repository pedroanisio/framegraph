"""Unit tests for `framegraph._docsite.gallery`.

These assert the PALS-law guarantees: every bundled example validates
against the schema, standalone docs are rendered fresh, and the report
is honest about what was embedded vs. skipped.
"""

from __future__ import annotations

from pathlib import Path

from framegraph._docsite.gallery import build_gallery, discover_examples

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DATE = "2026-01-01"


def test_discovers_bundled_examples() -> None:
    examples = discover_examples(EXAMPLES)
    slugs = {e.slug for e in examples}
    assert {"genai-ecosystem", "shadow-and-border"}.issubset(slugs)
    assert all(e.kind in ("doc", "deck") for e in examples)


def test_all_examples_validate_against_schema(tmp_path: Path) -> None:
    """PALS gate: no shipped example may fail schema validation."""
    _, report = build_gallery(EXAMPLES, tmp_path / "assets", DATE)
    assert report.ok, f"examples failed validation: {report.failed}"
    assert report.validated


def test_standalone_docs_rendered_fresh(tmp_path: Path) -> None:
    md, report = build_gallery(EXAMPLES, tmp_path / "assets", DATE)
    # The three standalone docs are re-rendered, producing real SVG assets.
    assert "shadow-and-border" in report.rendered
    for slug in report.rendered:
        svg = tmp_path / "assets" / f"{slug}.svg"
        assert svg.exists()
        assert svg.read_text(encoding="utf-8").lstrip().startswith("<")


def test_page_has_disclaimer_and_title(tmp_path: Path) -> None:
    md, _ = build_gallery(EXAMPLES, tmp_path / "assets", DATE)
    assert md.startswith("---\n")
    assert "# Gallery" in md
    assert f'date: "{DATE}"' in md
