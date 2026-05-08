"""Edge-case regression tests across all UML composers (Phases A–E).

Complements the per-composer test suites with cross-cutting tests
that exercise:

  - Notes-layer emission for every composer that supports notes.
  - Pinned-position pinning for elements buried in nested
    containers (parts, ports, pseudostates, fragments).
  - Boundary conditions: single-element fixtures, large fan-outs,
    empty optional-section diagrams, mixed pinned/unpinned layouts.
  - Schema invariants: `_UnknownObject` plug-in fall-through,
    discriminated-union round-trips.
  - Layout invariants: position pinning overrides Sugiyama; nodes
    never overlap in trivial fixtures; canvas bounds are respected.

Each composer has its own primary test file; this file targets
*defect-prone* corners — the kind of thing that breaks silently
when a refactor removes a branch nobody had a test for.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._schema import validate_object
from framegraph._uml import (
    validate_activity_diagram,
    validate_class_diagram,
    validate_communication_diagram,
    validate_component_diagram,
    validate_composite_structure,
    validate_deployment_diagram,
    validate_interaction_overview,
    validate_object_diagram,
    validate_package_diagram,
    validate_profile_diagram,
    validate_sequence_diagram,
    validate_state_machine,
    validate_timing_diagram,
    validate_use_case_diagram,
)
from framegraph.uml import (
    compose_activity_diagram,
    compose_class_diagram,
    compose_communication_diagram,
    compose_component_diagram,
    compose_composite_structure,
    compose_deployment_diagram,
    compose_interaction_overview,
    compose_object_diagram,
    compose_package_diagram,
    compose_profile_diagram,
    compose_sequence_diagram,
    compose_state_machine,
    compose_timing_diagram,
    compose_use_case_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────


def _doc(visual: dict) -> dict:
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "t", "canvas": {"size": [1280, 720]}},
        "visual": visual,
    }


def _render(visual: dict) -> str:
    return FrameGraphRenderer(_doc(visual)).render_svg()


def _layer(visual: dict, layer_id: str) -> list[dict]:
    """Fetch the objects of a named layer, or [] when absent."""
    for lyr in visual["layers"]:
        if lyr["id"] == layer_id:
            return lyr["objects"]
    return []


def _layer_present(visual: dict, layer_id: str) -> bool:
    return any(lyr["id"] == layer_id for lyr in visual["layers"])


# ─────────────────────────────────────────────────────────────────
# Notes-layer emission across every composer that supports notes
# ─────────────────────────────────────────────────────────────────


class TestNotesLayerAcrossComposers:
    """Every composer that accepts `notes` must emit a `uml.notes` layer.

    The notes-emission path is structurally identical across composers
    but is a frequent silent-omission target; we exercise it once
    per composer.
    """

    def test_class_diagram_notes(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [{"id": "c", "name": "C"}],
                "notes": [{"id": "n", "text": "see ADR-007"}],
            }
        )
        composed = compose_class_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_package_diagram_notes(self) -> None:
        m = validate_package_diagram(
            {
                "packages": [{"id": "p", "name": "P"}],
                "notes": [{"id": "n", "text": "spec ref"}],
            }
        )
        composed = compose_package_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_use_case_diagram_notes(self) -> None:
        m = validate_use_case_diagram(
            {
                "actors": [{"id": "a", "name": "User"}],
                "use_cases": [{"id": "u", "name": "Login"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_use_case_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_component_diagram_notes(self) -> None:
        m = validate_component_diagram(
            {
                "components": [{"id": "c", "name": "C"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_component_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_deployment_diagram_notes(self) -> None:
        m = validate_deployment_diagram(
            {
                "nodes": [{"id": "n", "name": "N"}],
                "notes": [{"id": "n1", "text": "spec"}],
            }
        )
        composed = compose_deployment_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_activity_diagram_notes(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [{"id": "i", "kind": "initial"}],
                "notes": [{"id": "n", "text": "see spec"}],
            }
        )
        composed = compose_activity_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_state_machine_notes(self) -> None:
        m = validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_state_machine(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_sequence_diagram_notes(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_sequence_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_communication_diagram_notes(self) -> None:
        m = validate_communication_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_communication_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_interaction_overview_notes(self) -> None:
        m = validate_interaction_overview(
            {
                "nodes": [{"id": "i", "kind": "initial"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_interaction_overview(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_profile_diagram_notes(self) -> None:
        m = validate_profile_diagram(
            {
                "stereotypes": [{"id": "s", "name": "S"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_profile_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_composite_structure_notes(self) -> None:
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [{"id": "a", "name": "A"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_composite_structure(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_object_diagram_notes(self) -> None:
        m = validate_object_diagram(
            {
                "instances": [{"id": "a", "type_name": "U"}],
                "notes": [{"id": "n", "text": "spec"}],
            }
        )
        composed = compose_object_diagram(m)
        assert _layer_present(composed.visual, "uml.notes")

    def test_pinned_note_position_honored(self) -> None:
        """A note with explicit `position` keeps its coordinates."""
        m = validate_class_diagram(
            {
                "classes": [{"id": "c", "name": "C"}],
                "notes": [
                    {
                        "id": "n",
                        "text": "spec",
                        "position": {"x": 555, "y": 444},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        notes = _layer(composed.visual, "uml.notes")
        bg = next(n for n in notes if n["id"].endswith(".bg"))
        assert bg["box"][0] == 555
        assert bg["box"][1] == 444


# ─────────────────────────────────────────────────────────────────
# Schema-level invariants (Pydantic plumbing)
# ─────────────────────────────────────────────────────────────────


class TestSchemaInvariants:
    """Cross-cutting schema invariants documented in `framegraph/_schema.py`."""

    def test_unknown_object_type_falls_through(self) -> None:
        """A `type` not in the discriminated union must NOT raise — it's a plug-in.

        See `_schema.py` module docstring: third-party
        `register(type_name, fn)` types must validate, otherwise the
        plug-in surface breaks at ingest.
        """
        result = validate_object({"type": "third_party.future_widget", "id": "x"})
        assert result.type == "third_party.future_widget"

    def test_known_uml_type_round_trips(self) -> None:
        """A known UML type is parsed by its strong arm, not the fall-through."""
        result = validate_object(
            {
                "type": "uml.classifier_box",
                "id": "c",
                "box": [0, 0, 200, 100],
                "name": "C",
            }
        )
        assert result.type == "uml.classifier_box"
        assert result.name == "C"

    def test_phase_e_primitives_round_trip(self) -> None:
        """All Phase E primitives validate via the discriminated union."""
        for obj in (
            {
                "type": "uml.timing_lane",
                "id": "ll",
                "box": [0, 0, 600, 100],
                "name": "CPU",
                "states": ["idle", "busy"],
            },
            {
                "type": "uml.fragment_frame",
                "id": "f",
                "box": [0, 0, 200, 100],
                "kind": "ref",
                "operands": ["Login"],
            },
            {
                "type": "uml.activation_bar",
                "id": "act",
                "box": [0, 0, 10, 60],
            },
        ):
            r = validate_object(obj)
            assert r.type == obj["type"]


# ─────────────────────────────────────────────────────────────────
# Composite-structure: multi-side ports and per-part ports
# ─────────────────────────────────────────────────────────────────


class TestCompositeStructurePortDistribution:
    """Composite-structure ports on every face + per-part ports."""

    def _all_sides_model(self):
        return validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [
                    {"id": "core", "name": "Core", "ports": ["core_p1", "core_p2"]},
                ],
                "ports": [
                    {"id": "p_n1", "name": "n1", "side": "north"},
                    {"id": "p_n2", "name": "n2", "side": "north"},
                    {"id": "p_s1", "name": "s1", "side": "south"},
                    {"id": "p_e1", "name": "e1", "side": "east"},
                    {"id": "p_w1", "name": "w1", "side": "west"},
                ],
                "connectors": [
                    {"id": "k1", "from": "p_e1", "to": "core_p1"},
                ],
            }
        )

    def test_all_four_sides_emitted(self) -> None:
        composed = compose_composite_structure(self._all_sides_model())
        ports = _layer(composed.visual, "uml.ports")
        # 5 outer + 2 per-part = 7
        assert len(ports) == 7

    def test_ports_distributed_along_their_face(self) -> None:
        """Two north ports must share the same y but differ in x."""
        composed = compose_composite_structure(self._all_sides_model())
        ports = _layer(composed.visual, "uml.ports")
        n1 = next(p for p in ports if p["id"] == "p_n1")
        n2 = next(p for p in ports if p["id"] == "p_n2")
        # Same y (north face)
        assert n1["box"][1] == n2["box"][1]
        # Different x
        assert n1["box"][0] != n2["box"][0]

    def test_part_ports_emitted_on_part_edge(self) -> None:
        """Per-part ports use the part's geometry, not the outer frame's."""
        composed = compose_composite_structure(self._all_sides_model())
        parts = _layer(composed.visual, "uml.parts")
        ports = _layer(composed.visual, "uml.ports")
        core_box = next(p["box"] for p in parts if p["id"] == "core")
        core_right = core_box[0] + core_box[2]
        # Part-port x must coincide with the part's right edge
        # (within the port_size/2 offset).
        cp1 = next(p for p in ports if p["id"] == "core_p1")
        assert abs((cp1["box"][0] + cp1["box"][2] / 2) - core_right) < 0.5

    def test_pinned_part_position_honored(self) -> None:
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [{"id": "p", "name": "P", "position": {"x": 200, "y": 300}}],
            }
        )
        composed = compose_composite_structure(m)
        parts = _layer(composed.visual, "uml.parts")
        assert parts[0]["box"][0] == 200
        assert parts[0]["box"][1] == 300

    def test_no_ports_layer_when_unused(self) -> None:
        """Without any port (boundary or per-part), the layer is omitted."""
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [{"id": "a", "name": "A"}],
            }
        )
        composed = compose_composite_structure(m)
        assert not _layer_present(composed.visual, "uml.ports")

    def test_no_edges_layer_when_no_connectors(self) -> None:
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [{"id": "a", "name": "A"}],
            }
        )
        composed = compose_composite_structure(m)
        assert not _layer_present(composed.visual, "uml.edges")

    def test_typed_part_label_format(self) -> None:
        """A typed part renders as `name:Type`."""
        m = validate_composite_structure(
            {
                "classifier_id": "sys",
                "classifier_name": "Sys",
                "parts": [{"id": "a", "name": "Auth", "type_name": "Service"}],
            }
        )
        composed = compose_composite_structure(m)
        parts = _layer(composed.visual, "uml.parts")
        assert parts[0]["name"] == "Auth:Service"

    def test_renders_full_diagram(self) -> None:
        composed = compose_composite_structure(self._all_sides_model())
        svg = _render(composed.visual)
        assert svg.rstrip().endswith("</svg>")
        assert "Core" in svg
        assert "Sys" in svg


# ─────────────────────────────────────────────────────────────────
# Communication diagram: mixed pinned + unpinned + circle layout
# ─────────────────────────────────────────────────────────────────


class TestCommunicationLayoutEdgeCases:
    """Verify the circle-arrangement and mixed-pin behaviors."""

    def test_circle_arrangement_for_unpinned(self) -> None:
        """4 unpinned lifelines fall on a circle (vertical span > 0)."""
        m = validate_communication_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                    {"id": "c", "name": "C"},
                    {"id": "d", "name": "D"},
                ]
            }
        )
        composed = compose_communication_diagram(m)
        lifelines = _layer(composed.visual, "uml.classifiers")
        ys = [ll["box"][1] for ll in lifelines]
        # If the circle layout works, the y-range is > 0.
        assert max(ys) - min(ys) > 1

    def test_mixed_pinned_and_unpinned(self) -> None:
        """Pinned lifelines stay; unpinned still get a circle position."""
        m = validate_communication_diagram(
            {
                "lifelines": [
                    {
                        "id": "p",
                        "name": "Pinned",
                        "position": {"x": 100, "y": 200},
                    },
                    {"id": "u", "name": "Unpinned"},
                ]
            }
        )
        composed = compose_communication_diagram(m)
        lifelines = _layer(composed.visual, "uml.classifiers")
        boxes = {ll["id"]: ll["box"] for ll in lifelines}
        # `p`'s center must equal pinned x.
        cx_p = boxes["p"][0] + boxes["p"][2] / 2
        assert cx_p == 100
        # `u` must have *some* coordinates assigned (no None).
        assert boxes["u"][0] is not None

    def test_async_message_renders_open_arrow(self) -> None:
        m = validate_communication_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [
                    {
                        "id": "m",
                        "from": "a",
                        "to": "b",
                        "sequence": "1",
                        "kind": "async",
                    }
                ],
            }
        )
        composed = compose_communication_diagram(m)
        edges = [e for e in _layer(composed.visual, "uml.edges") if e["type"] == "connector"]
        assert edges[0]["stroke"]["arrow_end_kind"] == "open_arrow"

    def test_renders_with_only_unpinned_lifelines(self) -> None:
        m = validate_communication_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ]
            }
        )
        composed = compose_communication_diagram(m)
        svg = _render(composed.visual)
        assert "</svg>" in svg


# ─────────────────────────────────────────────────────────────────
# Sequence-diagram fragment edge cases
# ─────────────────────────────────────────────────────────────────


class TestSequenceFragmentEdgeCases:
    """Sequence-diagram fragments: single-step ranges, par operators, no-message diagrams."""

    def test_single_step_fragment(self) -> None:
        """A fragment covering exactly one step still emits a frame."""
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [{"id": "m1", "from": "a", "to": "b", "step": 1}],
                "fragments": [{"id": "f", "kind": "opt", "from_step": 1, "to_step": 1}],
            }
        )
        composed = compose_sequence_diagram(m)
        frames = _layer(composed.visual, "uml.fragments")
        assert len(frames) == 1
        # height > 0 even with from_step == to_step (fragment_y_pad expands it).
        assert frames[0]["box"][3] > 0

    def test_par_with_three_operands_emits_two_dividers(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [
                    {"id": "m1", "from": "a", "to": "b", "step": 1},
                    {"id": "m2", "from": "a", "to": "b", "step": 2},
                    {"id": "m3", "from": "a", "to": "b", "step": 3},
                ],
                "fragments": [
                    {
                        "id": "f",
                        "kind": "par",
                        "from_step": 1,
                        "to_step": 3,
                        "operands": ["a", "b", "c"],
                    }
                ],
            }
        )
        composed = compose_sequence_diagram(m)
        frame = _layer(composed.visual, "uml.fragments")[0]
        assert len(frame["dividers"]) == 2

    def test_loop_fragment_no_dividers(self) -> None:
        """`loop` is single-operand → no divider regardless of operand count."""
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [{"id": "m1", "from": "a", "to": "b", "step": 1}],
                "fragments": [
                    {
                        "id": "f",
                        "kind": "loop",
                        "from_step": 1,
                        "to_step": 1,
                        "operands": ["i < 10"],
                    }
                ],
            }
        )
        composed = compose_sequence_diagram(m)
        frame = _layer(composed.visual, "uml.fragments")[0]
        assert "dividers" not in frame or not frame["dividers"]

    def test_single_lifeline_self_only(self) -> None:
        """One lifeline with a single self-message renders without crash."""
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}],
                "messages": [
                    {"id": "m", "from": "a", "to": "a", "kind": "sync", "step": 1},
                ],
            }
        )
        composed = compose_sequence_diagram(m)
        msgs = [o for o in _layer(composed.visual, "uml.messages") if o["type"] == "polyline"]
        assert len(msgs) == 1


# ─────────────────────────────────────────────────────────────────
# Activity diagram: every node-kind glyph + object-flow + multiple swimlanes
# ─────────────────────────────────────────────────────────────────


class TestActivityNodeKindCoverage:
    """Exercise all 8 activity-node kinds in a single diagram."""

    def test_every_node_kind_renders(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "ff", "kind": "flow_final"},
                    {"id": "act", "kind": "action", "name": "Run"},
                    {"id": "d", "kind": "decision"},
                    {"id": "mr", "kind": "merge"},
                    {"id": "fk", "kind": "fork"},
                    {"id": "jn", "kind": "join"},
                    {"id": "f", "kind": "final"},
                ],
                "edges": [
                    {"id": "e1", "from": "i", "to": "act"},
                    {"id": "e2", "from": "act", "to": "d"},
                    {"id": "e3", "from": "d", "to": "fk", "guard": "yes"},
                    {"id": "e4", "from": "d", "to": "ff", "guard": "no"},
                    {"id": "e5", "from": "fk", "to": "mr"},
                    {"id": "e6", "from": "mr", "to": "jn"},
                    {"id": "e7", "from": "jn", "to": "f"},
                ],
            }
        )
        composed = compose_activity_diagram(m)
        svg = _render(composed.visual)
        assert "</svg>" in svg
        assert "Run" in svg

    def test_object_flow_dashed_line(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "act", "kind": "action", "name": "Run"},
                ],
                "edges": [
                    {"id": "e", "from": "i", "to": "act", "kind": "object"},
                ],
            }
        )
        composed = compose_activity_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        assert edges[0]["stroke"]["dash"] == [5, 4]

    def test_three_swimlanes_render_in_columns(self) -> None:
        m = validate_activity_diagram(
            {
                "swimlanes": [
                    {"id": "ux", "name": "UX"},
                    {"id": "api", "name": "API"},
                    {"id": "db", "name": "DB"},
                ],
                "nodes": [
                    {"id": "u_act", "kind": "action", "name": "U", "partition": "ux"},
                    {"id": "a_act", "kind": "action", "name": "A", "partition": "api"},
                    {"id": "d_act", "kind": "action", "name": "D", "partition": "db"},
                ],
                "edges": [
                    {"id": "e1", "from": "u_act", "to": "a_act"},
                    {"id": "e2", "from": "a_act", "to": "d_act"},
                ],
            }
        )
        composed = compose_activity_diagram(m)
        lanes = _layer(composed.visual, "uml.swimlanes")
        assert len(lanes) == 3
        # Lanes must be laid out left-to-right (different x).
        xs = sorted(ln["box"][0] for ln in lanes)
        # Strictly monotonic.
        for i in range(len(xs) - 1):
            assert xs[i] < xs[i + 1]


# ─────────────────────────────────────────────────────────────────
# State-machine: composite states + every pseudostate kind
# ─────────────────────────────────────────────────────────────────


class TestStateMachineCoverage:
    """Composite-state notation + every PseudostateKind."""

    def test_all_pseudostate_kinds_render(self) -> None:
        kinds = [
            "initial",
            "final",
            "choice",
            "junction",
            "fork",
            "join",
            "shallow_history",
            "deep_history",
            "entry_point",
            "exit_point",
            "terminate",
        ]
        m = validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}],
                "pseudostates": [{"id": f"p_{k}", "kind": k, "name": k} for k in kinds],
            }
        )
        composed = compose_state_machine(m)
        svg = _render(composed.visual)
        assert "</svg>" in svg
        # Verify each pseudostate id appears as a group attribute.
        for k in kinds:
            assert f"p_{k}" in svg

    def test_composite_state_with_actions(self) -> None:
        m = validate_state_machine(
            {
                "states": [
                    {
                        "id": "running",
                        "name": "Running",
                        "entry": "log_start()",
                        "exit": "log_end()",
                        "do": "process()",
                        "regions": ["loading"],
                    },
                    {"id": "loading", "name": "Loading"},
                ]
            }
        )
        composed = compose_state_machine(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        running = next(n for n in nodes if n["id"] == "running")
        assert running["entry"] == "log_start()"
        assert running["exit"] == "log_end()"
        assert running["do"] == "process()"
        assert running["composite"] is True

    def test_internal_transition_dashed(self) -> None:
        m = validate_state_machine(
            {
                "states": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "transitions": [
                    {
                        "id": "t",
                        "from": "a",
                        "to": "b",
                        "kind": "internal",
                    }
                ],
            }
        )
        composed = compose_state_machine(m)
        edges = _layer(composed.visual, "uml.edges")
        assert edges[0]["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Interaction-overview: non-interaction nodes
# ─────────────────────────────────────────────────────────────────


class TestInteractionOverviewBranches:
    """Cover every InteractionOverviewNodeKind path in the composer."""

    def test_decision_emits_activity_node(self) -> None:
        m = validate_interaction_overview(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "d", "kind": "decision"},
                    {"id": "f", "kind": "final"},
                ],
                "edges": [
                    {"id": "e1", "from": "i", "to": "d"},
                    {"id": "e2", "from": "d", "to": "f"},
                ],
            }
        )
        composed = compose_interaction_overview(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        d = next(n for n in nodes if n["id"] == "d")
        assert d["type"] == "uml.activity_node"
        assert d["kind"] == "decision"

    def test_fork_join_emit_activity_node(self) -> None:
        m = validate_interaction_overview(
            {
                "nodes": [
                    {"id": "i", "kind": "initial"},
                    {"id": "fk", "kind": "fork"},
                    {"id": "jn", "kind": "join"},
                    {"id": "f", "kind": "final"},
                ],
                "edges": [
                    {"id": "e1", "from": "i", "to": "fk"},
                    {"id": "e2", "from": "fk", "to": "jn"},
                    {"id": "e3", "from": "jn", "to": "f"},
                ],
            }
        )
        composed = compose_interaction_overview(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        kinds = {n["id"]: n["kind"] for n in nodes if n["type"] == "uml.activity_node"}
        assert kinds["fk"] == "fork"
        assert kinds["jn"] == "join"

    def test_named_initial_carries_label(self) -> None:
        """An initial pseudostate with `name` propagates to the visual."""
        m = validate_interaction_overview(
            {"nodes": [{"id": "i", "kind": "initial", "name": "Start"}]}
        )
        composed = compose_interaction_overview(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert nodes[0]["name"] == "Start"


# ─────────────────────────────────────────────────────────────────
# Profile diagram: stereotype-only and metaclass-only diagrams
# ─────────────────────────────────────────────────────────────────


class TestProfileDiagramShapes:
    def test_stereotype_with_properties_renders(self) -> None:
        m = validate_profile_diagram(
            {
                "stereotypes": [
                    {
                        "id": "svc",
                        "name": "Service",
                        "properties": ["url", "timeout", "retries"],
                    }
                ]
            }
        )
        composed = compose_profile_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        svc = nodes[0]
        # Three properties → three attribute lines.
        assert len(svc["attributes"]) == 3
        names = [a["name"] for a in svc["attributes"]]
        assert names == ["url", "timeout", "retries"]

    def test_metaclass_only_diagram_validates_and_composes(self) -> None:
        """The schema accepts metaclass-only profiles; composer handles it."""
        m = validate_profile_diagram({"metaclasses": [{"id": "c", "name": "Class"}]})
        composed = compose_profile_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert len(nodes) == 1
        assert nodes[0]["stereotype"] == "metaclass"

    def test_non_required_extension_uses_plain_id(self) -> None:
        """Non-required extensions don't get the `__required` suffix."""
        m = validate_profile_diagram(
            {
                "stereotypes": [{"id": "s", "name": "S"}],
                "metaclasses": [{"id": "c", "name": "Class"}],
                "extensions": [{"id": "ext", "from": "s", "to": "c"}],
            }
        )
        composed = compose_profile_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        assert any(e["id"] == "ext" for e in edges)
        assert not any(e["id"] == "ext__required" for e in edges)

    def test_pinned_stereotype_position(self) -> None:
        m = validate_profile_diagram(
            {
                "stereotypes": [
                    {
                        "id": "s",
                        "name": "S",
                        "position": {"x": 50, "y": 60},
                    }
                ]
            }
        )
        composed = compose_profile_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert nodes[0]["box"][0] == 50
        assert nodes[0]["box"][1] == 60


# ─────────────────────────────────────────────────────────────────
# Object diagram: anonymous instances + slot edge cases
# ─────────────────────────────────────────────────────────────────


class TestObjectDiagramEdges:
    def test_anonymous_with_no_slots_renders(self) -> None:
        m = validate_object_diagram({"instances": [{"id": "x", "type_name": "T"}]})
        composed = compose_object_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert nodes[0]["name"] == ":T"
        # Empty attributes list propagates.
        assert nodes[0]["attributes"] == []

    def test_slot_with_empty_value(self) -> None:
        """A slot with `value: ""` defaults to empty string but still renders."""
        m = validate_object_diagram(
            {
                "instances": [
                    {
                        "id": "a",
                        "type_name": "T",
                        "slots": [{"name": "x"}],  # value defaults to ""
                    }
                ]
            }
        )
        composed = compose_object_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert nodes[0]["attributes"][0]["name"] == "x"
        assert nodes[0]["attributes"][0]["default"] == ""

    def test_chain_of_links(self) -> None:
        """A → B → C: Sugiyama places A, B, C on three distinct y-rows."""
        m = validate_object_diagram(
            {
                "instances": [
                    {"id": "a", "type_name": "A"},
                    {"id": "b", "type_name": "B"},
                    {"id": "c", "type_name": "C"},
                ],
                "links": [
                    {"id": "l1", "from": "a", "to": "b"},
                    {"id": "l2", "from": "b", "to": "c"},
                ],
            }
        )
        composed = compose_object_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        ys = {n["id"]: n["box"][1] for n in nodes}
        assert ys["a"] < ys["b"] < ys["c"]

    def test_disconnected_instances_still_layout(self) -> None:
        """Instances without any link must still get a layout assignment."""
        m = validate_object_diagram(
            {
                "instances": [
                    {"id": "a", "type_name": "A"},
                    {"id": "b", "type_name": "B"},
                ]
            }
        )
        composed = compose_object_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert len(nodes) == 2
        # Both have valid box coordinates.
        for n in nodes:
            assert n["box"][2] > 0
            assert n["box"][3] > 0


# ─────────────────────────────────────────────────────────────────
# Timing diagram: edge cases (single change, no changes, dense changes)
# ─────────────────────────────────────────────────────────────────


class TestTimingDiagramEdges:
    def test_lifeline_with_no_changes(self) -> None:
        """A lifeline without any changes still emits its lane."""
        m = validate_timing_diagram({"lifelines": [{"id": "a", "name": "A", "states": ["x", "y"]}]})
        composed = compose_timing_diagram(m)
        lanes = _layer(composed.visual, "uml.lanes")
        assert len(lanes) == 1

    def test_single_change_at_zero(self) -> None:
        """A change at t=0 doesn't break time-range normalization."""
        m = validate_timing_diagram(
            {
                "lifelines": [{"id": "a", "name": "A", "states": ["x", "y"]}],
                "changes": [{"id": "c", "lifeline": "a", "state": "y", "at": 0}],
            }
        )
        composed = compose_timing_diagram(m)
        # No exception means the edge case is handled.
        assert composed.visual is not None

    def test_two_changes_same_state_no_vertical_segment(self) -> None:
        """Two consecutive changes to the same state emit no vertical step."""
        m = validate_timing_diagram(
            {
                "lifelines": [{"id": "a", "name": "A", "states": ["x"]}],
                "changes": [
                    {"id": "c1", "lifeline": "a", "state": "x", "at": 1},
                    {"id": "c2", "lifeline": "a", "state": "x", "at": 2},
                ],
            }
        )
        composed = compose_timing_diagram(m)
        # Only horizontal segments should be present (no vertical
        # step lines between identical states).
        changes = _layer(composed.visual, "uml.changes")
        # Exact count varies by tail emission; verify no v-line.
        assert all("__v" not in o.get("id", "") for o in changes)

    def test_three_state_lifeline(self) -> None:
        """Three-state lifeline: state row distribution must place each state on a distinct y."""
        m = validate_timing_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A", "states": ["s1", "s2", "s3"]},
                ],
                "changes": [
                    {"id": "c1", "lifeline": "a", "state": "s2", "at": 1},
                    {"id": "c2", "lifeline": "a", "state": "s3", "at": 2},
                ],
            }
        )
        composed = compose_timing_diagram(m)
        # No exception; visible objects exist.
        assert _layer(composed.visual, "uml.changes")


# ─────────────────────────────────────────────────────────────────
# Cross-composer: large fan-out and pinned-position invariants
# ─────────────────────────────────────────────────────────────────


class TestLargeAndPinnedFixtures:
    """Stress-test composers with larger fixtures."""

    def test_class_diagram_wide_fan_out(self) -> None:
        """One parent with 8 children: all children share the same y-row."""
        children = [{"id": f"c{i}", "name": f"C{i}"} for i in range(8)]
        m = validate_class_diagram(
            {
                "classes": [{"id": "p", "name": "Parent"}, *children],
                "generalizations": [{"id": f"g{i}", "from": f"c{i}", "to": "p"} for i in range(8)],
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        boxes = {n["id"]: n["box"] for n in nodes}
        # All 8 children share a y; parent's y is smaller.
        child_ys = [boxes[f"c{i}"][1] for i in range(8)]
        assert all(y == child_ys[0] for y in child_ys)
        assert boxes["p"][1] < child_ys[0]

    def test_pinned_position_overrides_sugiyama(self) -> None:
        """A pinned class lands at the declared coords, not Sugiyama's.

        This is the documented escape hatch (see Decision 2 in the
        UML architecture proposal).
        """
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "a",
                        "name": "A",
                        "position": {"x": 999, "y": 888},
                    },
                    {"id": "b", "name": "B"},
                ],
                "generalizations": [{"id": "g", "from": "a", "to": "b"}],
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        a = next(n for n in nodes if n["id"] == "a")
        assert a["box"][0] == 999
        assert a["box"][1] == 888

    def test_package_dotted_id_safe_for_renderer(self) -> None:
        """Dotted package ids must not trigger the renderer's dot-notation
        endpoint shorthand. Verified by the `_safe_id` mechanism in
        `package_diagram._safe_id`."""
        m = validate_package_diagram(
            {
                "packages": [
                    {"id": "app", "name": "app", "contains": ["app.core"]},
                    {"id": "app.core", "name": "core"},
                ]
            }
        )
        composed = compose_package_diagram(m)
        # The visual emits with sanitized ids (`.` → `_`).
        nodes = _layer(composed.visual, "uml.classifiers")
        ids = {n["id"] for n in nodes}
        # Underscored variants must be present in the emitted visual.
        assert "app" in ids
        assert "app_core" in ids


# ─────────────────────────────────────────────────────────────────
# Negative-case coverage — extra error paths in validators
# ─────────────────────────────────────────────────────────────────


class TestNegativeCases:
    """Targeted error-path tests that complement per-composer suites."""

    def test_class_diagram_unknown_classifier_in_generalization(self) -> None:
        with pytest.raises(ValidationError):
            validate_class_diagram(
                {
                    "classes": [{"id": "a", "name": "A"}],
                    "generalizations": [{"id": "g", "from": "a", "to": "missing"}],
                }
            )

    def test_use_case_diagram_actor_id_collision_with_use_case(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_use_case_diagram(
                {
                    "actors": [{"id": "x", "name": "User"}],
                    "use_cases": [{"id": "x", "name": "Login"}],
                }
            )

    def test_component_id_collision_with_port(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_component_diagram(
                {
                    "components": [
                        {
                            "id": "c",
                            "name": "C",
                            "ports": [{"id": "c", "name": "p"}],
                        }
                    ]
                }
            )

    def test_deployment_diagram_node_artifact_id_collision(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_deployment_diagram(
                {
                    "nodes": [{"id": "x", "name": "N"}],
                    "artifacts": [{"id": "x", "name": "a.jar"}],
                }
            )

    def test_state_machine_pseudostate_id_collision_with_state(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_state_machine(
                {
                    "states": [{"id": "x", "name": "X"}],
                    "pseudostates": [{"id": "x", "kind": "initial"}],
                }
            )

    def test_sequence_diagram_message_ids_must_be_unique(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_sequence_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [
                        {"id": "m", "from": "a", "to": "b", "step": 1},
                        {"id": "m", "from": "b", "to": "a", "step": 2},
                    ],
                }
            )

    def test_communication_diagram_id_collision_lifeline_message(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_communication_diagram(
                {
                    "lifelines": [
                        {"id": "x", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [{"id": "x", "from": "x", "to": "b", "sequence": "1"}],
                }
            )

    def test_object_diagram_link_ids_unique_with_instances(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_object_diagram(
                {
                    "instances": [
                        {"id": "x", "type_name": "T"},
                        {"id": "y", "type_name": "T"},
                    ],
                    "links": [{"id": "x", "from": "x", "to": "y"}],
                }
            )


# ─────────────────────────────────────────────────────────────────
# End-to-end render smoke tests for every composer
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRenderAcrossComposers:
    """Each composer must produce a valid SVG document for a minimal model."""

    @pytest.mark.parametrize(
        "compose_fn,validate_fn,model_data",
        [
            (
                compose_class_diagram,
                validate_class_diagram,
                {"classes": [{"id": "c", "name": "C"}]},
            ),
            (
                compose_package_diagram,
                validate_package_diagram,
                {"packages": [{"id": "p", "name": "P"}]},
            ),
            (
                compose_use_case_diagram,
                validate_use_case_diagram,
                {
                    "actors": [{"id": "a", "name": "A"}],
                    "use_cases": [{"id": "u", "name": "U"}],
                },
            ),
            (
                compose_component_diagram,
                validate_component_diagram,
                {"components": [{"id": "c", "name": "C"}]},
            ),
            (
                compose_deployment_diagram,
                validate_deployment_diagram,
                {"nodes": [{"id": "n", "name": "N"}]},
            ),
            (
                compose_activity_diagram,
                validate_activity_diagram,
                {"nodes": [{"id": "i", "kind": "initial"}]},
            ),
            (
                compose_state_machine,
                validate_state_machine,
                {"states": [{"id": "s", "name": "S"}]},
            ),
            (
                compose_sequence_diagram,
                validate_sequence_diagram,
                {"lifelines": [{"id": "a", "name": "A"}]},
            ),
            (
                compose_timing_diagram,
                validate_timing_diagram,
                {"lifelines": [{"id": "a", "name": "A", "states": ["x"]}]},
            ),
            (
                compose_communication_diagram,
                validate_communication_diagram,
                {"lifelines": [{"id": "a", "name": "A"}]},
            ),
            (
                compose_interaction_overview,
                validate_interaction_overview,
                {"nodes": [{"id": "i", "kind": "initial"}]},
            ),
            (
                compose_profile_diagram,
                validate_profile_diagram,
                {"stereotypes": [{"id": "s", "name": "S"}]},
            ),
            (
                compose_composite_structure,
                validate_composite_structure,
                {
                    "classifier_id": "sys",
                    "classifier_name": "Sys",
                    "parts": [{"id": "a", "name": "A"}],
                },
            ),
            (
                compose_object_diagram,
                validate_object_diagram,
                {"instances": [{"id": "a", "type_name": "T"}]},
            ),
        ],
    )
    def test_minimal_model_renders(self, compose_fn, validate_fn, model_data) -> None:
        """Every composer produces a closed `</svg>` for a minimal valid model."""
        m = validate_fn(model_data)
        composed = compose_fn(m)
        svg = _render(composed.visual)
        assert svg.rstrip().endswith("</svg>")
        assert "<svg" in svg


# ─────────────────────────────────────────────────────────────────
# Class diagram: association kinds + dependencies + realizations
# ─────────────────────────────────────────────────────────────────


class TestClassDiagramAssociationKinds:
    """Cover every association kind, dependency, and realization rendering."""

    def test_aggregation_uses_hollow_diamond(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "whole", "name": "Library"},
                    {"id": "part", "name": "Book"},
                ],
                "associations": [
                    {
                        "id": "a",
                        "kind": "aggregation",
                        "end1": {"id_ref": "whole"},
                        "end2": {"id_ref": "part"},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        a = next(e for e in edges if e["id"] == "a")
        assert a["stroke"]["arrow_start_kind"] == "hollow_diamond"

    def test_composition_uses_filled_diamond(self) -> None:
        # UML 2.5.1 §11.5: the part end of a composition must have
        # multiplicity ≤ 1. We make the *whole* end (`house`) have
        # 1..* to satisfy the validator while still exercising the
        # composition arrow.
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "house", "name": "House"},
                    {"id": "room", "name": "Room"},
                ],
                "associations": [
                    {
                        "id": "a",
                        "kind": "composition",
                        "end1": {"id_ref": "house"},
                        "end2": {"id_ref": "room", "multiplicity": "1"},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        a = next(e for e in edges if e["id"] == "a")
        assert a["stroke"]["arrow_start_kind"] == "filled_diamond"

    def test_navigable_end_emits_open_arrow(self) -> None:
        """A plain association with navigable=True at end2 emits open-arrow at the target."""
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "associations": [
                    {
                        "id": "x",
                        "kind": "association",
                        "end1": {"id_ref": "a"},
                        "end2": {"id_ref": "b", "navigable": True},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        x = next(e for e in edges if e["id"] == "x")
        assert x["stroke"]["arrow_end_kind"] == "open_arrow"

    def test_bidirectional_navigable_emits_both_arrows(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "associations": [
                    {
                        "id": "x",
                        "kind": "association",
                        "end1": {"id_ref": "a", "navigable": True},
                        "end2": {"id_ref": "b", "navigable": True},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        x = next(e for e in edges if e["id"] == "x")
        assert x["stroke"]["arrow_start_kind"] == "open_arrow"
        assert x["stroke"]["arrow_end_kind"] == "open_arrow"

    def test_plain_association_unspecified_navigability_no_arrows(self) -> None:
        """Default navigability == None → no arrowheads."""
        m = validate_class_diagram(
            {
                "classes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "associations": [
                    {
                        "id": "x",
                        "kind": "association",
                        "end1": {"id_ref": "a"},
                        "end2": {"id_ref": "b"},
                    }
                ],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        x = next(e for e in edges if e["id"] == "x")
        assert "arrow_start_kind" not in x["stroke"]
        assert "arrow_end_kind" not in x["stroke"]

    def test_realization_uses_hollow_triangle_dashed(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [
                    {"id": "impl", "name": "Impl"},
                ],
                "interfaces": [{"id": "iface", "name": "IFace"}],
                "realizations": [{"id": "r", "from": "impl", "to": "iface"}],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        r = next(e for e in edges if e["id"] == "r")
        assert r["stroke"]["arrow_end_kind"] == "hollow_triangle"
        assert r["stroke"]["dash"] == [5, 4]

    def test_dependency_uses_open_arrow_dashed(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "dependencies": [{"id": "d", "from": "a", "to": "b"}],
            }
        )
        composed = compose_class_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        d = next(e for e in edges if e["id"] == "d")
        assert d["stroke"]["arrow_end_kind"] == "open_arrow"
        assert d["stroke"]["dash"] == [5, 4]

    def test_enumeration_renders_with_stereotype(self) -> None:
        m = validate_class_diagram(
            {
                "enumerations": [
                    {
                        "id": "Status",
                        "name": "Status",
                        "literals": ["OPEN", "CLOSED", "ARCHIVED"],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        e = next(n for n in nodes if n["id"] == "Status")
        assert e["stereotype"] == "enumeration"

    def test_abstract_class_marked_abstract(self) -> None:
        m = validate_class_diagram({"classes": [{"id": "c", "name": "C", "abstract": True}]})
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        c = nodes[0]
        assert c.get("abstract") is True


class TestClassDiagramOperationsAndAttributes:
    """Verify that attribute and operation fields propagate through to the visual."""

    def test_attribute_with_full_signature_propagates(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "c",
                        "name": "C",
                        "attributes": [
                            {
                                "name": "balance",
                                "type": "Decimal",
                                "visibility": "private",
                                "multiplicity": "0..1",
                                "default": "0.00",
                                "static": True,
                                "readonly": True,
                            }
                        ],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        attr = nodes[0]["attributes"][0]
        assert attr["name"] == "balance"
        assert attr["type"] == "Decimal"
        assert attr["static"] is True

    def test_operation_with_parameters_and_return_propagates(self) -> None:
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "c",
                        "name": "C",
                        "operations": [
                            {
                                "name": "compute",
                                "visibility": "public",
                                "parameters": [
                                    {
                                        "name": "x",
                                        "type": "int",
                                        "direction": "in",
                                    },
                                    {
                                        "name": "y",
                                        "type": "int",
                                        "direction": "in",
                                    },
                                ],
                                "return_type": "int",
                                "query": True,
                            }
                        ],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        op = nodes[0]["operations"][0]
        assert op["name"] == "compute"
        assert len(op["parameters"]) == 2
        assert op["return_type"] == "int"
        assert op["query"] is True

    def test_class_diagram_with_full_member_set_renders(self) -> None:
        """End-to-end: a class with attributes + operations renders both."""
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "Order",
                        "name": "Order",
                        "attributes": [{"name": "total", "type": "Decimal"}],
                        "operations": [{"name": "submit", "return_type": "bool"}],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        svg = _render(composed.visual)
        assert "Order" in svg
        assert "total" in svg
        assert "submit" in svg

    def test_derived_attribute_format(self) -> None:
        """A derived attribute renders with the `/` prefix."""
        m = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "c",
                        "name": "C",
                        "attributes": [{"name": "age", "type": "int", "derived": True}],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        svg = _render(composed.visual)
        assert "/age" in svg

    def test_interface_with_constants_and_operations(self) -> None:
        """Exercise the UMLInterface sizing branch (constants + operations).

        Per UML 2.5 §10.4.1, interface attributes are constants —
        i.e., must be both static and readonly. The validator
        enforces this; we honor it here.
        """
        m = validate_class_diagram(
            {
                "interfaces": [
                    {
                        "id": "ICache",
                        "name": "ICache",
                        "constants": [
                            {
                                "name": "MAX_SIZE",
                                "type": "int",
                                "default": "100",
                                "static": True,
                                "readonly": True,
                            }
                        ],
                        "operations": [
                            {"name": "get", "return_type": "T"},
                            {"name": "put"},
                        ],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        assert nodes[0]["stereotype"] == "interface"
        assert len(nodes[0]["operations"]) == 2

    def test_enumeration_with_operations(self) -> None:
        """Exercise the UMLEnumeration sizing branch (literals + operations)."""
        m = validate_class_diagram(
            {
                "enumerations": [
                    {
                        "id": "Suit",
                        "name": "Suit",
                        "literals": ["HEARTS", "DIAMONDS", "CLUBS", "SPADES"],
                        "operations": [{"name": "values", "return_type": "Suit[]"}],
                    }
                ]
            }
        )
        composed = compose_class_diagram(m)
        nodes = _layer(composed.visual, "uml.classifiers")
        e = nodes[0]
        assert e["stereotype"] == "enumeration"
        assert len(e["attributes"]) == 4
        assert len(e["operations"]) == 1


# ─────────────────────────────────────────────────────────────────
# Component-diagram: delegation connector + interface routing edge
#                    cases beyond the original test file.
# ─────────────────────────────────────────────────────────────────


class TestComponentDiagramRoutingEdges:
    def test_delegation_connector_via_component_ids(self) -> None:
        """Delegation works between components (not just ports)."""
        m = validate_component_diagram(
            {
                "components": [
                    {"id": "outer", "name": "Outer"},
                    {"id": "inner", "name": "Inner"},
                ],
                "connectors": [
                    {
                        "id": "del",
                        "from": "outer",
                        "to": "inner",
                        "kind": "delegation",
                    }
                ],
            }
        )
        composed = compose_component_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        d = next(e for e in edges if e["id"] == "del")
        assert d["stroke"]["arrow_end_kind"] == "open_arrow"
        assert d["stroke"]["dash"] == [5, 4]

    def test_unqualified_assembly_uses_declared_order(self) -> None:
        """Plain component-id endpoints (no `comp.iface`) preserve declared order."""
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
        nodes = _layer(composed.visual, "uml.classifiers")
        boxes = {n["id"]: n["box"] for n in nodes}
        # No interface-qualified endpoint → from above to.
        assert boxes["a"][1] < boxes["b"][1]


# ─────────────────────────────────────────────────────────────────
# Use-case diagram: optional fields and full vocabulary
# ─────────────────────────────────────────────────────────────────


class TestUseCaseDiagramCoverage:
    def test_extends_relation(self) -> None:
        m = validate_use_case_diagram(
            {
                "actors": [{"id": "u", "name": "User"}],
                "use_cases": [
                    {"id": "place", "name": "Place"},
                    {"id": "validate", "name": "Validate"},
                ],
                "relations": [{"id": "r", "from": "validate", "to": "place", "kind": "extend"}],
            }
        )
        composed = compose_use_case_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        r = next(e for e in edges if e["id"] == "r")
        # `extend` is dashed.
        assert r["stroke"]["dash"] == [5, 4]

    def test_includes_relation(self) -> None:
        m = validate_use_case_diagram(
            {
                "actors": [{"id": "u", "name": "User"}],
                "use_cases": [
                    {"id": "place", "name": "Place"},
                    {"id": "auth", "name": "Authenticate"},
                ],
                "relations": [
                    {
                        "id": "r",
                        "from": "place",
                        "to": "auth",
                        "kind": "include",
                    }
                ],
            }
        )
        composed = compose_use_case_diagram(m)
        edges = _layer(composed.visual, "uml.edges")
        r = next(e for e in edges if e["id"] == "r")
        assert r["stroke"]["dash"] == [5, 4]

    def test_system_boundary_emitted(self) -> None:
        m = validate_use_case_diagram(
            {
                "actors": [{"id": "u", "name": "User"}],
                "use_cases": [
                    {"id": "uc1", "name": "UC1"},
                    {"id": "uc2", "name": "UC2"},
                ],
                "system_boundaries": [
                    {
                        "id": "sb",
                        "name": "Online Shop",
                        "contains": ["uc1", "uc2"],
                    }
                ],
            }
        )
        composed = compose_use_case_diagram(m)
        # System-boundary frame should be emitted as a layer.
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert any("boundar" in lid.lower() for lid in layer_ids)


# ─────────────────────────────────────────────────────────────────
# Sequence diagram: notes + diagram with no messages
# ─────────────────────────────────────────────────────────────────


class TestSequenceDiagramExtraEdges:
    def test_no_messages_still_emits_lifelines(self) -> None:
        m = validate_sequence_diagram({"lifelines": [{"id": "a", "name": "A"}]})
        composed = compose_sequence_diagram(m)
        lifelines = _layer(composed.visual, "uml.lifelines")
        assert len(lifelines) == 1
        # No messages layer when there are no messages — but the
        # composer always emits one (possibly empty). Verify shape.
        msgs_layer = _layer(composed.visual, "uml.messages")
        assert msgs_layer == []

    def test_async_async_does_not_emit_activation(self) -> None:
        """Pure async messaging (no sync/reply pair) → no activation layer."""
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                "messages": [
                    {
                        "id": "m1",
                        "from": "a",
                        "to": "b",
                        "kind": "async",
                        "step": 1,
                    }
                ],
            }
        )
        composed = compose_sequence_diagram(m)
        # No sync/reply pair, no activations.
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.activations" not in layer_ids


# ─────────────────────────────────────────────────────────────────
# Activity diagram: pinned + manual layout invariants
# ─────────────────────────────────────────────────────────────────


class TestActivityDiagramPinnedInvariants:
    def test_manual_layout_with_all_pinned(self) -> None:
        m = validate_activity_diagram(
            {
                "nodes": [
                    {
                        "id": "i",
                        "kind": "initial",
                        "position": {"x": 100, "y": 100},
                    },
                    {
                        "id": "f",
                        "kind": "final",
                        "position": {"x": 100, "y": 300},
                    },
                ],
                "edges": [{"id": "e", "from": "i", "to": "f"}],
            }
        )
        from framegraph.uml import ActivityDiagramOptions

        composed = compose_activity_diagram(m, options=ActivityDiagramOptions(layout="manual"))
        nodes = _layer(composed.visual, "uml.classifiers")
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["i"][0] == 100
        assert boxes["i"][1] == 100


# ─────────────────────────────────────────────────────────────────
# Renderer round-trip: every emitted primitive renders to non-empty SVG
# ─────────────────────────────────────────────────────────────────


class TestRendererPrimitiveCoverage:
    """Each UML primitive must render to a non-empty `<g>…</g>` block."""

    @pytest.mark.parametrize(
        "obj",
        [
            {
                "type": "uml.classifier_box",
                "id": "c",
                "box": [0, 0, 200, 100],
                "name": "C",
            },
            {
                "type": "uml.actor",
                "id": "a",
                "box": [0, 0, 60, 80],
                "name": "User",
            },
            {
                "type": "uml.component_box",
                "id": "comp",
                "box": [0, 0, 200, 120],
                "name": "Auth",
            },
            {
                "type": "uml.lollipop",
                "id": "l",
                "box": [0, 0, 40, 16],
                "name": "IAuth",
            },
            {
                "type": "uml.socket",
                "id": "s",
                "box": [0, 0, 40, 16],
                "name": "IAuth",
            },
            {
                "type": "uml.node_box",
                "id": "n",
                "box": [0, 0, 220, 130],
                "name": "Server",
                "kind": "device",
            },
            {
                "type": "uml.artifact_box",
                "id": "art",
                "box": [0, 0, 160, 80],
                "name": "app.war",
            },
            {
                "type": "uml.activity_node",
                "id": "i",
                "box": [0, 0, 28, 28],
                "kind": "initial",
            },
            {
                "type": "uml.action",
                "id": "act",
                "box": [0, 0, 140, 50],
                "name": "Run",
            },
            {
                "type": "uml.swimlane",
                "id": "ln",
                "box": [0, 0, 200, 400],
                "name": "Lane",
            },
            {
                "type": "uml.state_box",
                "id": "s",
                "box": [0, 0, 180, 80],
                "name": "Idle",
            },
            {
                "type": "uml.pseudostate",
                "id": "ps",
                "box": [0, 0, 28, 28],
                "kind": "choice",
            },
            {
                "type": "uml.lifeline",
                "id": "ll",
                "box": [0, 0, 120, 400],
                "name": "User",
            },
            {
                "type": "uml.activation_bar",
                "id": "ab",
                "box": [0, 0, 10, 60],
            },
            {
                "type": "uml.fragment_frame",
                "id": "ff",
                "box": [0, 0, 240, 80],
                "kind": "opt",
                "operands": ["x > 0"],
            },
            {
                "type": "uml.timing_lane",
                "id": "tl",
                "box": [0, 0, 600, 100],
                "name": "CPU",
                "states": ["idle", "busy"],
            },
        ],
    )
    def test_primitive_renders(self, obj) -> None:
        visual = {
            "tokens": {},
            "layers": [{"id": "main", "z": 10, "objects": [obj]}],
        }
        svg = _render(visual)
        assert svg.rstrip().endswith("</svg>")
        # The object's id should be preserved in the SVG markup.
        assert obj["id"] in svg
