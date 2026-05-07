#!/usr/bin/env python3
"""Rewrite `static/refs/slides-patter-a.yml` to the refined schema.

Reads the loose-string original, applies the normalization tables
in `scripts/_pattern_normalization.py`, and writes the result back
in place. After this script runs, the YAML must validate against
`framegraph._patterns.PatternCatalog`.

Run from the repo root:

    python3 scripts/normalize_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Allow running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._pattern_normalization import (  # noqa: E402
    POSITION_NORMALIZATION,
    SIZE_NORMALIZATION,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "static" / "refs" / "slides-patter-a.yml"


def normalize_zone(z: dict) -> dict:
    """Rewrite one zone from the legacy shape to the refined shape."""
    role = z["role"]
    legacy_size = z["size"]
    legacy_position = z["position"]

    size_entry = SIZE_NORMALIZATION[legacy_size]
    placement = POSITION_NORMALIZATION[legacy_position]

    new_zone: dict = {
        "role": role,
        "size": size_entry["size"],
        "placement": placement,
    }
    if "shape" in size_entry:
        new_zone["shape"] = size_entry["shape"]
    return new_zone


def main() -> int:
    data = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    for pattern in data["slide_template_patterns"]:
        pattern["zones"] = [normalize_zone(z) for z in pattern["zones"]]

    SRC.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    print(f"normalized {len(data['slide_template_patterns'])} patterns -> {SRC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
