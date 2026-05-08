"""Unit tests for `framegraph.patterns.fill` — Phase 1 of the fill-and-render roadmap.

The fill layer turns a pattern's typed zones into a payload contract:
given a pattern id, an agent supplies content keyed by zone role,
and validation enforces shape per `content_type`.

Phase 1 scope (per `docs/ROADMAP-FILL-RENDER.md`):

- `PatternFill` model — wraps a pattern_id + per-role content dict
- `derive_default_fill_schema(pattern)` — computes the default
  Pydantic-style shape from the pattern's zones' content_types
- `load_fill(pattern_id, payload)` — resolver that loads + validates
- `MissingContentTypeError` — raised when a pattern has any zone
  without a content_type (sidecar required for those, Phase 2+)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph._patterns import PatternZone, SlidePattern
from framegraph.patterns import (
    MissingContentTypeError,
    PatternFill,
    derive_default_fill_schema,
    load_fill,
)


# ─────────────────────────────────────────────────────────────────
# Helpers — minimal fully-typed pattern fixtures
# ─────────────────────────────────────────────────────────────────


def _zone(
    role: str,
    *,
    content_type: str | None = "title_body",
    size: str = "medium",
    h: str = "center",
    v: str = "middle",
) -> dict:
    """Build one PatternZone-shaped dict for a fixture."""
    z: dict = {
        "role": role,
        "size": size,
        "placement": {"anchor": {"h": h, "v": v}},
    }
    if content_type is not None:
        z["content_type"] = content_type
    return z


def _pattern(pattern_id: int, zones: list[dict]) -> SlidePattern:
    """Build a SlidePattern fixture from minimal zone dicts."""
    return SlidePattern.model_validate(
        {
            "id": pattern_id,
            "name": f"P{pattern_id}",
            "layout_disposition": "x",
            "zones": zones,
        }
    )


# ─────────────────────────────────────────────────────────────────
# Test 1 — empty payload rejected when required zones unfilled
# ─────────────────────────────────────────────────────────────────


class TestRequiredZones:
    def test_empty_payload_rejected_when_zones_required(self) -> None:
        """A pattern with required zones must have content for all of them.

        For Phase 1, every annotated zone is required (sidecars in
        Phase 2 may mark zones optional).
        """
        p = _pattern(1, [_zone("title", content_type="title_body")])
        with pytest.raises(ValidationError, match="title"):
            PatternFill.model_validate(
                {"pattern_id": 1, "content": {}, "_pattern": p}
            )


# ─────────────────────────────────────────────────────────────────
# Test 2 — title_body default shape
# ─────────────────────────────────────────────────────────────────


class TestDefaultSchemas:
    def test_title_body_accepts_title_and_body(self) -> None:
        p = _pattern(1, [_zone("headline", content_type="title_body")])
        fill = PatternFill.model_validate(
            {
                "pattern_id": 1,
                "content": {"headline": {"title": "T", "body": "B"}},
                "_pattern": p,
            }
        )
        assert fill.content.headline.title == "T"
        assert fill.content.headline.body == "B"

    def test_title_body_body_is_optional(self) -> None:
        p = _pattern(1, [_zone("headline", content_type="title_body")])
        fill = PatternFill.model_validate(
            {
                "pattern_id": 1,
                "content": {"headline": {"title": "T"}},
                "_pattern": p,
            }
        )
        assert fill.content.headline.body is None

    def test_metric_accepts_label_value_trend(self) -> None:
        p = _pattern(1, [_zone("kpi", content_type="metric")])
        fill = PatternFill.model_validate(
            {
                "pattern_id": 1,
                "content": {
                    "kpi": {"label": "Revenue", "value": "$2.4M", "trend": "+12%"},
                },
                "_pattern": p,
            }
        )
        assert fill.content.kpi.label == "Revenue"
        assert fill.content.kpi.value == "$2.4M"
        assert fill.content.kpi.trend == "+12%"

    def test_metric_trend_optional(self) -> None:
        p = _pattern(1, [_zone("kpi", content_type="metric")])
        fill = PatternFill.model_validate(
            {
                "pattern_id": 1,
                "content": {"kpi": {"label": "R", "value": "$1"}},
                "_pattern": p,
            }
        )
        assert fill.content.kpi.trend is None

    def test_list_items_accepts_string_list(self) -> None:
        p = _pattern(1, [_zone("steps", content_type="list_items")])
        fill = PatternFill.model_validate(
            {
                "pattern_id": 1,
                "content": {"steps": ["one", "two", "three"]},
                "_pattern": p,
            }
        )
        assert fill.content.steps == ["one", "two", "three"]

    def test_decorative_accepts_no_content(self) -> None:
        """`decorative` zones don't need a fill — pure visual.

        The user may pass None (or omit) for a decorative role.
        """
        p = _pattern(1, [_zone("divider", content_type="decorative")])
        fill = PatternFill.model_validate(
            {"pattern_id": 1, "content": {"divider": None}, "_pattern": p}
        )
        assert fill.content.divider is None


# ─────────────────────────────────────────────────────────────────
# Test 3 — extra roles rejected (no silent acceptance)
# ─────────────────────────────────────────────────────────────────


class TestStrictness:
    def test_unknown_role_in_payload_rejected(self) -> None:
        p = _pattern(1, [_zone("title", content_type="title_body")])
        with pytest.raises(ValidationError, match="unknown_role|extra"):
            PatternFill.model_validate(
                {
                    "pattern_id": 1,
                    "content": {
                        "title": {"title": "T"},
                        "rogue_field": "shouldnt be here",
                    },
                    "_pattern": p,
                }
            )

    def test_pattern_id_must_match_pattern(self) -> None:
        """Defensive: pattern_id in payload must match the resolved pattern."""
        p = _pattern(1, [_zone("title", content_type="title_body")])
        with pytest.raises(ValidationError, match="pattern_id"):
            PatternFill.model_validate(
                {
                    "pattern_id": 99,
                    "content": {"title": {"title": "T"}},
                    "_pattern": p,
                }
            )


# ─────────────────────────────────────────────────────────────────
# Test 4 — patterns with un-annotated zones raise MissingContentTypeError
# ─────────────────────────────────────────────────────────────────


class TestMissingContentType:
    def test_unannotated_zone_raises_missing_content_type_error(self) -> None:
        """Phase 1 hard-requires every zone to have a content_type.

        The 34% un-annotated tail is curated in Phase 6 or
        overridden by sidecars in Phase 2.
        """
        p = _pattern(
            1,
            [
                _zone("title", content_type="title_body"),
                _zone("mystery", content_type=None),
            ],
        )
        with pytest.raises(MissingContentTypeError, match="mystery"):
            derive_default_fill_schema(p)

    def test_error_names_all_missing_zones(self) -> None:
        """The error message lists every offender, not just the first."""
        p = _pattern(
            1,
            [
                _zone("a", content_type=None),
                _zone("b", content_type="title_body"),
                _zone("c", content_type=None),
            ],
        )
        with pytest.raises(MissingContentTypeError) as exc_info:
            derive_default_fill_schema(p)
        msg = str(exc_info.value)
        assert "a" in msg and "c" in msg


# ─────────────────────────────────────────────────────────────────
# Test 5 — load_fill resolves and validates
# ─────────────────────────────────────────────────────────────────


class TestLoadFill:
    def test_load_fill_resolves_pattern_from_catalog(self) -> None:
        """`load_fill(pattern_id, payload)` looks up the pattern and validates."""
        # Catalog pattern #1 (Title Slide) — known to exist; check
        # whether all zones are annotated. If not, this test
        # exercises the round-trip on the first fully-annotated
        # catalog pattern instead.
        from framegraph._patterns import load_pattern_catalog

        cat = load_pattern_catalog()
        target = next(
            (
                p
                for p in cat.slide_template_patterns
                if all(z.content_type is not None for z in p.zones)
            ),
            None,
        )
        assert target is not None, "catalog has no fully-annotated patterns"

        # Build a default fill for the target pattern.
        payload = {}
        for z in target.zones:
            ct = z.content_type
            if ct == "title_body":
                payload[z.role] = {"title": "x", "body": "y"}
            elif ct == "metric":
                payload[z.role] = {"label": "L", "value": "V"}
            elif ct == "list_items":
                payload[z.role] = ["a", "b"]
            elif ct == "key_value":
                payload[z.role] = {"k": "v"}
            elif ct == "comparison":
                payload[z.role] = {"left": "L", "right": "R"}
            elif ct == "chart_data":
                payload[z.role] = {"type": "bar", "series": []}
            elif ct == "table_data":
                payload[z.role] = {"headers": ["h"], "rows": [["v"]]}
            elif ct == "image":
                payload[z.role] = {"src": "x.png"}
            elif ct == "axis_label":
                payload[z.role] = {"title": "T"}
            elif ct == "decorative":
                payload[z.role] = None
        fill = load_fill(target.id, payload)
        assert fill.pattern_id == target.id

    def test_load_fill_unknown_id_raises(self) -> None:
        with pytest.raises(KeyError):
            load_fill(99999, {})


# ─────────────────────────────────────────────────────────────────
# Test 6 — derive_default_fill_schema returns per-role types
# ─────────────────────────────────────────────────────────────────


class TestDeriveDefaultSchema:
    def test_schema_has_one_field_per_zone(self) -> None:
        p = _pattern(
            1,
            [
                _zone("a", content_type="title_body"),
                _zone("b", content_type="metric"),
                _zone("c", content_type="list_items"),
            ],
        )
        schema_cls = derive_default_fill_schema(p)
        # The returned class is a Pydantic model; its fields are the roles.
        assert set(schema_cls.model_fields.keys()) == {"a", "b", "c"}


# ─────────────────────────────────────────────────────────────────
# Phase 2 — sidecar loading
# ─────────────────────────────────────────────────────────────────


class TestSidecarLoading:
    """Sidecar YAML files override default per-zone fill shapes.

    The sidecar mini-DSL (v1) supports only what BMC needs:

    - For `list_items` zones, declare `item_kind: string | object`.
    - When `item_kind: object`, declare `item_fields: {name: {type, required}}`.

    Anything richer waits for later phases.
    """

    def test_sidecar_file_validates_with_pydantic_model(self, tmp_path) -> None:
        """A sidecar YAML loads into a `PatternFillSidecar` Pydantic model."""
        from framegraph.patterns import PatternFillSidecar, load_sidecar

        path = tmp_path / "044-test.yml"
        path.write_text(
            """
pattern_id: 44
zones:
  revenue_streams:
    item_kind: object
    item_fields:
      label: {type: string, required: true}
      metric: {type: string, required: true}
example_fill:
  revenue_streams:
    - {label: "Subscriptions", metric: "$2.4M"}
""",
            encoding="utf-8",
        )
        sidecar = load_sidecar(path)
        assert isinstance(sidecar, PatternFillSidecar)
        assert sidecar.pattern_id == 44
        assert "revenue_streams" in sidecar.zones

    def test_sidecar_overrides_default_list_items_to_object_list(
        self, tmp_path
    ) -> None:
        """A list_items zone with an object override accepts list[dict]."""
        from framegraph.patterns import load_sidecar

        # Use a synthetic pattern (single list_items zone) so this
        # test doesn't depend on BMC bundled-catalog state.
        from framegraph._patterns import SlidePattern

        pattern = SlidePattern.model_validate(
            {
                "id": 99001,
                "name": "Test",
                "layout_disposition": "x",
                "zones": [
                    {
                        "role": "items",
                        "size": "medium",
                        "placement": {"anchor": {"h": "center", "v": "middle"}},
                        "content_type": "list_items",
                    }
                ],
            }
        )

        path = tmp_path / "99001-test.yml"
        path.write_text(
            """
pattern_id: 99001
zones:
  items:
    item_kind: object
    item_fields:
      label: {type: string, required: true}
      metric: {type: string, required: true}
""",
            encoding="utf-8",
        )
        sidecar = load_sidecar(path)

        # Build the Model from pattern + sidecar; should accept
        # list[{label, metric}] but reject plain list[str].
        from framegraph.patterns import derive_fill_schema_with_sidecar

        Model = derive_fill_schema_with_sidecar(pattern, sidecar)
        # Object-list payload validates.
        Model.model_validate(
            {"items": [{"label": "A", "metric": "$1"}, {"label": "B", "metric": "$2"}]}
        )
        # String-list payload (default shape) is now rejected because
        # the sidecar tightened the type.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Model.model_validate({"items": ["a", "b"]})

    def test_sidecar_pattern_id_must_match(self, tmp_path) -> None:
        """A sidecar declares its pattern_id; mismatch with the pattern is rejected."""
        from framegraph.patterns import (
            PatternFillSidecar,
            derive_fill_schema_with_sidecar,
        )
        from framegraph._patterns import SlidePattern

        sidecar = PatternFillSidecar.model_validate(
            {"pattern_id": 999, "zones": {}}
        )
        pattern = SlidePattern.model_validate(
            {
                "id": 1,
                "name": "X",
                "layout_disposition": "x",
                "zones": [
                    {
                        "role": "r",
                        "size": "medium",
                        "placement": {"anchor": {"h": "center", "v": "middle"}},
                        "content_type": "title_body",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="pattern_id"):
            derive_fill_schema_with_sidecar(pattern, sidecar)


class TestBmcSidecar:
    """The bundled BMC sidecar must round-trip its example_fill."""

    def test_bmc_sidecar_file_exists(self) -> None:
        from framegraph.patterns import BMC_SIDECAR_PATH

        assert BMC_SIDECAR_PATH.exists()

    def test_bmc_sidecar_validates(self) -> None:
        from framegraph.patterns import BMC_SIDECAR_PATH, load_sidecar

        sidecar = load_sidecar(BMC_SIDECAR_PATH)
        assert sidecar.pattern_id == 44
        assert sidecar.example_fill is not None
        # All 9 BMC zones referenced in example_fill.
        assert len(sidecar.example_fill) == 9

    def test_bmc_example_fill_round_trips(self) -> None:
        """The example_fill in the BMC sidecar must validate against
        the pattern's effective fill schema (default + sidecar overrides)."""
        from framegraph._patterns import load_pattern_catalog
        from framegraph.patterns import (
            BMC_SIDECAR_PATH,
            derive_fill_schema_with_sidecar,
            load_sidecar,
        )

        cat = load_pattern_catalog()
        bmc = cat.get(44)
        sidecar = load_sidecar(BMC_SIDECAR_PATH)
        Model = derive_fill_schema_with_sidecar(bmc, sidecar)
        # Round-trip: example_fill validates against the model.
        Model.model_validate(sidecar.example_fill)

    def test_bmc_required_role_missing_rejected(self) -> None:
        """Removing any required BMC zone from the example fill raises."""
        from framegraph._patterns import load_pattern_catalog
        from framegraph.patterns import (
            BMC_SIDECAR_PATH,
            derive_fill_schema_with_sidecar,
            load_sidecar,
        )

        cat = load_pattern_catalog()
        bmc = cat.get(44)
        sidecar = load_sidecar(BMC_SIDECAR_PATH)
        Model = derive_fill_schema_with_sidecar(bmc, sidecar)

        broken = dict(sidecar.example_fill or {})
        del broken["value_propositions"]
        with pytest.raises(ValidationError, match="value_propositions"):
            Model.model_validate(broken)

    def test_bmc_unknown_role_rejected(self) -> None:
        from framegraph._patterns import load_pattern_catalog
        from framegraph.patterns import (
            BMC_SIDECAR_PATH,
            derive_fill_schema_with_sidecar,
            load_sidecar,
        )

        cat = load_pattern_catalog()
        bmc = cat.get(44)
        sidecar = load_sidecar(BMC_SIDECAR_PATH)
        Model = derive_fill_schema_with_sidecar(bmc, sidecar)

        bad = dict(sidecar.example_fill or {})
        bad["rogue"] = "shouldnt be here"
        with pytest.raises(ValidationError):
            Model.model_validate(bad)
