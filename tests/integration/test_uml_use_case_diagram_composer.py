"""Regression tests for `framegraph.uml.compose_use_case_diagram` — Phase B.2.

Mirrors `test_uml_class_diagram_composer.py` and
`test_uml_package_diagram_composer.py`. Schema validation +
composer output structure + end-to-end render.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLUseCaseDiagramModel,
    validate_use_case_diagram,
)
from framegraph.uml import (
    UseCaseDiagramOptions,
    compose_use_case_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────


class TestUseCaseDiagramSchema:
    """`validate_use_case_diagram` enforces UML 2.5.1 §18 rules."""

    def test_minimal_diagram_validates(self) -> None:
        m = validate_use_case_diagram({"actors": [{"id": "A", "name": "A"}]})
        assert len(m.actors) == 1

    def test_empty_diagram_rejected(self) -> None:
        """Empty diagram has nothing to render — caught at the model layer."""
        with pytest.raises(ValidationError, match="at least one"):
            validate_use_case_diagram({})

    def test_only_use_cases_is_valid(self) -> None:
        """A diagram with only use cases (no actors) is legal."""
        m = validate_use_case_diagram({"use_cases": [{"id": "u", "name": "u"}]})
        assert len(m.use_cases) == 1

    def test_relation_self_loop_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot relate to itself"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "A", "name": "A"}],
                    "relations": [{"id": "r", "from": "A", "to": "A"}],
                }
            )

    def test_unknown_relation_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "A", "name": "A"}],
                    "use_cases": [{"id": "U", "name": "U"}],
                    "relations": [{"id": "r", "from": "A", "to": "missing"}],
                }
            )

    def test_include_with_actor_endpoint_rejected(self) -> None:
        """UML 2.5.1 §18.1.4 — include is use-case to use-case only."""
        with pytest.raises(ValidationError, match="include/extend to use-case pairs"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "A", "name": "A"}],
                    "use_cases": [{"id": "U", "name": "U"}],
                    "relations": [{"id": "r", "from": "A", "to": "U", "kind": "include"}],
                }
            )

    def test_extend_with_actor_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="include/extend to use-case pairs"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "A", "name": "A"}],
                    "use_cases": [{"id": "U", "name": "U"}],
                    "relations": [{"id": "r", "from": "U", "to": "A", "kind": "extend"}],
                }
            )

    def test_boundary_unknown_use_case_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown use-case id"):
            validate_use_case_diagram(
                {
                    "use_cases": [{"id": "U", "name": "U"}],
                    "system_boundaries": [{"id": "S", "name": "S", "contains": ["missing"]}],
                }
            )

    def test_duplicate_id_across_categories_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "X", "name": "X"}],
                    "use_cases": [{"id": "X", "name": "X"}],
                }
            )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_node_model() -> UMLUseCaseDiagramModel:
    return validate_use_case_diagram(
        {
            "actors": [{"id": "A", "name": "Customer"}],
            "use_cases": [{"id": "U", "name": "Browse"}],
            "relations": [{"id": "r", "from": "A", "to": "U"}],
        }
    )


def _full_vocabulary() -> UMLUseCaseDiagramModel:
    return validate_use_case_diagram(
        {
            "actors": [
                {"id": "Customer", "name": "Customer"},
                {"id": "Admin", "name": "Admin"},
            ],
            "use_cases": [
                {"id": "Browse", "name": "Browse Catalog"},
                {"id": "Order", "name": "Place Order"},
                {"id": "Pay", "name": "Pay"},
                {"id": "Refund", "name": "Refund"},
                {"id": "Auth", "name": "Authenticate"},
            ],
            "system_boundaries": [
                {
                    "id": "Shop",
                    "name": "Online Shop",
                    "contains": ["Browse", "Order", "Pay", "Refund"],
                }
            ],
            "relations": [
                {"id": "r1", "from": "Customer", "to": "Browse"},
                {"id": "r2", "from": "Customer", "to": "Order"},
                {"id": "r3", "from": "Order", "to": "Pay", "kind": "include"},
                {"id": "r4", "from": "Order", "to": "Auth", "kind": "include"},
                {"id": "r5", "from": "Refund", "to": "Pay", "kind": "extend"},
                {"id": "r6", "from": "Admin", "to": "Refund"},
            ],
        }
    )


def _render(model: UMLUseCaseDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_use_case_diagram(model, canvas_size=(1280, 720))
    doc = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [1280, 720]}},
        "visual": composed.visual,
    }
    r = FrameGraphRenderer(doc)
    return r.render_svg(), r


# ─────────────────────────────────────────────────────────────────
# Composer structure
# ─────────────────────────────────────────────────────────────────


class TestComposerStructure:
    """Layer/object structure of the composed visual block."""

    def test_three_default_layers(self) -> None:
        composed = compose_use_case_diagram(_two_node_model())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert layer_ids[:3] == ["uml.boundaries", "uml.edges", "uml.classifiers"]

    def test_actor_uses_uml_actor_type(self) -> None:
        composed = compose_use_case_diagram(_two_node_model())
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        actor_obj = next(o for o in classifiers if o["id"] == "A")
        assert actor_obj["type"] == "uml.actor"

    def test_use_case_uses_ellipse_plus_label(self) -> None:
        """A use-case emits an ellipse and a separate label text element."""
        composed = compose_use_case_diagram(_two_node_model())
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        ellipse = next(o for o in classifiers if o["id"] == "U")
        label = next(o for o in classifiers if o["id"] == "U__label")
        assert ellipse["type"] == "ellipse"
        assert label["type"] == "text"

    def test_relation_count_matches_edge_count(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        # 6 relations declared in the model
        assert len(edges) == 6

    def test_boundary_emits_frame_and_label(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        boundaries = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.boundaries"
        )["objects"]
        # 1 boundary → 2 objects (frame rect + name text)
        assert any(o["id"] == "Shop__frame" for o in boundaries)
        assert any(o["id"] == "Shop__name" for o in boundaries)


# ─────────────────────────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────────────────────────


class TestLayout:
    """Sugiyama produces the actor-left → use-case-right column layout."""

    def test_actors_to_left_of_use_cases(self) -> None:
        """Actor x < use-case x (associations push use cases to the right)."""
        composed = compose_use_case_diagram(_full_vocabulary())
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        boxes = {o["id"]: o["box"] for o in classifiers}
        # Customer should be left of all the use cases it associates with
        assert boxes["Customer"][0] < boxes["Browse"][0]
        assert boxes["Customer"][0] < boxes["Order"][0]
        assert boxes["Admin"][0] < boxes["Refund"][0]

    def test_include_targets_to_right_of_source(self) -> None:
        """For include relations, the target ends up right of the source."""
        composed = compose_use_case_diagram(_full_vocabulary())
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        boxes = {o["id"]: o["box"] for o in classifiers}
        # Order includes Pay and Auth — both should sit to the right
        assert boxes["Order"][0] < boxes["Pay"][0]
        assert boxes["Order"][0] < boxes["Auth"][0]

    def test_layout_result_zero_crossings(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        assert composed.layout_result is not None
        # On this DAG, Sugiyama should reach 0 crossings
        assert composed.layout_result.crossings == 0


# ─────────────────────────────────────────────────────────────────
# Edge styling
# ─────────────────────────────────────────────────────────────────


class TestEdgeStyling:
    """Each relation kind maps to the right stroke convention."""

    def test_association_is_plain_solid(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assoc = next(e for e in edges if e["id"] == "r1")
        assert "dash" not in assoc["stroke"]
        assert "arrow_end_kind" not in assoc["stroke"]

    def test_include_dashed_with_open_arrow(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        inc = next(e for e in edges if e["id"] == "r3")
        assert inc["stroke"]["arrow_end_kind"] == "open_arrow"
        assert inc["stroke"]["dash"] == [5, 4]

    def test_extend_dashed_with_open_arrow(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        ext = next(e for e in edges if e["id"] == "r5")
        assert ext["stroke"]["arrow_end_kind"] == "open_arrow"
        assert ext["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    """`position` hints override Sugiyama coordinates."""

    def test_pinned_actor(self) -> None:
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A", "position": {"x": 50, "y": 80}}],
                "use_cases": [{"id": "U", "name": "U"}],
                "relations": [{"id": "r", "from": "A", "to": "U"}],
            }
        )
        composed = compose_use_case_diagram(model)
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        actor = next(o for o in classifiers if o["id"] == "A")
        assert actor["box"][0] == 50
        assert actor["box"][1] == 80


# ─────────────────────────────────────────────────────────────────
# Manual layout
# ─────────────────────────────────────────────────────────────────


class TestManualLayout:
    """`layout='manual'` requires every element to have a position."""

    def test_manual_layout_with_positions(self) -> None:
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A", "position": {"x": 0, "y": 0}}],
                "use_cases": [{"id": "U", "name": "U", "position": {"x": 200, "y": 0}}],
            }
        )
        composed = compose_use_case_diagram(model, options=UseCaseDiagramOptions(layout="manual"))
        classifiers = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        boxes = {o["id"]: o["box"] for o in classifiers}
        assert boxes["A"][0] == 0
        assert boxes["U"][0] == 200

    def test_manual_layout_missing_position_raises(self) -> None:
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A", "position": {"x": 0, "y": 0}}],
                "use_cases": [{"id": "U", "name": "U"}],  # no position
            }
        )
        with pytest.raises(ValueError, match="layout='manual' requires"):
            compose_use_case_diagram(model, options=UseCaseDiagramOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    """Composed visual block reaches the renderer cleanly."""

    def test_minimal_renders_without_warnings(self) -> None:
        svg, r = _render(_two_node_model())
        assert r.warnings == []
        assert "<svg" in svg

    def test_full_vocabulary_renders_without_warnings(self) -> None:
        svg, r = _render(_full_vocabulary())
        assert r.warnings == [], f"unexpected warnings: {r.warnings}"

    def test_actor_names_present_in_svg(self) -> None:
        svg, _ = _render(_full_vocabulary())
        for name in ("Customer", "Admin"):
            assert f">{name}<" in svg

    def test_use_case_names_present_in_svg(self) -> None:
        svg, _ = _render(_full_vocabulary())
        for name in ("Browse Catalog", "Place Order", "Pay", "Refund", "Authenticate"):
            assert name in svg

    def test_system_boundary_label_present(self) -> None:
        svg, _ = _render(_full_vocabulary())
        assert "Online Shop" in svg

    def test_open_arrow_marker_emitted(self) -> None:
        """include/extend edges trigger registration of the open_arrow marker."""
        svg, _ = _render(_full_vocabulary())
        assert "open_arrow" in svg


# ─────────────────────────────────────────────────────────────────
# Diagnostics
# ─────────────────────────────────────────────────────────────────


class TestDiagnostics:
    """`ComposedDiagram` exposes useful side-channel data."""

    def test_node_dimensions_filled(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        # 2 actors + 5 use cases = 7 entries
        assert len(composed.node_dimensions) == 7

    def test_layout_result_present_for_sugiyama(self) -> None:
        composed = compose_use_case_diagram(_full_vocabulary())
        assert composed.layout_result is not None


# ─────────────────────────────────────────────────────────────────
# Notes + boundary edge cases
# ─────────────────────────────────────────────────────────────────


class TestNotesAndBoundaries:
    """Optional features — notes layer, empty boundaries, no-actor case."""

    def test_notes_layer_appears_when_notes_present(self) -> None:
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A"}],
                "notes": [
                    {
                        "id": "n",
                        "text": "important annotation",
                        "position": {"x": 100, "y": 200},
                    }
                ],
            }
        )
        composed = compose_use_case_diagram(model)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids

    def test_note_without_position_uses_default(self) -> None:
        """A note without position defaults to a canvas-bottom location."""
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A"}],
                "notes": [{"id": "n", "text": "no-pos"}],
            }
        )
        # Should not raise
        compose_use_case_diagram(model)

    def test_boundary_with_no_contents_is_skipped(self) -> None:
        """An empty boundary doesn't emit a frame."""
        model = validate_use_case_diagram(
            {
                "actors": [{"id": "A", "name": "A"}],
                "use_cases": [{"id": "U", "name": "U"}],
                "system_boundaries": [{"id": "S", "name": "S", "contains": []}],
            }
        )
        composed = compose_use_case_diagram(model)
        boundaries = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.boundaries"
        )["objects"]
        # Boundary with empty contents → no frame/label emitted
        assert not any(o["id"].startswith("S__") for o in boundaries)

    def test_only_use_cases_no_actors_renders(self) -> None:
        """A diagram with use cases but no actors is valid."""
        model = validate_use_case_diagram({"use_cases": [{"id": "U", "name": "U"}]})
        svg, r = _render(model)
        assert r.warnings == []
        assert ">U<" in svg
