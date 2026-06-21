"""Unit tests for `framegraph._docsite.generate` — catalog → Markdown.

The generator is a pure function of the catalog, so these tests assert
structural invariants (determinism, page set, frontmatter, field tables,
CLI coverage) rather than a brittle byte snapshot of evolving docstrings.
"""

from __future__ import annotations

from typing import Any

import pytest

from framegraph._docsite.generate import (
    DISCLAIMER_NOTICE,
    generate_nav,
    generate_pages,
    write_pages,
)
from framegraph.docs import build_catalog

DATE = "2026-01-01"


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return build_catalog()


@pytest.fixture(scope="module")
def pages(catalog: dict[str, Any]) -> dict[str, str]:
    return generate_pages(catalog, DATE)


class TestPageSet:
    """The expected reference pages are produced."""

    def test_core_pages_present(self, pages: dict[str, str]) -> None:
        assert "reference/api/index.md" in pages
        assert "reference/schema.md" in pages
        assert "reference/cli.md" in pages

    def test_one_page_per_module(self, pages: dict[str, str], catalog: dict[str, Any]) -> None:
        for name in catalog["modules"]:
            key = "reference/api/" + name.replace(".", "-").lstrip("-") + ".md"
            assert key in pages, f"missing module page: {key}"

    def test_every_page_nonempty_markdown(self, pages: dict[str, str]) -> None:
        for path, text in pages.items():
            assert text.strip(), f"empty page: {path}"
            assert text.endswith("\n")


class TestDeterminism:
    """Same catalog + same date → byte-identical output (CI drift safe)."""

    def test_pages_deterministic(self, catalog: dict[str, Any]) -> None:
        a = generate_pages(catalog, DATE)
        b = generate_pages(build_catalog(), DATE)
        assert a == b


class TestDisclaimerCompliance:
    """CLAUDE.md rule 5: every generated Markdown carries the disclaimer."""

    def test_all_pages_have_frontmatter(self, pages: dict[str, str]) -> None:
        for path, text in pages.items():
            assert text.startswith("---\n"), path
            assert DISCLAIMER_NOTICE in text, path
            assert f'date: "{DATE}"' in text, path

    def test_date_is_injected_not_clocked(self, catalog: dict[str, Any]) -> None:
        other = generate_pages(catalog, "1999-12-31")
        assert all('date: "1999-12-31"' in t for t in other.values())


class TestSchemaPage:
    """The schema reference renders model field tables."""

    def test_known_model_rendered_with_fields(self, pages: dict[str, str]) -> None:
        schema = pages["reference/schema.md"]
        # `RectObject` is a stable document object-type model.
        assert "## `RectObject`" in schema
        assert "| Field | Type | Required | Description | Constraints |" in schema
        assert "`id`" in schema

    def test_object_type_index_present(self, pages: dict[str, str]) -> None:
        schema = pages["reference/schema.md"]
        assert "## Object types" in schema
        # The `type:` value and its model both appear.
        assert "`rect`" in schema and "`RectObject`" in schema


class TestCliPage:
    """The CLI reference renders every introspected command."""

    def test_top_level_commands_have_sections(self, pages: dict[str, str]) -> None:
        cli = pages["reference/cli.md"]
        for cmd in ("render", "deck", "validate", "docs", "sitemap"):
            assert f"## `{cmd}`" in cli, f"missing CLI command section: {cmd}"

    def test_render_options_table_present(self, pages: dict[str, str]) -> None:
        cli = pages["reference/cli.md"]
        assert "**Options**" in cli
        assert "`--output`" in cli


class TestNav:
    """`generate_nav` returns a MkDocs-shaped nav subtree."""

    def test_nav_structure(self, catalog: dict[str, Any]) -> None:
        nav = generate_nav(catalog)
        keys = [list(entry)[0] for entry in nav]
        assert keys == ["API", "Schema", "CLI"]
        api = nav[0]["API"]
        # Overview plus one entry per module.
        assert len(api) == 1 + len(catalog["modules"])


class TestWritePages:
    """`write_pages` materializes the page set on disk."""

    def test_writes_all_pages(self, tmp_path: Any, catalog: dict[str, Any]) -> None:
        written = write_pages(catalog, tmp_path, DATE)
        assert written
        for p in written:
            assert p.exists()
            assert p.read_text(encoding="utf-8").startswith("---\n")
        # index + schema + cli + one per module
        assert len(written) == 3 + len(catalog["modules"])
