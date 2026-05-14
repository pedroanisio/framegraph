"""Regression tests for drift-risk-map Finding #8 — fill-contract docs drift.

The default `content_type → Pydantic shape` table is restated by hand in
`AGENTS.md` and `docs/AUTHORING-FILLS.md`. It is currently in sync with
`framegraph.patterns.fill._DEFAULT_TYPES`, but a future schema change can
silently stale both docs while runtime validation keeps working.

These tests pin the contract: the set of `content_type` keys advertised in
each doc must match `_DEFAULT_TYPES.keys()` exactly. The test does not
police the rendered shape strings — those are hand-readable approximations
of the Pydantic shape — but the key-set drift is the load-bearing failure
mode: a new `content_type` added to the code without doc updates makes the
docs lie to authors.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from framegraph.patterns.fill import _DEFAULT_TYPES

ROOT = Path(__file__).resolve().parents[2]

# Active docs that publish the default-shape table.
FILL_CONTRACT_DOCS = [
    "AGENTS.md",
    "docs/AUTHORING-FILLS.md",
]


def _extract_content_type_keys_from_markdown(text: str) -> set[str]:
    """Return the set of `content_type` keys mentioned in any Markdown table row.

    A table row looks like:
        | `title_body` | `{title: str, body: str \\| None}` |

    The regex matches a backtick-quoted identifier in the first table cell.
    Restricted to the table that mentions Pydantic shapes by requiring the
    surrounding context to include the literal heading "Default Pydantic
    shape" (or its variant) — otherwise unrelated backtick identifiers in
    other tables would be swept in.
    """
    # Find every table whose header row contains "Default Pydantic shape"
    # or "Default content shape". Then extract first-column backtick keys.
    keys: set[str] = set()
    lines = text.splitlines()
    in_target_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and (
            "Default Pydantic shape" in line or "Default content shape" in line
        ):
            in_target_table = True
            continue
        if in_target_table:
            if not stripped.startswith("|"):
                # Table ended.
                in_target_table = False
                continue
            if set(stripped) <= set("|-: "):
                # Separator row like `|---|---|`
                continue
            # First-column backticked identifier.
            m = re.match(r"\|\s*`([a-z_][a-z0-9_]*)`", stripped)
            if m:
                keys.add(m.group(1))
    return keys


@pytest.mark.parametrize("doc_path", FILL_CONTRACT_DOCS)
def test_default_content_type_table_matches_live_keys(doc_path: str) -> None:
    """Each doc's default-shapes table must list exactly the live `_DEFAULT_TYPES` keys.

    Finding #8: a future schema change (new content_type, renamed key,
    removed key) silently stales these tables. This guard fails CI the
    moment the key sets drift.
    """
    text = (ROOT / doc_path).read_text(encoding="utf-8")
    doc_keys = _extract_content_type_keys_from_markdown(text)
    live_keys = set(_DEFAULT_TYPES.keys())

    missing_from_doc = live_keys - doc_keys
    extra_in_doc = doc_keys - live_keys

    assert not missing_from_doc and not extra_in_doc, (
        f"{doc_path} default-shapes table is out of sync with "
        f"framegraph.patterns.fill._DEFAULT_TYPES.\n"
        f"  Missing from doc:  {sorted(missing_from_doc)}\n"
        f"  Extra in doc:      {sorted(extra_in_doc)}\n"
        f"  Live keys:         {sorted(live_keys)}\n"
        f"Update the table or `_DEFAULT_TYPES` so they agree."
    )


def test_extractor_finds_the_documented_table() -> None:
    """Sanity: the extractor must actually find a non-empty key set in each doc.

    A regex that silently matches zero rows would make
    `test_default_content_type_table_matches_live_keys` vacuously pass
    if the doc table were renamed. Guard against that footgun.
    """
    for doc_path in FILL_CONTRACT_DOCS:
        text = (ROOT / doc_path).read_text(encoding="utf-8")
        keys = _extract_content_type_keys_from_markdown(text)
        assert keys, (
            f"Extractor found no `content_type` rows in {doc_path}. The "
            f"default-shapes table may have been renamed away from the "
            f"'Default Pydantic shape' / 'Default content shape' heading "
            f"the extractor looks for — update the extractor in this test."
        )
