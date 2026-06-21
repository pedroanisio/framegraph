"""Docstring-coverage gate test (PALS's law).

The documentation portal is generated from docstrings; an undocumented
public symbol becomes a blank or misleading portal entry. This test
makes the gate enforceable in CI: the moment a new public class or
function lands without a docstring, the suite goes red.

See `framegraph._docsite.coverage` for the policy.
"""

from __future__ import annotations

from framegraph._docsite.coverage import (
    Gap,
    coverage_summary,
    undocumented_symbols,
)


def test_no_undocumented_public_symbols() -> None:
    """Zero public symbols may lack a docstring across the package.

    On failure the assertion message lists every gap as
    ``path:line  kind name`` so the fix is mechanical.
    """
    gaps = undocumented_symbols()
    if gaps:
        listing = "\n".join(f"  {g.path}:{g.line}  {g.kind} {g.name}" for g in gaps)
        raise AssertionError(f"{len(gaps)} undocumented public symbol(s):\n{listing}")


def test_coverage_summary_is_complete() -> None:
    """Documented counts must equal totals for every kind."""
    s = coverage_summary()
    assert s["modules_documented"] == s["modules_total"]
    assert s["classes_documented"] == s["classes_total"]
    assert s["functions_documented"] == s["functions_total"]


def test_gaps_are_sorted_and_typed() -> None:
    """`undocumented_symbols` returns a deterministic, typed list."""
    gaps = undocumented_symbols()
    assert all(isinstance(g, Gap) for g in gaps)
    assert gaps == sorted(gaps)
