"""Regression tests for drift-risk-map Finding #7 — wheel-data contract drift.

`pyproject.toml`'s `[tool.setuptools.package-data]` manifest declares which
non-`.py` files travel with the wheel. Source-tree development cannot detect
when a new data file is *not* listed — it works locally but fails after
`pip install`. Before this guard, that gap was only caught in the tag-triggered
publish job.

These tests do the source-tree side of the contract verification: every file
the runtime loaders reach for must be declared by a glob in
`[tool.setuptools.package-data]`. The CI `wheel-smoke` job does the install-time
side by building the wheel and exercising the packaged loaders end-to-end.

Together they catch package-data drift at PR time instead of release time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "framegraph"
PYPROJECT = ROOT / "pyproject.toml"


def _declared_package_data_globs() -> list[str]:
    """Extract the `framegraph` entries from `[tool.setuptools.package-data]`.

    Hand-parses the TOML rather than depending on `tomllib`, since this test
    needs to run under Python 3.10 (where `tomllib` is unavailable) and the
    shape is trivial.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    # Find the [tool.setuptools.package-data] section, then capture the
    # `framegraph = [ ... ]` list within it.
    match = re.search(
        r"\[tool\.setuptools\.package-data\]\s*\n"
        r"framegraph\s*=\s*\[(?P<body>.*?)\]",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, (
        "Could not find `framegraph = [...]` under "
        "`[tool.setuptools.package-data]` in pyproject.toml"
    )
    body = match.group("body")
    return re.findall(r'"([^"]+)"', body)


def _matches_any_glob(rel_path: str, globs: list[str]) -> bool:
    """True iff `rel_path` (relative to `framegraph/`) matches any declared glob."""
    p = Path(rel_path)
    for g in globs:
        if p.match(g):
            return True
        # Path.match has weaker semantics than the setuptools glob:
        # `lib/symbols/**/*.yml` must match nested dirs. Fall back to a
        # manual prefix-suffix check for double-star globs.
        if "**" in g:
            prefix, suffix = g.split("**", 1)
            if rel_path.startswith(prefix) and Path(rel_path).match("*" + suffix):
                return True
    return False


def test_pattern_catalogs_are_declared_as_package_data() -> None:
    """Every `framegraph/data/patterns/*.yml` file must be declared package data.

    If a new pattern catalog is added to `data/patterns/` without updating
    `pyproject.toml`'s package-data manifest, it ships missing from the wheel
    — and runtime loaders raise `FileNotFoundError` after `pip install`.
    """
    globs = _declared_package_data_globs()
    patterns_dir = PACKAGE_ROOT / "data" / "patterns"
    if not patterns_dir.is_dir():
        pytest.skip("framegraph/data/patterns/ does not exist")
    for yml in patterns_dir.glob("*.yml"):
        rel = yml.relative_to(PACKAGE_ROOT).as_posix()
        assert _matches_any_glob(rel, globs), (
            f"Pattern catalog `{rel}` is not covered by any "
            f"`[tool.setuptools.package-data]` glob in pyproject.toml. "
            f"The file will be missing from the built wheel. "
            f"Add it (or the appropriate glob) to package-data."
        )


def test_sidecars_are_declared_as_package_data() -> None:
    """Every `framegraph/data/fills/*.yml` sidecar must be declared package data."""
    globs = _declared_package_data_globs()
    fills_dir = PACKAGE_ROOT / "data" / "fills"
    if not fills_dir.is_dir():
        pytest.skip("framegraph/data/fills/ does not exist")
    for yml in fills_dir.glob("*.yml"):
        rel = yml.relative_to(PACKAGE_ROOT).as_posix()
        assert _matches_any_glob(rel, globs), (
            f"Sidecar `{rel}` is not covered by any package-data glob. "
            f"It will be missing from the built wheel."
        )


def test_library_tokens_and_symbols_are_declared() -> None:
    """Token packs and symbol packs under `framegraph/lib/` must be declared."""
    globs = _declared_package_data_globs()
    lib_dir = PACKAGE_ROOT / "lib"
    if not lib_dir.is_dir():
        pytest.skip("framegraph/lib/ does not exist")
    for yml in lib_dir.rglob("*.yml"):
        rel = yml.relative_to(PACKAGE_ROOT).as_posix()
        assert _matches_any_glob(rel, globs), (
            f"Library asset `{rel}` is not covered by any package-data glob. "
            f"The wheel will install without it."
        )


def test_py_typed_marker_is_declared() -> None:
    """The PEP 561 `py.typed` marker must be declared package data."""
    globs = _declared_package_data_globs()
    marker = PACKAGE_ROOT / "py.typed"
    if not marker.is_file():
        pytest.skip("framegraph/py.typed does not exist")
    assert _matches_any_glob("py.typed", globs), (
        "framegraph/py.typed exists but is not declared in "
        "`[tool.setuptools.package-data]`. Type checkers consuming the "
        "installed wheel will treat the package as untyped."
    )
