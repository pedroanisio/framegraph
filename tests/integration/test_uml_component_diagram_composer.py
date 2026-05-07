"""Regression tests for `framegraph.uml.compose_component_diagram` — Phase C.1.

Mirrors the structure of the package-diagram tests. Three test
layers: schema-level (validate_component_diagram), composer output
structure, end-to-end render through `FrameGraphRenderer`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLComponentDiagramModel,
    validate_component_diagram,
)
from framegraph.uml import (
    ComponentDiagramOptions,
    compose_component_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestComponentDiagramSchema:
    """`validate_component_diagram` enforces the metamodel."""

    def test_minimal_diagram_validates(self) -> None:
        m = validate_component_diagram({"components": [{"id": "c", "name": "C"}]})
        assert len(m.components) == 1
        assert m.connectors == []

    def test_empty_components_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_component_diagram({"components": []})

    def test_missing_components_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_component_diagram({})

    def test_self_connector_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot connect to itself"):
            validate_component_diagram(
                {
                    "components": [{"id": "c", "name": "C"}],
                    "connectors": [{"id": "k", "from": "c", "to": "c"}],
                }
            )

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_component_diagram(
                {
                    "components": [
                        {"id": "c", "name": "C1"},
                        {"id": "c", "name": "C2"},
                    ]
                }
            )

    def test_connector_to_unknown_component_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_component_diagram(
                {
                    "components": [{"id": "a", "name": "A"}],
                    "connectors": [{"id": "k", "from": "a", "to": "missing"}],
                }
            )

    def test_connector_via_provided_interface_resolves(self) -> None:
        validate_component_diagram(
            {
                "components": [
                    {
                        "id": "a",
                        "name": "A",
                        "provided_interfaces": ["I1"],
                    },
                    {
                        "id": "b",
                        "name": "B",
                        "required_interfaces": ["I1"],
                    },
                ],
                "connectors": [
                    {"id": "k", "from": "b.I1", "to": "a.I1"},
                ],
            }
        )

    def test_port_id_collision_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_component_diagram(
                {
                    "components": [
                        {
                            "id": "a",
                            "name": "A",
                            "ports": [{"id": "a", "name": "p"}],
                        }
                    ]
                }
            )

    @pytest.mark.parametrize("kind", ["assembly", "delegation"])
    def test_valid_connector_kinds_accepted(self, kind: str) -> None:
        validate_component_diagram(
            {
                "components": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "connectors": [
                    {"id": "k", "from": "a", "to": "b", "kind": kind},
                ],
            }
        )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_component_assembly() -> UMLComponentDiagramModel:
    """Consumer (B, requires I) → provider (A, provides I)."""
    return validate_component_diagram(
        {
            "components": [
                {"id": "a", "name": "Auth", "provided_interfaces": ["IAuth"]},
                {"id": "b", "name": "Web", "required_interfaces": ["IAuth"]},
            ],
            "connectors": [
                {"id": "k1", "from": "b.IAuth", "to": "a.IAuth"},
            ],
        }
    )


def _full_vocabulary() -> UMLComponentDiagramModel:
    """Realistic 4-component model exercising provided/required + delegation."""
    return validate_component_diagram(
        {
            "components": [
                {
                    "id": "web",
                    "name": "Web",
                    "required_interfaces": ["IAuth", "IOrder"],
                },
                {
                    "id": "auth",
                    "name": "Auth",
                    "provided_interfaces": ["IAuth"],
                },
                {
                    "id": "order",
                    "name": "Order",
                    "provided_interfaces": ["IOrder"],
                    "required_interfaces": ["IDB"],
                },
                {
                    "id": "db",
                    "name": "Database",
                    "provided_interfaces": ["IDB"],
                },
            ],
            "connectors": [
                {"id": "k1", "from": "web.IAuth", "to": "auth.IAuth"},
                {"id": "k2", "from": "web.IOrder", "to": "order.IOrder"},
                {"id": "k3", "from": "order.IDB", "to": "db.IDB"},
            ],
        }
    )


def _delegation_model() -> UMLComponentDiagramModel:
    """Delegation connector via ports."""
    return validate_component_diagram(
        {
            "components": [
                {
                    "id": "outer",
                    "name": "Outer",
                    "ports": [{"id": "p_out", "name": "p_out"}],
                },
                {
                    "id": "inner",
                    "name": "Inner",
                    "ports": [{"id": "p_in", "name": "p_in"}],
                },
            ],
            "connectors": [
                {
                    "id": "k_del",
                    "from": "p_out",
                    "to": "p_in",
                    "kind": "delegation",
                },
            ],
        }
    )


def _render(model: UMLComponentDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_component_diagram(model, canvas_size=(1280, 720))
    doc = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [1280, 720]}},
        "visual": composed.visual,
    }
    r = FrameGraphRenderer(doc)
    return r.render_svg(), r


# ─────────────────────────────────────────────────────────────────
# Composer output structure
# ─────────────────────────────────────────────────────────────────


class TestComposerStructure:
    """The composer emits the expected layer/object structure."""

    def test_core_layers_emitted(self) -> None:
        composed = compose_component_diagram(_two_component_assembly())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.edges" in layer_ids
        assert "uml.classifiers" in layer_ids
        # Interfaces layer present whenever any component declares one
        assert "uml.interfaces" in layer_ids

    def test_one_node_object_per_component(self) -> None:
        composed = compose_component_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        assert len(nodes) == 4

    def test_node_objects_use_component_box_type(self) -> None:
        composed = compose_component_diagram(_two_component_assembly())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        for n in nodes:
            assert n["type"] == "uml.component_box"

    def test_edge_count_matches_connectors(self) -> None:
        composed = compose_component_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert len(edges) == 3

    def test_no_interfaces_layer_when_unused(self) -> None:
        m = validate_component_diagram(
            {
                "components": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "connectors": [{"id": "k", "from": "a", "to": "b"}],
            }
        )
        composed = compose_component_diagram(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.interfaces" not in layer_ids


# ─────────────────────────────────────────────────────────────────
# Sugiyama integration
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaIntegration:
    """Assembly connectors drive the y-axis hierarchy.

    Convention: the consumer (component holding the *required*
    interface) sits above the provider (component holding the
    *provided* interface).
    """

    def test_consumer_above_provider(self) -> None:
        composed = compose_component_diagram(_two_component_assembly())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        # Web requires IAuth (consumer) → Auth provides IAuth (provider)
        assert boxes["b"][1] < boxes["a"][1]

    def test_three_layer_chain(self) -> None:
        """web → order → db: web at top, db at bottom."""
        composed = compose_component_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        web_y = boxes["web"][1]
        order_y = boxes["order"][1]
        db_y = boxes["db"][1]
        assert web_y < order_y < db_y


# ─────────────────────────────────────────────────────────────────
# Connector styling
# ─────────────────────────────────────────────────────────────────


class TestConnectorStyling:
    """Assembly vs delegation get the right strokes/arrows."""

    def test_assembly_connector_has_no_arrow(self) -> None:
        composed = compose_component_diagram(_two_component_assembly())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        e = edges[0]
        assert "arrow_end_kind" not in e["stroke"]
        assert "dash" not in e["stroke"]

    def test_delegation_uses_open_arrow_dashed(self) -> None:
        composed = compose_component_diagram(_delegation_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        d = next(e for e in edges if e["id"] == "k_del")
        assert d["stroke"]["arrow_end_kind"] == "open_arrow"
        assert d["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Interface decorations
# ─────────────────────────────────────────────────────────────────


class TestInterfaceDecorations:
    """Provided interfaces emit lollipops; required interfaces emit sockets."""

    def test_one_lollipop_per_provided_interface(self) -> None:
        composed = compose_component_diagram(_full_vocabulary())
        ifaces = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.interfaces")[
            "objects"
        ]
        # auth provides IAuth, order provides IOrder, db provides IDB → 3 lollipops
        lollipops = [o for o in ifaces if o["type"] == "uml.lollipop"]
        assert len(lollipops) == 3

    def test_one_socket_per_required_interface(self) -> None:
        composed = compose_component_diagram(_full_vocabulary())
        ifaces = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.interfaces")[
            "objects"
        ]
        # web requires IAuth + IOrder, order requires IDB → 3 sockets
        sockets = [o for o in ifaces if o["type"] == "uml.socket"]
        assert len(sockets) == 3

    def test_interface_decorations_attach_outside_component(self) -> None:
        composed = compose_component_diagram(_two_component_assembly())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        ifaces = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.interfaces")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        # Auth provides IAuth → lollipop should sit at x ≥ auth's right edge
        a_right = boxes["a"][0] + boxes["a"][2]
        lp = next(o for o in ifaces if o["type"] == "uml.lollipop")
        assert lp["box"][0] >= a_right - 0.1


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    """Pinned `position` overrides Sugiyama placement."""

    def test_pinned_position_honored(self) -> None:
        m = validate_component_diagram(
            {
                "components": [
                    {
                        "id": "a",
                        "name": "A",
                        "position": {"x": 100, "y": 200},
                    },
                    {"id": "b", "name": "B"},
                ],
                "connectors": [{"id": "k", "from": "a", "to": "b"}],
            }
        )
        composed = compose_component_diagram(m)
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        a_box = next(n["box"] for n in nodes if n["id"] == "a")
        assert a_box[0] == 100
        assert a_box[1] == 200

    def test_manual_layout_requires_all_positions(self) -> None:
        m = validate_component_diagram(
            {
                "components": [
                    {"id": "a", "name": "A", "position": {"x": 0, "y": 0}},
                    {"id": "b", "name": "B"},
                ],
            }
        )
        with pytest.raises(ValueError, match="manual"):
            compose_component_diagram(m, options=ComponentDiagramOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────


class TestNotes:
    """Notes flow into a separate `uml.notes` layer."""

    def test_notes_emit_separate_layer(self) -> None:
        m = validate_component_diagram(
            {
                "components": [{"id": "a", "name": "A"}],
                "notes": [{"id": "n1", "text": "see ADR-007"}],
            }
        )
        composed = compose_component_diagram(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    """The composed visual renders to valid SVG via FrameGraphRenderer."""

    def test_two_component_renders(self) -> None:
        svg, _ = _render(_two_component_assembly())
        assert svg.startswith("<?xml") or svg.startswith("<svg")
        assert "</svg>" in svg

    def test_full_vocabulary_renders(self) -> None:
        svg, _ = _render(_full_vocabulary())
        # Component names should appear in the SVG output
        assert "Web" in svg
        assert "Auth" in svg
        assert "Order" in svg
        assert "Database" in svg
        # Provided/required interface names appear via lollipops/sockets
        assert "IAuth" in svg
        assert "IDB" in svg

    def test_delegation_renders(self) -> None:
        svg, _ = _render(_delegation_model())
        assert "Outer" in svg
        assert "Inner" in svg
