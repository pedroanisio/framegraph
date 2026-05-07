"""Regression tests for `framegraph.uml.compose_deployment_diagram` — Phase C.2.

Mirrors the structure of the component-diagram tests. Schema-level,
composer structure, layout, relation styling, end-to-end render.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLDeploymentDiagramModel,
    validate_deployment_diagram,
)
from framegraph.uml import (
    DeploymentDiagramOptions,
    compose_deployment_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestDeploymentSchema:
    def test_minimal_validates(self) -> None:
        m = validate_deployment_diagram({"nodes": [{"id": "n", "name": "N"}]})
        assert len(m.nodes) == 1
        assert m.artifacts == []

    def test_empty_nodes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_deployment_diagram({"nodes": []})

    def test_missing_nodes_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_deployment_diagram({})

    def test_self_relation_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot relate to itself"):
            validate_deployment_diagram(
                {
                    "nodes": [{"id": "n", "name": "N"}],
                    "relations": [{"id": "r", "from": "n", "to": "n"}],
                }
            )

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_deployment_diagram(
                {
                    "nodes": [
                        {"id": "x", "name": "A"},
                        {"id": "x", "name": "B"},
                    ]
                }
            )

    def test_unknown_contains_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown node id"):
            validate_deployment_diagram(
                {
                    "nodes": [
                        {"id": "a", "name": "A", "contains": ["missing"]},
                    ]
                }
            )

    def test_unknown_artifact_in_node_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown artifact id"):
            validate_deployment_diagram(
                {
                    "nodes": [
                        {"id": "a", "name": "A", "artifacts": ["missing"]},
                    ],
                }
            )

    def test_relation_to_unknown_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_deployment_diagram(
                {
                    "nodes": [{"id": "a", "name": "A"}],
                    "relations": [{"id": "r", "from": "a", "to": "missing"}],
                }
            )

    def test_containment_cycle_rejected(self) -> None:
        with pytest.raises(ValidationError, match="containment cycle"):
            validate_deployment_diagram(
                {
                    "nodes": [
                        {"id": "a", "name": "A", "contains": ["b"]},
                        {"id": "b", "name": "B", "contains": ["a"]},
                    ]
                }
            )

    @pytest.mark.parametrize("kind", ["device", "execution_environment"])
    def test_node_kinds_accepted(self, kind: str) -> None:
        validate_deployment_diagram({"nodes": [{"id": "a", "name": "A", "kind": kind}]})

    @pytest.mark.parametrize("kind", ["deploy", "manifest", "communication"])
    def test_relation_kinds_accepted(self, kind: str) -> None:
        validate_deployment_diagram(
            {
                "nodes": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "relations": [{"id": "r", "from": "a", "to": "b", "kind": kind}],
            }
        )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_node_chain() -> UMLDeploymentDiagramModel:
    return validate_deployment_diagram(
        {
            "nodes": [
                {"id": "host", "name": "Host", "contains": ["jvm"]},
                {"id": "jvm", "name": "JVM", "kind": "execution_environment"},
            ]
        }
    )


def _full_vocabulary() -> UMLDeploymentDiagramModel:
    return validate_deployment_diagram(
        {
            "nodes": [
                {
                    "id": "appServer",
                    "name": "AppServer",
                    "contains": ["jvm"],
                    "kind": "device",
                },
                {
                    "id": "jvm",
                    "name": "JVM",
                    "kind": "execution_environment",
                    "artifacts": ["app.war"],
                },
                {
                    "id": "dbServer",
                    "name": "DBServer",
                    "kind": "device",
                    "artifacts": ["schema.sql"],
                },
            ],
            "artifacts": [
                {"id": "app.war", "name": "app.war"},
                {"id": "schema.sql", "name": "schema.sql"},
            ],
            "relations": [
                {
                    "id": "comm1",
                    "from": "appServer",
                    "to": "dbServer",
                    "kind": "communication",
                    "label": "JDBC",
                },
            ],
        }
    )


def _delegation_relations() -> UMLDeploymentDiagramModel:
    return validate_deployment_diagram(
        {
            "nodes": [{"id": "n", "name": "N"}],
            "artifacts": [{"id": "a", "name": "A.jar"}],
            "relations": [
                {"id": "d1", "from": "a", "to": "n", "kind": "deploy"},
            ],
        }
    )


def _render(model: UMLDeploymentDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_deployment_diagram(model, canvas_size=(1280, 720))
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
        composed = compose_deployment_diagram(_full_vocabulary())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.edges" in layer_ids
        assert "uml.classifiers" in layer_ids
        assert "uml.artifacts" in layer_ids

    def test_one_node_object_per_node(self) -> None:
        composed = compose_deployment_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        assert len(nodes) == 3

    def test_node_objects_use_node_box_type(self) -> None:
        composed = compose_deployment_diagram(_two_node_chain())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        for n in nodes:
            assert n["type"] == "uml.node_box"

    def test_artifact_objects_use_artifact_box_type(self) -> None:
        composed = compose_deployment_diagram(_full_vocabulary())
        artifacts = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.artifacts")[
            "objects"
        ]
        assert all(a["type"] == "uml.artifact_box" for a in artifacts)
        assert len(artifacts) == 2

    def test_no_artifact_layer_when_unused(self) -> None:
        composed = compose_deployment_diagram(_two_node_chain())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.artifacts" not in layer_ids

    def test_implicit_deploy_connectors_emitted(self) -> None:
        """Artifacts listed under node.artifacts get an auto deploy edge."""
        composed = compose_deployment_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        deploy_ids = [e["id"] for e in edges if e["id"].startswith("deploy__")]
        # 2 implicit deploys + 1 communication + 1 containment = 4
        assert len(deploy_ids) == 2


# ─────────────────────────────────────────────────────────────────
# Sugiyama containment
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaContainment:
    def test_parent_above_child(self) -> None:
        composed = compose_deployment_diagram(_two_node_chain())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["host"][1] < boxes["jvm"][1]

    def test_node_kind_propagates(self) -> None:
        composed = compose_deployment_diagram(_two_node_chain())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        jvm = next(n for n in nodes if n["id"] == "jvm")
        assert jvm["kind"] == "execution_environment"


# ─────────────────────────────────────────────────────────────────
# Relation styling
# ─────────────────────────────────────────────────────────────────


class TestRelationStyling:
    def test_deploy_dashed_with_open_arrow(self) -> None:
        composed = compose_deployment_diagram(_delegation_relations())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        d = next(e for e in edges if e["id"] == "d1")
        assert d["stroke"]["arrow_end_kind"] == "open_arrow"
        assert d["stroke"]["dash"] == [5, 4]

    def test_communication_plain_solid(self) -> None:
        composed = compose_deployment_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        c = next(e for e in edges if e["id"] == "comm1")
        assert "arrow_end_kind" not in c["stroke"]
        assert "dash" not in c["stroke"]


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    def test_pinned_node_position_honored(self) -> None:
        m = validate_deployment_diagram(
            {
                "nodes": [
                    {"id": "n", "name": "N", "position": {"x": 99, "y": 77}},
                ]
            }
        )
        composed = compose_deployment_diagram(m)
        node = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ][0]
        assert node["box"][0] == 99
        assert node["box"][1] == 77

    def test_pinned_artifact_position_honored(self) -> None:
        m = validate_deployment_diagram(
            {
                "nodes": [{"id": "n", "name": "N"}],
                "artifacts": [{"id": "a", "name": "a.jar", "position": {"x": 500, "y": 400}}],
            }
        )
        composed = compose_deployment_diagram(m)
        artifact = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.artifacts")[
            "objects"
        ][0]
        assert artifact["box"][0] == 500
        assert artifact["box"][1] == 400

    def test_manual_layout_requires_all_positions(self) -> None:
        m = validate_deployment_diagram(
            {"nodes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}
        )
        with pytest.raises(ValueError, match="manual"):
            compose_deployment_diagram(m, options=DeploymentDiagramOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────


class TestNotes:
    def test_notes_emit_separate_layer(self) -> None:
        m = validate_deployment_diagram(
            {
                "nodes": [{"id": "n", "name": "N"}],
                "notes": [{"id": "n1", "text": "Production"}],
            }
        )
        composed = compose_deployment_diagram(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    def test_two_node_renders(self) -> None:
        svg, _ = _render(_two_node_chain())
        assert "</svg>" in svg
        assert "Host" in svg
        assert "JVM" in svg

    def test_full_vocabulary_renders(self) -> None:
        svg, _ = _render(_full_vocabulary())
        assert "AppServer" in svg
        assert "DBServer" in svg
        assert "app.war" in svg
        assert "schema.sql" in svg
        # Stereotype keywords should appear via the renderer.
        assert "device" in svg
        assert "executionEnvironment" in svg
