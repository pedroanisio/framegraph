"""Tests for the opt-in strict authoring check (`iter_strict_violations`).

PALS's Law (CLAUDE.md): LLM-authored YAML carries typos and hallucinated
field names. The ingestion schema is permissive (`extra="allow"`) for v1.x
backward-compat, so those slip through silently. The strict layer flags
unknown top-level object keys — with did-you-mean hints — without changing
what the default (`validate_*`) path accepts.
"""

from __future__ import annotations

from framegraph._schema import (
    StrictViolation,
    iter_strict_violations,
    validate_any,
)


def _doc(*objects: dict) -> dict:
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "s", "canvas": {"size": [400, 300]}},
        "visual": {"layers": [{"id": "content", "objects": list(objects)}]},
    }


def test_clean_document_has_no_violations() -> None:
    doc = _doc(
        {"type": "rect", "id": "r", "box": [0, 0, 10, 10], "radius": 4, "fill": "ink"},
        {"type": "text", "id": "t", "box": [0, 0, 10, 10], "text": "hi", "style": "h1"},
    )
    assert iter_strict_violations(doc) == []


def test_typo_is_flagged_with_suggestion() -> None:
    doc = _doc({"type": "rect", "id": "r", "box": [0, 0, 1, 1], "radious": 8})
    violations = iter_strict_violations(doc)
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, StrictViolation)
    assert v.object_type == "rect"
    assert v.key == "radious"
    assert v.suggestion == "radius"
    assert "did you mean 'radius'" in str(v)


def test_hallucinated_key_flagged_without_false_suggestion() -> None:
    # `align` is real, but belongs under `style`, not as a top-level text key.
    doc = _doc({"type": "text", "id": "t", "text": "x", "align": "center"})
    violations = iter_strict_violations(doc)
    assert len(violations) == 1
    assert violations[0].key == "align"
    # No top-level text field is a close match → no misleading suggestion.
    assert violations[0].suggestion is None


def test_open_types_allow_arbitrary_keys() -> None:
    # `use` (symbol slots) and `component` (component slots) pull arbitrary
    # top-level keys by design — they must never be flagged.
    doc = _doc(
        {"type": "use", "symbol": "card", "box": [0, 0, 1, 1], "anySlot": "v", "x": 1},
        {"type": "component", "component": "kpi", "box": [0, 0, 1, 1], "title": "T", "body": "B"},
    )
    assert iter_strict_violations(doc) == []


def test_unknown_plugin_type_is_exempt() -> None:
    # Third-party types validate via `_UnknownObject`; no declared contract.
    doc = _doc({"type": "my_custom_widget", "id": "w", "whatever": 1, "foo": "bar"})
    assert iter_strict_violations(doc) == []


def test_flex_layout_hint_allowed_on_children() -> None:
    doc = _doc(
        {
            "type": "container",
            "id": "c",
            "box": [0, 0, 100, 100],
            "layout": {"kind": "stack"},
            "children": [
                {"type": "rect", "id": "a", "flex": 1},
                {"type": "rect", "id": "b", "flex": 2, "bogus": True},
            ],
        }
    )
    violations = iter_strict_violations(doc)
    # `flex` is fine on both; only `bogus` is flagged.
    assert [v.key for v in violations] == ["bogus"]
    assert violations[0].path.endswith("children[1]")


def test_nested_group_objects_are_checked() -> None:
    doc = _doc(
        {
            "type": "group",
            "id": "g",
            "objects": [{"type": "rect", "id": "r", "radiuss": 3}],
        }
    )
    violations = iter_strict_violations(doc)
    assert len(violations) == 1
    assert violations[0].key == "radiuss"
    assert violations[0].suggestion == "radius"


def test_strict_check_is_independent_of_default_validation() -> None:
    # The same typo'd doc passes default validation (extra="allow") but is
    # caught by the strict layer — backward-compat preserved.
    doc = _doc({"type": "rect", "id": "r", "box": [0, 0, 1, 1], "colour": "ink"})
    validate_any(doc)  # must not raise
    assert len(iter_strict_violations(doc)) == 1


def test_deck_objects_are_walked() -> None:
    deck = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "slides": [
            {
                "id": "s1",
                "visual": {
                    "layers": [{"id": "l", "objects": [{"type": "rect", "id": "r", "nope": 1}]}]
                },
            }
        ],
    }
    violations = iter_strict_violations(deck)
    assert len(violations) == 1
    assert violations[0].key == "nope"
    assert "slides[0]" in violations[0].path
