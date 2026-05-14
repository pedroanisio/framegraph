"""Regression tests for drift-risk-map Finding #4 — documented Python API gaps.

The README, AGENTS.md, and docs/MANUAL.md instruct users to call
`FrameGraphLibrary(...).list_themes()`. Before this fix the method did not
exist, so anyone following the documented snippet got an `AttributeError`.

These tests pin the *documented* surface: every method the docs tell a
human or agent to call must exist, be callable, and return data of the
expected shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph import FrameGraphLibrary

ROOT = Path(__file__).resolve().parents[2]
LIB_PATH = ROOT / "framegraph" / "lib"


@pytest.fixture(scope="module")
def lib() -> FrameGraphLibrary:
    return FrameGraphLibrary(LIB_PATH)


def test_library_list_themes_is_callable(lib: FrameGraphLibrary) -> None:
    """The documented `list_themes()` method must exist and return a list of theme ids.

    Drift-risk-map Finding #4: docs instructed users to call
    `FrameGraphLibrary(...).list_themes()`, but the method did not exist
    until this regression guard was added.
    """
    themes = lib.list_themes()
    assert isinstance(themes, list)
    assert all(isinstance(t, str) for t in themes)
    assert themes == sorted(themes), "themes should be sorted"


def test_list_themes_matches_token_ids(lib: FrameGraphLibrary) -> None:
    """`list_themes()` must be equivalent to the canonical `token_ids()`.

    The shim must not silently diverge from the canonical implementation.
    """
    assert lib.list_themes() == lib.token_ids()


def test_documented_themes_are_loadable(lib: FrameGraphLibrary) -> None:
    """Every theme `list_themes()` returns must successfully load via `load_tokens`.

    Closes the loop: a theme id appearing in the documented enumeration must
    actually be a usable id — not an orphan filename that breaks at load time.
    """
    for theme_id in lib.list_themes():
        tokens = lib.load_tokens(theme_id)
        assert isinstance(tokens, dict), f"theme '{theme_id}' did not load to a dict"


def test_documented_consulting_themes_present(lib: FrameGraphLibrary) -> None:
    """AGENTS.md advertises specific consulting themes; ensure they are all present.

    AGENTS.md line ~85 lists `bain, bcg, deloitte, ey, kpmg, mckinsey, pwc`
    as available themes for `$theme:`. Drift would mean a documented theme
    was renamed or removed without updating the advertised set.
    """
    advertised = {"bain", "bcg", "deloitte", "ey", "kpmg", "mckinsey", "pwc"}
    available = set(lib.list_themes())
    missing = advertised - available
    assert not missing, (
        f"Themes advertised in AGENTS.md are missing from the library: {sorted(missing)}. "
        f"Available: {sorted(available)}"
    )
