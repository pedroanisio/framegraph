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
