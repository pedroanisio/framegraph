#!/usr/bin/env python3
"""Validate every shipped sidecar (`framegraph/data/fills/`) against the catalog.

For each sidecar YAML:

  1. Parse it as a `PatternFillSidecar`.
  2. Resolve the corresponding pattern from the bundled catalog.
  3. Build the effective fill schema (default + overrides).
  4. If the sidecar declares an ``example_fill``, validate it
     against the effective schema (round-trip contract).

Exit 0 if every sidecar passes; non-zero with a per-file error
listing on any failure.

Run from the repo root:

    python3 scripts/validate_fills.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import load_pattern_catalog  # noqa: E402
from framegraph.patterns import (  # noqa: E402
    SIDECAR_DIR,
    derive_fill_schema_with_sidecar,
    load_sidecar,
)

# Resolve through the package's canonical sidecar directory rather than a
# hand-mirrored path. The previous `static/refs/fills/` literal had drifted
# to a non-existent location (drift-risk-map Finding C2), so this validator
# silently found nothing to check.
FILLS_DIR = SIDECAR_DIR


def _validate_one(path: Path, catalog) -> list[str]:
    """Return a list of error strings for one sidecar; empty on success."""
    errors: list[str] = []
    try:
        sidecar = load_sidecar(path)
    except Exception as exc:
        return [f"  load failed: {exc}"]

    try:
        pattern = catalog.get(sidecar.pattern_id)
    except KeyError:
        return [f"  pattern_id {sidecar.pattern_id} not in catalog"]

    try:
        Model = derive_fill_schema_with_sidecar(pattern, sidecar)
    except Exception as exc:
        return [f"  schema-build failed: {exc}"]

    if sidecar.example_fill is not None:
        try:
            Model.model_validate(sidecar.example_fill)
        except Exception as exc:
            errors.append(f"  example_fill failed validation: {exc}")

    return errors


def main() -> int:
    """Validate every shipped sidecar; return 0 on success, 1 on any failure."""
    if not FILLS_DIR.exists():
        print(f"fills directory not found: {FILLS_DIR}", file=sys.stderr)
        return 1

    sidecar_paths = sorted(FILLS_DIR.glob("*.yml"))
    if not sidecar_paths:
        print(f"no sidecars found in {FILLS_DIR} — nothing to validate.")
        return 0

    catalog = load_pattern_catalog()
    failures: list[tuple[Path, list[str]]] = []
    print(f"Validating {len(sidecar_paths)} sidecar(s) in {FILLS_DIR}:")
    for path in sidecar_paths:
        errs = _validate_one(path, catalog)
        if errs:
            failures.append((path, errs))
            print(f"  ✗ {path.name}")
        else:
            print(f"  ✓ {path.name}")

    if failures:
        print(f"\n{len(failures)} sidecar(s) failed validation:\n")
        for path, errs in failures:
            print(f"{path}:")
            for e in errs:
                print(e)
        return 1

    print(f"\nAll {len(sidecar_paths)} sidecar(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
