"""Regression tests for `framegraph.uml.compose_package_diagram` — Phase B.

Mirrors the structure of `test_uml_class_diagram_composer.py`. Three
test layers: schema-level (validate_package_diagram), composer
output structure, end-to-end render.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphRenderer
from framegraph._uml import (
    UMLPackageDiagramModel,
    validate_package_diagram,
)
from framegraph.uml import (
    PackageDiagramOptions,
    compose_package_diagram,
)

# ─────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────


class TestPackageDiagramSchema:
    """`validate_package_diagram` enforces the package-diagram metamodel."""

    def test_minimal_diagram_validates(self) -> None:
        m = validate_package_diagram({"packages": [{"id": "p", "name": "p"}]})
        assert len(m.packages) == 1
        assert m.dependencies == []

    def test_empty_packages_rejected(self) -> None:
        """A package diagram with no packages is meaningless."""
        with pytest.raises(ValidationError):
            validate_package_diagram({"packages": []})

    def test_missing_packages_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_package_diagram({})

    def test_self_dependency_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot depend on itself"):
            validate_package_diagram(
                {
                    "packages": [{"id": "p", "name": "p"}],
                    "dependencies": [{"id": "d", "from": "p", "to": "p"}],
                }
            )

    def test_duplicate_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate UML element id"):
            validate_package_diagram(
                {
                    "packages": [
                        {"id": "p", "name": "p1"},
                        {"id": "p", "name": "p2"},
                    ]
                }
            )

    def test_dependency_to_unknown_package_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown"):
            validate_package_diagram(
                {
                    "packages": [{"id": "a", "name": "a"}],
                    "dependencies": [{"id": "d", "from": "a", "to": "missing"}],
                }
            )

    def test_contains_unknown_package_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown package id"):
            validate_package_diagram(
                {
                    "packages": [
                        {"id": "a", "name": "a", "contains": ["missing"]},
                    ]
                }
            )

    def test_containment_cycle_rejected(self) -> None:
        with pytest.raises(ValidationError, match="containment cycle"):
            validate_package_diagram(
                {
                    "packages": [
                        {"id": "a", "name": "a", "contains": ["b"]},
                        {"id": "b", "name": "b", "contains": ["a"]},
                    ]
                }
            )

    def test_dependency_kind_enum_enforced(self) -> None:
        with pytest.raises(ValidationError):
            validate_package_diagram(
                {
                    "packages": [
                        {"id": "a", "name": "a"},
                        {"id": "b", "name": "b"},
                    ],
                    "dependencies": [{"id": "d", "from": "a", "to": "b", "kind": "weird"}],
                }
            )

    @pytest.mark.parametrize("kind", ["dependency", "import", "access", "merge"])
    def test_valid_dependency_kinds_accepted(self, kind: str) -> None:
        validate_package_diagram(
            {
                "packages": [
                    {"id": "a", "name": "a"},
                    {"id": "b", "name": "b"},
                ],
                "dependencies": [{"id": "d", "from": "a", "to": "b", "kind": kind}],
            }
        )


# ─────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────


def _two_package_chain() -> UMLPackageDiagramModel:
    """parent → child via containment."""
    return validate_package_diagram(
        {
            "packages": [
                {"id": "parent", "name": "parent", "contains": ["child"]},
                {"id": "child", "name": "child"},
            ]
        }
    )


def _full_vocabulary() -> UMLPackageDiagramModel:
    """Realistic 5-package model exercising every feature."""
    return validate_package_diagram(
        {
            "packages": [
                {"id": "app", "name": "app", "contains": ["app.ui", "app.core"]},
                {"id": "app.ui", "name": "ui"},
                {"id": "app.core", "name": "core", "contains": ["app.core.db"]},
                {"id": "app.core.db", "name": "db"},
                {"id": "common", "name": "common"},
            ],
            "dependencies": [
                {"id": "d1", "from": "app.ui", "to": "app.core", "kind": "import"},
                {"id": "d2", "from": "app.core", "to": "common"},
            ],
        }
    )


def _render(model: UMLPackageDiagramModel) -> tuple[str, FrameGraphRenderer]:
    composed = compose_package_diagram(model, canvas_size=(1280, 720))
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

    def test_minimum_two_layers_emitted(self) -> None:
        composed = compose_package_diagram(_two_package_chain())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        # `uml.edges` and `uml.classifiers` are always present;
        # `uml.notes` only when notes are declared.
        assert "uml.edges" in layer_ids
        assert "uml.classifiers" in layer_ids

    def test_one_node_object_per_package(self) -> None:
        composed = compose_package_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        assert len(nodes) == 5

    def test_node_objects_use_group_type(self) -> None:
        """Each package emits as a group (tab + body + name)."""
        composed = compose_package_diagram(_two_package_chain())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        for n in nodes:
            assert n["type"] == "group"

    def test_edge_count_includes_containment_and_dependencies(self) -> None:
        """Containment edges + dependency edges all show in uml.edges."""
        composed = compose_package_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        # 3 containments (app→ui, app→core, core→db) + 2 dependencies = 5
        assert len(edges) == 5


# ─────────────────────────────────────────────────────────────────
# Sugiyama integration
# ─────────────────────────────────────────────────────────────────


class TestSugiyamaIntegration:
    """Containment drives the y-axis hierarchy."""

    def test_parent_above_child(self) -> None:
        composed = compose_package_diagram(_two_package_chain())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["parent"][1] < boxes["child"][1]

    def test_grandparent_above_grandchild(self) -> None:
        composed = compose_package_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        # `app.core.db` (sanitized to `app_core_db`) is the deepest.
        # Verify it has the largest y of the app→core→db chain.
        app_y = boxes["app"][1]
        core_y = boxes["app_core"][1]
        db_y = boxes["app_core_db"][1]
        assert app_y < core_y < db_y

    def test_sibling_packages_share_layer(self) -> None:
        """app.ui and app.core both descend from app — same layer."""
        composed = compose_package_diagram(_full_vocabulary())
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["app_ui"][1] == boxes["app_core"][1]


# ─────────────────────────────────────────────────────────────────
# Edge styling
# ─────────────────────────────────────────────────────────────────


class TestEdgeStyling:
    """Containment vs dependency get the right strokes/arrows."""

    def test_containment_edge_has_no_arrow(self) -> None:
        composed = compose_package_diagram(_two_package_chain())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        contain = next(e for e in edges if e["id"].startswith("contains__"))
        assert "arrow_end_kind" not in contain["stroke"]
        assert "arrow_start_kind" not in contain["stroke"]
        assert "dash" not in contain["stroke"]

    def test_dependency_uses_open_arrow_dashed(self) -> None:
        composed = compose_package_diagram(_full_vocabulary())
        edges = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.edges")[
            "objects"
        ]
        dep = next(e for e in edges if e["id"] == "d1")
        assert dep["stroke"]["arrow_end_kind"] == "open_arrow"
        assert dep["stroke"]["dash"] == [5, 4]


# ─────────────────────────────────────────────────────────────────
# Position pinning
# ─────────────────────────────────────────────────────────────────


class TestPositionPinning:
    """`position` hints override Sugiyama coordinates per package."""

    def test_pinned_package_at_declared_position(self) -> None:
        model = validate_package_diagram(
            {
                "packages": [
                    {"id": "a", "name": "a", "position": {"x": 50, "y": 80}},
                    {"id": "b", "name": "b", "contains": []},
                ],
            }
        )
        composed = compose_package_diagram(model)
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["a"][0] == 50
        assert boxes["a"][1] == 80


# ─────────────────────────────────────────────────────────────────
# Manual layout
# ─────────────────────────────────────────────────────────────────


class TestManualLayout:
    """`layout='manual'` requires every package to have a position."""

    def test_manual_layout_with_all_positions(self) -> None:
        model = validate_package_diagram(
            {
                "packages": [
                    {"id": "a", "name": "a", "position": {"x": 50, "y": 50}},
                    {"id": "b", "name": "b", "position": {"x": 250, "y": 50}},
                ]
            }
        )
        composed = compose_package_diagram(model, options=PackageDiagramOptions(layout="manual"))
        nodes = next(lyr for lyr in composed.visual["layers"] if lyr["id"] == "uml.classifiers")[
            "objects"
        ]
        boxes = {n["id"]: n["box"] for n in nodes}
        assert boxes["a"][0] == 50
        assert boxes["b"][0] == 250

    def test_manual_layout_missing_position_raises(self) -> None:
        model = validate_package_diagram(
            {
                "packages": [
                    {"id": "a", "name": "a", "position": {"x": 0, "y": 0}},
                    {"id": "b", "name": "b"},
                ]
            }
        )
        with pytest.raises(ValueError, match="layout='manual' requires"):
            compose_package_diagram(model, options=PackageDiagramOptions(layout="manual"))


# ─────────────────────────────────────────────────────────────────
# Renderer integration
# ─────────────────────────────────────────────────────────────────


class TestEndToEndRender:
    """Composed output renders cleanly with no warnings."""

    def test_minimal_renders_clean(self) -> None:
        svg, r = _render(_two_package_chain())
        assert r.warnings == []
        assert "<svg" in svg

    def test_full_vocabulary_renders_clean(self) -> None:
        """Crucial: dotted ids (app.core.db) used to trigger dot-notation
        endpoint resolution and produce per-edge skipped warnings.
        """
        svg, r = _render(_full_vocabulary())
        assert r.warnings == [], f"unexpected warnings: {r.warnings}"

    def test_package_names_in_svg(self) -> None:
        svg, _ = _render(_full_vocabulary())
        for name in ("app", "ui", "core", "db", "common"):
            assert f">{name}<" in svg, f"package name {name!r} missing"

    def test_open_arrow_marker_emitted_for_dependencies(self) -> None:
        svg, _ = _render(_full_vocabulary())
        assert "open_arrow" in svg


# ─────────────────────────────────────────────────────────────────
# Notes layer
# ─────────────────────────────────────────────────────────────────


class TestNotes:
    """`notes` declarations emit a third layer with rect+text fallbacks."""

    def test_notes_layer_emitted_when_notes_present(self) -> None:
        model = validate_package_diagram(
            {
                "packages": [{"id": "a", "name": "a"}],
                "notes": [{"id": "n", "text": "hello", "position": {"x": 100, "y": 200}}],
            }
        )
        composed = compose_package_diagram(model)
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" in layer_ids

    def test_notes_layer_omitted_when_no_notes(self) -> None:
        composed = compose_package_diagram(_two_package_chain())
        layer_ids = [lyr["id"] for lyr in composed.visual["layers"]]
        assert "uml.notes" not in layer_ids


# ─────────────────────────────────────────────────────────────────
# Diagnostics
# ─────────────────────────────────────────────────────────────────


class TestDiagnostics:
    """The ComposedDiagram exposes useful side-channel data."""

    def test_layout_result_present_for_sugiyama(self) -> None:
        composed = compose_package_diagram(_full_vocabulary())
        assert composed.layout_result is not None
        assert composed.layout_result.crossings == 0

    def test_node_dimensions_filled(self) -> None:
        composed = compose_package_diagram(_full_vocabulary())
        # 5 packages → 5 entries
        assert len(composed.node_dimensions) == 5
        for w, h in composed.node_dimensions.values():
            assert w > 0
            assert h > 0
