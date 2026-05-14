"""Unit tests for the inline-markdown parser.

The parser converts a single line of text containing inline markdown
runs (`**bold**`, `*italic*`, `` `code` ``) into a list of span dicts
compatible with `spans_svg` / `bullet_list`. Block-level constructs
(headers, lists, blockquotes) are out of scope — the parser is line-
local.
"""

from __future__ import annotations

from framegraph._inline_markdown import parse_inline_markdown


def test_plain_text_returns_single_span() -> None:
    spans = parse_inline_markdown("hello world")
    assert spans == [{"text": "hello world"}]


def test_bold_emits_three_spans() -> None:
    spans = parse_inline_markdown("foo **bar** baz")
    assert spans == [
        {"text": "foo "},
        {"text": "bar", "weight": "bold"},
        {"text": " baz"},
    ]


def test_italic_with_single_asterisks() -> None:
    spans = parse_inline_markdown("an *important* note")
    assert spans == [
        {"text": "an "},
        {"text": "important", "italic": True},
        {"text": " note"},
    ]


def test_inline_code_marks_monospace() -> None:
    spans = parse_inline_markdown("use `tests_edges.py` to bind")
    assert spans == [
        {"text": "use "},
        {"text": "tests_edges.py", "font": "monospace"},
        {"text": " to bind"},
    ]


def test_bold_at_start_and_end() -> None:
    assert parse_inline_markdown("**lead** rest") == [
        {"text": "lead", "weight": "bold"},
        {"text": " rest"},
    ]
    assert parse_inline_markdown("rest **tail**") == [
        {"text": "rest "},
        {"text": "tail", "weight": "bold"},
    ]


def test_multiple_bold_runs() -> None:
    spans = parse_inline_markdown("**a** and **b**")
    assert spans == [
        {"text": "a", "weight": "bold"},
        {"text": " and "},
        {"text": "b", "weight": "bold"},
    ]


def test_unbalanced_asterisks_are_literal() -> None:
    # A single dangling `**` must not consume the rest of the line.
    spans = parse_inline_markdown("ratio **0.47 — heuristic underfires")
    assert spans == [{"text": "ratio **0.47 — heuristic underfires"}]


def test_empty_string_returns_empty_list() -> None:
    assert parse_inline_markdown("") == []


def test_returns_none_passthrough() -> None:
    # Defensive: None input → empty list, not a crash.
    assert parse_inline_markdown(None) == []  # type: ignore[arg-type]


def test_has_markdown_helper_detects_runs() -> None:
    from framegraph._inline_markdown import has_inline_markdown

    assert has_inline_markdown("plain text") is False
    assert has_inline_markdown("with **bold**") is True
    assert has_inline_markdown("with *italic*") is True
    assert has_inline_markdown("with `code`") is True
    # Bare asterisk that is not a delimiter → no markdown.
    assert has_inline_markdown("5 * 4 = 20") is False
