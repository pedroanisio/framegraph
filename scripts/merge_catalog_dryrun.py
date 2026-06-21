#!/usr/bin/env python3
"""Dry-run multi-source catalog merge — validate, surface duplicates, write nothing.

Reads the same `SOURCES` list as `merge_catalogs.py`, normalizes
each source in memory, validates the merged catalog against
`framegraph._patterns.PatternCatalog`, and reports:

  1. Hard structural duplicates (same fingerprint — would block
     the merge).
  2. Near-duplicates (same shape-only fingerprint, role names
     differ — surfaces reusable base patterns for review).

Writes nothing. Exit 0 if the merge would succeed; non-zero on
hard duplicates.

Run from the repo root:

    python3 scripts/merge_catalog_dryrun.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import (  # noqa: E402
    Anchor,
    PatternCatalog,
    RegionPlacement,
    SlidePattern,
)
from scripts.merge_catalogs import (  # noqa: E402
    BUNDLED,
    SOURCES,
    normalize_pattern,
)


def shape_only_fingerprint(p: SlidePattern) -> frozenset[tuple[Any, ...]]:
    """Fingerprint that ignores role names — surfaces reusable shapes.

    Two patterns with this fingerprint share the structural skeleton
    (same zone count, same size+placement+shape multiset) but use
    different role-name vocabularies — i.e. domain specializations
    of one base pattern.
    """
    items = []
    for z in p.zones:
        place = z.placement
        if isinstance(place, Anchor):
            pk: tuple[Any, ...] = (
                "anchor",
                place.h or "",
                place.v or "",
                str(place.fullbleed),
            )
        elif isinstance(place, RegionPlacement):
            pk = ("region", place.region)
        else:  # RelativePlacement — relation only, target name ignored
            pk = ("relative", place.relation)
        items.append((z.size, pk, z.shape or ""))
    return frozenset(items)


def main() -> int:
    bundled_data = yaml.safe_load(BUNDLED.read_text(encoding="utf-8"))
    bundled_patterns = bundled_data["slide_template_patterns"]
    sourced_cats = {s["category"] for s in SOURCES}
    surviving = [p for p in bundled_patterns if p.get("category") not in sourced_cats]
    for p in surviving:
        p.setdefault("category", "generic")
        if "consulting_use" in p and "use_case" not in p:
            p["use_case"] = p.pop("consulting_use")

    merged = list(surviving)
    for source in SOURCES:
        src_data = yaml.safe_load(source["path"].read_text(encoding="utf-8"))
        src_raw = src_data[source["top_level_key"]]
        merged.extend(
            normalize_pattern(
                p,
                source["category"],
                source.get("use_case_field", "consulting_use"),
            )
            for p in src_raw
        )

    cats = Counter(p.get("category", "generic") for p in merged)
    breakdown = ", ".join(f"{n} {c}" for c, n in sorted(cats.items()))
    print(f"Merged candidate: {len(merged)} patterns ({breakdown})\n")

    # Try to validate the merged catalog. Pydantic raises on the
    # FIRST structural duplicate; for the full report we compute
    # fingerprints ourselves below.
    cat = None
    try:
        cat = PatternCatalog.model_validate({"slide_template_patterns": merged})
    except Exception as exc:
        print(f"⚠ VALIDATION ERROR (first failure):\n  {exc}\n")

    # Hard-duplicate detection (full structural fingerprint).
    hard: dict[frozenset[tuple[Any, ...]], list[SlidePattern]] = defaultdict(list)
    near: dict[frozenset[tuple[Any, ...]], list[SlidePattern]] = defaultdict(list)
    for raw in merged:
        sp = SlidePattern.model_validate(raw)
        hard[sp.structural_fingerprint()].append(sp)
        near[shape_only_fingerprint(sp)].append(sp)

    hard_groups = [g for g in hard.values() if len(g) > 1]
    near_groups = [g for g in near.values() if len(g) > 1]

    if hard_groups:
        print(f"⚠ {len(hard_groups)} HARD-DUPLICATE group(s) — would block merge:\n")
        for i, group in enumerate(hard_groups, 1):
            print(f"  Group {i}:")
            for sp in group:
                print(f"    [{sp.category}] #{sp.id:3d}  {sp.name!r}")
            print()
    else:
        print("✅ No hard structural duplicates.")

    if near_groups:
        print(
            f"\n💡 {len(near_groups)} near-duplicate group(s) "
            "(same shape, different role names — candidates for base patterns):\n"
        )
        for i, group in enumerate(near_groups, 1):
            print(f"  Group {i} ({len(group)} patterns):")
            for sp in group:
                roles = ", ".join(z.role for z in sp.zones)
                print(f"    [{sp.category}] #{sp.id:3d}  {sp.name!r}")
                print(f"        roles: [{roles}]")
            print()
    else:
        print("\n💡 No near-duplicates (every pattern has a unique shape).")

    if cat is not None and not hard_groups:
        print(f"\n✅ Merge would succeed ({len(cat.slide_template_patterns)} patterns).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
