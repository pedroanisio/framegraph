"""Tests for the catalog's per-pattern ``enterprise_layout`` polish presets.

The presets ship designed defaults (treatments, typography, optional
hand-tuned coordinate overrides) that travel *with* the pattern, so
every catalog item renders as a polished enterprise layout out of the
box. The user's stylesheet still controls brand/theme tokens.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph._patterns import (
    EnterpriseLayout,
    EnterpriseZonePreset,
    load_pattern_catalog,
)
from framegraph.patterns.style import (
    Stylesheet,
    resolve_zone_style,
)

# ── Schema ──────────────────────────────────────────────────────────


def test_enterprise_zone_preset_accepts_all_optional_fields() -> None:
    preset = EnterpriseZonePreset(
        treatment={"fill_color": "surface", "corner_radius": 6},
        typography="card_body",
        box=(100.0, 200.0, 300.0, 400.0),
        label_text="STRENGTHS",
    )
    assert preset.box == (100.0, 200.0, 300.0, 400.0)
    assert preset.label_text == "STRENGTHS"
    assert isinstance(preset.treatment, dict)


def test_enterprise_zone_preset_treatment_accepts_string_name() -> None:
    preset = EnterpriseZonePreset(treatment="card_recommend")
    assert preset.treatment == "card_recommend"


def test_enterprise_layout_default_zones_is_empty() -> None:
    layout = EnterpriseLayout()
    assert layout.zones == {}
    assert layout.canvas_overrides == {}
    assert layout.notes is None


def test_enterprise_zone_preset_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EnterpriseZonePreset(treatment={}, font_size=72)  # type: ignore[call-arg]


# ── Catalog integration ─────────────────────────────────────────────


def test_catalog_pattern_1_ships_enterprise_layout() -> None:
    cat = load_pattern_catalog()
    p1 = next(p for p in cat.slide_template_patterns if p.id == 1)
    assert p1.enterprise_layout is not None
    assert "title" in p1.enterprise_layout.zones
    title_preset = p1.enterprise_layout.zones["title"]
    # Pilot pattern 1 has a hand-tuned title box.
    assert title_preset.box is not None
    # And inline treatment with display-grade slot typography.
    assert isinstance(title_preset.treatment, dict)
    slots = title_preset.treatment.get("slots", {})
    title_slot = slots.get("title", {})
    typo = title_slot.get("typography", {})
    assert typo.get("size") == 72


def test_catalog_pilot_patterns_all_have_enterprise_layout() -> None:
    """The Stage-1 pilot covers patterns 1, 2, 10, 49, 93, 219."""
    cat = load_pattern_catalog()
    by_id = {p.id: p for p in cat.slide_template_patterns}
    pilot_ids = [1, 2, 10, 49, 93, 219]
    for pid in pilot_ids:
        p = by_id[pid]
        assert p.enterprise_layout is not None, (
            f"pattern {pid} ({p.name!r}) missing enterprise_layout"
        )
        assert p.enterprise_layout.zones, f"pattern {pid} has empty enterprise_layout.zones"


def test_catalog_unpolished_patterns_have_no_enterprise_layout() -> None:
    """Most patterns still ship without a preset — the field is optional
    and absence is the backward-compatible default."""
    cat = load_pattern_catalog()
    without = [p for p in cat.slide_template_patterns if p.enterprise_layout is None]
    # We have not yet polished every pattern; the catalog still has
    # plenty without a preset. This will shrink over time.
    assert len(without) > 0


# ── Resolution ──────────────────────────────────────────────────────


def _minimal_stylesheet() -> Stylesheet:
    """A near-empty stylesheet so the preset's intent is observable
    without any rule-side overrides muddying the result."""
    return Stylesheet.model_validate(
        {
            "text_styles": {
                "card_body": {"font": "primary", "size": 10},
            },
            "treatments": {},
            "roles": [],
        }
    )


def test_resolve_zone_style_applies_preset_when_stylesheet_silent() -> None:
    cat = load_pattern_catalog()
    p1 = next(p for p in cat.slide_template_patterns if p.id == 1)
    title_zone = next(z for z in p1.zones if z.role == "title")
    preset = p1.enterprise_layout.zones["title"]

    ss = _minimal_stylesheet()
    result = resolve_zone_style(title_zone, ss, enterprise_preset=preset)

    # Preset's box override propagates.
    assert result["box"] == (120.0, 360.0, 1680.0, 180.0)
    # Inline treatment becomes treatment_props so emitters consume it.
    tp = result.get("treatment_props")
    assert isinstance(tp, dict)
    assert tp.get("slots", {}).get("title", {}).get("typography", {}).get("size") == 72


def test_resolve_zone_style_preset_overrides_stylesheet_rule() -> None:
    """Preset wins on conflict — catalog *is* the design; stylesheet
    rules can't accidentally clobber a polished pattern's geometry."""
    cat = load_pattern_catalog()
    p1 = next(p for p in cat.slide_template_patterns if p.id == 1)
    title_zone = next(z for z in p1.zones if z.role == "title")
    preset = p1.enterprise_layout.zones["title"]

    ss = Stylesheet.model_validate(
        {
            "text_styles": {"card_body": {"size": 10}},
            "treatments": {"junk": {"fill_color": "garbage"}},
            "roles": [
                # Generic rule that would otherwise apply a tiny body
                # treatment to every title_body zone.
                {
                    "match": {"content_type": "title_body"},
                    "treatment": "junk",
                    "typography": "card_body",
                }
            ],
        }
    )

    result = resolve_zone_style(title_zone, ss, enterprise_preset=preset)
    # Preset's treatment dict beat the rule's "junk" treatment name.
    tp = result.get("treatment_props")
    assert isinstance(tp, dict)
    assert tp.get("fill_color") == "none"


def test_resolve_zone_style_no_preset_falls_back_to_stylesheet() -> None:
    """Patterns without an enterprise_layout still honor stylesheet
    rules — the merge is additive."""
    cat = load_pattern_catalog()
    # Find a pattern with no enterprise_layout (there are many).
    p_unpolished = next(p for p in cat.slide_template_patterns if p.enterprise_layout is None)
    zone = p_unpolished.zones[0]

    ss = Stylesheet.model_validate(
        {
            "text_styles": {"card_body": {"size": 10}},
            "treatments": {"plain": {"fill_color": "surface"}},
            "roles": [{"match": {}, "treatment": "plain", "typography": "card_body"}],
        }
    )

    result = resolve_zone_style(zone, ss, enterprise_preset=None)
    assert result.get("treatment") == "plain"
    tp = result.get("treatment_props")
    assert tp == {"fill_color": "surface"}
