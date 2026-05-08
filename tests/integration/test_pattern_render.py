"""Integration tests for `framegraph.patterns.render` — Phase 4 of the fill-and-render roadmap.

Phase 4 acceptance criteria (per `docs/ROADMAP-FILL-RENDER.md`):

  - `compose_document(pattern, fill, layout)` produces a `Document`
    that passes `Document.model_validate` and has 9 visual objects
    (for BMC).
  - `FrameGraphRenderer(doc).render_svg()` returns valid SVG (parses
    with an XML parser, has nonzero size, contains expected text
    from the fill).
  - Re-running the pipeline on the same fill produces a byte-
    identical SVG (determinism).
  - At least one negative test: a fill with the wrong content_type
    for a zone raises before rendering.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from framegraph._patterns import load_pattern_catalog
from framegraph._schema import Document
from framegraph.patterns import (
    BMC_SIDECAR_PATH,
    compose_document,
    compute_boxes,
    derive_fill_schema_with_sidecar,
    load_sidecar,
    render_pattern_svg,
)


CANVAS_W = 1920.0
CANVAS_H = 1080.0


# ─────────────────────────────────────────────────────────────────
# Helpers — build the BMC validated payload once per session
# ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def bmc_pattern():
    return load_pattern_catalog().get(44)


@pytest.fixture(scope="module")
def bmc_sidecar():
    return load_sidecar(BMC_SIDECAR_PATH)


@pytest.fixture(scope="module")
def bmc_filled(bmc_pattern, bmc_sidecar):
    """Validate the sidecar's example_fill against the effective schema."""
    Model = derive_fill_schema_with_sidecar(bmc_pattern, bmc_sidecar)
    return Model.model_validate(bmc_sidecar.example_fill)


@pytest.fixture(scope="module")
def bmc_layout(bmc_pattern):
    return compute_boxes(bmc_pattern, CANVAS_W, CANVAS_H)


# ─────────────────────────────────────────────────────────────────
# Compose Document
# ─────────────────────────────────────────────────────────────────


class TestComposeDocument:
    def test_compose_returns_validated_document(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        # Round-trip through the official Pydantic schema.
        validated = Document.model_validate(doc)
        assert validated.dsl == "FrameGraph"
        assert validated.scene.canvas.size == [CANVAS_W, CANVAS_H]

    def test_compose_emits_one_object_per_zone(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        # Walk the layers; sum visual objects.
        total = sum(len(layer["objects"]) for layer in doc["visual"]["layers"])
        # BMC has 9 zones — at least 9 visual objects (some content
        # types may emit multiple, but the floor is one per zone).
        assert total >= 9

    def test_compose_assigns_box_to_each_object(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        for obj in objects:
            assert "box" in obj, obj
            box = obj["box"]
            assert len(box) == 4
            x, y, w, h = box
            assert w > 0 and h > 0


# ─────────────────────────────────────────────────────────────────
# End-to-end SVG render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    def test_render_pattern_svg_returns_valid_svg(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        svg = render_pattern_svg(
            bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H
        )
        assert isinstance(svg, str)
        assert len(svg) > 0
        # Parse as XML — must be well-formed.
        root = ET.fromstring(svg)
        # Root element must be SVG.
        assert root.tag.endswith("svg"), root.tag

    def test_rendered_svg_contains_fill_text(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        """The rendered SVG must contain text from the supplied fill."""
        svg = render_pattern_svg(
            bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H
        )
        # BMC example_fill has "Subscription tiers" as a revenue stream label.
        assert "Subscription" in svg or "Engineering" in svg

    def test_render_is_deterministic(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        a = render_pattern_svg(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        b = render_pattern_svg(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        assert a == b


# ─────────────────────────────────────────────────────────────────
# Golden snapshot — BMC SVG
# ─────────────────────────────────────────────────────────────────


GOLDEN_DIR = Path(__file__).resolve().parent.parent / "goldens"
BMC_GOLDEN = GOLDEN_DIR / "bmc-example.svg"


class TestGoldenSnapshot:
    """The BMC golden snapshot pins the visual contract.

    First run captures the snapshot; subsequent runs verify the
    pipeline produces byte-identical output. To re-capture (e.g.
    after a deliberate visual change), delete the file and run
    the test once.
    """

    def test_bmc_golden_snapshot_matches(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        svg = render_pattern_svg(
            bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H
        )
        if not BMC_GOLDEN.exists():
            BMC_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            BMC_GOLDEN.write_text(svg, encoding="utf-8")
            pytest.skip(
                f"captured golden at {BMC_GOLDEN}; rerun the test to verify."
            )
        expected = BMC_GOLDEN.read_text(encoding="utf-8")
        assert svg == expected, "BMC golden mismatch — visual output drifted"


# ─────────────────────────────────────────────────────────────────
# Negative tests — bad fill is rejected before rendering
# ─────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
# Round 2 Phase 3 — list[object] sidecar overrides emit table objects
# ─────────────────────────────────────────────────────────────────


class TestListObjectTableEmission:
    """When a sidecar declares `item_kind: object` for a list_items
    zone, the renderer bridge must emit a `table` object (not the
    flattened `bullet_list` with stringified items).
    """

    def test_bmc_revenue_streams_emits_table(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        revenue_obj = next(
            (o for o in objects if o.get("id") == "zone_revenue_streams"), None
        )
        assert revenue_obj is not None
        assert revenue_obj["type"] == "table", (
            f"revenue_streams should emit a table; got {revenue_obj['type']!r}"
        )

    def test_bmc_cost_structure_emits_table(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        cost_obj = next(
            (o for o in objects if o.get("id") == "zone_cost_structure"), None
        )
        assert cost_obj is not None
        assert cost_obj["type"] == "table"

    def test_bmc_table_headers_from_sidecar_fields(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        """Table header row matches the sidecar's `item_fields` keys."""
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        revenue_obj = next(
            (o for o in objects if o.get("id") == "zone_revenue_streams"), None
        )
        # Sidecar declared `label` + `metric` on revenue_streams.
        assert revenue_obj["header"] == ["label", "metric"]

    def test_bmc_table_rows_carry_field_values(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        """Each list item becomes one row of cell values."""
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        revenue_obj = next(
            (o for o in objects if o.get("id") == "zone_revenue_streams"), None
        )
        rows = revenue_obj["rows"]
        # Sidecar example_fill has 3 revenue streams; each row has [label, metric].
        assert len(rows) == 3
        for row in rows:
            assert len(row) == 2
        # First row's label should match the example fill.
        assert "Subscription tiers" in rows[0][0]

    def test_bmc_other_zones_still_bullet_list(
        self, bmc_pattern, bmc_filled, bmc_layout
    ) -> None:
        """Non-object list_items zones (the 7 simple BMC blocks) still
        render as bullet_list — the override is per-zone."""
        doc = compose_document(bmc_pattern, bmc_filled, bmc_layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        key_partners_obj = next(
            (o for o in objects if o.get("id") == "zone_key_partners"), None
        )
        assert key_partners_obj is not None
        assert key_partners_obj["type"] == "bullet_list"

    def test_string_list_still_bullet_list(self) -> None:
        """A pattern with no sidecar override on a list_items zone keeps
        bullet_list emission (default behavior unchanged)."""
        # Catalog #10 SWOT — list_items zones, no object overrides.
        from framegraph._patterns import load_pattern_catalog
        from framegraph.patterns import (
            compute_boxes as _compute_boxes,
            derive_default_fill_schema,
        )

        cat = load_pattern_catalog()
        swot = cat.get(10)
        Model = derive_default_fill_schema(swot)
        fill = Model.model_validate(
            {
                "strengths": ["S1", "S2"],
                "weaknesses": ["W1"],
                "opportunities": ["O1"],
                "threats": ["T1"],
            }
        )
        layout = _compute_boxes(swot, CANVAS_W, CANVAS_H)
        doc = compose_document(swot, fill, layout, CANVAS_W, CANVAS_H)
        objects = [
            o for layer in doc["visual"]["layers"] for o in layer["objects"]
        ]
        # Every SWOT zone is bullet_list.
        for o in objects:
            assert o["type"] == "bullet_list", (
                f"SWOT zone {o.get('id')!r} should be bullet_list; got {o['type']!r}"
            )

    def test_empty_list_still_bullet_list(self) -> None:
        """An empty list (no items to introspect) falls back to
        bullet_list — we don't speculate on shape with no data."""
        from framegraph._patterns import SlidePattern
        from framegraph.patterns import compute_boxes as _compute_boxes
        from framegraph.patterns import derive_default_fill_schema

        p = SlidePattern.model_validate(
            {
                "id": 99300,
                "name": "T",
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
        Model = derive_default_fill_schema(p)
        fill = Model.model_validate({"items": []})
        layout = _compute_boxes(p, CANVAS_W, CANVAS_H)
        doc = compose_document(p, fill, layout, CANVAS_W, CANVAS_H)
        obj = doc["visual"]["layers"][0]["objects"][0]
        assert obj["type"] == "bullet_list"


class TestNegative:
    def test_wrong_content_shape_rejected(
        self, bmc_pattern, bmc_sidecar, bmc_layout
    ) -> None:
        """A fill that doesn't match the pattern's effective schema is rejected."""
        from pydantic import ValidationError

        Model = derive_fill_schema_with_sidecar(bmc_pattern, bmc_sidecar)
        # revenue_streams expects list[{label, metric}]; supply
        # plain strings instead.
        bad_fill_dict = dict(bmc_sidecar.example_fill or {})
        bad_fill_dict["revenue_streams"] = ["just a string"]
        with pytest.raises(ValidationError):
            Model.model_validate(bad_fill_dict)

    def test_compose_with_missing_role_box_raises(
        self, bmc_pattern, bmc_filled
    ) -> None:
        """If the layout dict is missing a role's box, compose_document raises."""
        # Drop one role from the layout — should fail explicitly.
        broken_layout = compute_boxes(bmc_pattern, CANVAS_W, CANVAS_H)
        del broken_layout["value_propositions"]
        with pytest.raises(KeyError, match="value_propositions"):
            compose_document(
                bmc_pattern, bmc_filled, broken_layout, CANVAS_W, CANVAS_H
            )
