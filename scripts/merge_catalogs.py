#!/usr/bin/env python3
"""Merge external pattern source files into the bundled catalog.

The bundled catalog lives at `static/refs/slides-patter-a.yml`.
External source files live alongside it under `static/refs/` and
plug in via the `SOURCES` list below.

Each source declares:

  - `path` — the YAML file to read.
  - `top_level_key` — the source-specific top-level list key
    (e.g. `big4_consulting_slide_template_patterns`).
  - `category` — `PatternCategory` value to tag every pattern
    coming from this source with.

Catalog A patterns already living in the bundled file pass through
unchanged (and acquire `category: generic` if missing). Patterns
from any source matching a known category are dropped from the
existing bundled file and re-loaded from their source — making
this script idempotent across re-runs.

After validation, the merged result is written back to
`slides-patter-a.yml` and the script exits 0. Any structural
duplicate (same zone set under different ids) raises an error
naming both offenders.

Run from the repo root:

    python3 scripts/merge_catalogs.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import PatternCatalog  # noqa: E402
from scripts._pattern_normalization import (  # noqa: E402
    POSITION_NORMALIZATION,
    SIZE_NORMALIZATION,
)

BUNDLED = REPO_ROOT / "static" / "refs" / "slides-patter-a.yml"

# External sources to merge. Add a row per new pattern file. The
# bundled file is *not* in this list — it carries the previously
# merged generic patterns plus whatever is normalized from sources.
SOURCES: list[dict[str, Any]] = [
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-patter-b.yml",
        "top_level_key": "big4_consulting_slide_template_patterns",
        "category": "consulting",
        "use_case_field": "consulting_use",
    },
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-pattern-c.yml",
        "top_level_key": "big4_consulting_slide_template_patterns_extension",
        "category": "consulting",
        "use_case_field": "consulting_use",
    },
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-pattern-d.yml",
        "top_level_key": "big4_consulting_slide_template_patterns_extension_75",
        "category": "consulting",
        "use_case_field": "consulting_use",
    },
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-pattern-e.yml",
        "top_level_key": "big4_consulting_slide_template_patterns_extension_50",
        "category": "consulting",
        "use_case_field": "consulting_use",
    },
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-pattern-f.yml",
        "top_level_key": "expert_designed_slide_template_patterns_extension_50",
        "category": "consulting",
        "use_case_field": "consulting_use",
    },
    {
        "path": REPO_ROOT / "static" / "refs" / "slides-pattern-g.yml",
        "top_level_key": "expert_only_slide_template_patterns",
        "category": "expert",
        "use_case_field": "expert_use",
    },
]


def normalize_zone(z: dict[str, Any]) -> dict[str, Any]:
    """Rewrite one legacy-shape zone into the refined-schema shape."""
    size_entry = SIZE_NORMALIZATION[z["size"]]
    out: dict[str, Any] = {
        "role": z["role"],
        "size": size_entry["size"],
        "placement": POSITION_NORMALIZATION[z["position"]],
    }
    if "shape" in size_entry:
        out["shape"] = size_entry["shape"]
    return out


def normalize_pattern(
    p: dict[str, Any],
    category: str,
    use_case_field: str = "consulting_use",
) -> dict[str, Any]:
    """Normalize one source pattern, tagging it with the source category.

    The source-specific use-case field (``consulting_use`` for
    consulting catalogs, ``expert_use`` for expert catalogs) is
    unified into the schema's canonical ``use_case`` field.
    """
    out: dict[str, Any] = {
        "id": p["id"],
        "name": p["name"],
        "layout_disposition": p["layout_disposition"],
        "category": category,
        "zones": [normalize_zone(z) for z in p["zones"]],
    }
    if use_case_field in p:
        out["use_case"] = p[use_case_field]
    return out


def main() -> int:
    bundled_data = yaml.safe_load(BUNDLED.read_text(encoding="utf-8"))
    bundled_patterns: list[dict[str, Any]] = bundled_data["slide_template_patterns"]

    # Drop patterns from any source category we'll re-merge below
    # (idempotency).
    sourced_categories = {s["category"] for s in SOURCES}
    bundled_patterns = [p for p in bundled_patterns if p.get("category") not in sourced_categories]
    # Tag any leftover patterns with `generic` if absent.
    # Migrate the legacy `consulting_use` field name to `use_case`
    # if it survived from a pre-rename bundled file.
    for p in bundled_patterns:
        p.setdefault("category", "generic")
        if "consulting_use" in p and "use_case" not in p:
            p["use_case"] = p.pop("consulting_use")

    merged: list[dict[str, Any]] = list(bundled_patterns)
    for source in SOURCES:
        src_data = yaml.safe_load(source["path"].read_text(encoding="utf-8"))
        src_raw = src_data[source["top_level_key"]]
        merged.extend(
            normalize_pattern(p, source["category"], source.get("use_case_field", "consulting_use"))
            for p in src_raw
        )

    # Validate before writing — fail loud on structural duplicates.
    cat = PatternCatalog.model_validate({"slide_template_patterns": merged})

    cats = Counter(p.category for p in cat.slide_template_patterns)
    breakdown = ", ".join(f"{n} {c}" for c, n in sorted(cats.items()))
    print(f"Validated merged catalog: {len(cat.slide_template_patterns)} patterns ({breakdown})")

    BUNDLED.write_text(
        yaml.safe_dump(
            {"slide_template_patterns": merged},
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    print(f"wrote {BUNDLED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
