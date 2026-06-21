"""Markdown → FrameGraph deck converter.

Maps a CommonMark/GFM-subset Markdown document to a FrameGraph
``presentation-deck`` dict: an **A4-paged document** in which Markdown
blocks become positioned SVG objects, paginated to fit the page.

Design (per the project's pure-Python / minimal-dependency commitment):

- **No new runtime dependency.** Block parsing is hand-rolled here;
  inline runs (``**bold**`` / ``*italic*`` / ```` `code` ````) are left as
  raw text in ``text`` objects and rendered by the existing
  ``framegraph._inline_markdown`` path at render time.
- **Hybrid output.** Most content becomes *bespoke* ``visual:`` slides
  with computed boxes. A fenced ```` ```framegraph ```` block whose body
  is ``use: <id>`` (+ optional ``fill:``) becomes a *pattern-composed*
  slide instead, so curated catalog patterns drop into a prose document.
- **A4 default canvas**, resolved through :func:`framegraph.canvas.resolve_canvas_preset`
  so paper geometry has a single source of truth. Front-matter may
  override the canvas (``a4`` / ``a3`` / ``letter`` / ``[w, h]``), theme,
  and DSL version.

The emitted deck is validated against the schema before it is returned
(LLM/codegen output is untrusted until verified — see CLAUDE.md PALS's Law).

CLI::

    python -m framegraph.markdown INPUT.md -o OUTPUT.yml [--theme T] [--canvas a4]
    framegraph deck OUTPUT.yml -o ./out --pdf
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framegraph.canvas import resolve_canvas_preset

__all__ = [
    "Block",
    "BlockQuote",
    "CodeBlock",
    "Heading",
    "Image",
    "ListBlock",
    "Paragraph",
    "PatternDirective",
    "Table",
    "ThematicBreak",
    "convert_file",
    "markdown_to_deck",
    "parse_markdown",
]

CURRENT_DSL_VERSION = 1.5

# ── Page geometry (CSS px @ 96 DPI; A4 = 794 × 1123) ───────────────────────────
_MARGIN = 56.0
_BLOCK_GAP = 14.0
_LINE_H = 20.0
_CHAR_W = 7.2  # average advance at the 14px body size; wrap estimate only


# ─────────────────────────────────────────────────────────────────
# Block model
# ─────────────────────────────────────────────────────────────────


@dataclass
class Block:
    """Base class for a parsed Markdown block."""


@dataclass
class Heading(Block):
    """An ATX heading. ``level`` is 1–6; ``text`` keeps inline markup raw."""

    level: int
    text: str


@dataclass
class Paragraph(Block):
    """A paragraph of (soft-wrapped) text with raw inline markup."""

    text: str


@dataclass
class ListBlock(Block):
    """An ordered or unordered list, already flattened to display lines.

    Each entry of ``items`` is the fully composed visible line (marker +
    indentation + content), so nested and ordered lists render uniformly.
    """

    items: list[str]
    ordered: bool = False


@dataclass
class Table(Block):
    """A GFM pipe table: a header row plus zero or more body rows."""

    header: list[str]
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Image(Block):
    """A block image (``![alt](src)`` on its own line)."""

    src: str
    alt: str = ""


@dataclass
class CodeBlock(Block):
    """A fenced code block (non-``framegraph`` language)."""

    lang: str
    lines: list[str]


@dataclass
class BlockQuote(Block):
    """A block quote (``>`` prefixed lines), inline markup kept raw."""

    text: str


@dataclass
class ThematicBreak(Block):
    """A thematic break (``---`` / ``***`` / ``___``) → forces a page break."""


@dataclass
class PatternDirective(Block):
    """A ```` ```framegraph ```` fenced directive → a pattern-composed slide.

    ``payload`` is the parsed YAML body and must carry a ``use`` key
    (catalog id or slug); an optional ``fill`` maps zone roles to content.
    """

    payload: dict[str, Any]


# ─────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d+[.)])\s+(?P<text>.*)$")
_IMAGE_ONLY_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)[^)]*\)$")
_TABLE_DELIM_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")


def _split_table_row(line: str) -> list[str]:
    """Split a GFM table row into trimmed cells, dropping edge pipes."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_list(lines: list[str], start: int) -> tuple[ListBlock, int]:
    """Parse a (possibly nested) list starting at ``start``.

    Nested items are flattened into composed display lines: each nesting
    level is indented and ordered items keep their ``N.`` numbering.
    """
    items: list[str] = []
    i = start
    base_indent: int | None = None
    top_ordered = False
    while i < len(lines):
        m = _LIST_RE.match(lines[i])
        if m is None:
            if lines[i].strip() == "":
                break
            break
        indent = len(m.group("indent").expandtabs(4))
        if base_indent is None:
            base_indent = indent
            top_ordered = m.group("marker")[0].isdigit()
        level = max(0, (indent - base_indent) // 2)
        marker = m.group("marker")
        ordered = marker[0].isdigit()
        bullet = f"{marker} " if ordered else "• "
        items.append(f"{'    ' * level}{bullet}{m.group('text').strip()}")
        i += 1
    return ListBlock(items=items, ordered=top_ordered), i


def parse_markdown(text: str) -> tuple[dict[str, Any], list[Block]]:
    """Parse a Markdown document into ``(front_matter, blocks)``.

    Args:
        text: The raw Markdown source.

    Returns:
        A tuple of the YAML front-matter mapping (empty when absent) and
        the ordered list of parsed blocks.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lines)
    frontmatter: dict[str, Any] = {}
    i = 0

    # YAML front-matter: a leading `---` … `---` fence.
    if lines and lines[0].strip() == "---":
        j = 1
        while j < n and lines[j].strip() != "---":
            j += 1
        if j < n:
            loaded = yaml.safe_load("\n".join(lines[1:j]))
            if isinstance(loaded, dict):
                frontmatter = loaded
            i = j + 1

    blocks: list[Block] = []
    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        # Fenced code / pattern directive.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            lang = stripped[3:].strip()
            i += 1
            buf: list[str] = []
            while i < n and lines[i].strip()[:3] != fence:
                buf.append(lines[i])
                i += 1
            i += 1  # consume closing fence (or run off end)
            if lang.lower() in ("framegraph", "fg"):
                payload = yaml.safe_load("\n".join(buf))
                blocks.append(PatternDirective(payload if isinstance(payload, dict) else {}))
            else:
                blocks.append(CodeBlock(lang=lang, lines=buf))
            continue

        # Thematic break → page break.
        if _HR_RE.match(stripped):
            blocks.append(ThematicBreak())
            i += 1
            continue

        # ATX heading.
        m = _HEADING_RE.match(stripped)
        if m:
            blocks.append(Heading(level=len(m.group(1)), text=m.group(2).strip()))
            i += 1
            continue

        # Block quote.
        if stripped.startswith(">"):
            qbuf: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                qbuf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            blocks.append(BlockQuote(text=" ".join(s.strip() for s in qbuf if s.strip())))
            continue

        # GFM pipe table: a row followed by a delimiter row.
        if "|" in raw and i + 1 < n and _TABLE_DELIM_RE.match(lines[i + 1]):
            header = _split_table_row(raw)
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_table_row(lines[i]))
                i += 1
            blocks.append(Table(header=header, rows=rows))
            continue

        # List.
        if _LIST_RE.match(raw):
            block, i = _parse_list(lines, i)
            blocks.append(block)
            continue

        # Block image on its own line.
        im = _IMAGE_ONLY_RE.match(stripped)
        if im:
            blocks.append(Image(src=im.group("src"), alt=im.group("alt")))
            i += 1
            continue

        # Paragraph: gather until a blank line or the next block start.
        pbuf: list[str] = []
        while i < n and lines[i].strip() and not _starts_block(lines, i):
            pbuf.append(lines[i].strip())
            i += 1
        blocks.append(Paragraph(text=" ".join(pbuf)))

    return frontmatter, blocks


def _starts_block(lines: list[str], i: int) -> bool:
    """True if line ``i`` begins a non-paragraph block (paragraph terminator)."""
    s = lines[i].strip()
    if (
        s.startswith(("```", "~~~", ">"))
        or _HR_RE.match(s)
        or _HEADING_RE.match(s)
        or _LIST_RE.match(lines[i])
        or _IMAGE_ONLY_RE.match(s)
    ):
        return True
    return "|" in lines[i] and i + 1 < len(lines) and bool(_TABLE_DELIM_RE.match(lines[i + 1]))


# ─────────────────────────────────────────────────────────────────
# Deck builder (A4 pagination)
# ─────────────────────────────────────────────────────────────────

_HEADING_H = {1: 46.0, 2: 36.0, 3: 30.0, 4: 26.0, 5: 24.0, 6: 24.0}
_HEADING_STYLE = {1: "h1", 2: "h2", 3: "h3", 4: "h4", 5: "h5", 6: "h6"}


def _wrap_lines(text: str, width: float) -> int:
    """Estimate the number of wrapped lines for ``text`` at ``width`` px."""
    cpl = max(1, int(width / _CHAR_W))
    return max(1, -(-len(text) // cpl))  # ceil division


def _estimate_height(block: Block, width: float) -> float:
    """Estimate a block's rendered height in pixels (for pagination + box)."""
    if isinstance(block, Heading):
        return _HEADING_H.get(block.level, 24.0)
    if isinstance(block, Paragraph):
        return _wrap_lines(block.text, width) * _LINE_H + 4.0
    if isinstance(block, ListBlock):
        return sum(_wrap_lines(it, width - 14.0) for it in block.items) * _LINE_H + 4.0
    if isinstance(block, Table):
        return (1 + len(block.rows)) * 30.0
    if isinstance(block, Image):
        return 340.0
    if isinstance(block, CodeBlock):
        return len(block.lines) * 16.0 + 20.0
    if isinstance(block, BlockQuote):
        return _wrap_lines(block.text, width - 20.0) * _LINE_H + 16.0
    return _LINE_H


def _block_to_objects(block: Block, box: list[float], idx: int) -> list[dict[str, Any]]:
    """Render one block to FrameGraph visual objects within ``box``."""
    x, y, w, h = box
    oid = f"o{idx}"
    if isinstance(block, Heading):
        return [
            {
                "type": "text",
                "id": oid,
                "box": box,
                "text": block.text,
                "style": _HEADING_STYLE.get(block.level, "h6"),
            }
        ]
    if isinstance(block, Paragraph):
        return [{"type": "text", "id": oid, "box": box, "text": block.text, "style": "body"}]
    if isinstance(block, ListBlock):
        return [
            {
                "type": "bullet_list",
                "id": oid,
                "box": box,
                "marker": "",
                "style": "body",
                "items": block.items,
            }
        ]
    if isinstance(block, Table):
        return [
            {"type": "table", "id": oid, "box": box, "header": block.header, "rows": block.rows}
        ]
    if isinstance(block, Image):
        return [
            {
                "type": "image",
                "id": oid,
                "box": box,
                "href": block.src,
                "alt": block.alt,
                "preserve_aspect_ratio": "xMidYMid meet",
            }
        ]
    if isinstance(block, CodeBlock):
        return [
            {
                "type": "rect",
                "id": f"{oid}_bg",
                "box": box,
                "fill": "surface",
                "stroke": {"color": "border", "width": 0.5},
                "radius": 4,
            },
            {
                "type": "text",
                "id": oid,
                "box": [x + 10, y + 8, w - 20, h - 16],
                "text": "\n".join(block.lines),
                "style": "code",
            },
        ]
    if isinstance(block, BlockQuote):
        return [
            {"type": "rect", "id": f"{oid}_bar", "box": [x, y, 3.0, h], "fill": "accent"},
            {
                "type": "text",
                "id": oid,
                "box": [x + 14, y, w - 14, h],
                "text": block.text,
                "style": "quote",
            },
        ]
    return []


def _default_tokens() -> dict[str, Any]:
    """Deck-level tokens (colors + text styles) for the document theme."""
    return {
        "colors": {
            "ink": "#1A1A2E",
            "muted": "#5B5B6B",
            "accent": "#2D5BFF",
            "surface": "#F5F5F7",
            "border": "#D8D8E0",
            "page_bg": "#FFFFFF",
        },
        "fonts": {
            "primary": "Helvetica, Arial, sans-serif",
            "mono": "DejaVu Sans Mono, Menlo, monospace",
        },
        "text_styles": {
            "h1": {"font": "primary", "size": 30, "weight": 700, "color": "ink"},
            "h2": {"font": "primary", "size": 23, "weight": 700, "color": "ink"},
            "h3": {"font": "primary", "size": 18, "weight": 600, "color": "ink"},
            "h4": {"font": "primary", "size": 15, "weight": 600, "color": "ink"},
            "h5": {"font": "primary", "size": 13, "weight": 600, "color": "muted"},
            "h6": {"font": "primary", "size": 12, "weight": 600, "color": "muted"},
            "body": {
                "font": "primary",
                "size": 14,
                "weight": 400,
                "color": "ink",
                "align": "left",
                "v_align": "top",
            },
            "code": {
                "font": "mono",
                "size": 12,
                "weight": 400,
                "color": "ink",
                "align": "left",
                "v_align": "top",
            },
            "quote": {
                "font": "primary",
                "size": 14,
                "weight": 400,
                "color": "muted",
                "align": "left",
                "v_align": "top",
            },
        },
    }


def _canvas_size(name_or_size: Any) -> tuple[float, float]:
    """Resolve a canvas spec (preset name or ``[w, h]``) to ``(w, h)`` px."""
    if isinstance(name_or_size, (list, tuple)) and len(name_or_size) == 2:
        return float(name_or_size[0]), float(name_or_size[1])
    cs = resolve_canvas_preset(str(name_or_size), orientation="portrait")
    return float(cs.width), float(cs.height)


def build_deck(
    frontmatter: dict[str, Any],
    blocks: list[Block],
    *,
    theme: str | None = None,
    canvas: str = "a4",
) -> dict[str, Any]:
    """Assemble a ``presentation-deck`` dict from parsed blocks.

    Bespoke content is paginated to the resolved canvas; ``---`` and H1
    headings force a page break, and a page is also flushed when the next
    block would overflow. ``framegraph`` directives become pattern slides.

    Args:
        frontmatter: Parsed YAML front-matter (may set ``theme`` /
            ``canvas`` / ``version`` / ``title``).
        blocks: The parsed Markdown blocks.
        theme: Optional library theme id; overrides front-matter ``theme``.
        canvas: Canvas preset name (default ``"a4"``); overridden by
            front-matter ``canvas``.

    Returns:
        A deck dict ready to serialize and feed to ``framegraph deck``.
    """
    canvas_spec = frontmatter.get("canvas", canvas)
    width, height = _canvas_size(canvas_spec)
    content_x = _MARGIN
    content_w = width - 2 * _MARGIN
    top = _MARGIN
    bottom = height - _MARGIN

    slides: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    cursor = top
    obj_idx = 0
    page_title: str | None = None

    def flush() -> None:
        nonlocal objects, cursor, page_title
        if objects:
            n = len(slides) + 1
            slides.append(
                {
                    "id": f"page_{n:02d}",
                    "slide": n,
                    "title": page_title or f"Page {n}",
                    "visual": {"layers": [{"id": "content", "objects": objects}]},
                }
            )
        objects = []
        cursor = top
        page_title = None

    for block in blocks:
        if isinstance(block, ThematicBreak):
            flush()
            continue
        if isinstance(block, PatternDirective):
            flush()
            n = len(slides) + 1
            slide: dict[str, Any] = {"id": f"page_{n:02d}", "slide": n}
            slide.update(block.payload)
            slide.setdefault("use", block.payload.get("use"))
            slides.append(slide)
            continue

        # H1 starts a fresh page (document section boundary).
        if isinstance(block, Heading) and block.level == 1 and objects:
            flush()

        h = _estimate_height(block, content_w)
        if objects and cursor + h > bottom:
            flush()

        box = [content_x, cursor, content_w, h]
        objects.extend(_block_to_objects(block, box, obj_idx))
        obj_idx += 1
        cursor += h + _BLOCK_GAP

        if isinstance(block, Heading) and page_title is None:
            page_title = block.text

    flush()
    if not slides:  # empty document → one blank page, still valid
        slides.append(
            {
                "id": "page_01",
                "slide": 1,
                "title": "Page 1",
                "visual": {"layers": [{"id": "content", "objects": []}]},
            }
        )

    deck: dict[str, Any] = {
        "dsl": "FrameGraph",
        "version": float(frontmatter.get("version", CURRENT_DSL_VERSION)),
        "kind": "presentation-deck",
    }
    resolved_theme = theme or frontmatter.get("theme")
    if resolved_theme:
        deck["$theme"] = resolved_theme
    deck["deck"] = {
        "canvas": {"size": [width, height], "units": "px"},
        "tokens": _default_tokens(),
    }
    deck["slides"] = slides
    return deck


def markdown_to_deck(
    text: str, *, theme: str | None = None, canvas: str = "a4", validate: bool = True
) -> dict[str, Any]:
    """Convert Markdown source to a validated FrameGraph deck dict.

    Args:
        text: Raw Markdown source.
        theme: Optional library theme id (overrides front-matter).
        canvas: Canvas preset (default ``"a4"``; front-matter wins).
        validate: When True (default), validate the emitted deck against
            the schema before returning — output is untrusted until checked.

    Returns:
        The deck dict.

    Raises:
        pydantic.ValidationError: If ``validate`` and the emitted deck does
            not satisfy the deck schema.
    """
    frontmatter, blocks = parse_markdown(text)
    deck = build_deck(frontmatter, blocks, theme=theme, canvas=canvas)
    if validate:
        from framegraph._schema import DeckDocument

        DeckDocument.model_validate(deck)
    return deck


def convert_file(
    in_path: Path | str, out_path: Path | str, *, theme: str | None = None, canvas: str = "a4"
) -> Path:
    """Convert a Markdown file to a deck YAML file; return the output path."""
    src = Path(in_path).read_text(encoding="utf-8")
    deck = markdown_to_deck(src, theme=theme, canvas=canvas)
    out = Path(out_path)
    out.write_text(
        yaml.safe_dump(deck, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m framegraph.markdown IN.md -o OUT.yml``."""
    parser = argparse.ArgumentParser(
        prog="framegraph.markdown",
        description="Convert a Markdown document to a FrameGraph presentation-deck YAML.",
    )
    parser.add_argument("input", help="Markdown source file (.md)")
    parser.add_argument("-o", "--output", help="Output deck YAML (default: <input>.deck.yml)")
    parser.add_argument("--theme", default=None, help="Library theme id (e.g. mckinsey)")
    parser.add_argument(
        "--canvas", default="a4", help="Canvas preset: a4 | a3 | letter (default a4)"
    )
    args = parser.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 1
    out_path = Path(args.output) if args.output else in_path.with_suffix(".deck.yml")
    try:
        written = convert_file(in_path, out_path, theme=args.theme, canvas=args.canvas)
    except Exception as exc:  # surface conversion/validation failures to the shell
        print(f"conversion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
