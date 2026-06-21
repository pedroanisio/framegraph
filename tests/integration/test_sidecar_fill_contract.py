"""Regression: every shipped sidecar validates against its catalog pattern.

drift-risk-map Finding C1 — before this guard only BMC (#44) was validated
end-to-end, so 15 of the 17 shipped sidecars in `framegraph/data/fills/`
could drift out of sync with their pattern's zones (a renamed or removed
role, a sidecar override pointing at a role the pattern no longer has) with
**no CI signal**. The break surfaced only when an agent or user ran
`framegraph patterns example <id>` / `build`, as a `pydantic.ValidationError`
at point of use rather than at PR time.

This pins the contract for the *whole* sidecar set: each sidecar must name a
real pattern, build an effective fill schema, and — when it ships an
``example_fill`` — round-trip-validate that example against the schema.

It resolves sidecars through the package's canonical ``SIDECAR_DIR`` (the
same constant the CLI, the corpus render-coverage test, and
``scripts/validate_fills.py`` use), so the path can never silently drift to a
stale location again (see Finding C2 and ``test_corpus_render_coverage``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph._patterns import load_pattern_catalog
from framegraph.patterns import (
    SIDECAR_DIR,
    derive_fill_schema_with_sidecar,
    load_sidecar,
)

# Collected at import time so each sidecar becomes its own parametrized case
# (a failure names the offending file, not "the sidecar suite").
_SIDECAR_PATHS = sorted(SIDECAR_DIR.glob("*.yml"))


@pytest.fixture(scope="module")
def catalog():
    return load_pattern_catalog()


def test_sidecar_dir_ships_sidecars() -> None:
    """The canonical sidecar dir must exist and be non-empty.

    Without this affirmative check, a directory that resolved to empty (the
    Finding C2 failure mode) would make the parametrized test below collect
    *zero* cases and pass green — the silent no-op this whole file exists to
    prevent. Fail loud instead.
    """
    assert SIDECAR_DIR.is_dir(), f"canonical sidecar dir missing: {SIDECAR_DIR}"
    assert _SIDECAR_PATHS, f"no sidecars discovered under {SIDECAR_DIR}"


@pytest.mark.parametrize("sidecar_path", _SIDECAR_PATHS, ids=lambda p: p.stem)
def test_sidecar_matches_its_pattern(sidecar_path: Path, catalog) -> None:
    """Each shipped sidecar must agree with its pattern's current zones.

    Steps mirror `scripts/validate_fills.py`:
      1. Load + validate the sidecar YAML (`PatternFillSidecar`).
      2. Resolve its `pattern_id` in the live catalog.
      3. Build the effective fill schema (catches zones referencing roles the
         pattern does not have, or zones missing a `content_type`).
      4. If an `example_fill` is shipped, round-trip-validate it.
    """
    sidecar = load_sidecar(sidecar_path)

    try:
        pattern = catalog.get(sidecar.pattern_id)
    except KeyError:
        pytest.fail(
            f"{sidecar_path.name}: pattern_id {sidecar.pattern_id} is not in "
            f"the catalog. Either the pattern was removed/renumbered or the "
            f"sidecar's pattern_id is wrong."
        )

    # Raises ValueError / KeyError / MissingContentTypeError on a zone-role
    # mismatch — exactly the silent drift Finding C1 calls out.
    model = derive_fill_schema_with_sidecar(pattern, sidecar)

    if sidecar.example_fill is not None:
        # Round-trip contract: the curated example must satisfy the schema the
        # CLI derives for this pattern. A renamed pattern role surfaces here
        # as `field required` / `extra inputs are not permitted`.
        model.model_validate(sidecar.example_fill)
