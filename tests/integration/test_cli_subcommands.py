"""Regression tests for drift-risk-map Finding #3 — agent-facing docs drift.

The `framegraph docs` catalog and the `build_parser()` docstring are the
grounding artefacts an LLM agent reads to learn the CLI surface. They are
generated from free-form docstrings, so they silently drift when subcommands
are added or removed.

These tests pin the docstring to the live parser:

  * `build_parser()` must mention every live top-level subcommand in its
    `Returns:` docstring (caught Finding #3's "only render/deck/version
    documented" drift).
  * Nested `patterns` subcommands must also be enumerated.

Pair with `tests/unit/test_patterns_docstring_drift.py` which guards the
sibling pattern-count drift in `framegraph/_patterns.py`.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
from pathlib import Path

import pytest

from framegraph.cli import build_parser, main

# Live subcommand inventory — derived from the parser, not hand-mirrored.
# `test_live_parser_exposes_expected_subcommands` keeps this set honest.
LIVE_TOP_LEVEL_SUBCOMMANDS = {
    "render",
    "deck",
    "validate",
    "docs",
    "sitemap",
    "version",
    "patterns",
}
LIVE_PATTERNS_SUBCOMMANDS = {"list", "show", "example", "build", "deck"}


def _parser_top_level_subcommands() -> set[str]:
    """Introspect the live parser for top-level subcommand names."""
    parser = build_parser()
    choices: set[str] = set()
    for action in parser._actions:  # noqa: SLF001 — argparse public-API gap
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            choices.update(action.choices.keys())
    return choices


def test_live_parser_exposes_expected_subcommands() -> None:
    """Sanity check: the inventory the docstring test uses matches reality.

    If a new top-level subcommand is added, this test fails first so the
    maintainer is forced to update both the inventory above and the
    `build_parser()` docstring in `framegraph/cli.py`.
    """
    assert _parser_top_level_subcommands() == LIVE_TOP_LEVEL_SUBCOMMANDS


def test_build_parser_docstring_lists_every_subcommand() -> None:
    """`build_parser()` docstring must enumerate every live top-level subcommand.

    Catches Finding #3's stale-docstring drift, where `render`, `deck`,
    `version` were the only subcommands listed even though `validate`,
    `docs`, `sitemap`, `patterns` were live.
    """
    doc = inspect.getdoc(build_parser) or ""
    missing = [name for name in LIVE_TOP_LEVEL_SUBCOMMANDS if name not in doc]
    assert not missing, (
        f"`build_parser()` docstring is missing live subcommand(s): {sorted(missing)}. "
        "Update the docstring in framegraph/cli.py to keep `framegraph docs` "
        "catalog output aligned with the live CLI surface."
    )


def test_build_parser_docstring_lists_nested_patterns_subcommands() -> None:
    """Nested `patterns` subcommands must also appear in the docstring."""
    doc = inspect.getdoc(build_parser) or ""
    missing = [name for name in LIVE_PATTERNS_SUBCOMMANDS if name not in doc]
    assert not missing, (
        f"`build_parser()` docstring is missing nested patterns subcommand(s): {sorted(missing)}."
    )


def test_docs_catalog_renders_without_error(tmp_path: Path) -> None:
    """`framegraph docs` must produce a non-empty catalog with module entries.

    The catalog is the agent's grounding artefact; if rendering breaks, every
    downstream agent loses its grip on the public API. This is a structural
    smoke test — the semantic CLI-surface drift guard is the
    `test_build_parser_docstring_lists_every_subcommand` test above, which
    pins the docstring that an agent reads from `framegraph <sub> --help`.
    """
    out = tmp_path / "catalog.json"
    rc = main(["docs", "-o", str(out)])
    assert rc == 0
    catalog = json.loads(out.read_text(encoding="utf-8"))
    assert catalog["modules"], "catalog has empty modules map"
    assert "framegraph" in catalog["modules"], "top-level framegraph module missing"


@pytest.mark.parametrize("subcommand", sorted(LIVE_TOP_LEVEL_SUBCOMMANDS - {"patterns"}))
def test_subcommand_help_runs(subcommand: str) -> None:
    """Every advertised subcommand must have a working `--help` page.

    Smoke test that prevents a documentation entry from pointing at a
    non-existent or broken subcommand handler. Invoked in-process via
    `main()` so the test does not depend on console-script install state.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit) as excinfo:
        main([subcommand, "--help"])
    # argparse exits 0 on --help.
    assert excinfo.value.code == 0, f"`framegraph {subcommand} --help` exited {excinfo.value.code}"
    assert buf.getvalue(), f"`framegraph {subcommand} --help` produced no output"


@pytest.mark.parametrize("subcommand", sorted(LIVE_PATTERNS_SUBCOMMANDS))
def test_patterns_subcommand_help_runs(subcommand: str) -> None:
    """Nested `patterns <sub>` --help must also work."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit) as excinfo:
        main(["patterns", subcommand, "--help"])
    assert excinfo.value.code == 0, (
        f"`framegraph patterns {subcommand} --help` exited {excinfo.value.code}"
    )
    assert buf.getvalue(), f"`framegraph patterns {subcommand} --help` produced no output"
