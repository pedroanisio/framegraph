"""Regression tests for drift-risk-map Finding #5 — stale `static/refs/*` paths.

Active fill-authoring docs once referenced a legacy `static/refs/` tree that
was migrated to `framegraph/data/` when packaging data moved under the wheel.
Anyone following the stale paths edited the wrong tree.

These tests pin the contract: no active fill-authoring doc may reference the
legacy `static/refs/` location. Historical/archival docs (`docs/archive/*`,
`ROADMAP-*.md`, `ANALYSIS.md`) are exempt — those are frozen snapshots and
mutating them rewrites history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Docs the drift-risk-map names as active dependents of the pattern/sidecar
# packaging layout. If a new active fill-authoring doc lands, add it here.
ACTIVE_FILL_AUTHORING_DOCS = [
    "docs/AUTHORING-FILLS.md",
    "docs/MANUAL.md",
    "AGENTS.md",
    "README.md",
]


@pytest.mark.parametrize("doc_path", ACTIVE_FILL_AUTHORING_DOCS)
def test_active_doc_does_not_reference_static_refs(doc_path: str) -> None:
    """Active fill-authoring docs must not reference the legacy `static/refs/` tree.

    Catches Finding #5's stale-path drift. The packaged data lives under
    `framegraph/data/`; `static/refs/` was the layout before the catalog
    became wheel-shipped package data.
    """
    text = (ROOT / doc_path).read_text(encoding="utf-8")
    lines = [(i + 1, line) for i, line in enumerate(text.splitlines()) if "static/refs" in line]
    assert not lines, (
        f"{doc_path} still references the legacy `static/refs/` location on "
        f"line(s) {[i for i, _ in lines]}. Migrate to `framegraph/data/` — "
        f"that is where the packaged catalog and sidecars live."
    )


@pytest.mark.parametrize("doc_path", ACTIVE_FILL_AUTHORING_DOCS)
def test_referenced_framegraph_data_files_exist(doc_path: str) -> None:
    """Every `framegraph/data/...` path advertised in active docs must exist.

    Closes the loop: doc fix → real path. If a future edit points at a
    nonexistent sidecar or pattern file, the doc itself becomes the
    misleading thing the original Finding warned about.
    """
    import re

    text = (ROOT / doc_path).read_text(encoding="utf-8")
    # Match framegraph/data/<rest>.yml (no whitespace, no closing bracket/quote)
    referenced = set(re.findall(r"framegraph/data/[A-Za-z0-9_./-]+\.yml", text))
    missing = sorted(p for p in referenced if not (ROOT / p).is_file())
    assert not missing, f"{doc_path} references nonexistent file(s): {missing}"
