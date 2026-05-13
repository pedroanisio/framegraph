"""Schema-validation tests for `framegraph._frameset`.

Phase 1 of ADR 0001 ("Collapse `Document` and `Deck` into a
`FrameSet` graph"). These tests pin the contract of the Pydantic
models — accepted shapes, rejected shapes, and the structural
invariants (id uniqueness, link-target resolution).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framegraph._frameset import (
    Frame,
    FrameLink,
    FrameTarget,
    validate_frameset,
)

# ─────────────────────────────────────────────────────────────────
# FrameTarget
# ─────────────────────────────────────────────────────────────────


class TestFrameTarget:
    def test_minimum_valid_target(self) -> None:
        t = FrameTarget(name="landscape", canvas=[1920.0, 1080.0])
        assert t.name == "landscape"
        assert t.canvas == [1920.0, 1080.0]
        assert t.adjustments is None

    def test_canvas_must_be_two_numbers(self) -> None:
        with pytest.raises(ValidationError):
            FrameTarget(name="bad", canvas=[1920.0])
        with pytest.raises(ValidationError):
            FrameTarget(name="bad", canvas=[1920.0, 1080.0, 100.0])

    def test_name_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            FrameTarget(name="", canvas=[100.0, 100.0])

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            FrameTarget.model_validate({"name": "x", "canvas": [100, 100], "spurious": True})


# ─────────────────────────────────────────────────────────────────
# FrameLink
# ─────────────────────────────────────────────────────────────────


class TestFrameLink:
    def test_default_relation_is_see_also(self) -> None:
        link = FrameLink(to="other")
        assert link.relation == "see_also"
        assert not link.external

    def test_external_link(self) -> None:
        link = FrameLink(to="https://example.com", external=True, label="Docs")
        assert link.external
        assert link.label == "Docs"

    @pytest.mark.parametrize(
        "relation",
        ["next", "prev", "see_also", "appendix", "source", "child", "parent", "external"],
    )
    def test_known_relations_accepted(self, relation: str) -> None:
        link = FrameLink(to="x", relation=relation)
        assert link.relation == relation

    def test_unknown_relation_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FrameLink.model_validate({"to": "x", "relation": "unknown"})

    def test_to_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            FrameLink(to="")


# ─────────────────────────────────────────────────────────────────
# Frame
# ─────────────────────────────────────────────────────────────────


class TestFrame:
    def test_minimum_valid_frame(self) -> None:
        f = Frame(id="cover")
        assert f.id == "cover"
        assert f.targets == []
        assert f.links == []
        assert f.next is None and f.prev is None

    def test_frame_with_targets_and_links(self) -> None:
        f = Frame(
            id="dashboard",
            title="Dashboard",
            targets=[FrameTarget(name="landscape", canvas=[1920, 1080])],
            next="next-slide",
            links=[FrameLink(to="appendix", relation="appendix")],
        )
        assert len(f.targets) == 1
        assert f.targets[0].name == "landscape"
        assert f.next == "next-slide"
        assert len(f.links) == 1

    def test_frame_id_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            Frame(id="")

    def test_frame_extra_keys_pass_through(self) -> None:
        # Frame is extra="allow" so authors can attach arbitrary
        # metadata (slide numbers, custom fields, deck-level keys
        # that survived the coercion).
        f = Frame.model_validate({"id": "f1", "slide": 7, "phase": "alpha"})
        # The structural keys are typed; the rest is accessible via
        # model_dump.
        dumped = f.model_dump()
        assert dumped.get("slide") == 7
        assert dumped.get("phase") == "alpha"


# ─────────────────────────────────────────────────────────────────
# FrameSetDocument — structural invariants
# ─────────────────────────────────────────────────────────────────


class TestFrameSetDocument:
    def test_minimum_valid_frameset(self) -> None:
        doc = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [{"id": "only"}],
            }
        )
        assert doc.kind == "frameset"
        assert len(doc.frames) == 1

    def test_frames_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            validate_frameset(
                {"dsl": "FrameGraph", "version": 2.0, "kind": "frameset", "frames": []}
            )

    def test_kind_must_be_frameset(self) -> None:
        with pytest.raises(ValidationError):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "presentation-deck",
                    "frames": [{"id": "x"}],
                }
            )

    def test_dsl_must_be_framegraph(self) -> None:
        with pytest.raises(ValidationError):
            validate_frameset(
                {
                    "dsl": "OtherDSL",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [{"id": "x"}],
                }
            )

    def test_extra_top_level_keys_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "spurious": "value",
                    "frames": [{"id": "x"}],
                }
            )

    def test_theme_alias_accepted(self) -> None:
        # The `$theme` alias is the legacy name for the field.
        doc = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "$theme": "mckinsey",
                "frames": [{"id": "x"}],
            }
        )
        assert doc.theme == "mckinsey"


# ─────────────────────────────────────────────────────────────────
# FrameSetDocument — validators (id uniqueness, link resolution)
# ─────────────────────────────────────────────────────────────────


class TestFrameSetValidators:
    def test_duplicate_frame_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [{"id": "a"}, {"id": "a"}],
                }
            )

    def test_dangling_next_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unresolved"):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [{"id": "a", "next": "missing"}],
                }
            )

    def test_dangling_prev_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unresolved"):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [{"id": "a", "prev": "missing"}],
                }
            )

    def test_dangling_extends_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unresolved"):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [{"id": "a", "extends": "missing"}],
                }
            )

    def test_dangling_internal_link_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unresolved"):
            validate_frameset(
                {
                    "dsl": "FrameGraph",
                    "version": 2.0,
                    "kind": "frameset",
                    "frames": [
                        {
                            "id": "a",
                            "links": [{"to": "missing", "relation": "see_also"}],
                        }
                    ],
                }
            )

    def test_external_link_skips_resolution_check(self) -> None:
        # External links carry URLs, not Frame ids — so resolution
        # is by definition not checked for them.
        doc = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "a",
                        "links": [
                            {
                                "to": "https://example.com",
                                "external": True,
                                "label": "Docs",
                            }
                        ],
                    }
                ],
            }
        )
        assert doc.frames[0].links[0].to == "https://example.com"

    def test_chain_with_resolved_next_prev_passes(self) -> None:
        doc = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {"id": "a", "next": "b"},
                    {"id": "b", "prev": "a", "next": "c"},
                    {"id": "c", "prev": "b"},
                ],
            }
        )
        assert doc.frames[1].next == "c"
        assert doc.frames[1].prev == "a"
