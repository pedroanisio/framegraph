"""Regression tests for drift-risk-map Finding #2 — version-literal drift.

The package version must have exactly one source of truth: the
`[project] version` key in `pyproject.toml`. Runtime callers
(`framegraph.__version__`, `framegraph version`, `framegraph docs`)
must derive their value from package metadata rather than hand-mirrored
literals.

These tests fail loudly if a maintainer reintroduces a hard-coded
version literal anywhere on the runtime path, and they verify that
the runtime surfaces all agree with one another.
"""

from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
INIT_PY = ROOT / "framegraph" / "__init__.py"
MAKEFILE = ROOT / "Makefile"
STANDARDS = ROOT / "codebase-standards.md"


def _pyproject_version() -> str:
    """Return the version string from `pyproject.toml` (`[project]` table)."""
    in_project = False
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise AssertionError("could not find version in pyproject.toml [project]")


def _installed_version_matches_source() -> bool:
    """True iff `framegraph` is installed from the current source tree.

    The CI matrix always installs `pip install -e ".[test]"` from the
    checkout, so the installed metadata matches pyproject. But a developer
    workstation can have a stale wheel from a previous install (e.g. an
    older PyPI build) sitting in `site-packages`. In that case the
    pyproject-vs-installed comparison is environment noise, not drift in
    the code under test. Skip those assertions when the install is stale;
    the within-runtime consistency assertions still run.
    """
    import framegraph

    return framegraph.__version__ == _pyproject_version()


def test_runtime_version_matches_pyproject() -> None:
    """`framegraph.__version__` must equal `pyproject.toml [project] version`.

    The runtime resolves `__version__` via `importlib.metadata.version`,
    with a pyproject-parsing fallback. Under a fresh editable install,
    these two strings must agree. A mismatch means either:
      (a) the editable install is stale — `pip install -e .` to refresh, or
      (b) someone reintroduced a hard-coded literal.
    """
    import framegraph

    expected = _pyproject_version()
    if framegraph.__version__ != expected:
        pytest.fail(
            f"framegraph.__version__ ({framegraph.__version__!r}) does not match "
            f"pyproject.toml [project] version ({expected!r}). If the package was "
            "installed from an older wheel, refresh with `pip install -e .`. If "
            "the literal was reintroduced in framegraph/__init__.py, remove it — "
            "the runtime must read version from importlib.metadata."
        )


def test_cli_version_subcommand_matches_runtime() -> None:
    """`framegraph version` must print the same version as `framegraph.__version__`.

    Calls `framegraph.cli.main(["version"])` in-process so the test is
    independent of console-script install state. The two values are both
    runtime surfaces; they must always agree, regardless of install state.
    """
    import framegraph
    from framegraph.cli import main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["version"])
    assert rc == 0
    assert buf.getvalue().strip() == f"framegraph {framegraph.__version__}"


def test_docs_catalog_version_matches_runtime(tmp_path: Path) -> None:
    """`framegraph docs` output must embed `framegraph.__version__`.

    Closes the loop runtime → catalog. Combined with the previous test,
    this guarantees: pyproject == __version__ == `version` command ==
    catalog["package"]["version"].
    """
    import framegraph
    from framegraph.cli import main

    out = tmp_path / "catalog.json"
    rc = main(["docs", "-o", str(out)])
    assert rc == 0
    catalog = json.loads(out.read_text(encoding="utf-8"))
    assert catalog["package"]["version"] == framegraph.__version__


def test_init_py_has_no_hardcoded_version_literal() -> None:
    """`framegraph/__init__.py` must not assign `__version__` to a SemVer literal.

    The version must come from `importlib.metadata.version("framegraph")`
    (or a pyproject-parsing fallback). A hard-coded SemVer string here is
    exactly the drift Finding #2 calls out — it gets out of sync with
    `pyproject.toml` whenever a maintainer bumps only one side.
    """
    text = INIT_PY.read_text(encoding="utf-8")
    matches = re.findall(r'^__version__\s*=\s*"\d+\.\d+\.\d+"', text, flags=re.MULTILINE)
    assert matches == [], (
        f"Hard-coded version literal(s) reintroduced in framegraph/__init__.py: {matches}. "
        "Use importlib.metadata.version('framegraph') instead."
    )


def test_resolve_version_reads_pyproject() -> None:
    """`_version.resolve_version()` returns the live `pyproject.toml` version."""
    from framegraph._version import resolve_version

    assert resolve_version() == _pyproject_version()


def test_resolve_version_returns_sentinel_when_pyproject_missing(tmp_path: Path) -> None:
    """Missing pyproject returns the `0+unknown` PEP 440 sentinel, not a crash."""
    from framegraph._version import resolve_version

    assert resolve_version(pyproject=tmp_path / "nonexistent.toml") == "0+unknown"


def test_resolve_version_returns_sentinel_when_version_line_missing(tmp_path: Path) -> None:
    """A pyproject without a `[project] version = ...` line returns the sentinel.

    Guards the inner exhausted-loop branch — without it, a malformed pyproject
    would let an undefined variable escape into `__version__`.
    """
    from framegraph._version import resolve_version

    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert resolve_version(pyproject=p) == "0+unknown"


def test_pyproject_fallback_recovers_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-importing `framegraph` with `importlib.metadata` failing must fall back to pyproject.

    Simulates the "uninstalled source-tree" case: the package can be imported
    directly from the checkout (PYTHONPATH=.) without being pip-installed, in
    which case `importlib.metadata.version("framegraph")` raises
    `PackageNotFoundError`. The fallback reads `pyproject.toml` so
    `__version__` is still meaningful instead of crashing the import.
    """
    import importlib

    import framegraph

    def _raise(_name: str) -> str:
        from importlib.metadata import PackageNotFoundError

        raise PackageNotFoundError("framegraph")

    monkeypatch.setattr("importlib.metadata.version", _raise)
    reloaded = importlib.reload(framegraph)
    try:
        assert reloaded.__version__ == _pyproject_version(), (
            "pyproject fallback in framegraph/__init__.py did not recover the version "
            "when importlib.metadata.version() raised PackageNotFoundError."
        )
    finally:
        # Restore the cleanly-installed module so later tests in the session
        # see the importlib.metadata-derived value, not the fallback.
        monkeypatch.undo()
        importlib.reload(framegraph)


@pytest.mark.parametrize("doc_path", ["README.md", "docs/PUBLISHING.md"])
def test_doc_version_assignment_lines_match_pyproject(doc_path: str) -> None:
    """Sanity-check: docs embedding the literal `pyproject.toml` version line stay aligned.

    Soft guard. Docs intentionally show *example* versions in release recipes
    (e.g. "publishes 0.2.0"); those are not policed. Only the exact form
    `version = "X.Y.Z"` (the pyproject assignment) is checked, because that's
    the form a maintainer copy-pastes from a release doc into pyproject.

    Skipped when the installed framegraph version disagrees with pyproject —
    in that case the developer's environment is the variable, not the doc.
    """
    if not _installed_version_matches_source():
        pytest.skip("installed framegraph version does not match source pyproject")

    expected = _pyproject_version()
    text = (ROOT / doc_path).read_text(encoding="utf-8")
    pyproject_lines = re.findall(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, flags=re.MULTILINE)
    for found in pyproject_lines:
        assert found == expected, (
            f'{doc_path} embeds a literal `version = "{found}"` line that '
            f"disagrees with pyproject.toml ({expected})."
        )


def test_release_prose_names_single_version_source() -> None:
    """Release instructions must not describe the obsolete two-site version bump."""
    stale_fragments = [
        "pyproject.toml + __init__.py",
        "two version sites",
        "two-site",
    ]
    checked = {
        "Makefile": MAKEFILE.read_text(encoding="utf-8"),
        "pyproject.toml": PYPROJECT.read_text(encoding="utf-8"),
    }

    for path, text in checked.items():
        for fragment in stale_fragments:
            assert fragment not in text, (
                f"{path} still contains stale release/version prose {fragment!r}; "
                "the single source of truth is pyproject.toml [project] version."
            )


def test_standards_no_longer_list_release_version_prose_as_drift() -> None:
    """Resolved standards discrepancies should be removed instead of fossilized."""
    text = STANDARDS.read_text(encoding="utf-8")

    assert "Makefile version prose vs recipe" not in text
