"""Build the portal gallery from the bundled examples — dogfooded.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW) — VERIFY BEFORE PUBLISHING.
Every example is validated against the Pydantic schema before it is
embedded; standalone documents are *re-rendered* fresh by framegraph
itself (never trusting a possibly-stale committed SVG). `build_gallery`
returns a structured report so the caller can fail the build when any
example does not validate.

The gallery is the project showcasing its own output: the SVGs on the
page are produced by `FrameGraphRenderer.render_svg()` at build time.

Public surface
--------------
- `discover_examples(examples_dir)` — list `Example` records.
- `build_gallery(examples_dir, assets_dir, generated_on)` — render +
  validate, write SVG assets, return ``(markdown, report)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framegraph._docsite.generate import DISCLAIMER_NOTICE

__all__ = [
    "Example",
    "GalleryReport",
    "build_gallery",
    "discover_examples",
]

# Source files that are fragments/data, not whole documents.
_SKIP_SUFFIXES = (".templates.yml",)
_SKIP_NAMES = ("data.yml",)


@dataclass(frozen=True)
class Example:
    """One discovered example document.

    Attributes:
        slug: Stable id derived from the example directory name.
        title: Human title (slug with separators normalised).
        source: Path to the source YAML.
        kind: ``"doc"`` (standalone scene) or ``"deck"`` (multi-slide).
    """

    slug: str
    title: str
    source: Path
    kind: str


@dataclass
class GalleryReport:
    """Outcome of a gallery build, for PALS-law verification.

    `validated` and `failed` are lists of ``(slug, detail)``. `rendered`
    lists slugs whose SVG was produced fresh; `embedded_static` lists
    slugs shown via a pre-existing committed SVG (decks).
    """

    validated: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    rendered: list[str] = field(default_factory=list)
    embedded_static: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no example failed schema validation."""
        return not self.failed


def _classify(doc: Any) -> str:
    """Return ``"deck"`` for deck documents, else ``"doc"``."""
    if isinstance(doc, dict) and ("slides" in doc or "deck" in doc):
        return "deck"
    return "doc"


def _title(slug: str) -> str:
    """Normalise a directory slug into a display title."""
    return slug.replace("-", " ").replace("_", " ").strip().title()


def discover_examples(examples_dir: Path | str) -> list[Example]:
    """Find example documents under ``examples_dir``, sorted by slug.

    One example per source ``*.yml`` (template/data fragments skipped).
    The example's ``slug`` is the parent directory name, so each example
    directory contributes at most the documents it declares.
    """
    base = Path(examples_dir)
    found: list[Example] = []
    for src in sorted(base.rglob("*.yml")):
        if src.name in _SKIP_NAMES or src.name.endswith(_SKIP_SUFFIXES):
            continue
        try:
            doc = yaml.safe_load(src.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        slug = src.parent.name
        found.append(Example(slug, _title(slug), src, _classify(doc)))
    return found


def _validate(doc: dict[str, Any], kind: str) -> str | None:
    """Validate a parsed document against its schema; return error or None."""
    from framegraph._schema import DeckDocument, Document

    model = DeckDocument if kind == "deck" else Document
    try:
        model.model_validate(doc)
        return None
    except Exception as exc:  # pydantic.ValidationError and friends
        return str(exc).splitlines()[0] if str(exc) else type(exc).__name__


def _render_doc_svg(doc: dict[str, Any]) -> str:
    """Render a standalone document to an SVG string via the public renderer."""
    from framegraph import FrameGraphRenderer

    return FrameGraphRenderer(doc).render_svg()


def _find_committed_svg(example: Example) -> Path | None:
    """Locate a representative committed SVG for a deck example."""
    # Beside the source, then in a sibling output/<slug>/ tree.
    siblings = sorted(example.source.parent.rglob("*.svg"))
    if siblings:
        return siblings[0]
    repo_root = _repo_root(example.source)
    out_dir = repo_root / "output" / example.slug
    if out_dir.is_dir():
        rendered = sorted(out_dir.glob("*.svg"))
        if rendered:
            return rendered[0]
    return None


def _repo_root(path: Path) -> Path:
    """Walk up from a path to the repo root (the dir holding ``examples/``)."""
    for parent in path.resolve().parents:
        if (parent / "examples").is_dir() and (parent / "framegraph").is_dir():
            return parent
    return path.resolve().parents[-1]


def _frontmatter(generated_on: str) -> str:
    """Disclaimer frontmatter for the gallery page (deterministic date)."""
    return "\n".join(
        [
            "---",
            "disclaimer:",
            "  notice: >-",
            f"    {DISCLAIMER_NOTICE}",
            '  generated_by: "framegraph._docsite.gallery"',
            f'  date: "{generated_on}"',
            'title: "Gallery"',
            "---",
        ]
    )


def build_gallery(
    examples_dir: Path | str,
    assets_dir: Path | str,
    generated_on: str,
) -> tuple[str, GalleryReport]:
    """Render + validate every example and build the gallery page.

    Args:
        examples_dir: Directory holding example sub-folders.
        assets_dir: Directory to write rendered/copied SVG assets into
            (created if missing). SVGs are referenced relatively from the
            gallery page, which is expected to sit one level above.
        generated_on: ISO date stamped into the page frontmatter.

    Returns:
        ``(markdown, report)``. The report's ``failed`` list is non-empty
        when any example fails schema validation — callers enforcing
        PALS's law should fail the build in that case.
    """
    assets = Path(assets_dir)
    assets.mkdir(parents=True, exist_ok=True)
    report = GalleryReport()

    parts = [
        _frontmatter(generated_on),
        "",
        "# Gallery",
        "",
        "Every figure below is framegraph rendering its own bundled "
        "examples. Standalone documents are re-rendered fresh at build "
        "time; each example is validated against the Pydantic schema "
        "before it appears here.",
        "",
    ]

    for ex in discover_examples(examples_dir):
        doc = yaml.safe_load(ex.source.read_text(encoding="utf-8"))
        err = _validate(doc, ex.kind)
        if err:
            report.failed.append((ex.slug, err))
            continue
        report.validated.append((ex.slug, ex.kind))

        svg_name = f"{ex.slug}.svg"
        svg_path = assets / svg_name
        embed: str | None = None
        if ex.kind == "doc":
            try:
                svg_path.write_text(_render_doc_svg(doc), encoding="utf-8")
                report.rendered.append(ex.slug)
                embed = svg_name
            except Exception as exc:  # render failure is a real defect
                report.failed.append((ex.slug, f"render: {exc}"))
                continue
        else:
            committed = _find_committed_svg(ex)
            if committed is not None:
                svg_path.write_text(committed.read_text(encoding="utf-8"), encoding="utf-8")
                report.embedded_static.append(ex.slug)
                embed = svg_name
            else:
                report.skipped.append((ex.slug, "no committed SVG to embed"))

        parts += [f"## {ex.title}", ""]
        note = "rendered fresh" if ex.kind == "doc" else "deck (pre-rendered slide)"
        if embed:
            parts.append(f'<img src="assets/{embed}" alt="{ex.title}" loading="lazy">')
            parts.append("")
        parts.append(f"*{ex.kind} — {note}.*")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n", report
