"""Regression tests for `framegraph.uml.compose_activity_diagram` — Phase C.3."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLActivityDiagramModel,
    validate_activity_diagram,
)
from framegraph.uml import (
    ActivityDiagramOptions,
    compose_activity_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestActivitySchema:
    def test_minimal_validates(self) -> None:
        m = validate_activity_diagram({"nodes": [{"id": "n", "kind": "initial"}]})
        assert len(m.nodes) == 1

    def test_empty_nodes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_activity_diagram({"nodes": []})

    def test_missing_nodes_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_activity_diagram({})

    def test_action_requires_name(self) -> None:
        with pytest.raises(ValidationError, match="requires a name"):
            validate_activity_diagram({"nodes": [{"id": "a", "kind": "action"}]})

    def test_self_edge_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot flow to itself"):
            validate_activity_diagram(
                {
                    "nodes": [{"id": "a", "kind": "action", "name": "Act"}],
                    "edges": [{"id": "e", "from": "a", "to": "a"}],
                }
            )

    def test_initial_with_incoming_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot have incoming edges"):
            validate_activity_diagram(
                {
                    "nodes": [
                        {"id": "i", "kind": "initial"},
                        {"id": "a", "kind": "action", "name": "A"},
                    ],
                    "edges": [{"id": "e", "from": "a", "to": "i"}],
                }
            )

    def test_unknown_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_activity_diagram(
                {
                    "nodes": [{"id": "i", "kind": "initial"}],
                    "edges": [{"id": "e", "from": "i", "to": "missing"}],
                }
            )

    def test_unknown_partition_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown swimlane"):
            validate_activity_diagram(
                {
                    "nodes": [
                        {
                            "id": "a",
                            "kind": "action",
                            "name": "A",
                            "partition": "missing",
                        }
                    ]
                }
            )

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_activity_diagram(
                {
                    "nodes": [
                        {"id": "x", "kind": "initial"},
                        {"id": "x", "kind": "final"},
                    ]
                }
            )

    @pytest.mark.parametrize(
        "kind",
        ["initial", "final", "flow_final", "decision", "merge", "fork", "join"],
    )
    def test_node_kinds_without_name_accepted(self, kind: str) -> None:
        validate_activity_diagram({"nodes": [{"id": "n", "kind": kind}]})

    @pytest.mark.parametrize("kind", ["control", "object"])
    def test_edge_kinds_accepted(self, kind: str) -> None:
        validate_activity_diagram(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "a", "kind": "action", "name": "A"},
                ],
                "edges": [{"id": "e", "from": "i", "to": "a", "kind": kind}],
            }
        )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _linear_flow() -> UMLActivityDiagramModel:
    """initial → action → final."""
    return validate_activity_diagram(
        {
            "nodes": [
                {"id": "i", "kind": "initial"},
                {"id": "a", "kind": "action", "name": "Process"},
                {"id": "f", "kind": "final"},
            ],
            "edges": [
                {"id": "e1", "from": "i", "to": "a"},
                {"id": "e2", "from": "a", "to": "f"},
            ],
        }
    )


def _decision_flow() -> UMLActivityDiagramModel:
    """initial → decision → (yes-branch | no-branch) → final."""
    return validate_activity_diagram(
        {
            "nodes": [
                {"id": "i", "kind": "initial"},
                {"id": "d", "kind": "decision"},
                {"id": "yes", "kind": "action", "name": "Approve"},
                {"id": "no", "kind": "action", "name": "Reject"},
                {"id": "f", "kind": "final"},
            ],
            "edges": [
                {"id": "e1", "from": "i", "to": "d"},
                {"id": "e2", "from": "d", "to": "yes", "guard": "valid"},
                {"id": "e3", "from": "d", "to": "no", "guard": "invalid"},
                {"id": "e4", "from": "yes", "to": "f"},
                {"id": "e5", "from": "no", "to": "f"},
            ],
        }
    )


def _swimlane_flow() -> UMLActivityDiagramModel:
    """initial → action(lane=customer) → action(lane=service) → final."""
    return validate_activity_diagram(
        {
            "swimlanes": [
                {"id": "customer", "name": "Customer"},
                {"id": "service", "name": "Service"},
            ],
            "nodes": [
                {"id": "i", "kind": "initial", "partition": "customer"},
                {
                    "id": "place",
                    "kind": "action",
                    "name": "Place Order",
                    "partition": "customer",
                },
                {
                    "id": "fulfill",
                    "kind": "action",
                    "name": "Fulfill Order",
                    "partition": "service",
                },
                {"id": "f", "kind": "final", "partition": "service"},
            ],
            "edges": [
                {"id": "e1", "from": "i", "to": "place"},
                {"id": "e2", "from": "place", "to": "fulfill"},
                {"id": "e3", "from": "fulfill", "to": "f"},
            ],
        }
    )


def _render(model: UMLActivityDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_activity_diagram(model, canvas_size=(1280, 720))
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
    def test_core_layers_present(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.edges" in layer_ids
        assert "uml.classifiers" in layer_ids

    def test_one_node_object_per_node(self) -> None:
        composed = compose_activity_diagram(_decision_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        assert len(nodes) == 5

    def test_action_node_uses_action_type(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        a = next(n for n in nodes if n["id"] == "a")
        assert a["type"] == "uml.action"
        assert a["name"] == "Process"

    def test_decision_node_uses_activity_node_type(self) -> None:
        composed = compose_activity_diagram(_decision_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        d = next(n for n in nodes if n["id"] == "d")
        assert d["type"] == "uml.activity_node"
        assert d["kind"] == "decision"

    def test_initial_and_final_emit_activity_node(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        i = next(n for n in nodes if n["id"] == "i")
        f = next(n for n in nodes if n["id"] == "f")
        assert i["type"] == "uml.activity_node"
        assert i["kind"] == "initial"
        assert f["type"] == "uml.activity_node"
        assert f["kind"] == "final"


# ─────────────────────────────────────────────────────────────────
# Sugiyama topology
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaIntegration:
    def test_initial_above_action_above_final(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["i"][1] < boxes["a"][1] < boxes["f"][1]

    def test_decision_branches_share_layer(self) -> None:
        composed = compose_activity_diagram(_decision_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["yes"][1] == boxes["no"][1]


# ─────────────────────────────────────────────────────────────────
# Edge styling
# ─────────────────────────────────────────────────────────────────


class TestEdgeStyling:
    def test_control_flow_solid_with_arrow(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        e = edges[0]
        assert e["stroke"]["arrow_end_kind"] == "open_arrow"
        assert "dash" not in e["stroke"]

    def test_object_flow_dashed(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "a", "kind": "action", "name": "A"},
                ],
                "edges": [
                    {"id": "e", "from": "i", "to": "a", "kind": "object"},
                ],
            }
        )
        composed = compose_activity_diagram(m)
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert edges[0]["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Swim lanes
# ─────────────────────────────────────────────────────────────────


class TestSwimlanes:
    def test_swimlane_layer_emitted(self) -> None:
        composed = compose_activity_diagram(_swimlane_flow())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.swimlanes" in layer_ids

    def test_swimlane_layer_has_one_object_per_lane(self) -> None:
        composed = compose_activity_diagram(_swimlane_flow())
        lanes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.swimlanes")[
            "objects"
        ]
        assert len(lanes) == 2
        assert {ln["id"] for ln in lanes} == {"customer", "service"}

    def test_no_swimlane_layer_when_unused(self) -> None:
        composed = compose_activity_diagram(_linear_flow())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.swimlanes" not in layer_ids

    def test_nodes_constrained_to_their_lane(self) -> None:
        composed = compose_activity_diagram(_swimlane_flow())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        lanes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.swimlanes")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        lane_boxes = {ln["id"]: ln["box"] for ln in lanes}
        # Customer-lane nodes should sit horizontally inside the
        # customer lane's bounds (with some tolerance for centring).
        cust_x, _, cust_w, _ = lane_boxes["customer"]
        for nid in ("i", "place"):
            nx = boxes[nid][0]
            nw = boxes[nid][2]
            # Center of node within lane horizontal extent.
            center = nx + nw / 2
            assert cust_x - 5 <= center <= cust_x + cust_w + 5


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    def test_pinned_node_position_honored(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {
                        "id": "n",
                        "kind": "initial",
                        "position": {"x": 333, "y": 222},
                    },
                ]
            }
        )
        composed = compose_activity_diagram(m)
        node = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ][0]
        assert node["box"][0] == 333
        assert node["box"][1] == 222

    def test_manual_layout_requires_all_positions(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "a", "kind": "action", "name": "A"},
                ],
            }
        )
        with pytest.raises(ValueError, match="manual"):
            compose_activity_diagram(m, options=ActivityDiagramOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    def test_linear_renders(self) -> None:
        svg, _ = _render(_linear_flow())
        assert "</svg>" in svg
        assert "Process" in svg

    def test_decision_renders(self) -> None:
        svg, _ = _render(_decision_flow())
        assert "Approve" in svg
        assert "Reject" in svg

    def test_swimlane_renders(self) -> None:
        svg, _ = _render(_swimlane_flow())
        assert "Customer" in svg
        assert "Service" in svg
