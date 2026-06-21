"""Regression tests for `uml.classifier_box` — Phase A.2 of UML support.

Test bar: schema + render coverage per the test-bar policy
established in `test_layout_features.py`. No byte-identity hashes
(the visual output is allowed to evolve as Phase A.3's composer
work surfaces tweaks). Structural assertions only.
"""

from __future__ import annotations

import re
from typing import Any

from framegraph import FrameGraphRenderer
from framegraph._schema import validate_document, validate_object
from framegraph.renderers.uml import _format_attribute, _format_operation


def _doc_with_classifier(obj: dict[str, Any]) -> dict[str, Any]:
    """Wrap a single classifier_box object in a minimal valid Document."""
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [800, 600]}},
        "visual": {
            "layers": [{"id": "main", "z": 0, "objects": [obj]}],
        },
    }


# ─────────────────────────────────────────────────────────────────
# Schema integration
# ─────────────────────────────────────────────────────────────────


class TestClassifierBoxSchema:
    """`uml.classifier_box` registers in the discriminated union."""

    def test_minimal_classifier_box_validates(self) -> None:
        obj = validate_object(
            {
                "type": "uml.classifier_box",
                "id": "C",
                "box": [0, 0, 200, 100],
                "name": "MyClass",
            }
        )
        assert obj.type == "uml.classifier_box"
        assert obj.name == "MyClass"

    def test_classifier_with_attributes_and_operations_validates(self) -> None:
        obj = validate_object(
            {
                "type": "uml.classifier_box",
                "id": "C",
                "box": [0, 0, 200, 100],
                "name": "C",
                "attributes": [{"name": "x", "type": "int"}],
                "operations": [{"name": "f", "return_type": "void"}],
            }
        )
        assert len(obj.attributes) == 1
        assert len(obj.operations) == 1

    def test_missing_name_falls_through_to_unknown_object(self) -> None:
        """When required `name` is missing, discriminated-union resolution
        falls through to `_UnknownObject` — the same plug-in fall-through
        behavior used for third-party `register(type_name, fn)` types.

        This means malformed `uml.classifier_box` documents render as
        unknown-type comments at paint time rather than failing at
        ingest. That's a known limitation of the current discriminated-
        union behavior; tightening it for *known* types is a follow-up
        on the schema design (would require either custom validators on
        `_UnknownObject` or a separate post-resolution check). Phase A.2
        documents this; Phase A.3 (the composer) avoids it by always
        constructing well-formed objects.
        """
        # The validator does NOT raise; the result is an _UnknownObject.
        obj = validate_object(
            {
                "type": "uml.classifier_box",
                "id": "C",
                "box": [0, 0, 200, 100],
            }
        )
        assert obj.type == "uml.classifier_box"
        # The render path will emit "<!-- unsupported object type … -->"
        # downstream because the renderer dispatch keys on the typed
        # `UMLClassifierBoxObject` constructor, not on the unknown
        # fallback. Smoke that:
        from framegraph import FrameGraphRenderer

        doc = _doc_with_classifier(
            {
                "type": "uml.classifier_box",
                "id": "C",
                "box": [0, 0, 200, 100],
                # name omitted — exercises the unknown-fallback path
            }
        )
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        # The renderer's per-object try/except wraps errors as comments.
        # Since the dispatch DOES find `uml.classifier_box`, the call
        # succeeds with empty-string name — that is, the renderer is
        # forgiving where the schema is. Document that.
        assert "<text" in svg or "<!--" in svg

    def test_inside_layer_validates_through_discriminator(self) -> None:
        """Validates as a Document so the discriminated-union path runs."""
        validate_document(
            _doc_with_classifier(
                {
                    "type": "uml.classifier_box",
                    "id": "C",
                    "box": [0, 0, 200, 100],
                    "name": "C",
                }
            )
        )


# ─────────────────────────────────────────────────────────────────
# Helpers — _format_attribute / _format_operation
# ─────────────────────────────────────────────────────────────────


class TestAttributeFormatting:
    """`_format_attribute` produces the UML §9.5.4 signature string."""

    def test_minimal_attribute(self) -> None:
        s = _format_attribute({"name": "x"})
        assert s == "+ x"  # public default

    def test_typed_attribute(self) -> None:
        s = _format_attribute({"name": "balance", "type": "Money", "visibility": "private"})
        assert s == "- balance: Money"

    def test_multiplicity_appended_after_type(self) -> None:
        s = _format_attribute(
            {"name": "items", "type": "Order", "multiplicity": "0..*", "visibility": "public"}
        )
        assert s == "+ items: Order[0..*]"

    def test_multiplicity_without_type(self) -> None:
        """Multiplicity may appear even without a declared type."""
        s = _format_attribute({"name": "tags", "multiplicity": "1..*"})
        assert "[1..*]" in s

    def test_default_value_appended(self) -> None:
        s = _format_attribute({"name": "limit", "type": "int", "default": "100"})
        assert s == "+ limit: int = 100"

    def test_derived_attribute_gets_slash_prefix(self) -> None:
        s = _format_attribute({"name": "age", "type": "int", "derived": True})
        assert "/age" in s

    def test_readonly_constraint_emitted(self) -> None:
        s = _format_attribute({"name": "id", "type": "UUID", "readonly": True})
        assert "{readOnly}" in s

    def test_protected_visibility_prefix(self) -> None:
        s = _format_attribute({"name": "x", "visibility": "protected"})
        assert s.startswith("# ")

    def test_package_visibility_prefix(self) -> None:
        s = _format_attribute({"name": "x", "visibility": "package"})
        assert s.startswith("~ ")


class TestOperationFormatting:
    """`_format_operation` produces the UML §9.6.4 signature string."""

    def test_no_param_no_return(self) -> None:
        s = _format_operation({"name": "ping"})
        assert s == "+ ping()"

    def test_simple_signature(self) -> None:
        s = _format_operation(
            {
                "name": "deposit",
                "parameters": [{"name": "amount", "type": "Money"}],
                "return_type": "boolean",
            }
        )
        assert s == "+ deposit(amount: Money): boolean"

    def test_multiple_parameters_comma_separated(self) -> None:
        s = _format_operation(
            {
                "name": "transfer",
                "parameters": [
                    {"name": "from", "type": "Account"},
                    {"name": "to", "type": "Account"},
                    {"name": "amount", "type": "Money"},
                ],
            }
        )
        assert "from: Account" in s
        assert "to: Account" in s
        assert s.count(",") == 2

    def test_return_direction_parameter_consumed_into_return_type(self) -> None:
        """A `direction: return` parameter becomes the return type when no return_type is set."""
        s = _format_operation(
            {
                "name": "compute",
                "parameters": [
                    {"name": "result", "direction": "return", "type": "Money"},
                ],
            }
        )
        assert s == "+ compute(): Money"

    def test_explicit_return_type_overrides_return_param(self) -> None:
        """When both return_type and a direction:return param are set, return_type wins."""
        s = _format_operation(
            {
                "name": "compute",
                "return_type": "int",
                "parameters": [
                    {"name": "r", "direction": "return", "type": "Money"},
                ],
            }
        )
        assert s.endswith("): int")

    def test_out_direction_prefix(self) -> None:
        """Non-`in` parameter directions render as a prefix per UML 2.5 §9.6.4."""
        s = _format_operation(
            {
                "name": "fetch",
                "parameters": [{"name": "result", "direction": "out", "type": "Data"}],
            }
        )
        assert "out result" in s

    def test_query_constraint_emitted(self) -> None:
        s = _format_operation({"name": "size", "return_type": "int", "query": True})
        assert "{query}" in s

    def test_protected_visibility_prefix(self) -> None:
        s = _format_operation({"name": "f", "visibility": "protected"})
        assert s.startswith("# ")

    def test_param_default_value(self) -> None:
        s = _format_operation(
            {
                "name": "f",
                "parameters": [{"name": "x", "type": "int", "default": "0"}],
            }
        )
        assert "x: int = 0" in s


# ─────────────────────────────────────────────────────────────────
# Render-time behaviour
# ─────────────────────────────────────────────────────────────────


class TestClassifierBoxRender:
    """End-to-end rendering of `uml.classifier_box` to SVG."""

    def _render(self, obj_overrides: dict[str, Any]) -> str:
        base: dict[str, Any] = {
            "type": "uml.classifier_box",
            "id": "C",
            "box": [0, 0, 240, 120],
            "name": "MyClass",
        }
        base.update(obj_overrides)
        doc = _doc_with_classifier(base)
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        assert r.warnings == [], f"render produced warnings: {r.warnings}"
        return svg

    def test_minimal_class_renders_one_text_element_for_name(self) -> None:
        svg = self._render({})
        # Header has one text element (the name)
        text_count = len(re.findall(r"<text[^>]*>[^<]*</text>", svg))
        assert text_count == 1

    def test_stereotype_emitted_with_guillemets(self) -> None:
        svg = self._render({"stereotype": "interface"})
        assert "«interface»" in svg

    def test_abstract_class_name_renders_italic(self) -> None:
        svg = self._render({"abstract": True})
        # The name is the only italic text in a no-attribute, no-operation class
        assert 'font-style="italic"' in svg

    def test_attribute_compartment_emits_one_text_per_attribute(self) -> None:
        svg = self._render(
            {
                "attributes": [
                    {"name": "x", "type": "int"},
                    {"name": "y", "type": "int"},
                ]
            }
        )
        # Header (1) + 2 attributes = 3
        text_count = len(re.findall(r"<text[^>]*>[^<]*</text>", svg))
        assert text_count == 3

    def test_operation_compartment_emits_one_text_per_operation(self) -> None:
        svg = self._render(
            {
                "operations": [
                    {"name": "f"},
                    {"name": "g"},
                    {"name": "h"},
                ]
            }
        )
        text_count = len(re.findall(r"<text[^>]*>[^<]*</text>", svg))
        # Header (1) + 3 operations = 4
        assert text_count == 4

    def test_static_member_gets_underline(self) -> None:
        svg = self._render(
            {
                "attributes": [{"name": "instances", "static": True, "type": "List"}],
            }
        )
        assert 'text-decoration="underline"' in svg

    def test_abstract_member_gets_italic(self) -> None:
        svg = self._render(
            {
                "operations": [{"name": "render", "abstract": True}],
            }
        )
        # Two italic things possible: name (only when class abstract) and operation.
        # Class is not abstract here, so the only italic must be the abstract operation.
        assert 'font-style="italic"' in svg

    def test_visibility_prefixes_in_output(self) -> None:
        svg = self._render(
            {
                "attributes": [
                    {"name": "a", "visibility": "public"},
                    {"name": "b", "visibility": "private"},
                    {"name": "c", "visibility": "protected"},
                    {"name": "d", "visibility": "package"},
                ],
            }
        )
        assert "+ a" in svg
        assert "- b" in svg
        assert "# c" in svg
        assert "~ d" in svg

    def test_horizontal_rules_between_compartments(self) -> None:
        """Two horizontal lines: name/attrs separator + attrs/ops separator."""
        svg = self._render(
            {
                "attributes": [{"name": "a"}],
                "operations": [{"name": "f"}],
            }
        )
        # Find <line> elements with the same y for x1/x2 (i.e., horizontal)
        # Easier: count lines emitted; should be exactly 2 (the separators).
        lines = re.findall(r"<line[^/]+/>", svg)
        assert len(lines) == 2

    def test_outer_frame_emitted(self) -> None:
        """A no-fill bordered rect wraps the whole shape."""
        svg = self._render({})
        # The outer frame is the only no-fill rect with a stroke
        assert re.search(r'<rect [^/]*fill="none"[^/]*stroke=', svg) is not None

    def test_compressed_box_with_attributes_does_not_cut_through_text(self) -> None:
        """When the explicit height is too small to hold both compartments
        plus the attribute text, the inner separator must NOT land on
        top of an attribute row. The compressor honours the actual
        text extent first; the now-empty operation band is suppressed
        per UML 2.5.1 §9.5.4 (compartments may be omitted)."""
        svg = self._render(
            {
                "stereotype": "component",
                "box": [0, 0, 380, 80],
                "attributes": [{"name": "field_a"}, {"name": "field_b"}],
            }
        )
        # Capture the y baseline of every drawn attribute row.
        attr_ys = [
            float(m.group(1)) for m in re.finditer(r'<text x="8" y="([0-9.]+)"[^>]*>\+ field_', svg)
        ]
        assert len(attr_ys) == 2, "both attribute rows must be emitted"
        # Every horizontal separator <line> must clear the bottom of
        # the lowest attribute row (text baseline + small descender).
        for m in re.finditer(r'<line[^>]*y1="([0-9.]+)"', svg):
            ly = float(m.group(1))
            for ay in attr_ys:
                # Allow up to 4px below the baseline for descenders;
                # the separator must land outside that band.
                assert not (ay - 12 < ly < ay + 4), (
                    f"separator at y={ly} cuts through attribute row baseline y={ay}"
                )

    def test_compressed_box_keeps_inner_separator_inside_frame(self) -> None:
        """When the composer supplies an explicit height smaller than the
        natural sum of compartments, the renderer must compress the
        attribute and operation compartments rather than letting the
        inner separator overshoot below the outer frame.

        Reproduction: a small `«component»` box (h=44) with no
        attributes and no operations was rendering its second separator
        line at y_box + 55 instead of y_box + 44, leaving a hairline
        hanging below the box.
        """
        svg = self._render(
            {
                "stereotype": "component",
                "box": [10, 20, 240, 44],
            }
        )
        outer_bottom = 20 + 44
        # All horizontal separator <line>s emitted by the renderer must
        # have y1 ≤ outer_bottom; the outer frame is the only geometry
        # that touches that edge.
        for m in re.finditer(r'<line[^>]*y1="([0-9.]+)"', svg):
            y = float(m.group(1))
            assert y <= outer_bottom + 0.5, (
                f"separator line at y={y} overshoots the outer frame bottom (y={outer_bottom})"
            )

    def test_box_height_zero_auto_computes_total(self) -> None:
        """When height=0, the renderer computes total from compartment counts."""
        svg = self._render(
            {
                "box": [0, 0, 200, 0],
                "attributes": [{"name": "a"}, {"name": "b"}],
            }
        )
        # The outer frame's height should reflect the auto-computed total
        m = re.search(
            r'<rect x="0" y="0" width="200" height="([0-9.]+)" fill="none" stroke=',
            svg,
        )
        assert m is not None
        height = float(m.group(1))
        # Header (28) + attrs (2*19+8=46 minimum) + ops (19+8=27 minimum)
        # Don't pin exact pixel value; just assert it's > the minimum reasonable.
        assert height > 28 + 19 + 19


class TestArtifactStereotypeOverlay:
    """`stereotype: "artifact"` on a classifier_box must overlay the
    UML 2.5.1 §A.4 folded-document icon in the upper-right corner.
    Decks that previously rendered «artifact» as just a text label
    now get the proper glyph automatically."""

    def _render_artifact(self, **overrides: Any) -> str:
        base: dict[str, Any] = {
            "type": "uml.classifier_box",
            "id": "A",
            "box": [0, 0, 200, 80],
            "name": "MyArtifact",
            "stereotype": "artifact",
        }
        base.update(overrides)
        doc = _doc_with_classifier(base)
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        assert r.warnings == []
        return svg

    def test_artifact_emits_folded_document_polygon(self) -> None:
        svg = self._render_artifact()
        # The icon polygon has 5 points (rect with the upper-right
        # corner cut). Search inside the artifact's <g>.
        m = re.search(
            r'<g id="A"[^>]*>(.*?)</g>',
            svg,
            re.DOTALL,
        )
        assert m
        body = m.group(1)
        polygons = re.findall(r"<polygon points=\"([^\"]+)\"", body)
        assert polygons, "no polygon emitted for «artifact» icon"
        # Pick the polygon with exactly 5 vertices (the icon).
        five_pt = [p for p in polygons if len(p.split()) == 5]
        assert five_pt, "no 5-vertex icon polygon found"

    def test_artifact_icon_sits_in_upper_right(self) -> None:
        svg = self._render_artifact(box=[10, 20, 200, 80])
        m = re.search(
            r'<g id="A"[^>]*>.*?<polygon points="([0-9.,\- ]+)"',
            svg,
            re.DOTALL,
        )
        # First polygon in the box is the artifact icon. Its first
        # vertex should be near the upper-right corner of the box
        # (right=210, top=20). The icon has padding so x≈190, y≈26.
        assert m
        first_pt = m.group(1).split()[0]
        ix, iy = (float(v) for v in first_pt.split(","))
        # Icon spans x in [right - icon_w - pad, right - pad]; for
        # box right=210, that's roughly [190, 204].
        assert 185 < ix < 205, f"icon x={ix} not in upper-right band"
        assert 20 < iy < 40, f"icon y={iy} not in upper-right band"

    def test_non_artifact_stereotypes_get_no_icon(self) -> None:
        svg = self._render_artifact(stereotype="component")
        m = re.search(
            r'<g id="A"[^>]*>(.*?)</g>',
            svg,
            re.DOTALL,
        )
        assert m
        polygons = re.findall(r"<polygon", m.group(1))
        assert not polygons, "non-artifact stereotype emitted unexpected polygon"


class TestUMLNodeBoxShape:
    """`uml.node_box` must produce a real UML 3D node (front face +
    parallelogram top + parallelogram right side), per UML 2.5.1
    §19.3.3 — not the 2D-rect-with-drop-shadow hack the deployment
    deck previously used."""

    def _render_node(self, **overrides: Any) -> str:
        base: dict[str, Any] = {
            "type": "uml.node_box",
            "id": "N",
            "box": [100, 100, 300, 180],
            "name": "AppServer",
            "kind": "device",
        }
        base.update(overrides)
        doc = _doc_with_classifier(base)
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        assert r.warnings == []
        return svg

    def test_node_emits_three_3d_faces(self) -> None:
        svg = self._render_node()
        m = re.search(r'<g id="N"[^>]*>(.*?)</g>', svg, re.DOTALL)
        assert m
        body = m.group(1)
        # Two parallelogram polygons (top + right) plus one front rect.
        polygons = re.findall(r"<polygon", body)
        rects = re.findall(r"<rect", body)
        assert len(polygons) >= 2, (
            f"expected ≥2 parallelograms (top + right face); got {len(polygons)}"
        )
        assert len(rects) >= 1, "expected at least one front-face rect"

    def test_node_emits_implicit_device_keyword(self) -> None:
        svg = self._render_node(kind="device")
        assert "«device»" in svg

    def test_node_emits_execution_environment_keyword(self) -> None:
        svg = self._render_node(kind="execution_environment")
        assert "«executionEnvironment»" in svg

    def test_node_explicit_stereotype_overrides_kind(self) -> None:
        svg = self._render_node(stereotype="container", kind="device")
        assert "«container»" in svg
        assert "«device»" not in svg


class TestFullClassifierBoxOutput:
    """End-to-end realistic rendering — the kind of input Phase A.3 will produce."""

    def test_account_classifier_renders_all_features(self) -> None:
        """A realistic Account class with stereotype, abstract op, static member, query."""
        doc = _doc_with_classifier(
            {
                "type": "uml.classifier_box",
                "id": "Account",
                "box": [40, 40, 320, 0],
                "name": "Account",
                "stereotype": "entity",
                "attributes": [
                    {
                        "name": "id",
                        "type": "UUID",
                        "visibility": "private",
                        "readonly": True,
                    },
                    {
                        "name": "balance",
                        "type": "Money",
                        "visibility": "private",
                    },
                    {
                        "name": "instances",
                        "type": "List<Account>",
                        "visibility": "private",
                        "static": True,
                    },
                ],
                "operations": [
                    {
                        "name": "deposit",
                        "parameters": [{"name": "amount", "type": "Money"}],
                        "return_type": "boolean",
                    },
                    {
                        "name": "compute",
                        "abstract": True,
                        "return_type": "Money",
                    },
                    {
                        "name": "size",
                        "static": True,
                        "return_type": "int",
                        "query": True,
                    },
                ],
            }
        )
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        assert r.warnings == []

        # Stereotype, name, all visibility prefixes, italic abstract, underlined static, query
        assert "«entity»" in svg
        assert ">Account<" in svg
        assert "- id: UUID {readOnly}" in svg
        assert "- balance: Money" in svg
        assert "+ deposit(amount: Money): boolean" in svg
        assert "+ size(): int {query}" in svg
        # Static instances + abstract compute → both decorations used
        assert 'font-style="italic"' in svg
        assert 'text-decoration="underline"' in svg
