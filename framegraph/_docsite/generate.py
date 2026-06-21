"""Render the API catalog into MkDocs-ready Markdown pages.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW) — this is the *only* place the
portal's reference pages are produced, and they are a pure function of
`framegraph.docs.build_catalog()`. There is no second docstring parser:
the catalog is the single source of truth, so the portal cannot drift
from the catalog that CI already byte-diff-checks.

`generate_pages(catalog, generated_on)` returns a mapping of
``relative/path.md`` → Markdown text, deterministically (same catalog +
same date → byte-identical output). `write_pages(...)` is the thin disk
wrapper used by the CLI / Makefile. Pages produced:

- ``reference/api/index.md`` — module overview.
- ``reference/api/<module>.md`` — one page per public module: every
  symbol with its signature, docstring, and parsed sections.
- ``reference/schema.md`` — every Pydantic model with a flat field
  table (name / type / required / default / description).
- ``reference/cli.md`` — the full CLI reference from the argparse tree.

The `nav` returned by `generate_nav(catalog)` is the list MkDocs expects
under its ``nav:`` key for the generated section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "DISCLAIMER_NOTICE",
    "generate_nav",
    "generate_pages",
    "write_pages",
]

DISCLAIMER_NOTICE = (
    "No information within this document should be taken for granted. "
    "Any statement or premise not backed by a real logical definition or "
    "verifiable reference may be invalid, erroneous, or a hallucination."
)

_GENERATED_BY = "framegraph._docsite.generate"


# ─────────────────────────────────────────────────────────────────
# Small Markdown helpers (pure)
# ─────────────────────────────────────────────────────────────────


def _frontmatter(generated_on: str, *, extra: dict[str, str] | None = None) -> str:
    """Render the mandatory disclaimer YAML frontmatter block.

    `generated_on` is injected (never read from the clock) so the output
    stays deterministic for snapshot tests and CI drift checks.
    """
    lines = [
        "---",
        "disclaimer:",
        "  notice: >-",
        f"    {DISCLAIMER_NOTICE}",
        f'  generated_by: "{_GENERATED_BY}"',
        f'  date: "{generated_on}"',
    ]
    for key, value in (extra or {}).items():
        lines.append(f'{key}: "{value}"')
    lines.append("---")
    return "\n".join(lines)


def _escape_cell(text: str) -> str:
    """Escape a string for safe inclusion in a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured Markdown table; '' when there are no rows."""
    if not rows:
        return ""
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _anchor(module_name: str) -> str:
    """Map an import path to a flat page filename (``a.b.c`` → ``a-b-c``)."""
    return module_name.replace(".", "-").lstrip("-") or "root"


def _kind_label(kind: str) -> str:
    """Human label for a symbol kind."""
    return {"class": "class", "function": "function", "type_alias": "type alias"}.get(kind, kind)


# ─────────────────────────────────────────────────────────────────
# Symbol / module rendering
# ─────────────────────────────────────────────────────────────────


def _render_sections(sections: dict[str, Any]) -> list[str]:
    """Render the parsed Google-style docstring sections as Markdown."""
    out: list[str] = []
    for title, body in sections.items():
        body_text = body if isinstance(body, str) else str(body)
        if not body_text.strip():
            continue
        out.append(f"**{title}:**")
        out.append("")
        out.append("```text")
        out.append(body_text.rstrip())
        out.append("```")
        out.append("")
    return out


def _render_symbol(sym: dict[str, Any]) -> list[str]:
    """Render one catalog symbol entry to Markdown lines."""
    out = [f"### `{sym['name']}`", "", f"*{_kind_label(sym['kind'])}*", ""]
    signature = sym.get("signature")
    if signature:
        out += ["```python", signature, "```", ""]

    doc = (sym.get("docstring") or "").strip()
    sections = sym.get("docstring_sections") or {}
    # Use only the summary paragraph here; sections are rendered separately.
    if doc:
        summary = doc
        for title in sections:
            marker = f"\n{title}:"
            idx = summary.find(marker)
            if idx != -1:
                summary = summary[:idx]
        summary = summary.strip()
        if summary:
            out += [summary, ""]
    out += _render_sections(sections)

    fields = sym.get("schema_fields")
    if fields:
        out += ["**Fields**", ""]
        rows = [
            [
                f"`{f['name']}`",
                f"`{f['type']}`",
                "yes" if f.get("required") else "no",
                f"`{f['default']!r}`" if "default" in f else "—",
                f.get("description", ""),
            ]
            for f in fields
        ]
        table = _md_table(["Field", "Type", "Required", "Default", "Description"], rows)
        out += [table, ""]
    return out


def _render_module_page(module_name: str, mod: dict[str, Any], generated_on: str) -> str:
    """Render the per-module API reference page."""
    parts = [
        _frontmatter(generated_on, extra={"title": module_name}),
        "",
        f"# `{module_name}`",
        "",
    ]
    overview = (mod.get("docstring") or "").strip()
    if overview:
        parts += [overview, ""]
    symbols = mod.get("symbols") or []
    if not symbols:
        parts += ["*No public symbols.*", ""]
    for sym in symbols:
        parts += _render_symbol(sym)
    return "\n".join(parts).rstrip() + "\n"


def _render_api_index(catalog: dict[str, Any], generated_on: str) -> str:
    """Render the API overview page that links every module page."""
    parts = [
        _frontmatter(generated_on, extra={"title": "API reference"}),
        "",
        "# API reference",
        "",
        "Generated from in-source docstrings via the deterministic API "
        "catalog (`framegraph docs`). Every entry below is byte-checked "
        "against the catalog in CI.",
        "",
    ]
    rows = []
    for name, mod in catalog["modules"].items():
        summary = (mod.get("docstring") or "").strip().splitlines()
        first = summary[0] if summary else ""
        n = len(mod.get("symbols") or [])
        rows.append([f"[`{name}`](./{_anchor(name)}.md)", str(n), _escape_cell(first)])
    parts += [_md_table(["Module", "Symbols", "Summary"], rows), ""]
    return "\n".join(parts).rstrip() + "\n"


def _render_schema_page(catalog: dict[str, Any], generated_on: str) -> str:
    """Render the COMPLETE schema reference from the document-model surface.

    Enumerates `catalog["schema_models"]` — the `$defs` closure of the
    document roots — so the page covers every object `type` and every
    reachable model. Completeness is enforced by
    `tests/unit/test_schema_reference_complete.py`.
    """
    sm = catalog.get("schema_models") or {}
    models = sm.get("models") or []
    object_types = sm.get("object_types") or {}
    roots = sm.get("roots") or []

    parts = [
        _frontmatter(generated_on, extra={"title": "Schema reference"}),
        "",
        "# Schema reference",
        "",
        "Complete field tables for every model reachable from the document "
        "root"
        + ("s " if len(roots) != 1 else " ")
        + ", ".join(f"`{r}`" for r in roots)
        + ". Derived structurally from `model_json_schema()`, so this page "
        "cannot omit a type the schema accepts — a CI gate "
        "(`test_schema_reference_complete`) fails the build if it ever does.",
        "",
    ]

    # Object-type index — what may appear in an `objects:` list.
    if object_types:
        parts += [
            "## Object types",
            "",
            "Every first-class `type:` value and the model that defines it.",
            "",
        ]
        rows = [[f"`{t}`", f"[`{model}`](#{model.lower()})"] for t, model in object_types.items()]
        parts += [_md_table(["`type:`", "Model"], rows), ""]

    # Per-model field tables (one `##` heading each → stable anchors).
    for m in models:
        parts += [f"## `{m['name']}`", ""]
        desc = (m.get("description") or "").strip().splitlines()
        if desc:
            parts += [desc[0], ""]
        fields = m.get("schema_fields") or []
        if not fields:
            parts += ["*No declared fields (enum, alias, or open type).*", ""]
            continue
        rows = [
            [
                f"`{f['name']}`",
                f"`{f['type']}`",
                "yes" if f.get("required") else "no",
                f.get("description", ""),
                _escape_cell(f.get("constraints", "")),
            ]
            for f in fields
        ]
        parts += [
            _md_table(["Field", "Type", "Required", "Description", "Constraints"], rows),
            "",
        ]
    return "\n".join(parts).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────
# CLI rendering
# ─────────────────────────────────────────────────────────────────


def _render_command(cmd: dict[str, Any], depth: int) -> list[str]:
    """Render one CLI command (recursively for nested sub-commands)."""
    heading = "#" * min(depth, 6)
    name = cmd.get("name", "framegraph")
    out = [f"{heading} `{name}`", ""]
    desc = (cmd.get("help") or cmd.get("description") or "").strip()
    if desc:
        out += [desc, ""]

    positionals = cmd.get("positionals") or []
    if positionals:
        rows = [
            [f"`{p['dest']}`", p.get("help", ""), ", ".join(p.get("choices", []))]
            for p in positionals
        ]
        out += ["**Arguments**", "", _md_table(["Name", "Help", "Choices"], rows), ""]

    options = cmd.get("options") or []
    if options:
        rows = []
        for o in options:
            names = ", ".join(f"`{n}`" for n in o.get("names", []))
            default = repr(o["default"]) if "default" in o else ""
            rows.append([names, o.get("help", ""), default])
        out += ["**Options**", "", _md_table(["Flag", "Help", "Default"], rows), ""]

    for sub in cmd.get("subcommands") or []:
        out += _render_command(sub, depth + 1)
    return out


def _render_cli_page(catalog: dict[str, Any], generated_on: str) -> str:
    """Render the CLI reference from the introspected argparse tree."""
    cli = catalog.get("cli") or {}
    parts = [
        _frontmatter(generated_on, extra={"title": "CLI reference"}),
        "",
        "# CLI reference",
        "",
        "Introspected directly from the live argparse parser "
        "(`framegraph.cli.build_parser`) — these flags cannot drift from "
        "the implemented command surface.",
        "",
    ]
    desc = (cli.get("description") or "").strip()
    if desc:
        parts += [desc, ""]
    for cmd in cli.get("subcommands") or []:
        parts += _render_command(cmd, depth=2)
    return "\n".join(parts).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────


def generate_pages(catalog: dict[str, Any], generated_on: str) -> dict[str, str]:
    """Render the full set of reference pages from a catalog.

    Args:
        catalog: The dict returned by `framegraph.docs.build_catalog`.
        generated_on: ISO date (``YYYY-MM-DD``) stamped into each page's
            disclaimer frontmatter. Injected rather than read from the
            clock so output is deterministic.

    Returns:
        Mapping of POSIX-style relative path (e.g.
        ``"reference/api/framegraph.md"``) to Markdown text. Insertion
        order is stable.
    """
    pages: dict[str, str] = {
        "reference/api/index.md": _render_api_index(catalog, generated_on),
        "reference/schema.md": _render_schema_page(catalog, generated_on),
        "reference/cli.md": _render_cli_page(catalog, generated_on),
    }
    for name, mod in catalog["modules"].items():
        pages[f"reference/api/{_anchor(name)}.md"] = _render_module_page(name, mod, generated_on)
    return pages


def generate_nav(catalog: dict[str, Any]) -> list[Any]:
    """Return the MkDocs ``nav`` subtree for the generated reference pages."""
    api_children: list[Any] = [{"Overview": "reference/api/index.md"}]
    for name in catalog["modules"]:
        api_children.append({name: f"reference/api/{_anchor(name)}.md"})
    return [
        {"API": api_children},
        {"Schema": "reference/schema.md"},
        {"CLI": "reference/cli.md"},
    ]


def write_pages(catalog: dict[str, Any], out_dir: Path | str, generated_on: str) -> list[Path]:
    """Write all generated pages under ``out_dir``; return the paths written.

    Parent directories are created as needed. Existing files are
    overwritten — the directory is expected to be build-only (gitignored).
    """
    base = Path(out_dir)
    written: list[Path] = []
    for rel, text in generate_pages(catalog, generated_on).items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written
