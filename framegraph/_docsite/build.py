"""Materialize the MkDocs ``docs_dir`` for the framegraph portal.

This is the orchestration step the ``make portal`` target calls before
``mkdocs build``. It is intentionally the *only* writer of the portal
source tree, which is a build artifact (gitignored) regenerated from
source on every build:

1. the deterministic API catalog → ``reference/`` pages
   (`framegraph._docsite.generate`),
2. the bundled examples → ``gallery/`` (`framegraph._docsite.gallery`),
3. the hand-written narrative docs under ``docs/`` → ``guides/``,
4. a generated ``index.md`` home page.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW): the build *fails* (non-zero exit)
when the docstring-coverage gate is unmet or any gallery example does
not validate against the schema. A portal that silently omitted a
broken example would misrepresent the package.

CLI: ``python -m framegraph._docsite.build --out docs/portal --date YYYY-MM-DD``
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from framegraph._docsite.coverage import undocumented_symbols
from framegraph._docsite.gallery import build_gallery
from framegraph._docsite.generate import DISCLAIMER_NOTICE, write_pages
from framegraph.docs import build_catalog

__all__ = ["build_portal", "main"]

# Narrative docs copied into the portal as guides: (source under docs/, dest slug).
_GUIDES: tuple[tuple[str, str], ...] = (
    ("MANUAL.md", "manual.md"),
    ("AUTHORING-FILLS.md", "authoring-fills.md"),
    ("PUBLISHING.md", "publishing.md"),
)


def _repo_root() -> Path:
    """Return the repository root (parent of the ``framegraph`` package)."""
    return Path(__file__).resolve().parent.parent.parent


def _index_md(generated_on: str, version: str) -> str:
    """Render the portal home page."""
    return "\n".join(
        [
            "---",
            "disclaimer:",
            "  notice: >-",
            f"    {DISCLAIMER_NOTICE}",
            '  generated_by: "framegraph._docsite.build"',
            f'  date: "{generated_on}"',
            'title: "framegraph"',
            "---",
            "",
            "# framegraph",
            "",
            f"YAML-first DSL for semantic-visual diagrams and presentations "
            f"— renders to clean SVG / PDF. *Version {version}.*",
            "",
            "This portal is generated from the package's own docstrings and "
            "Pydantic schemas via a deterministic, CI-drift-checked pipeline.",
            "",
            "## Where to go",
            "",
            "- **[API reference](reference/api/index.md)** — every public "
            "module, class, and function, from in-source docstrings.",
            "- **[Schema reference](reference/schema.md)** — field tables for "
            "authoring valid FrameGraph YAML.",
            "- **[CLI reference](reference/cli.md)** — every command and flag, "
            "introspected from the argparse parser.",
            "- **[Gallery](gallery/index.md)** — framegraph rendering its own bundled examples.",
            "",
        ]
    )


def build_portal(
    out_dir: Path | str,
    generated_on: str,
    *,
    enforce: bool = True,
) -> Path:
    """Build the portal source tree under ``out_dir``.

    Args:
        out_dir: The MkDocs ``docs_dir`` to (re)populate. Wiped and
            recreated so stale generated pages never linger.
        generated_on: ISO date stamped into every generated page.
        enforce: When True (PALS's law), raise `SystemExit` if the
            docstring-coverage gate is unmet or any gallery example fails
            schema validation.

    Returns:
        The ``out_dir`` path.
    """
    root = _repo_root()
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 0. PALS gate — docstring coverage.
    gaps = undocumented_symbols()
    if gaps and enforce:
        listing = "\n".join(f"  {g.path}:{g.line} {g.kind} {g.name}" for g in gaps)
        raise SystemExit(f"Docstring-coverage gate failed: {len(gaps)} gap(s)\n{listing}")

    catalog = build_catalog()
    version = catalog["package"]["version"]

    # 1. Home page.
    (out / "index.md").write_text(_index_md(generated_on, version), encoding="utf-8")

    # 2. Reference pages (API / schema / CLI).
    write_pages(catalog, out, generated_on)

    # 3. Gallery (renders + validates examples).
    gallery_md, report = build_gallery(root / "examples", out / "gallery" / "assets", generated_on)
    (out / "gallery" / "index.md").write_text(gallery_md, encoding="utf-8")
    if not report.ok and enforce:
        failed = "\n".join(f"  {slug}: {why}" for slug, why in report.failed)
        raise SystemExit(f"Gallery validation failed:\n{failed}")

    # 4. Narrative guides (copied verbatim from docs/).
    guides_dir = out / "guides"
    guides_dir.mkdir(parents=True, exist_ok=True)
    for src_name, dest_name in _GUIDES:
        src = root / "docs" / src_name
        if src.exists():
            shutil.copyfile(src, guides_dir / dest_name)

    print(
        "portal built: "
        f"{len(catalog['modules'])} modules, "
        f"{len(report.validated)} examples validated "
        f"({len(report.rendered)} rendered, "
        f"{len(report.embedded_static)} static, "
        f"{len(report.skipped)} skipped)"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m framegraph._docsite.build``."""
    parser = argparse.ArgumentParser(
        prog="framegraph-portal-build",
        description="Generate the MkDocs source tree for the framegraph portal.",
    )
    parser.add_argument(
        "--out",
        default="docs/portal",
        help="Output docs_dir to populate (default: docs/portal)",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="ISO date (YYYY-MM-DD) stamped into generated pages",
    )
    parser.add_argument(
        "--no-enforce",
        action="store_true",
        help="Do not fail on coverage/validation gaps (preview builds)",
    )
    args = parser.parse_args(argv)
    try:
        build_portal(args.out, args.date, enforce=not args.no_enforce)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
