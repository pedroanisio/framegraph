"""Regression tests for `framegraph.uml.compose_state_machine` — Phase C.4."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLStateMachineModel,
    UMLTransition,
    validate_state_machine,
)
from framegraph.uml import (
    StateMachineOptions,
    compose_state_machine,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestStateMachineSchema:
    def test_minimal_validates(self) -> None:
        m = validate_state_machine({"states": [{"id": "s", "name": "S"}]})
        assert len(m.states) == 1

    def test_empty_states_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_state_machine({"states": []})

    def test_missing_states_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_state_machine({})

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_state_machine(
                {
                    "states": [
                        {"id": "s", "name": "A"},
                        {"id": "s", "name": "B"},
                    ]
                }
            )

    def test_unknown_transition_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_state_machine(
                {
                    "states": [{"id": "s", "name": "S"}],
                    "transitions": [{"id": "t", "from": "s", "to": "missing"}],
                }
            )

    def test_self_region_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot contain itself"):
            validate_state_machine({"states": [{"id": "s", "name": "S", "regions": ["s"]}]})

    def test_region_cycle_rejected(self) -> None:
        with pytest.raises(ValidationError, match="region cycle"):
            validate_state_machine(
                {
                    "states": [
                        {"id": "a", "name": "A", "regions": ["b"]},
                        {"id": "b", "name": "B", "regions": ["a"]},
                    ]
                }
            )

    def test_unknown_region_member_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown region member"):
            validate_state_machine({"states": [{"id": "s", "name": "S", "regions": ["missing"]}]})

    @pytest.mark.parametrize(
        "kind",
        [
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
        ],
    )
    def test_pseudostate_kinds_accepted(self, kind: str) -> None:
        validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}],
                "pseudostates": [{"id": "p", "kind": kind}],
            }
        )


class TestTransitionLabel:
    """`UMLTransition.label()` formats the trigger/guard/effect properly."""

    def test_trigger_only(self) -> None:
        t = UMLTransition(id="t", **{"from": "a", "to": "b", "trigger": "click"})
        assert t.label() == "click"

    def test_trigger_and_guard(self) -> None:
        t = UMLTransition(
            id="t",
            **{"from": "a", "to": "b", "trigger": "click", "guard": "valid"},
        )
        assert t.label() == "click [valid]"

    def test_full_form(self) -> None:
        t = UMLTransition(
            id="t",
            **{
                "from": "a",
                "to": "b",
                "trigger": "click",
                "guard": "valid",
                "effect": "save()",
            },
        )
        assert t.label() == "click [valid] / save()"

    def test_effect_only(self) -> None:
        t = UMLTransition(id="t", **{"from": "a", "to": "b", "effect": "save()"})
        assert t.label() == "/ save()"

    def test_empty_label(self) -> None:
        t = UMLTransition(id="t", **{"from": "a", "to": "b"})
        assert t.label() == ""


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _basic_machine() -> UMLStateMachineModel:
    """initial → Idle → Active → final."""
    return validate_state_machine(
        {
            "states": [
                {"id": "idle", "name": "Idle"},
                {"id": "active", "name": "Active", "entry": "log()"},
            ],
            "pseudostates": [
                {"id": "i", "kind": "initial"},
                {"id": "f", "kind": "final"},
            ],
            "transitions": [
                {"id": "t1", "from": "i", "to": "idle"},
                {"id": "t2", "from": "idle", "to": "active", "trigger": "start"},
                {"id": "t3", "from": "active", "to": "f", "trigger": "stop"},
            ],
        }
    )


def _composite_machine() -> UMLStateMachineModel:
    """A composite state with two simple sub-states."""
    return validate_state_machine(
        {
            "states": [
                {
                    "id": "running",
                    "name": "Running",
                    "regions": ["loading", "ready"],
                },
                {"id": "loading", "name": "Loading"},
                {"id": "ready", "name": "Ready"},
            ],
            "pseudostates": [{"id": "i", "kind": "initial"}],
            "transitions": [{"id": "t1", "from": "i", "to": "running"}],
        }
    )


def _choice_machine() -> UMLStateMachineModel:
    """Choice pseudostate splits into two branches."""
    return validate_state_machine(
        {
            "states": [
                {"id": "input", "name": "Input"},
                {"id": "valid", "name": "Valid"},
                {"id": "invalid", "name": "Invalid"},
            ],
            "pseudostates": [{"id": "c", "kind": "choice"}],
            "transitions": [
                {"id": "t1", "from": "input", "to": "c"},
                {
                    "id": "t2",
                    "from": "c",
                    "to": "valid",
                    "guard": "ok",
                },
                {
                    "id": "t3",
                    "from": "c",
                    "to": "invalid",
                    "guard": "not ok",
                },
            ],
        }
    )


def _render(model: UMLStateMachineModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_state_machine(model, canvas_size=(1280, 720))
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
        composed = compose_state_machine(_basic_machine())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.edges" in layer_ids
        assert "uml.classifiers" in layer_ids

    def test_one_object_per_state_and_pseudostate(self) -> None:
        composed = compose_state_machine(_basic_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        # 2 states + 2 pseudostates = 4
        assert len(nodes) == 4

    def test_state_uses_state_box_type(self) -> None:
        composed = compose_state_machine(_basic_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        s = next(n for n in nodes if n["id"] == "active")
        assert s["type"] == "uml.state_box"
        assert s["entry"] == "log()"

    def test_pseudostate_uses_pseudostate_type(self) -> None:
        composed = compose_state_machine(_basic_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        p = next(n for n in nodes if n["id"] == "i")
        assert p["type"] == "uml.pseudostate"
        assert p["kind"] == "initial"

    def test_composite_state_marked(self) -> None:
        composed = compose_state_machine(_composite_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        running = next(n for n in nodes if n["id"] == "running")
        assert running.get("composite") is True


# ─────────────────────────────────────────────────────────────────
# Sugiyama topology
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaIntegration:
    def test_initial_above_first_state(self) -> None:
        composed = compose_state_machine(_basic_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["i"][1] < boxes["idle"][1]

    def test_choice_branches_share_layer(self) -> None:
        composed = compose_state_machine(_choice_machine())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["valid"][1] == boxes["invalid"][1]


# ─────────────────────────────────────────────────────────────────
# Edge styling
# ─────────────────────────────────────────────────────────────────


class TestEdgeStyling:
    def test_external_transition_solid_with_arrow(self) -> None:
        composed = compose_state_machine(_basic_machine())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        e = edges[0]
        assert e["stroke"]["arrow_end_kind"] == "open_arrow"
        assert "dash" not in e["stroke"]

    def test_internal_transition_dashed(self) -> None:
        m = validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}, {"id": "t", "name": "T"}],
                "transitions": [
                    {
                        "id": "tr",
                        "from": "s",
                        "to": "t",
                        "kind": "internal",
                    }
                ],
            }
        )
        composed = compose_state_machine(m)
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        assert edges[0]["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    def test_pinned_state_position_honored(self) -> None:
        m = validate_state_machine(
            {
                "states": [
                    {
                        "id": "s",
                        "name": "S",
                        "position": {"x": 444, "y": 333},
                    }
                ]
            }
        )
        composed = compose_state_machine(m)
        node = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ][0]
        assert node["box"][0] == 444
        assert node["box"][1] == 333

    def test_pinned_pseudostate_position_honored(self) -> None:
        m = validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}],
                "pseudostates": [{"id": "p", "kind": "choice", "position": {"x": 1, "y": 2}}],
            }
        )
        composed = compose_state_machine(m)
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        p = next(n for n in nodes if n["id"] == "p")
        assert p["box"][0] == 1
        assert p["box"][1] == 2

    def test_manual_layout_requires_all_positions(self) -> None:
        m = validate_state_machine(
            {
                "states": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ]
            }
        )
        with pytest.raises(ValueError, match="manual"):
            compose_state_machine(m, options=StateMachineOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────


class TestNotes:
    def test_notes_emit_separate_layer(self) -> None:
        m = validate_state_machine(
            {
                "states": [{"id": "s", "name": "S"}],
                "notes": [{"id": "n1", "text": "spec ref"}],
            }
        )
        composed = compose_state_machine(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    def test_basic_renders(self) -> None:
        svg, _ = _render(_basic_machine())
        assert "</svg>" in svg
        assert "Idle" in svg
        assert "Active" in svg
        assert "log()" in svg

    def test_composite_renders(self) -> None:
        svg, _ = _render(_composite_machine())
        assert "Running" in svg
        assert "Loading" in svg
        assert "Ready" in svg

    def test_choice_renders(self) -> None:
        svg, _ = _render(_choice_machine())
        assert "Input" in svg
        assert "Valid" in svg
        assert "Invalid" in svg
