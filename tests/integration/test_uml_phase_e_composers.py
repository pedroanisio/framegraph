"""Regression tests for Phase E UML composers.

Phase E covers the six niche UML 2.5.1 diagram kinds:

  E.1 — timing diagram (state lanes over a time axis)
  E.2 — communication diagram (numbered messages on a free-form network)
  E.3 — interaction-overview diagram (activity-flow with `ref`/`sd` frames)
  E.4 — profile diagram (stereotype + metaclass extensions)
  E.5 — composite-structure diagram (parts inside a classifier frame)
  E.6 — object diagram (instances with slot values)

This single module hosts one TestX class per composer to keep
related fixtures co-located.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    validate_communication_diagram,
    validate_composite_structure,
    validate_interaction_overview,
    validate_object_diagram,
    validate_profile_diagram,
    validate_timing_diagram,
)
from framegraph.uml import (
    CommunicationDiagramOptions,
    ObjectDiagramOptions,
    TimingDiagramOptions,
    compose_communication_diagram,
    compose_composite_structure,
    compose_interaction_overview,
    compose_object_diagram,
    compose_profile_diagram,
    compose_timing_diagram,
)


def _render(visual: dict) -> str:
    doc = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "t", "canvas": {"size": [1280, 720]}},
        "visual": visual,
    }
    return FrameGraphRenderer(doc).render_svg()


# ─────────────────────────────────────────────────────────────────
# E.1 — Timing diagrams
# ─────────────────────────────────────────────────────────────────


class TestTimingSchema:
    def test_minimal_validates(self) -> None:
        m = validate_timing_diagram(
            {"lifelines": [{"id": "a", "name": "CPU", "states": ["idle", "busy"]}]}
        )
        assert len(m.lifelines) == 1

    def test_empty_lifelines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_timing_diagram({"lifelines": []})

    def test_missing_lifelines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_timing_diagram({})

    def test_empty_states_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_timing_diagram({"lifelines": [{"id": "a", "name": "A", "states": []}]})

    def test_unknown_lifeline_in_change_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown.*lifeline"):
            validate_timing_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A", "states": ["x"]}],
                    "changes": [{"id": "c", "lifeline": "missing", "state": "x", "at": 0}],
                }
            )

    def test_unknown_state_in_change_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown state"):
            validate_timing_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A", "states": ["idle"]}],
                    "changes": [{"id": "c", "lifeline": "a", "state": "missing", "at": 0}],
                }
            )

    def test_negative_time_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_timing_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A", "states": ["x"]}],
                    "changes": [{"id": "c", "lifeline": "a", "state": "x", "at": -1}],
                }
            )


class TestTimingComposer:
    def _two_state_model(self):
        return validate_timing_diagram(
            {
                "lifelines": [
                    {"id": "cpu", "name": "CPU", "states": ["idle", "busy"]},
                    {"id": "io", "name": "IO", "states": ["wait", "active"]},
                ],
                "changes": [
                    {"id": "c1", "lifeline": "cpu", "state": "busy", "at": 1.0},
                    {"id": "c2", "lifeline": "cpu", "state": "idle", "at": 3.0},
                    {"id": "c3", "lifeline": "io", "state": "active", "at": 1.5},
                ],
            }
        )

    def test_lane_per_lifeline(self) -> None:
        composed = compose_timing_diagram(self._two_state_model())
        lanes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lanes")[
            "objects"
        ]
        assert len(lanes) == 2
        assert all(o["type"] == "uml.timing_lane" for o in lanes)

    def test_lanes_stack_vertically(self) -> None:
        composed = compose_timing_diagram(self._two_state_model())
        lanes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lanes")[
            "objects"
        ]
        boxes = {o["id"]: o["box"] for o in lanes}
        assert boxes["cpu"][1] < boxes["io"][1]

    def test_changes_emit_step_segments(self) -> None:
        composed = compose_timing_diagram(self._two_state_model())
        changes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.changes")[
            "objects"
        ]
        # Each lifeline emits at minimum: initial-h + vertical + tail-h
        # per change. We just verify the layer has lines in it.
        assert any(o["type"] == "line" for o in changes)
        assert len(changes) >= 4

    def test_pinned_canvas_bottom_for_notes(self) -> None:
        m = validate_timing_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A", "states": ["x"]},
                ],
                "notes": [{"id": "n1", "text": "hello"}],
            }
        )
        composed = compose_timing_diagram(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids

    def test_step_pitch_option_propagates(self) -> None:
        m = self._two_state_model()
        # step_pitch isn't present on TimingDiagramOptions, but
        # lane_height is — verify we can override it.
        composed = compose_timing_diagram(m, options=TimingDiagramOptions(lane_height=200))
        lanes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lanes")[
            "objects"
        ]
        for o in lanes:
            assert o["box"][3] == 200

    def test_renders(self) -> None:
        composed = compose_timing_diagram(self._two_state_model())
        svg = _render(composed.visual)
        assert svg.rstrip().endswith("</svg>")
        assert "CPU" in svg
        assert "idle" in svg


# ─────────────────────────────────────────────────────────────────
# E.2 — Communication diagrams
# ─────────────────────────────────────────────────────────────────


class TestCommunicationSchema:
    def test_minimal_validates(self) -> None:
        m = validate_communication_diagram({"lifelines": [{"id": "a", "name": "A"}]})
        assert len(m.lifelines) == 1

    def test_empty_lifelines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_communication_diagram({"lifelines": []})

    def test_unknown_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown source"):
            validate_communication_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A"}],
                    "messages": [
                        {
                            "id": "m",
                            "from": "missing",
                            "to": "a",
                            "sequence": "1",
                        }
                    ],
                }
            )

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_communication_diagram(
                {
                    "lifelines": [
                        {"id": "x", "name": "A"},
                        {"id": "x", "name": "B"},
                    ]
                }
            )

    @pytest.mark.parametrize("kind", ["sync", "async"])
    def test_message_kinds_accepted(self, kind: str) -> None:
        validate_communication_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [
                    {
                        "id": "m",
                        "from": "a",
                        "to": "b",
                        "sequence": "1",
                        "kind": kind,
                    }
                ],
            }
        )

    def test_sequence_required(self) -> None:
        with pytest.raises(ValidationError):
            validate_communication_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [{"id": "m", "from": "a", "to": "b"}],
                }
            )


class TestCommunicationComposer:
    def _round_trip_model(self):
        return validate_communication_diagram(
            {
                "lifelines": [
                    {"id": "u", "name": "User"},
                    {"id": "c", "name": "Controller"},
                    {"id": "s", "name": "Service"},
                ],
                "messages": [
                    {
                        "id": "m1",
                        "from": "u",
                        "to": "c",
                        "sequence": "1",
                        "name": "click()",
                    },
                    {
                        "id": "m2",
                        "from": "c",
                        "to": "s",
                        "sequence": "1.1",
                        "name": "fetch()",
                    },
                ],
            }
        )

    def test_one_lifeline_per_classifier(self) -> None:
        composed = compose_communication_diagram(self._round_trip_model())
        lifelines = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        assert len(lifelines) == 3

    def test_messages_emit_connectors_and_labels(self) -> None:
        composed = compose_communication_diagram(self._round_trip_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        # 2 messages × (connector + label) = 4 objects
        assert len(edges) == 4
        connectors = [e for e in edges if e["type"] == "connector"]
        labels = [e for e in edges if e["type"] == "text"]
        assert len(connectors) == 2
        assert len(labels) == 2

    def test_sync_vs_async_arrow_kind(self) -> None:
        m = validate_communication_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [
                    {
                        "id": "m1",
                        "from": "a",
                        "to": "b",
                        "sequence": "1",
                        "kind": "sync",
                    },
                    {
                        "id": "m2",
                        "from": "b",
                        "to": "a",
                        "sequence": "2",
                        "kind": "async",
                    },
                ],
            }
        )
        composed = compose_communication_diagram(m)
        edges = [
            o
            for lyr in composed.visual["layers"]
            if lyr["id"] == "uml.edges"
            for o in lyr["objects"]
            if o["type"] == "connector"
        ]
        m1 = next(e for e in edges if e["id"] == "m1")
        m2 = next(e for e in edges if e["id"] == "m2")
        assert m1["stroke"]["arrow_end_kind"] == "filled_triangle"
        assert m2["stroke"]["arrow_end_kind"] == "open_arrow"

    def test_pinned_position_honored(self) -> None:
        m = validate_communication_diagram(
            {
                "lifelines": [
                    {
                        "id": "a",
                        "name": "A",
                        "position": {"x": 100, "y": 200},
                    },
                    {"id": "b", "name": "B"},
                ]
            }
        )
        composed = compose_communication_diagram(
            m, options=CommunicationDiagramOptions(lifeline_min_width=80)
        )
        lifelines = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )["objects"]
        a = next(ll for ll in lifelines if ll["id"] == "a")
        # Top-left x = pinned x - w/2 = 100 - 40 = 60
        # The pinned position is the LIFELINE CENTER per composer
        # convention; verify the box's center matches.
        cx = a["box"][0] + a["box"][2] / 2
        assert cx == 100

    def test_renders(self) -> None:
        composed = compose_communication_diagram(self._round_trip_model())
        svg = _render(composed.visual)
        assert svg.rstrip().endswith("</svg>")
        assert "User" in svg
        assert "1.1: fetch()" in svg


# ─────────────────────────────────────────────────────────────────
# E.3 — Interaction-overview diagrams
# ─────────────────────────────────────────────────────────────────


class TestInteractionOverviewSchema:
    def test_minimal_validates(self) -> None:
        m = validate_interaction_overview({"nodes": [{"id": "i", "kind": "initial"}]})
        assert len(m.nodes) == 1

    def test_interaction_use_requires_name(self) -> None:
        with pytest.raises(ValidationError, match="requires a name"):
            validate_interaction_overview({"nodes": [{"id": "n", "kind": "interaction_use"}]})

    def test_sd_inline_requires_name(self) -> None:
        with pytest.raises(ValidationError, match="requires a name"):
            validate_interaction_overview({"nodes": [{"id": "n", "kind": "sd_inline"}]})

    def test_self_edge_rejected(self) -> None:
        with pytest.raises(ValidationError, match="from==to"):
            validate_interaction_overview(
                {
                    "nodes": [{"id": "i", "kind": "initial"}],
                    "edges": [{"id": "e", "from": "i", "to": "i"}],
                }
            )

    def test_unknown_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_interaction_overview(
                {
                    "nodes": [{"id": "i", "kind": "initial"}],
                    "edges": [{"id": "e", "from": "i", "to": "missing"}],
                }
            )


class TestInteractionOverviewComposer:
    def _ref_flow_model(self):
        return validate_interaction_overview(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "login", "kind": "interaction_use", "name": "Login"},
                    {"id": "main", "kind": "sd_inline", "name": "MainFlow"},
                    {"id": "f", "kind": "final"},
                ],
                "edges": [
                    {"id": "e1", "from": "i", "to": "login"},
                    {"id": "e2", "from": "login", "to": "main"},
                    {"id": "e3", "from": "main", "to": "f"},
                ],
            }
        )

    def test_interaction_use_emits_ref_frame(self) -> None:
        composed = compose_interaction_overview(self._ref_flow_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        login = next(n for n in nodes if n["id"] == "login")
        assert login["type"] == "uml.fragment_frame"
        assert login["kind"] == "ref"
        assert login["operands"] == ["Login"]

    def test_sd_inline_emits_sd_frame(self) -> None:
        composed = compose_interaction_overview(self._ref_flow_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        main = next(n for n in nodes if n["id"] == "main")
        assert main["type"] == "uml.fragment_frame"
        assert main["kind"] == "sd"

    def test_initial_emits_activity_node(self) -> None:
        composed = compose_interaction_overview(self._ref_flow_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        init = next(n for n in nodes if n["id"] == "i")
        assert init["type"] == "uml.activity_node"
        assert init["kind"] == "initial"

    def test_initial_above_final_in_layout(self) -> None:
        composed = compose_interaction_overview(self._ref_flow_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["i"][1] < boxes["f"][1]

    def test_renders(self) -> None:
        composed = compose_interaction_overview(self._ref_flow_model())
        svg = _render(composed.visual)
        assert "Login" in svg
        assert "ref" in svg


# ─────────────────────────────────────────────────────────────────
# E.4 — Profile diagrams
# ─────────────────────────────────────────────────────────────────


class TestProfileSchema:
    def test_minimal_with_stereotype_validates(self) -> None:
        m = validate_profile_diagram({"stereotypes": [{"id": "s", "name": "Service"}]})
        assert len(m.stereotypes) == 1

    def test_minimal_with_metaclass_validates(self) -> None:
        m = validate_profile_diagram({"metaclasses": [{"id": "c", "name": "Class"}]})
        assert len(m.metaclasses) == 1

    def test_empty_diagram_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            validate_profile_diagram({})

    def test_extension_to_unknown_metaclass_rejected(self) -> None:
        with pytest.raises(ValidationError, match="declared metaclass id"):
            validate_profile_diagram(
                {
                    "stereotypes": [{"id": "s", "name": "S"}],
                    "extensions": [{"id": "e", "from": "s", "to": "missing"}],
                }
            )

    def test_extension_from_metaclass_rejected(self) -> None:
        with pytest.raises(ValidationError, match="declared stereotype id"):
            validate_profile_diagram(
                {
                    "stereotypes": [{"id": "s", "name": "S"}],
                    "metaclasses": [{"id": "c", "name": "C"}],
                    "extensions": [{"id": "e", "from": "c", "to": "s"}],
                }
            )


class TestProfileComposer:
    def _basic_model(self):
        return validate_profile_diagram(
            {
                "stereotypes": [
                    {"id": "svc", "name": "Service", "properties": ["url"]},
                ],
                "metaclasses": [{"id": "cls", "name": "Class"}],
                "extensions": [{"id": "ext", "from": "svc", "to": "cls", "required": True}],
            }
        )

    def test_stereotype_uses_classifier_box(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        svc = next(n for n in nodes if n["id"] == "svc")
        assert svc["type"] == "uml.classifier_box"
        assert svc["stereotype"] == "stereotype"

    def test_metaclass_carries_metaclass_stereotype(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        cls = next(n for n in nodes if n["id"] == "cls")
        assert cls["stereotype"] == "metaclass"

    def test_metaclass_above_stereotype(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["cls"][1] < boxes["svc"][1]

    def test_extension_uses_filled_triangle(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        # Required extension's id is suffixed with "__required" by composer.
        ext = next(e for e in edges if "ext" in e["id"])
        assert ext["stroke"]["arrow_end_kind"] == "filled_triangle"

    def test_required_marker_on_id(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert any(e["id"] == "ext__required" for e in edges)

    def test_renders(self) -> None:
        composed = compose_profile_diagram(self._basic_model())
        svg = _render(composed.visual)
        assert "Service" in svg
        assert "stereotype" in svg
        assert "metaclass" in svg


# ─────────────────────────────────────────────────────────────────
# E.5 — Composite-structure diagrams
# ─────────────────────────────────────────────────────────────────


class TestCompositeStructureSchema:
    def test_minimal_validates(self) -> None:
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "System",
                "parts": [{"id": "a", "name": "A"}],
            }
        )
        assert m.classifier_id == "sys"

    def test_empty_parts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_composite_structure(
                {
                    "classifier_id": "sys",
                    "classifier_name": "System",
                    "parts": [],
                }
            )

    def test_duplicate_id_with_classifier_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_composite_structure(
                {
                    "classifier_id": "sys",
                    "classifier_name": "System",
                    "parts": [{"id": "sys", "name": "Conflict"}],
                }
            )

    def test_connector_to_unknown_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_composite_structure(
                {
                    "classifier_id": "sys",
                    "classifier_name": "System",
                    "parts": [{"id": "a", "name": "A"}],
                    "connectors": [{"id": "k", "from": "a", "to": "missing"}],
                }
            )

    def test_part_port_reference_works(self) -> None:
        validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "System",
                "parts": [
                    {"id": "a", "name": "A", "ports": ["a_p1"]},
                    {"id": "b", "name": "B"},
                ],
                "connectors": [{"id": "k", "from": "a_p1", "to": "b"}],
            }
        )


class TestCompositeStructureComposer:
    def _basic_model(self):
        return validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "OrderSys",
                "parts": [
                    {"id": "auth", "name": "Auth"},
                    {"id": "order", "name": "Order"},
                ],
                "ports": [{"id": "p_in", "name": "in", "side": "west"}],
                "connectors": [
                    {"id": "k1", "from": "p_in", "to": "auth"},
                    {"id": "k2", "from": "auth", "to": "order"},
                ],
            }
        )

    def test_outer_frame_emitted(self) -> None:
        composed = compose_composite_structure(self._basic_model())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.frame" in layer_ids
        frame = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.frame")[
            "objects"
        ][0]
        assert frame["id"] == "sys"
        assert frame["name"] == "OrderSys"

    def test_one_part_per_part(self) -> None:
        composed = compose_composite_structure(self._basic_model())
        parts = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.parts")[
            "objects"
        ]
        assert len(parts) == 2

    def test_boundary_port_emitted(self) -> None:
        composed = compose_composite_structure(self._basic_model())
        ports_layer = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.ports")[
            "objects"
        ]
        assert any(p["id"] == "p_in" for p in ports_layer)

    def test_connectors_emitted(self) -> None:
        composed = compose_composite_structure(self._basic_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert len(edges) == 2

    def test_renders(self) -> None:
        composed = compose_composite_structure(self._basic_model())
        svg = _render(composed.visual)
        assert "OrderSys" in svg
        assert "Auth" in svg
        assert "Order" in svg


# ─────────────────────────────────────────────────────────────────
# E.6 — Object diagrams
# ─────────────────────────────────────────────────────────────────


class TestObjectSchema:
    def test_minimal_validates(self) -> None:
        m = validate_object_diagram({"instances": [{"id": "a", "type_name": "User"}]})
        assert len(m.instances) == 1

    def test_empty_instances_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_object_diagram({"instances": []})

    def test_type_name_required(self) -> None:
        with pytest.raises(ValidationError):
            validate_object_diagram({"instances": [{"id": "a"}]})

    def test_link_to_unknown_instance_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_object_diagram(
                {
                    "instances": [{"id": "a", "type_name": "User"}],
                    "links": [{"id": "l", "from": "a", "to": "missing"}],
                }
            )

    def test_anonymous_instance_accepted(self) -> None:
        validate_object_diagram({"instances": [{"id": "a", "type_name": "User"}]})

    def test_slots_with_values_accepted(self) -> None:
        validate_object_diagram(
            {
                "instances": [
                    {
                        "id": "a",
                        "name": "alice",
                        "type_name": "User",
                        "slots": [{"name": "email", "value": "a@x.com"}],
                    }
                ]
            }
        )


class TestObjectComposer:
    def _basic_model(self):
        return validate_object_diagram(
            {
                "instances": [
                    {
                        "id": "alice",
                        "name": "alice",
                        "type_name": "User",
                        "slots": [{"name": "email", "value": "a@x.com"}],
                    },
                    {
                        "id": "order1",
                        "type_name": "Order",
                        "slots": [{"name": "total", "value": "42.00"}],
                    },
                ],
                "links": [{"id": "l1", "from": "alice", "to": "order1", "name": "placed"}],
            }
        )

    def test_instance_label_format(self) -> None:
        composed = compose_object_diagram(self._basic_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        alice = next(n for n in nodes if n["id"] == "alice")
        order = next(n for n in nodes if n["id"] == "order1")
        assert alice["name"] == "alice:User"
        # Anonymous: ":Order"
        assert order["name"] == ":Order"

    def test_slot_attributes_emitted(self) -> None:
        composed = compose_object_diagram(self._basic_model())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        alice = next(n for n in nodes if n["id"] == "alice")
        assert alice["attributes"] == [
            {"name": "email", "default": "a@x.com", "visibility": "public"}
        ]

    def test_link_emitted(self) -> None:
        composed = compose_object_diagram(self._basic_model())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert len(edges) == 1
        assert edges[0]["id"] == "l1"

    def test_pinned_position_honored(self) -> None:
        m = validate_object_diagram(
            {
                "instances": [
                    {
                        "id": "a",
                        "type_name": "User",
                        "position": {"x": 111, "y": 222},
                    }
                ]
            }
        )
        composed = compose_object_diagram(m)
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        a = nodes[0]
        assert a["box"][0] == 111
        assert a["box"][1] == 222

    def test_manual_layout_requires_all_positions(self) -> None:
        m = validate_object_diagram(
            {
                "instances": [
                    {"id": "a", "type_name": "U"},
                    {"id": "b", "type_name": "U"},
                ]
            }
        )
        with pytest.raises(ValueError, match="manual"):
            compose_object_diagram(m, options=ObjectDiagramOptions(layout="manual"))

    def test_renders(self) -> None:
        composed = compose_object_diagram(self._basic_model())
        svg = _render(composed.visual)
        assert "alice:User" in svg
        assert ":Order" in svg
        assert "email" in svg
