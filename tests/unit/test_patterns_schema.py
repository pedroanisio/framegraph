"""Unit tests for `framegraph._patterns` — the slide-pattern catalog schema.

Refined-vocabulary schema (Phase 2):

- ``size`` is a `Literal` of nine controlled values.
- ``placement`` replaces the loose ``position`` string with a typed
  union: a 9-cell `Anchor`, a `RegionPlacement` (named area), or a
  `RelativePlacement` (relation + target zone role).
- ``shape`` is an optional new field for what a zone *is*
  (``card``, ``bar``, ``node``, …) — extracted from the previous
  size-leakage values.

The bundled `static/refs/slides-patter-a.yml` is normalized to this
shape via `scripts/normalize_patterns.py` and validates cleanly here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from framegraph._patterns import (
    PATTERN_CATALOG_PATH,
    Anchor,
    PatternCatalog,
    PatternZone,
    Placement,
    RegionPlacement,
    RelativePlacement,
    SlidePattern,
    load_pattern_catalog,
)


# ─────────────────────────────────────────────────────────────────
# Anchor — 9-cell grid + fullbleed
# ─────────────────────────────────────────────────────────────────


class TestAnchor:
    def test_grid_anchor(self) -> None:
        a = Anchor.model_validate({"h": "left", "v": "top"})
        assert a.h == "left" and a.v == "top"
        assert a.fullbleed is False

    def test_fullbleed_anchor(self) -> None:
        a = Anchor.model_validate({"fullbleed": True})
        assert a.fullbleed is True

    @pytest.mark.parametrize("h", ["left", "center", "right"])
    @pytest.mark.parametrize("v", ["top", "middle", "bottom"])
    def test_all_nine_cells(self, h: str, v: str) -> None:
        Anchor(h=h, v=v)  # type: ignore[arg-type]

    def test_invalid_h_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Anchor(h="middle", v="top")  # type: ignore[arg-type]

    def test_invalid_v_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Anchor(h="left", v="center")  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────
# RelativePlacement — relation + target role
# ─────────────────────────────────────────────────────────────────


class TestRelativePlacement:
    @pytest.mark.parametrize(
        "rel",
        ["above", "below", "left_of", "right_of", "inside", "around", "between", "near", "on"],
    )
    def test_all_relations_accepted(self, rel: str) -> None:
        p = RelativePlacement(relation=rel, target="title")  # type: ignore[arg-type]
        assert p.relation == rel

    def test_invalid_relation_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RelativePlacement(relation="behind", target="title")  # type: ignore[arg-type]

    def test_target_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            RelativePlacement(relation="below", target="")


# ─────────────────────────────────────────────────────────────────
# RegionPlacement — named structured area
# ─────────────────────────────────────────────────────────────────


class TestRegionPlacement:
    def test_minimal_region(self) -> None:
        r = RegionPlacement(region="matrix_body")
        assert r.region == "matrix_body"

    def test_region_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            RegionPlacement(region="")


# ─────────────────────────────────────────────────────────────────
# PatternZone — refined shape with size + placement
# ─────────────────────────────────────────────────────────────────


class TestPatternZone:
    def test_minimal_zone_with_anchor(self) -> None:
        z = PatternZone.model_validate(
            {
                "role": "title",
                "size": "large",
                "placement": {"anchor": {"h": "center", "v": "middle"}},
            }
        )
        assert isinstance(z.placement, Anchor)
        assert z.placement.h == "center"

    def test_zone_with_region_placement(self) -> None:
        z = PatternZone.model_validate(
            {
                "role": "risks",
                "size": "equal",
                "placement": {"region": "matrix_body"},
            }
        )
        assert isinstance(z.placement, RegionPlacement)

    def test_zone_with_relative_placement(self) -> None:
        z = PatternZone.model_validate(
            {
                "role": "subtitle",
                "size": "medium",
                "placement": {"relative": {"relation": "below", "target": "title"}},
            }
        )
        assert isinstance(z.placement, RelativePlacement)

    def test_zone_with_optional_shape(self) -> None:
        z = PatternZone.model_validate(
            {
                "role": "items",
                "size": "equal",
                "placement": {"anchor": {"h": "center", "v": "middle"}},
                "shape": "card",
            }
        )
        assert z.shape == "card"

    @pytest.mark.parametrize(
        "size",
        ["xs", "small", "medium", "large", "xl", "full", "equal", "variable", "contextual"],
    )
    def test_all_size_values_accepted(self, size: str) -> None:
        PatternZone.model_validate(
            {
                "role": "r",
                "size": size,
                "placement": {"anchor": {"h": "center", "v": "middle"}},
            }
        )

    def test_invalid_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone.model_validate(
                {
                    "role": "r",
                    "size": "huge",
                    "placement": {"anchor": {"h": "center", "v": "middle"}},
                }
            )

    def test_role_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone.model_validate(
                {
                    "role": "",
                    "size": "large",
                    "placement": {"anchor": {"h": "center", "v": "middle"}},
                }
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PatternZone.model_validate(
                {
                    "role": "r",
                    "size": "large",
                    "placement": {"anchor": {"h": "center", "v": "middle"}},
                    "rotation": 45,
                }
            )


# ─────────────────────────────────────────────────────────────────
# Pattern + catalog invariants (unchanged from Phase 1)
# ─────────────────────────────────────────────────────────────────


def _zone(role: str = "r") -> dict[str, object]:
    return {
        "role": role,
        "size": "medium",
        "placement": {"anchor": {"h": "center", "v": "middle"}},
    }


class TestSlidePattern:
    def test_minimal_pattern(self) -> None:
        p = SlidePattern.model_validate(
            {"id": 1, "name": "X", "layout_disposition": "x", "zones": [_zone()]}
        )
        assert p.id == 1

    def test_id_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            SlidePattern.model_validate(
                {"id": 0, "name": "X", "layout_disposition": "x", "zones": [_zone()]}
            )

    def test_at_least_one_zone(self) -> None:
        with pytest.raises(ValidationError):
            SlidePattern.model_validate(
                {"id": 1, "name": "X", "layout_disposition": "x", "zones": []}
            )

    def test_duplicate_role_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate role"):
            SlidePattern.model_validate(
                {
                    "id": 1,
                    "name": "X",
                    "layout_disposition": "x",
                    "zones": [_zone("title"), _zone("title")],
                }
            )


class TestPatternCatalog:
    def _patt(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": 1,
            "name": "X",
            "layout_disposition": "x",
            "zones": [_zone()],
        }
        base.update(overrides)
        return base

    def test_minimal_catalog(self) -> None:
        c = PatternCatalog.model_validate(
            {"slide_template_patterns": [self._patt()]}
        )
        assert len(c.slide_template_patterns) == 1

    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate pattern id"):
            PatternCatalog.model_validate(
                {
                    "slide_template_patterns": [
                        self._patt(id=1, name="A"),
                        self._patt(id=1, name="B"),
                    ]
                }
            )

    def test_duplicate_names_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate pattern name"):
            PatternCatalog.model_validate(
                {
                    "slide_template_patterns": [
                        self._patt(id=1, name="Same"),
                        self._patt(id=2, name="Same"),
                    ]
                }
            )

    def test_get_by_id(self) -> None:
        # Use distinct zone sets so the structural-duplicate validator
        # doesn't reject this catalog.
        zone_a = {
            "role": "title",
            "size": "large",
            "placement": {"anchor": {"h": "center", "v": "top"}},
        }
        zone_b = {
            "role": "title",
            "size": "small",
            "placement": {"anchor": {"h": "left", "v": "bottom"}},
        }
        c = PatternCatalog.model_validate(
            {
                "slide_template_patterns": [
                    {"id": 1, "name": "A", "layout_disposition": "x", "zones": [zone_a]},
                    {"id": 2, "name": "B", "layout_disposition": "x", "zones": [zone_b]},
                ]
            }
        )
        assert c.get(2).name == "B"

    def test_get_unknown_raises(self) -> None:
        c = PatternCatalog.model_validate(
            {"slide_template_patterns": [self._patt()]}
        )
        with pytest.raises(KeyError):
            c.get(99)

    def test_structurally_identical_patterns_rejected(self) -> None:
        """Two patterns with the same zone set under different ids/names is a duplicate.

        Pattern identity is structural: the multiset of
        ``(role, size, placement, shape)`` tuples across zones.
        Different ``id``, ``name``, or ``layout_disposition`` does
        not make two structurally-equal patterns distinct.
        """
        with pytest.raises(ValidationError, match="structurally identical"):
            PatternCatalog.model_validate(
                {
                    "slide_template_patterns": [
                        self._patt(id=1, name="Alpha"),
                        self._patt(id=2, name="Beta"),  # same zones
                    ]
                }
            )

    def test_structurally_identical_detected_despite_zone_order(self) -> None:
        """Zone order does not make patterns distinct — composition is unordered."""
        z1 = {
            "role": "title",
            "size": "large",
            "placement": {"anchor": {"h": "center", "v": "top"}},
        }
        z2 = {
            "role": "subtitle",
            "size": "medium",
            "placement": {"anchor": {"h": "center", "v": "middle"}},
        }
        with pytest.raises(ValidationError, match="structurally identical"):
            PatternCatalog.model_validate(
                {
                    "slide_template_patterns": [
                        {
                            "id": 1,
                            "name": "Alpha",
                            "layout_disposition": "first",
                            "zones": [z1, z2],
                        },
                        {
                            "id": 2,
                            "name": "Beta",
                            "layout_disposition": "second",
                            "zones": [z2, z1],  # reordered
                        },
                    ]
                }
            )

    def test_distinct_patterns_with_overlapping_zones_allowed(self) -> None:
        """Sharing a few zones is fine — only full structural equality collides."""
        common = {
            "role": "title",
            "size": "large",
            "placement": {"anchor": {"h": "center", "v": "top"}},
        }
        only_a = {
            "role": "footer",
            "size": "small",
            "placement": {"anchor": {"h": "center", "v": "bottom"}},
        }
        only_b = {
            "role": "sidebar",
            "size": "medium",
            "placement": {"anchor": {"h": "left", "v": "middle"}},
        }
        c = PatternCatalog.model_validate(
            {
                "slide_template_patterns": [
                    {
                        "id": 1,
                        "name": "Alpha",
                        "layout_disposition": "x",
                        "zones": [common, only_a],
                    },
                    {
                        "id": 2,
                        "name": "Beta",
                        "layout_disposition": "x",
                        "zones": [common, only_b],
                    },
                ]
            }
        )
        assert len(c.slide_template_patterns) == 2

    def test_shape_difference_makes_patterns_distinct(self) -> None:
        """A `shape` mismatch between otherwise-identical zones is a real difference."""
        base = {
            "role": "items",
            "size": "equal",
            "placement": {"anchor": {"h": "center", "v": "middle"}},
        }
        c = PatternCatalog.model_validate(
            {
                "slide_template_patterns": [
                    {
                        "id": 1,
                        "name": "Alpha",
                        "layout_disposition": "x",
                        "zones": [{**base, "shape": "card"}],
                    },
                    {
                        "id": 2,
                        "name": "Beta",
                        "layout_disposition": "x",
                        "zones": [{**base, "shape": "node"}],
                    },
                ]
            }
        )
        assert len(c.slide_template_patterns) == 2


# ─────────────────────────────────────────────────────────────────
# Bundled YAML — must satisfy the refined schema
# ─────────────────────────────────────────────────────────────────


class TestBundledCatalog:
    def test_canonical_path_exists(self) -> None:
        assert PATTERN_CATALOG_PATH.exists()

    def test_load_returns_validated_catalog(self) -> None:
        c = load_pattern_catalog()
        assert isinstance(c, PatternCatalog)
        assert len(c.slide_template_patterns) == 50

    def test_canonical_ids_contiguous_1_through_50(self) -> None:
        c = load_pattern_catalog()
        ids = sorted(p.id for p in c.slide_template_patterns)
        assert ids == list(range(1, 51))

    def test_every_pattern_has_at_least_one_zone(self) -> None:
        c = load_pattern_catalog()
        for p in c.slide_template_patterns:
            assert len(p.zones) >= 1, p.name

    def test_load_accepts_path_argument(self, tmp_path: Path) -> None:
        alt = tmp_path / "alt.yml"
        alt.write_text(
            yaml.safe_dump(
                {
                    "slide_template_patterns": [
                        {
                            "id": 1,
                            "name": "Custom",
                            "layout_disposition": "x",
                            "zones": [
                                {
                                    "role": "r",
                                    "size": "medium",
                                    "placement": {
                                        "anchor": {"h": "center", "v": "middle"}
                                    },
                                }
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        c = load_pattern_catalog(alt)
        assert c.slide_template_patterns[0].name == "Custom"
