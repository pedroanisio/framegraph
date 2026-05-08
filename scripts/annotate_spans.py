#!/usr/bin/env python3
"""Annotate `span` on bundled-catalog zones where it's clearly correct.

Round 2 Phase 1. Surveys the catalog for zones that would benefit
from horizontal spanning, suggests a span value, and (with
``--apply``) writes the annotation to
`static/refs/slides-patter-a.yml`.

Spanning rules (conservative — only annotate when the span is
unambiguously correct):

  R1 **Heavy zone, dominant size, alone in cell**:
     A zone with content_type ∈ {table_data, chart_data} or
     content_type=list_items with shape=chart, **alone** in its
     anchor cell, with size ∈ {large, xl, full} → ``span: {h: 3}``
     (claims the whole row).

  R2 **Heavy zone, medium size, alone in cell, no sibling in
     center column**:
     A zone with content_type ∈ {table_data, chart_data}, alone
     in cell, with size=medium, anchored at left/center/right of
     a row that has no other anchor zones → ``span: {h: 2}``.

A zone is "alone in its cell" when no other zone declares the
same anchor cell. A row is "no sibling in center column" when
the only zone in the (left, v), (center, v), (right, v) row is
this one.

Same-cell-sharing patterns are deferred to Phase 2 (stacking) —
``span`` does not solve them.

Run from the repo root:

    python3 scripts/annotate_spans.py            # dry-run, print suggestions
    python3 scripts/annotate_spans.py --apply    # write to bundled YAML
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import PatternCatalog  # noqa: E402

BUNDLED = REPO_ROOT / "static" / "refs" / "slides-patter-a.yml"


HEAVY_CONTENT_TYPES = {"table_data", "chart_data"}
DOMINANT_SIZES = {"large", "xl", "full"}


def _zone_cell(zone: dict) -> tuple[str, str] | None:
    """Return the (h, v) anchor cell of a zone, or None for non-anchor."""
    place = zone.get("placement", {})
    anchor = place.get("anchor")
    if anchor is None or anchor == "fullbleed":
        return None
    if not isinstance(anchor, dict):
        return None
    return (anchor.get("h"), anchor.get("v"))


def _is_heavy(zone: dict) -> bool:
    ct = zone.get("content_type")
    if ct in HEAVY_CONTENT_TYPES:
        return True
    if ct == "list_items" and zone.get("shape") == "chart":
        return True
    return False


def suggest_spans(pattern: dict) -> list[tuple[str, dict[str, int]]]:
    """For one pattern, return [(role, span_dict)] for every zone that
    should be annotated. Returns an empty list when no zones qualify.
    """
    suggestions: list[tuple[str, dict[str, int]]] = []

    # Group zones by anchor cell so we can detect cell-sharing.
    cell_to_zones: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for z in pattern["zones"]:
        c = _zone_cell(z)
        if c is not None:
            cell_to_zones[c].append(z)

    # Group zones by row for R2 (find rows where only one anchor zone exists).
    row_to_cells: dict[str, set[str]] = defaultdict(set)
    for c, zs in cell_to_zones.items():
        h, v = c
        row_to_cells[v].add(h)

    for z in pattern["zones"]:
        cell = _zone_cell(z)
        if cell is None:
            continue
        if not _is_heavy(z):
            continue

        # Skip if zone already has a non-default span.
        existing = z.get("span")
        if existing is not None and existing != {"h": 1, "v": 1}:
            continue

        cohort = cell_to_zones[cell]
        if len(cohort) > 1:
            # Cell-sharing — Phase 2 problem; do not annotate.
            continue

        size = z.get("size")
        h, v = cell

        # Detect siblings in adjacent cells of the same row. A zone
        # at (left, v) "spans into" the center and right cells; we
        # must check whether those cells host other anchored zones.
        cols = ("left", "center", "right")
        col_idx = cols.index(h)

        # R1: dominant size → claim as many adjacent cells as are
        # empty in the same row, capped at 3 (the full row).
        if size in DOMINANT_SIZES:
            # Walk rightward from the anchor cell counting empty cells.
            h_span = 1
            for nxt in range(col_idx + 1, 3):
                if cell_to_zones.get((cols[nxt], v)):
                    break
                h_span += 1
            # If the zone is anchored at right with empty left cells,
            # there's nothing to span into rightward; check leftward.
            # We don't span backward (annotation always grows right);
            # right-anchored zones with empty lefts get h_span=1.
            if h_span > 1:
                suggestions.append((z["role"], {"h": h_span}))
            continue

        # R2: medium size + no other zone anywhere in this row → span 2.
        if size == "medium":
            if len(row_to_cells[v]) == 1:
                # Only this zone occupies any cell in row v.
                # Span rightward up to 2 cells.
                if col_idx <= 1:  # left or center
                    suggestions.append((z["role"], {"h": 2}))

    return suggestions


def main() -> int:
    apply = "--apply" in sys.argv
    data = yaml.safe_load(BUNDLED.read_text(encoding="utf-8"))
    patterns = data["slide_template_patterns"]

    total = 0
    affected_patterns = 0
    by_h: dict[int, int] = defaultdict(int)
    for p in patterns:
        sug = suggest_spans(p)
        if not sug:
            continue
        affected_patterns += 1
        for role, span in sug:
            total += 1
            by_h[span["h"]] += 1
            if apply:
                # Write the span onto the matching zone in-place.
                for z in p["zones"]:
                    if z["role"] == role:
                        z["span"] = span
                        break

    print(
        f"Suggested {total} span annotation(s) across {affected_patterns} pattern(s):"
    )
    for h in sorted(by_h):
        print(f"  span: {{h: {h}}}  →  {by_h[h]} zones")

    # Show first 10 suggestions so the user can sanity-check.
    print("\nFirst 10 suggestions:")
    shown = 0
    for p in patterns:
        if shown >= 10:
            break
        sug = suggest_spans(p)
        for role, span in sug:
            if shown >= 10:
                break
            print(f"  #{p['id']:3d}  {p['name']!r:50s}  role={role!r:30s} → {span}")
            shown += 1

    if not apply:
        print(
            "\n(dry run — re-run with --apply to write these to the bundled YAML)"
        )
        return 0

    # Validate before writing.
    PatternCatalog.model_validate({"slide_template_patterns": patterns})

    BUNDLED.write_text(
        yaml.safe_dump(
            {"slide_template_patterns": patterns},
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {BUNDLED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
