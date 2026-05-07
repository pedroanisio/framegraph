"""Regression tests for `framegraph.uml.compose_sequence_diagram` — Phase D.

Sequence diagrams use a custom temporal layout (lifelines on x-axis,
time on y-axis), distinct from the Sugiyama-based composers in
Phases A–C. Tests cover schema validation, layout structure, message
arrow-kind propagation, activation-bar pairing, fragment frames, and
end-to-end render.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLSequenceDiagramModel,
    validate_sequence_diagram,
)
from framegraph.uml import (
    SequenceDiagramOptions,
    compose_sequence_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestSequenceSchema:
    def test_minimal_validates(self) -> None:
        m = validate_sequence_diagram({"lifelines": [{"id": "a", "name": "A"}]})
        assert len(m.lifelines) == 1
        assert m.messages == []

    def test_empty_lifelines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_sequence_diagram({"lifelines": []})

    def test_missing_lifelines_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_sequence_diagram({})

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_sequence_diagram(
                {"lifelines": [{"id": "x", "name": "A"}, {"id": "x", "name": "B"}]}
            )

    def test_unknown_message_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown source"):
            validate_sequence_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A"}],
                    "messages": [{"id": "m", "from": "missing", "to": "a", "step": 1}],
                }
            )

    def test_duplicate_step_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate message step"):
            validate_sequence_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [
                        {"id": "m1", "from": "a", "to": "b", "step": 1},
                        {"id": "m2", "from": "b", "to": "a", "step": 1},
                    ],
                }
            )

    def test_step_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            validate_sequence_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [
                        {"id": "m1", "from": "a", "to": "b", "step": 0},
                    ],
                }
            )

    def test_fragment_step_range_inverted_rejected(self) -> None:
        with pytest.raises(ValidationError, match="to_step.*from_step"):
            validate_sequence_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [{"id": "m1", "from": "a", "to": "b", "step": 1}],
                    "fragments": [
                        {
                            "id": "f",
                            "kind": "opt",
                            "from_step": 2,
                            "to_step": 1,
                        }
                    ],
                }
            )

    def test_fragment_outside_message_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exceeds messages range"):
            validate_sequence_diagram(
                {
                    "lifelines": [
                        {"id": "a", "name": "A"},
                        {"id": "b", "name": "B"},
                    ],
                    "messages": [{"id": "m1", "from": "a", "to": "b", "step": 1}],
                    "fragments": [
                        {
                            "id": "f",
                            "kind": "opt",
                            "from_step": 1,
                            "to_step": 5,
                        }
                    ],
                }
            )

    def test_fragment_with_no_messages_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no messages"):
            validate_sequence_diagram(
                {
                    "lifelines": [{"id": "a", "name": "A"}],
                    "fragments": [{"id": "f", "kind": "opt", "from_step": 1, "to_step": 1}],
                }
            )

    @pytest.mark.parametrize("kind", ["sync", "async", "reply", "create", "destroy"])
    def test_message_kinds_accepted(self, kind: str) -> None:
        validate_sequence_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "messages": [{"id": "m", "from": "a", "to": "b", "kind": kind, "step": 1}],
            }
        )

    @pytest.mark.parametrize(
        "kind",
        [
            "alt",
            "opt",
            "loop",
            "par",
            "break",
            "critical",
            "neg",
            "strict",
            "seq",
            "ignore",
            "consider",
            "assert",
        ],
    )
    def test_fragment_kinds_accepted(self, kind: str) -> None:
        validate_sequence_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "messages": [{"id": "m", "from": "a", "to": "b", "step": 1}],
                "fragments": [{"id": "f", "kind": kind, "from_step": 1, "to_step": 1}],
            }
        )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_lifeline_call() -> UMLSequenceDiagramModel:
    """User → Controller sync call + reply."""
    return validate_sequence_diagram(
        {
            "lifelines": [
                {"id": "u", "name": "User", "actor": True},
                {"id": "c", "name": "Controller", "type_name": "Ctrl"},
            ],
            "messages": [
                {
                    "id": "m1",
                    "from": "u",
                    "to": "c",
                    "kind": "sync",
                    "name": "click()",
                    "step": 1,
                },
                {
                    "id": "m2",
                    "from": "c",
                    "to": "u",
                    "kind": "reply",
                    "name": "rendered",
                    "step": 2,
                },
            ],
        }
    )


def _three_lifeline_chain() -> UMLSequenceDiagramModel:
    """User → Controller → Service, with replies back."""
    return validate_sequence_diagram(
        {
            "lifelines": [
                {"id": "u", "name": "User", "actor": True},
                {"id": "c", "name": "Controller"},
                {"id": "s", "name": "Service"},
            ],
            "messages": [
                {
                    "id": "m1",
                    "from": "u",
                    "to": "c",
                    "kind": "sync",
                    "name": "click()",
                    "step": 1,
                },
                {
                    "id": "m2",
                    "from": "c",
                    "to": "s",
                    "kind": "sync",
                    "name": "fetch()",
                    "step": 2,
                },
                {
                    "id": "m3",
                    "from": "s",
                    "to": "c",
                    "kind": "reply",
                    "name": "data",
                    "step": 3,
                },
                {
                    "id": "m4",
                    "from": "c",
                    "to": "u",
                    "kind": "reply",
                    "name": "rendered",
                    "step": 4,
                },
            ],
        }
    )


def _alt_fragment_diagram() -> UMLSequenceDiagramModel:
    """alt fragment with two operands wraps two messages."""
    return validate_sequence_diagram(
        {
            "lifelines": [
                {"id": "u", "name": "User"},
                {"id": "s", "name": "Server"},
            ],
            "messages": [
                {"id": "m1", "from": "u", "to": "s", "step": 1, "name": "A"},
                {"id": "m2", "from": "u", "to": "s", "step": 2, "name": "B"},
            ],
            "fragments": [
                {
                    "id": "f1",
                    "kind": "alt",
                    "from_step": 1,
                    "to_step": 2,
                    "operands": ["valid", "else"],
                }
            ],
        }
    )


def _create_destroy_diagram() -> UMLSequenceDiagramModel:
    """Includes a create + destroy message."""
    return validate_sequence_diagram(
        {
            "lifelines": [
                {"id": "f", "name": "Factory"},
                {"id": "p", "name": "Product"},
            ],
            "messages": [
                {
                    "id": "m1",
                    "from": "f",
                    "to": "p",
                    "kind": "create",
                    "name": "new",
                    "step": 1,
                },
                {
                    "id": "m2",
                    "from": "f",
                    "to": "p",
                    "kind": "sync",
                    "name": "use",
                    "step": 2,
                },
                {
                    "id": "m3",
                    "from": "f",
                    "to": "p",
                    "kind": "destroy",
                    "step": 3,
                },
            ],
        }
    )


def _self_message_diagram() -> UMLSequenceDiagramModel:
    """A lifeline calls itself."""
    return validate_sequence_diagram(
        {
            "lifelines": [{"id": "a", "name": "A"}],
            "messages": [
                {
                    "id": "m1",
                    "from": "a",
                    "to": "a",
                    "kind": "sync",
                    "name": "recurse()",
                    "step": 1,
                }
            ],
        }
    )


def _render(model: UMLSequenceDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_sequence_diagram(model, canvas_size=(1280, 720))
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
        composed = compose_sequence_diagram(_two_lifeline_call())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.lifelines" in layer_ids
        assert "uml.messages" in layer_ids

    def test_one_lifeline_object_per_lifeline(self) -> None:
        composed = compose_sequence_diagram(_three_lifeline_chain())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        assert len(lifelines) == 3

    def test_lifeline_objects_use_lifeline_type(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        for ll in lifelines:
            assert ll["type"] == "uml.lifeline"

    def test_actor_flag_propagates(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        u = next(ll for ll in lifelines if ll["id"] == "u")
        c = next(ll for ll in lifelines if ll["id"] == "c")
        assert u["actor"] is True
        assert "actor" not in c

    def test_type_name_propagates(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        c = next(ll for ll in lifelines if ll["id"] == "c")
        assert c["type_name"] == "Ctrl"

    def test_lifelines_evenly_spaced(self) -> None:
        """With no pinned positions, lifelines are uniformly spaced."""
        composed = compose_sequence_diagram(_three_lifeline_chain())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        boxes = {ll["id"]: ll["box"] for ll in lifelines}
        # Centers (x + w/2) should be evenly spaced.
        cx_u = boxes["u"][0] + boxes["u"][2] / 2
        cx_c = boxes["c"][0] + boxes["c"][2] / 2
        cx_s = boxes["s"][0] + boxes["s"][2] / 2
        # Within 0.5 px tolerance.
        assert abs((cx_c - cx_u) - (cx_s - cx_c)) < 0.5


# ─────────────────────────────────────────────────────────────────
# Message-arrow propagation
# ─────────────────────────────────────────────────────────────────


class TestMessageArrowKinds:
    def test_sync_filled_triangle_solid(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        messages = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ]
        m1 = next(o for o in messages if o["id"] == "m1")
        assert m1["stroke"]["arrow_end_kind"] == "filled_triangle"
        assert "dash" not in m1["stroke"]

    def test_reply_open_arrow_dashed(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        messages = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ]
        m2 = next(o for o in messages if o["id"] == "m2")
        assert m2["stroke"]["arrow_end_kind"] == "open_arrow"
        assert m2["stroke"]["dash"] == [5, 4]

    def test_async_open_arrow_solid(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
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
        msg = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ][0]
        assert msg["stroke"]["arrow_end_kind"] == "open_arrow"
        assert "dash" not in msg["stroke"]


# ─────────────────────────────────────────────────────────────────
# Timeline ordering
# ─────────────────────────────────────────────────────────────────


class TestTimelineOrdering:
    def test_messages_ordered_by_step(self) -> None:
        composed = compose_sequence_diagram(_three_lifeline_chain())
        messages = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ]
        # Filter to message lines (skip labels which are decorative text).
        lines = [o for o in messages if o["type"] == "line"]
        ys = [o["from"][1] for o in lines]
        assert ys == sorted(ys)


# ─────────────────────────────────────────────────────────────────
# Activation bars
# ─────────────────────────────────────────────────────────────────


class TestActivationBars:
    def test_sync_pair_emits_activation(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        bars = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.activations")[
            "objects"
        ]
        # Single sync/reply pair → one activation on Controller.
        assert len(bars) == 1
        assert bars[0]["type"] == "uml.activation_bar"

    def test_nested_sync_pairs_each_get_activation(self) -> None:
        composed = compose_sequence_diagram(_three_lifeline_chain())
        bars = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.activations")[
            "objects"
        ]
        # Two sync/reply pairs → two activation bars.
        assert len(bars) == 2

    def test_no_activation_layer_when_unused(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
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
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.activations" not in layer_ids


# ─────────────────────────────────────────────────────────────────
# Fragments
# ─────────────────────────────────────────────────────────────────


class TestFragments:
    def test_fragment_layer_emitted(self) -> None:
        composed = compose_sequence_diagram(_alt_fragment_diagram())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.fragments" in layer_ids

    def test_alt_fragment_has_dividers(self) -> None:
        composed = compose_sequence_diagram(_alt_fragment_diagram())
        frames = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.fragments")[
            "objects"
        ]
        assert len(frames) == 1
        f = frames[0]
        assert f["kind"] == "alt"
        assert f["operands"] == ["valid", "else"]
        # 2 operands → 1 divider between them
        assert len(f["dividers"]) == 1

    def test_opt_fragment_no_dividers(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [
                    {"id": "a", "name": "A"},
                    {"id": "b", "name": "B"},
                ],
                "messages": [{"id": "m1", "from": "a", "to": "b", "step": 1}],
                "fragments": [
                    {
                        "id": "f",
                        "kind": "opt",
                        "from_step": 1,
                        "to_step": 1,
                        "operands": ["logged_in"],
                    }
                ],
            }
        )
        composed = compose_sequence_diagram(m)
        frames = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.fragments")[
            "objects"
        ]
        # opt only has one operand band → no divider.
        assert "dividers" not in frames[0] or not frames[0]["dividers"]

    def test_no_fragment_layer_when_unused(self) -> None:
        composed = compose_sequence_diagram(_two_lifeline_call())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.fragments" not in layer_ids


# ─────────────────────────────────────────────────────────────────
# Create / destroy
# ─────────────────────────────────────────────────────────────────


class TestCreateDestroy:
    def test_created_lifeline_head_shifted_down(self) -> None:
        composed = compose_sequence_diagram(_create_destroy_diagram())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        boxes = {ll["id"]: ll["box"] for ll in lifelines}
        # Factory sits at the diagram top (y == margin); Product
        # is created at step 1, so its head sits below.
        assert boxes["p"][1] > boxes["f"][1]

    def test_destroyed_lifeline_terminated_early(self) -> None:
        composed = compose_sequence_diagram(_create_destroy_diagram())
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        boxes = {ll["id"]: ll["box"] for ll in lifelines}
        # Product's box height should be smaller than Factory's
        # because Product is destroyed at step 3.
        product_bottom = boxes["p"][1] + boxes["p"][3]
        factory_bottom = boxes["f"][1] + boxes["f"][3]
        assert product_bottom < factory_bottom

    def test_destroy_emits_x_glyph(self) -> None:
        composed = compose_sequence_diagram(_create_destroy_diagram())
        messages = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ]
        x_lines = [o for o in messages if "destroyX" in o.get("id", "")]
        assert len(x_lines) == 2  # two crossed lines forming the X


# ─────────────────────────────────────────────────────────────────
# Self-messages
# ─────────────────────────────────────────────────────────────────


class TestSelfMessage:
    def test_self_message_emits_polyline(self) -> None:
        composed = compose_sequence_diagram(_self_message_diagram())
        messages = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.messages")[
            "objects"
        ]
        loops = [o for o in messages if o["type"] == "polyline"]
        assert len(loops) == 1


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    def test_pinned_lifeline_x_honored(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [
                    {
                        "id": "a",
                        "name": "A",
                        "position": {"x": 555, "y": 0},
                    },
                    {"id": "b", "name": "B"},
                ]
            }
        )
        composed = compose_sequence_diagram(m)
        lifelines = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.lifelines")[
            "objects"
        ]
        a = next(ll for ll in lifelines if ll["id"] == "a")
        # cx of A should equal pinned x.
        cx_a = a["box"][0] + a["box"][2] / 2
        assert cx_a == 555


# ─────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────


class TestNotes:
    def test_notes_emit_separate_layer(self) -> None:
        m = validate_sequence_diagram(
            {
                "lifelines": [{"id": "a", "name": "A"}],
                "notes": [{"id": "n1", "text": "see ADR"}],
            }
        )
        composed = compose_sequence_diagram(m)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids


# ─────────────────────────────────────────────────────────────────
# Options surface
# ─────────────────────────────────────────────────────────────────


class TestOptions:
    def test_step_pitch_changes_message_y(self) -> None:
        m = _three_lifeline_chain()
        small = compose_sequence_diagram(m, options=SequenceDiagramOptions(step_pitch=40))
        large = compose_sequence_diagram(m, options=SequenceDiagramOptions(step_pitch=120))
        small_lines = [
            o
            for lyr in small.visual["layers"]
            if lyr["id"] == "uml.messages"
            for o in lyr["objects"]
            if o["type"] == "line"
        ]
        large_lines = [
            o
            for lyr in large.visual["layers"]
            if lyr["id"] == "uml.messages"
            for o in lyr["objects"]
            if o["type"] == "line"
        ]
        # The y of the last message under a larger step_pitch must
        # exceed that under a smaller step_pitch.
        small_last_y = max(o["from"][1] for o in small_lines)
        large_last_y = max(o["from"][1] for o in large_lines)
        assert large_last_y > small_last_y


# ─────────────────────────────────────────────────────────────────
# End-to-end render
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    def test_two_lifeline_renders(self) -> None:
        svg, _ = _render(_two_lifeline_call())
        assert svg.rstrip().endswith("</svg>")
        assert "User" in svg
        assert "click()" in svg

    def test_three_lifeline_renders(self) -> None:
        svg, _ = _render(_three_lifeline_chain())
        assert "Service" in svg
        assert "fetch()" in svg

    def test_alt_fragment_renders(self) -> None:
        svg, _ = _render(_alt_fragment_diagram())
        assert "alt" in svg
        assert "valid" in svg

    def test_create_destroy_renders(self) -> None:
        svg, _ = _render(_create_destroy_diagram())
        assert "Factory" in svg
        assert "Product" in svg

    def test_self_message_renders(self) -> None:
        svg, _ = _render(_self_message_diagram())
        assert "recurse()" in svg
