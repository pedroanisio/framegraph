"""Regression test for drift-risk-map Finding #3 — stale pattern-count claim.

`framegraph/_patterns.py` previously documented the catalog as
"50 canonical slide-template patterns", but the live loader returns 375.
The number is data-driven and must not be hard-coded in docstrings, because
hand-mirrored counts always go stale the moment patterns are added or removed.

This test pins the contract: the module docstring and the
`PATTERN_CATALOG_PATH` docstring must not embed an arbitrary integer count
for the pattern set. The authoritative figure is
`len(load_pattern_catalog().slide_template_patterns)`.
"""

from __future__ import annotations

import inspect
import re

import framegraph._patterns as patterns_mod
from framegraph._patterns import load_pattern_catalog

# Numbers that, if found in the module's documentation strings, indicate
# a hand-mirrored count. Restricted to 2+ digits to avoid false positives
# on "Phase 2", "9 cells", etc. that legitimately appear in the docstring.
_COUNT_PATTERN = re.compile(r"\b(\d{2,})\s+(?:canonical|slide-template|patterns?)\b", re.IGNORECASE)


def test_module_docstring_has_no_hardcoded_pattern_count() -> None:
    """The `_patterns` module docstring must not hard-code a pattern count.

    Finding #3 of the drift-risk map: an old "50 canonical slide-template
    patterns" claim survived a catalog expansion to 375. Hand-mirrored
    counts drift silently; the loaded catalog is the only source of truth.
    """
    doc = inspect.getdoc(patterns_mod) or ""
    matches = _COUNT_PATTERN.findall(doc)
    assert not matches, (
        f"`framegraph/_patterns.py` module docstring embeds a hard-coded "
        f"pattern count ({matches}). Remove the literal — the loaded "
        f"catalog has {len(load_pattern_catalog().slide_template_patterns)} "
        "patterns and that figure is data-driven."
    )


def test_pattern_catalog_path_docstring_has_no_hardcoded_count() -> None:
    """`PATTERN_CATALOG_PATH`'s attribute docstring must not hard-code a count."""
    # Attribute docstrings (PEP 257) aren't accessible via __doc__, so inspect
    # the source file directly for the literal-block string that follows the
    # PATTERN_CATALOG_PATH assignment.
    source = inspect.getsource(patterns_mod)
    # Capture the triple-quoted string immediately after PATTERN_CATALOG_PATH = …
    match = re.search(
        r'PATTERN_CATALOG_PATH:\s*Path\s*=.*?\n"""(.*?)"""',
        source,
        flags=re.DOTALL,
    )
    assert match is not None, "could not locate PATTERN_CATALOG_PATH docstring"
    attr_doc = match.group(1)
    stale = _COUNT_PATTERN.findall(attr_doc)
    assert not stale, (
        f"`PATTERN_CATALOG_PATH` docstring embeds a hard-coded count {stale}; "
        "the figure is data-driven and must not be mirrored in prose."
    )


def test_live_catalog_size_is_recoverable() -> None:
    """Sanity: the live catalog still loads and exposes a non-trivial count.

    This is the affirmative side of the drift guard — if a real regression
    silently zeroed the loaded catalog, this test fires.
    """
    cat = load_pattern_catalog()
    assert len(cat.slide_template_patterns) > 0, "catalog loaded empty"
