"""Regression tests for drift-risk-map Finding #6 — catalog-count drift in docs.

The 375-pattern catalog and 17-sidecar count are spread across README.md,
AGENTS.md, docs/AUTHORING-FILLS.md, and docs/PUBLISHING.md as literal numbers.
Tests verifying the catalog size already exist
(`tests/integration/test_cli_patterns.py`) — Finding #1's fix wired pytest
into CI, so those count checks are now enforced. This file extends the
contract to *documentation*: every literal count claim near "pattern" or
"sidecar" in an active doc must match the live catalog.

These tests run cheap regexes over the active-doc set. Historical docs
(`docs/archive/`, `ROADMAP-*.md`, `ANALYSIS.md`) are exempt; those are
frozen snapshots.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import framegraph
from framegraph._patterns import load_pattern_catalog

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def live_pattern_count() -> int:
    return len(load_pattern_catalog().slide_template_patterns)


@pytest.fixture(scope="module")
def live_sidecar_count() -> int:
    fills_dir = Path(framegraph.__file__).parent / "data" / "fills"
    return sum(1 for _ in fills_dir.glob("*.yml"))


# Active docs that publish catalog-count claims. The drift-risk map
# explicitly lists these as dependents in Finding #6.
ACTIVE_COUNT_DOCS = [
    "README.md",
    "AGENTS.md",
    "docs/AUTHORING-FILLS.md",
    "docs/PUBLISHING.md",
]

# Patterns that announce the *total catalog size*. These are the load-bearing
# claims a maintainer would expect to update on a catalog expansion. Narrower
# than "<N> patterns" prose — "17-pattern comparison-table family" is a
# subset claim, not a catalog-size claim, and must not match.
_CATALOG_SIZE_PATTERNS = [
    re.compile(r"all\s+(\d{2,4})\s+patterns", re.IGNORECASE),  # "all 375 patterns"
    re.compile(r"(\d{2,4})-pattern\s+catalog", re.IGNORECASE),  # "375-pattern catalog"
    re.compile(r"(\d{2,4})\s+of\s+them,\s+ids", re.IGNORECASE),  # "375 of them, ids 1–375"
    re.compile(r"\bof\s+all\s+(\d{2,4})\s+patterns", re.IGNORECASE),
    re.compile(r"list\s+of\s+all\s+(\d{2,4})\s+patterns", re.IGNORECASE),
]

# Patterns that announce the *sidecar inventory size*.
_SIDECAR_COUNT_PATTERNS = [
    re.compile(r"(\d{1,4})\s+curated\s+`example_fill`\s+sidecar", re.IGNORECASE),
    re.compile(r"(\d{1,4})\s+curated\s+sidecar", re.IGNORECASE),
    re.compile(r"the\s+(\d{1,4})\s+shipped", re.IGNORECASE),
    re.compile(r"only\s+the\s+curated\s+(\d{1,4})", re.IGNORECASE),
]


@pytest.mark.parametrize("doc_path", ACTIVE_COUNT_DOCS)
def test_pattern_count_claims_match_live_catalog(doc_path: str, live_pattern_count: int) -> None:
    """Every `<N> patterns` claim in an active doc must equal the live count.

    Catches Finding #6's count drift. Before this guard, "375" or "50"
    could appear in prose for arbitrary reasons — the catalog could grow
    and the docs would lie silently. The regex is conservative; it
    catches forms like "all 375 patterns", "375-pattern catalog",
    "375 of them".
    """
    text = (ROOT / doc_path).read_text(encoding="utf-8")
    for pat in _CATALOG_SIZE_PATTERNS:
        for match in pat.finditer(text):
            found = int(match.group(1))
            assert found == live_pattern_count, (
                f"{doc_path} claims '{match.group(0)}' but the live catalog has "
                f"{live_pattern_count} patterns. Update the doc or query the "
                f"live count via `framegraph patterns list --json | jq length` "
                f"instead of hard-coding it."
            )


@pytest.mark.parametrize("doc_path", ACTIVE_COUNT_DOCS)
def test_sidecar_count_claims_match_live_count(doc_path: str, live_sidecar_count: int) -> None:
    """Every `<N> sidecars` / `<N> shipped` claim must equal the live count."""
    text = (ROOT / doc_path).read_text(encoding="utf-8")
    for pat in _SIDECAR_COUNT_PATTERNS:
        for match in pat.finditer(text):
            found = int(match.group(1))
            assert found == live_sidecar_count, (
                f"{doc_path} claims '{match.group(0)}' but the live count is "
                f"{live_sidecar_count} sidecars. Update the doc or query via "
                f"`framegraph patterns list --has-sidecar --json | jq length`."
            )


def test_pattern_id_range_claim_matches_live(live_pattern_count: int) -> None:
    """The 'ids 1–375' range claim in AUTHORING-FILLS.md must match the live max id."""
    text = (ROOT / "docs" / "AUTHORING-FILLS.md").read_text(encoding="utf-8")
    range_matches = re.findall(r"ids?\s+1\s*[–—-]\s*(\d{2,4})", text)
    for upper in range_matches:
        assert int(upper) == live_pattern_count, (
            f"docs/AUTHORING-FILLS.md claims pattern ids 1–{upper}, but the live "
            f"catalog has {live_pattern_count} patterns."
        )
