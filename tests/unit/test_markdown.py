"""Tests for the Markdown → FrameGraph deck converter (`framegraph.markdown`).

Covers the block parser, the A4 deck builder (pagination, hybrid pattern
directives, front-matter), schema validity of the emitted deck, the
file/CLI entry points, and an end-to-end render through the real deck
renderer (the emitted deck must actually draw, not merely validate).
"""

from __future__ import annotations

from pathlib import Path

from framegraph.markdown import (
    BlockQuote,
    CodeBlock,
    Heading,
    Image,
    ListBlock,
    Paragraph,
    PatternDirective,
    Table,
    ThematicBreak,
    build_deck,
    convert_file,
    main,
    markdown_to_deck,
    parse_markdown,
)

# ── Parser ──────────────────────────────────────────────────────────


def test_frontmatter_is_extracted() -> None:
    fm, blocks = parse_markdown("---\ntitle: T\ntheme: mckinsey\n---\n\n# H\n")
    assert fm == {"title": "T", "theme": "mckinsey"}
    assert isinstance(blocks[0], Heading) and blocks[0].level == 1


def test_headings_paragraphs_and_breaks() -> None:
    _, blocks = parse_markdown("# Title\n\nsome text here\n\n---\n\n## Next\n")
    kinds = [type(b).__name__ for b in blocks]
    assert kinds == ["Heading", "Paragraph", "ThematicBreak", "Heading"]
    assert blocks[1].text == "some text here"


def test_unordered_ordered_and_nested_lists() -> None:
    md = "- a\n- b\n  - nested\n\n1. one\n2. two\n"
    _, blocks = parse_markdown(md)
    lists = [b for b in blocks if isinstance(b, ListBlock)]
    assert len(lists) == 2
    assert lists[0].ordered is False
    assert any("nested" in it for it in lists[0].items)
    assert lists[1].ordered is True
    assert lists[1].items[0].startswith("1.")


def test_gfm_table() -> None:
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
    _, blocks = parse_markdown(md)
    tbl = blocks[0]
    assert isinstance(tbl, Table)
    assert tbl.header == ["A", "B"]
    assert tbl.rows == [["1", "2"], ["3", "4"]]


def test_code_fence_vs_framegraph_directive() -> None:
    _, blocks = parse_markdown("```python\nx = 1\n```\n")
    assert isinstance(blocks[0], CodeBlock) and blocks[0].lang == "python"
    _, blocks2 = parse_markdown("```framegraph\nuse: 10\nfill: {strengths: [a]}\n```\n")
    assert isinstance(blocks2[0], PatternDirective)
    assert blocks2[0].payload["use"] == 10


def test_blockquote_and_block_image() -> None:
    _, blocks = parse_markdown("> quoted line\n> still quoted\n\n![alt text](pic.png)\n")
    assert isinstance(blocks[0], BlockQuote) and "quoted" in blocks[0].text
    assert (
        isinstance(blocks[1], Image) and blocks[1].src == "pic.png" and blocks[1].alt == "alt text"
    )


# ── Deck builder ────────────────────────────────────────────────────


def test_default_canvas_is_a4_portrait() -> None:
    deck = markdown_to_deck("# Hello\n\nbody\n")
    assert deck["deck"]["canvas"]["size"] == [794.0, 1123.0]
    assert deck["kind"] == "presentation-deck"
    assert deck["version"] == 1.5


def test_canvas_and_theme_overrides() -> None:
    deck = markdown_to_deck("# H\n", canvas="letter", theme="bcg")
    assert deck["deck"]["canvas"]["size"] == [816.0, 1056.0]
    assert deck["$theme"] == "bcg"


def test_frontmatter_overrides_canvas_and_theme() -> None:
    deck = markdown_to_deck("---\ncanvas: a3\ntheme: ey\n---\n# H\n")
    assert deck["deck"]["canvas"]["size"] == [1123.0, 1587.0]
    assert deck["$theme"] == "ey"


def test_h1_starts_new_page() -> None:
    deck = markdown_to_deck("# One\n\ntext\n\n# Two\n\nmore\n")
    assert len(deck["slides"]) == 2
    assert deck["slides"][0]["title"] == "One"
    assert deck["slides"][1]["title"] == "Two"


def test_thematic_break_forces_page_break() -> None:
    deck = markdown_to_deck("para a\n\n---\n\npara b\n")
    assert len(deck["slides"]) == 2


def test_pattern_directive_becomes_use_slide() -> None:
    md = "```framegraph\nuse: 10\nfill: {strengths: [Brand]}\n```\n"
    deck = markdown_to_deck(md)
    use_slides = [s for s in deck["slides"] if "use" in s]
    assert len(use_slides) == 1
    assert use_slides[0]["use"] == 10
    assert use_slides[0]["fill"] == {"strengths": ["Brand"]}


def test_long_content_paginates() -> None:
    body = "\n\n".join(f"Paragraph number {i} with enough text to take a line." for i in range(80))
    deck = markdown_to_deck(f"# Doc\n\n{body}\n")
    assert len(deck["slides"]) > 1, "long content should overflow onto multiple A4 pages"


def test_block_types_emit_expected_objects() -> None:
    md = (
        "# Title\n\npara\n\n- item\n\n| H |\n| --- |\n| v |\n\n"
        "> quote\n\n```py\ncode\n```\n\n![a](i.png)\n"
    )
    deck = markdown_to_deck(md)
    objs = [o for s in deck["slides"] for layer in s["visual"]["layers"] for o in layer["objects"]]
    types = {o["type"] for o in objs}
    assert {"text", "bullet_list", "table", "image", "rect"} <= types


def test_empty_document_yields_one_valid_page() -> None:
    deck = markdown_to_deck("")
    assert len(deck["slides"]) == 1


# ── Schema validity + render ────────────────────────────────────────


def test_emitted_deck_validates_against_schema() -> None:
    """`markdown_to_deck(validate=True)` must satisfy the deck schema."""
    # Raises pydantic.ValidationError on a bad deck; success = no raise.
    markdown_to_deck("# H\n\ntext\n\n- a\n- b\n", validate=True)


def test_emitted_deck_renders_to_svg(tmp_path: Path) -> None:
    """The emitted deck must actually render — validity alone is not enough.

    Exercises a bespoke content page and a `use:`-pattern slide together,
    through the real `FrameGraphDeckRenderer`.
    """
    from framegraph.library import FrameGraphDeckRenderer, FrameGraphLibrary

    md = (
        "# Title\n\nBody **bold** text.\n\n- one\n- two\n\n"
        "```framegraph\nuse: 10\nfill: {strengths: [Brand], weaknesses: [UX], "
        "opportunities: [Vertical], threats: [Entrant]}\n```\n"
    )
    deck = markdown_to_deck(md, theme="mckinsey")
    lib = FrameGraphLibrary(Path("framegraph/lib"))
    paths = FrameGraphDeckRenderer(deck, library=lib).render_all(tmp_path)
    assert paths, "no slides rendered"
    svgs = [p for p in paths if p.suffix == ".svg"]
    assert svgs, "no SVG output produced"
    for p in svgs:
        assert "<svg" in p.read_text(encoding="utf-8")


# ── File + CLI ──────────────────────────────────────────────────────


def test_convert_file_writes_yaml(tmp_path: Path) -> None:
    import yaml

    src = tmp_path / "doc.md"
    src.write_text("# H\n\nbody\n", encoding="utf-8")
    out = tmp_path / "doc.deck.yml"
    convert_file(src, out, canvas="a4")
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded["kind"] == "presentation-deck"
    assert loaded["deck"]["canvas"]["size"] == [794.0, 1123.0]


def test_cli_main_default_output(tmp_path: Path) -> None:
    src = tmp_path / "doc.md"
    src.write_text("# H\n\nbody\n", encoding="utf-8")
    rc = main([str(src)])
    assert rc == 0
    assert (tmp_path / "doc.deck.yml").is_file()


def test_cli_main_missing_input_returns_1(tmp_path: Path) -> None:
    rc = main([str(tmp_path / "nope.md")])
    assert rc == 1


def test_build_deck_direct_blocks() -> None:
    blocks = [Heading(1, "T"), Paragraph("p"), ThematicBreak(), Paragraph("q")]
    deck = build_deck({}, blocks, canvas="a4")
    assert len(deck["slides"]) == 2
