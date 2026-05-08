"""Regression tests for `framegraph.uml.compose_class_diagram` — Phase A.3.

End-to-end tests: typed UML model → composer → renderer → SVG.
Schema-level tests live in `test_uml_schema.py`; render-level tests
for the `uml.classifier_box` primitive live in
`test_uml_classifier_box.py`. This file covers the composer's
behaviour: layout-graph extraction, Sugiyama integration, position
pinning, and visual emission.

Test bar: schema + render structural assertions. No byte-identity
hashes — the composer's output is allowed to evolve as later phases
refine the layout. We assert structural properties: object counts,
edge id presence, marker registration, no warnings.
"""

from __future__ import annotations

import pytest

from framegraph import FrameGraphRenderer
from framegraph._uml import UMLClassDiagramModel, validate_class_diagram
from framegraph.uml import ClassDiagramOptions, compose_class_diagram

# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_class_inheritance() -> UMLClassDiagramModel:
    """Minimal model: parent + child + 1 generalization."""
    return validate_class_diagram(
        {
            "classes": [
                {"id": "Parent", "name": "Parent"},
                {"id": "Child", "name": "Child"},
            ],
            "generalizations": [{"id": "g", "from": "Child", "to": "Parent"}],
        }
    )


def _diamond_inheritance() -> UMLClassDiagramModel:
    """Multi-inheritance diamond: A, B both extend Top; C extends A and B."""
    return validate_class_diagram(
        {
            "classes": [
                {"id": "Top", "name": "Top"},
                {"id": "A", "name": "A"},
                {"id": "B", "name": "B"},
                {"id": "C", "name": "C"},
            ],
            "generalizations": [
                {"id": "g1", "from": "A", "to": "Top"},
                {"id": "g2", "from": "B", "to": "Top"},
                {"id": "g3", "from": "C", "to": "A"},
                {"id": "g4", "from": "C", "to": "B"},
            ],
        }
    )


def _full_vocabulary_model() -> UMLClassDiagramModel:
    """Realistic model exercising every edge kind."""
    return validate_class_diagram(
        {
            "classes": [
                {
                    "id": "Animal",
                    "name": "Animal",
                    "abstract": True,
                    "attributes": [{"name": "name", "type": "String"}],
                    "operations": [{"name": "speak", "abstract": True}],
                },
                {"id": "Dog", "name": "Dog"},
                {"id": "Owner", "name": "Owner"},
            ],
            "interfaces": [
                {"id": "Trainable", "name": "Trainable", "operations": [{"name": "train"}]}
            ],
            "enumerations": [{"id": "Mood", "name": "Mood", "literals": ["HAPPY", "GRUMPY"]}],
            "generalizations": [{"id": "g", "from": "Dog", "to": "Animal"}],
            "realizations": [{"id": "r", "from": "Dog", "to": "Trainable"}],
            "associations": [
                {
                    "id": "a",
                    "end1": {"id_ref": "Owner"},
                    "end2": {"id_ref": "Dog"},
                    "kind": "aggregation",
                }
            ],
            "dependencies": [{"id": "d", "from": "Animal", "to": "Mood"}],
        }
    )


def _render(model: UMLClassDiagramModel) -> tuple[str, FrameGraphRenderer]:
    """Compose + render; return (svg, renderer) for assertions."""
    composed = compose_class_diagram(model, canvas_size=(1280, 720))
    doc = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [1280, 720]}},
        "visual": composed.visual,
    }
    r = FrameGraphRenderer(doc)
    svg = r.render_svg()
    return svg, r


# ─────────────────────────────────────────────────────────────────
# Composer output structure
# ─────────────────────────────────────────────────────────────────


class TestComposedDiagramStructure:
    """The visual block has the expected layer/object structure."""

    def test_three_layers_emitted(self) -> None:
        """Edges, classifiers, notes — three z-ordered layers."""
        composed = compose_class_diagram(_two_class_inheritance())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert layer_ids == ["uml.edges", "uml.classifiers", "uml.notes"]

    def test_classifier_layer_has_one_object_per_classifier(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        classifier_layer = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )
        # 3 classes + 1 interface + 1 enumeration = 5
        assert len(classifier_layer["objects"]) == 5

    def test_edges_layer_has_one_object_per_edge(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        edges_layer = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")
        # 1 generalization + 1 realization + 1 association + 1 dependency = 4
        assert len(edges_layer["objects"]) == 4

    def test_classifier_objects_use_uml_classifier_box_type(self) -> None:
        composed = compose_class_diagram(_two_class_inheritance())
        classifier_layer = next(
            lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers"
        )
        for obj in classifier_layer["objects"]:
            assert obj["type"] == "uml.classifier_box"

    def test_edge_objects_use_connector_type(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        edges_layer = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")
        for obj in edges_layer["objects"]:
            assert obj["type"] == "connector"


# ─────────────────────────────────────────────────────────────────
# Sugiyama integration
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaIntegration:
    """Auto-layout puts parent above child, places diamond patterns."""

    def test_two_class_inheritance_parent_above_child(self) -> None:
        """In hierarchical layout, generalization parent gets a smaller y."""
        composed = compose_class_diagram(_two_class_inheritance())
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        parent_y = boxes["Parent"][1]
        child_y = boxes["Child"][1]
        assert parent_y < child_y, "parent should sit above child in y"

    def test_diamond_inheritance_three_layers(self) -> None:
        """Top, {A, B}, C → three Sugiyama layers."""
        composed = compose_class_diagram(_diamond_inheritance())
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        # Top in layer 0, A and B in layer 1, C in layer 2
        ys = sorted({box[1] for box in boxes.values()})
        assert len(ys) == 3, f"expected 3 distinct y-layers, got {ys}"
        # Top has the smallest y (top of diagram); C has the largest
        assert boxes["Top"][1] == ys[0]
        assert boxes["C"][1] == ys[2]

    def test_layout_result_records_zero_crossings_for_dag(self) -> None:
        """A clean tree should produce 0 crossings."""
        composed = compose_class_diagram(_two_class_inheritance())
        assert composed.layout_result is not None
        assert composed.layout_result.crossings == 0

    def test_layout_left_edge_does_not_clip_canvas(self) -> None:
        """The leftmost classifier's left edge must be ≥ 0 (no negative x)."""
        composed = compose_class_diagram(_full_vocabulary_model())
        boxes = [obj["box"] for obj in composed.visual["layers"][1]["objects"]]
        min_x = min(box[0] for box in boxes)
        assert min_x >= 0, f"leftmost x={min_x} clips off-canvas"


# ─────────────────────────────────────────────────────────────────
# Position pinning (Decision 2 escape hatch)
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    """Classifiers with `position` hints override Sugiyama coordinates."""

    def test_pinned_classifier_lands_at_declared_position(self) -> None:
        model = validate_class_diagram(
            {
                "classes": [
                    {"id": "A", "name": "A", "position": {"x": 100, "y": 50}},
                    {"id": "B", "name": "B"},
                ],
                "generalizations": [{"id": "g", "from": "B", "to": "A"}],
            }
        )
        composed = compose_class_diagram(model)
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        # A pinned at (100, 50) — its top-left should be exactly there.
        assert boxes["A"][0] == 100
        assert boxes["A"][1] == 50

    def test_unpinned_classifier_uses_sugiyama_position(self) -> None:
        """Pinning A doesn't pin B; B's position comes from Sugiyama."""
        model = validate_class_diagram(
            {
                "classes": [
                    {"id": "A", "name": "A", "position": {"x": 100, "y": 50}},
                    {"id": "B", "name": "B"},
                ],
                "generalizations": [{"id": "g", "from": "B", "to": "A"}],
            }
        )
        composed = compose_class_diagram(model)
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        # B is auto-laid-out
        assert boxes["B"] is not None
        # B should be placed at a different y than A (it's a child)
        assert boxes["B"][1] != boxes["A"][1]


# ─────────────────────────────────────────────────────────────────
# Manual layout
# ─────────────────────────────────────────────────────────────────


class TestManualLayout:
    """`layout: manual` requires every classifier to have a position."""

    def test_manual_layout_with_all_positions(self) -> None:
        model = validate_class_diagram(
            {
                "classes": [
                    {"id": "A", "name": "A", "position": {"x": 100, "y": 50}},
                    {"id": "B", "name": "B", "position": {"x": 300, "y": 50}},
                ],
            }
        )
        composed = compose_class_diagram(model, options=ClassDiagramOptions(layout="manual"))
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        assert boxes["A"][0] == 100
        assert boxes["B"][0] == 300

    def test_manual_layout_missing_position_raises(self) -> None:
        model = validate_class_diagram(
            {
                "classes": [
                    {"id": "A", "name": "A", "position": {"x": 0, "y": 0}},
                    {"id": "B", "name": "B"},  # no position
                ],
            }
        )
        with pytest.raises(ValueError, match="layout='manual' requires"):
            compose_class_diagram(model, options=ClassDiagramOptions(layout="manual"))

    def test_unknown_layout_raises(self) -> None:
        model = _two_class_inheritance()
        with pytest.raises(ValueError, match="unknown layout strategy"):
            compose_class_diagram(model, options=ClassDiagramOptions(layout="weird"))


# ─────────────────────────────────────────────────────────────────
# Edge arrowheads
# ─────────────────────────────────────────────────────────────────


class TestEdgeArrowheads:
    """Each UML edge type maps to the right arrowhead variant."""

    def test_generalization_uses_hollow_triangle(self) -> None:
        composed = compose_class_diagram(_two_class_inheritance())
        edges = composed.visual["layers"][0]["objects"]
        gen = next(e for e in edges if e["id"] == "g")
        assert gen["stroke"]["arrow_end_kind"] == "hollow_triangle"
        assert "dash" not in gen["stroke"]

    def test_realization_uses_hollow_triangle_dashed(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        edges = composed.visual["layers"][0]["objects"]
        real = next(e for e in edges if e["id"] == "r")
        assert real["stroke"]["arrow_end_kind"] == "hollow_triangle"
        assert real["stroke"]["dash"] == [5, 4]

    def test_aggregation_uses_hollow_diamond_at_whole_end(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        edges = composed.visual["layers"][0]["objects"]
        agg = next(e for e in edges if e["id"] == "a")
        # `kind: aggregation` on the model puts the diamond at the WHOLE
        # end (end1 by convention). Composer emits this as `arrow_start`.
        assert agg["stroke"]["arrow_start_kind"] == "hollow_diamond"

    def test_composition_uses_filled_diamond(self) -> None:
        model = validate_class_diagram(
            {
                "classes": [{"id": "X", "name": "X"}, {"id": "Y", "name": "Y"}],
                "associations": [
                    {
                        "id": "a",
                        "end1": {"id_ref": "X"},
                        "end2": {"id_ref": "Y"},
                        "kind": "composition",
                    }
                ],
            }
        )
        composed = compose_class_diagram(model)
        edges = composed.visual["layers"][0]["objects"]
        comp = next(e for e in edges if e["id"] == "a")
        assert comp["stroke"]["arrow_start_kind"] == "filled_diamond"

    def test_dependency_uses_open_arrow_dashed(self) -> None:
        composed = compose_class_diagram(_full_vocabulary_model())
        edges = composed.visual["layers"][0]["objects"]
        dep = next(e for e in edges if e["id"] == "d")
        assert dep["stroke"]["arrow_end_kind"] == "open_arrow"
        assert dep["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# End-to-end render — composer output reaches the renderer cleanly
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    """The composed visual block renders without warnings."""

    def test_two_class_renders_clean(self) -> None:
        svg, r = _render(_two_class_inheritance())
        assert r.warnings == []
        assert "<svg" in svg

    def test_full_vocabulary_renders_clean(self) -> None:
        svg, r = _render(_full_vocabulary_model())
        assert r.warnings == [], f"unexpected warnings: {r.warnings}"

    def test_diamond_renders_clean(self) -> None:
        svg, r = _render(_diamond_inheritance())
        assert r.warnings == []

    def test_classifier_names_present_in_svg(self) -> None:
        svg, _ = _render(_full_vocabulary_model())
        for name in ("Animal", "Dog", "Owner", "Trainable", "Mood"):
            assert f">{name}<" in svg, f"classifier {name!r} missing from SVG"

    def test_uml_arrowhead_markers_emitted(self) -> None:
        """`defs_svg` should emit the new marker shapes for the edges used."""
        svg, _ = _render(_full_vocabulary_model())
        # The full model uses generalization (hollow_triangle), realization
        # (hollow_triangle, dashed), aggregation (hollow_diamond),
        # dependency (open_arrow).
        assert "hollow_triangle" in svg
        assert "hollow_diamond" in svg
        assert "open_arrow" in svg


# ─────────────────────────────────────────────────────────────────
# Classifier sizing
# ─────────────────────────────────────────────────────────────────


class TestClassifierSizing:
    """Width/height respect the longest member signature."""

    def test_node_min_width_respected(self) -> None:
        """A class with no members still gets at least the minimum width."""
        model = validate_class_diagram({"classes": [{"id": "X", "name": "X"}]})
        composed = compose_class_diagram(model)
        box = composed.visual["layers"][1]["objects"][0]["box"]
        opts = ClassDiagramOptions()
        assert box[2] >= opts.node_min_width

    def test_long_member_widens_box(self) -> None:
        """A class with a long operation signature gets a wider box."""
        model = validate_class_diagram(
            {
                "classes": [
                    {
                        "id": "X",
                        "name": "X",
                        "operations": [
                            {
                                "name": "very_long_method_name_that_should_widen_the_box",
                                "parameters": [
                                    {"name": "argument_one", "type": "VeryLongTypeName"},
                                    {"name": "argument_two", "type": "AnotherLongTypeName"},
                                ],
                                "return_type": "ResultType",
                            }
                        ],
                    }
                ]
            }
        )
        composed = compose_class_diagram(model)
        box = composed.visual["layers"][1]["objects"][0]["box"]
        opts = ClassDiagramOptions()
        assert box[2] > opts.node_min_width

    def test_node_dimensions_returned_as_diagnostic(self) -> None:
        composed = compose_class_diagram(_two_class_inheritance())
        assert "Parent" in composed.node_dimensions
        assert "Child" in composed.node_dimensions
        for w, h in composed.node_dimensions.values():
            assert w > 0
            assert h > 0


# ─────────────────────────────────────────────────────────────────
# Node semantics — interface stereotype, enumeration literals
# ─────────────────────────────────────────────────────────────────


class TestNodeSemantics:
    """Interfaces and enumerations get the right stereotype labels."""

    def test_interface_gets_interface_stereotype(self) -> None:
        composed = compose_class_diagram(
            validate_class_diagram({"interfaces": [{"id": "I", "name": "I"}]})
        )
        iface_obj = composed.visual["layers"][1]["objects"][0]
        assert iface_obj["stereotype"] == "interface"

    def test_enumeration_gets_enumeration_stereotype(self) -> None:
        composed = compose_class_diagram(
            validate_class_diagram(
                {"enumerations": [{"id": "E", "name": "E", "literals": ["A", "B"]}]}
            )
        )
        enum_obj = composed.visual["layers"][1]["objects"][0]
        assert enum_obj["stereotype"] == "enumeration"

    def test_enumeration_literals_render_as_attribute_lines(self) -> None:
        composed = compose_class_diagram(
            validate_class_diagram(
                {"enumerations": [{"id": "E", "name": "E", "literals": ["RED", "GREEN", "BLUE"]}]}
            )
        )
        enum_obj = composed.visual["layers"][1]["objects"][0]
        attr_names = [a["name"] for a in enum_obj["attributes"]]
        assert attr_names == ["RED", "GREEN", "BLUE"]


# ─────────────────────────────────────────────────────────────────
# Cycle handling — defensive belt-and-suspenders only
# ─────────────────────────────────────────────────────────────────
#
# UML 2.5.1 Classifier::no_cycles_in_generalization forbids
# generalization cycles at the metamodel level. The schema validator
# in `framegraph._uml` enforces this, so the composer never sees a
# cyclic generalization graph from validated input. Sugiyama's
# stage-1 cycle removal is exercised in `test_sugiyama.py` directly.
#
# What IS legal at the metamodel level: realization edges that form
# cycles (rare but not forbidden). The composer feeds those to
# Sugiyama too; this section verifies the composer doesn't crash on
# them.


class TestCycleHandling:
    """Realization cycles (legal per UML) reach Sugiyama and lay out cleanly."""

    def test_realization_path_does_not_cycle_check(self) -> None:
        """Realizations can form chains the composer feeds to Sugiyama unchanged.

        The schema only forbids generalization cycles. A class
        realizing an interface that depends on it (a realization +
        dependency cycle, NOT a generalization cycle) is legal and
        the composer must compose it.
        """
        model = validate_class_diagram(
            {
                "classes": [{"id": "C", "name": "C"}],
                "interfaces": [{"id": "I", "name": "I"}],
                "realizations": [{"id": "r", "from": "C", "to": "I"}],
                "dependencies": [{"id": "d", "from": "I", "to": "C"}],
            }
        )
        composed = compose_class_diagram(model)
        boxes = {obj["id"]: obj["box"] for obj in composed.visual["layers"][1]["objects"]}
        assert {"C", "I"} <= set(boxes.keys())
        # The realization edge is in the layout graph; the dependency
        # is a non-layout edge that routes between resolved positions.
        edges = composed.visual["layers"][0]["objects"]
        assert any(e["id"] == "r" for e in edges)
        assert any(e["id"] == "d" for e in edges)
