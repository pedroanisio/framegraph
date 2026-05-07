"""Unit tests for `framegraph._patterns` — the slide-pattern catalog schema.

Validates the structure of `static/refs/slides-patter-a.yml` and the
`PatternCatalog` Pydantic model that consumes it.

The catalog is the layout-pattern vocabulary an LLM agent can address
by id ("give me a #44 with these contents") to request a known
composition. Strict validation here keeps that surface stable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from framegraph._patterns import (
    PATTERN_CATALOG_PATH,
    PatternCatalog,
    PatternZone,
    SlidePattern,
    load_pattern_catalog,
)


# ─────────────────────────────────────────────────────────────────
# Per-zone validation
# ─────────────────────────────────────────────────────────────────


class TestPatternZone:
    def test_minimal_zone(self) -> None:
        z = PatternZone(role="title", position="center", size="large")
        assert z.role == "title"

    def test_role_required(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone(position="center", size="large")  # type: ignore[call-arg]

    def test_role_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone(role="", position="center", size="large")

    def test_position_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone(role="title", position="", size="large")

    def test_size_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone(role="title", position="center", size="")

    def test_extra_fields_rejected(self) -> None:
        """`extra='forbid'` — typos in zone fields should fail loudly."""
        with pytest.raises(ValidationError):
            PatternZone(
                role="title",
                position="center",
                size="large",
                rotation=45,  # type: ignore[call-arg]
            )


# ─────────────────────────────────────────────────────────────────
# Per-pattern validation
# ─────────────────────────────────────────────────────────────────


class TestSlidePattern:
    def test_minimal_pattern(self) -> None:
        p = SlidePattern(
            id=1,
            name="Title",
            layout_disposition="A title slide.",
            zones=[
                {"role": "title", "position": "center", "size": "large"},
            ],
        )
        assert p.id == 1
        assert len(p.zones) == 1

    def test_id_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            SlidePattern(
                id=0,
                name="X",
                layout_disposition="x",
                zones=[{"role": "r", "position": "p", "size": "s"}],
            )

    def test_at_least_one_zone(self) -> None:
        """A pattern with no zones is meaningless."""
        with pytest.raises(ValidationError):
            SlidePattern(
                id=1,
                name="X",
                layout_disposition="x",
                zones=[],
            )

    def test_duplicate_role_within_pattern_rejected(self) -> None:
        """Within a pattern, role names must be distinguishable."""
        with pytest.raises(ValidationError, match="duplicate role"):
            SlidePattern(
                id=1,
                name="X",
                layout_disposition="x",
                zones=[
                    {"role": "title", "position": "center", "size": "large"},
                    {"role": "title", "position": "top", "size": "small"},
                ],
            )


# ─────────────────────────────────────────────────────────────────
# Catalog-level validation
# ─────────────────────────────────────────────────────────────────


class TestPatternCatalog:
    def _patt(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": 1,
            "name": "X",
            "layout_disposition": "x",
            "zones": [{"role": "r", "position": "p", "size": "s"}],
        }
        base.update(overrides)
        return base

    def test_minimal_catalog_validates(self) -> None:
        c = PatternCatalog(slide_template_patterns=[self._patt()])
        assert len(c.slide_template_patterns) == 1

    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate pattern id"):
            PatternCatalog(
                slide_template_patterns=[
                    self._patt(id=1, name="A"),
                    self._patt(id=1, name="B"),
                ]
            )

    def test_duplicate_names_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate pattern name"):
            PatternCatalog(
                slide_template_patterns=[
                    self._patt(id=1, name="Same"),
                    self._patt(id=2, name="Same"),
                ]
            )

    def test_get_by_id(self) -> None:
        c = PatternCatalog(
            slide_template_patterns=[
                self._patt(id=1, name="A"),
                self._patt(id=2, name="B"),
            ]
        )
        assert c.get(2).name == "B"

    def test_get_unknown_id_raises(self) -> None:
        c = PatternCatalog(slide_template_patterns=[self._patt()])
        with pytest.raises(KeyError):
            c.get(99)


# ─────────────────────────────────────────────────────────────────
# Bundled YAML — the canonical 50-pattern catalog
# ─────────────────────────────────────────────────────────────────


class TestBundledCatalog:
    """The shipped `slides-patter-a.yml` must validate cleanly.

    Acts as a regression guard: if anyone edits the YAML and breaks
    the schema, this test fires before the file ships.
    """

    def test_canonical_catalog_path_exists(self) -> None:
        assert PATTERN_CATALOG_PATH.exists()

    def test_load_pattern_catalog_returns_validated_model(self) -> None:
        c = load_pattern_catalog()
        assert isinstance(c, PatternCatalog)
        assert len(c.slide_template_patterns) == 50

    def test_canonical_ids_are_1_through_50_contiguous(self) -> None:
        c = load_pattern_catalog()
        ids = sorted(p.id for p in c.slide_template_patterns)
        assert ids == list(range(1, 51))

    def test_every_pattern_has_at_least_one_zone(self) -> None:
        c = load_pattern_catalog()
        for p in c.slide_template_patterns:
            assert len(p.zones) >= 1, p.name

    def test_load_pattern_catalog_accepts_path_argument(self, tmp_path: Path) -> None:
        """Callers may load alternate catalogs by path."""
        alt = tmp_path / "alt.yml"
        alt.write_text(
            yaml.safe_dump(
                {
                    "slide_template_patterns": [
                        {
                            "id": 1,
                            "name": "Custom",
                            "layout_disposition": "x",
                            "zones": [{"role": "r", "position": "p", "size": "s"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        c = load_pattern_catalog(alt)
        assert c.slide_template_patterns[0].name == "Custom"
