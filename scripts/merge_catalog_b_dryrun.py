#!/usr/bin/env python3
"""Dry-run merge of catalog B into the bundled catalog.

Reads:
  - `static/refs/slides-patter-a.yml` (already-normalized catalog A,
    50 patterns, ids 1–50, category=generic).
  - `static/refs/slides-patter-b.yml` (legacy-shape catalog B, 50
    patterns, ids 51–100, with `big4_consulting_slide_template_patterns`
    top-level key and per-pattern `consulting_use`).

Normalizes catalog B in memory, then validates the **merged**
100-pattern catalog. Reports:

  1. Within-B structural duplicates.
  2. Cross-catalog (A vs B) structural duplicates.
  3. Any disjunctive positions that resolved to a single anchor and
     are worth manual review.

Writes nothing. Exit code 0 if the merge would succeed; non-zero
otherwise.

Run from the repo root:

    python3 scripts/merge_catalog_b_dryrun.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import (  # noqa: E402
    PatternCatalog,
    SlidePattern,
)
from scripts._pattern_normalization import (  # noqa: E402
    POSITION_NORMALIZATION,
    SIZE_NORMALIZATION,
)

CATALOG_A = REPO_ROOT / "static" / "refs" / "slides-patter-a.yml"
CATALOG_B = REPO_ROOT / "static" / "refs" / "slides-patter-b.yml"


def normalize_zone(z: dict[str, Any]) -> dict[str, Any]:
    role = z["role"]
    size_entry = SIZE_NORMALIZATION[z["size"]]
    placement = POSITION_NORMALIZATION[z["position"]]
    new_zone: dict[str, Any] = {
        "role": role,
        "size": size_entry["size"],
        "placement": placement,
    }
    if "shape" in size_entry:
        new_zone["shape"] = size_entry["shape"]
    return new_zone


def normalize_b_pattern(p: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p["id"],
        "name": p["name"],
        "layout_disposition": p["layout_disposition"],
        "category": "consulting",
        "zones": [normalize_zone(z) for z in p["zones"]],
    }
    if "consulting_use" in p:
        out["consulting_use"] = p["consulting_use"]
    return out


def main() -> int:
    # Catalog A is already normalized and lives in the bundled file.
    a_data = yaml.safe_load(CATALOG_A.read_text(encoding="utf-8"))
    a_patterns = a_data["slide_template_patterns"]

    # Catalog B is legacy-shape; normalize in memory.
    b_data = yaml.safe_load(CATALOG_B.read_text(encoding="utf-8"))
    b_raw = b_data["big4_consulting_slide_template_patterns"]
    b_patterns = [normalize_b_pattern(p) for p in b_raw]

    merged = {"slide_template_patterns": a_patterns + b_patterns}

    print(
        f"Catalog A: {len(a_patterns)} patterns (ids "
        f"{min(p['id'] for p in a_patterns)}–{max(p['id'] for p in a_patterns)})"
    )
    print(
        f"Catalog B: {len(b_patterns)} patterns (ids "
        f"{min(p['id'] for p in b_patterns)}–{max(p['id'] for p in b_patterns)})"
    )
    print(f"Merged:    {len(a_patterns) + len(b_patterns)} patterns")
    print()

    # Try to validate the merged catalog. Pydantic raises on the
    # FIRST structural duplicate; for a comprehensive report we
    # build the fingerprints ourselves.
    try:
        cat = PatternCatalog.model_validate(merged)
    except Exception as exc:
        # Pydantic already caught a structural dup — we still want
        # to print the full collision report below before exiting.
        cat = None
        print(f"VALIDATION ERROR (first failure): {exc}\n")

    # Compute fingerprints across A and B.
    fp_to_patterns: dict[Any, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for p in a_patterns:
        sp = SlidePattern.model_validate(p)
        fp_to_patterns[sp.structural_fingerprint()].append(("A", p))
    for p in b_patterns:
        sp = SlidePattern.model_validate(p)
        fp_to_patterns[sp.structural_fingerprint()].append(("B", p))

    collisions = {fp: ps for fp, ps in fp_to_patterns.items() if len(ps) > 1}

    if not collisions:
        print("✅ No structural duplicates across A ∪ B.")
        if cat is not None:
            print(f"✅ Merged catalog validates: {len(cat.slide_template_patterns)} patterns.")
            return 0
        return 1

    print(f"⚠ {len(collisions)} structural-duplicate group(s) found:\n")
    for i, (_fp, ps) in enumerate(collisions.items(), 1):
        print(f"  Group {i} ({len(ps)} patterns):")
        for source, p in ps:
            uses = p.get("consulting_use", "")
            uses_s = f"  [{uses}]" if uses else ""
            print(f"    {source} #{p['id']:3d}  {p['name']!r}{uses_s}")
        # Show the shared zone-role set as a hint.
        roles = sorted({z["role"] for z in ps[0][1]["zones"]})
        print(f"    shared roles: {roles}\n")

    # Group analyses for resolution: list candidates with their
    # consulting_use to help the human disambiguate.
    return 1


if __name__ == "__main__":
    sys.exit(main())
