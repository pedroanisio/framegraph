"""Corpus-wide render-coverage regression — Phase 6.

Iterates every pattern in the bundled catalog; for each, derives
an effective fill schema (defaults + sidecar overrides), generates
a minimal valid example fill, and runs the full pipeline through
to SVG. Any pattern that fails to build is a regression.

This test is the project's strongest guarantee that the
fill-and-render pipeline works for the *whole* catalog, not just
BMC.

Phase 6 acceptance criteria (per `docs/ROADMAP-FILL-RENDER.md`):

  - 100% of catalog patterns either render successfully with
    default schemas or have a sidecar.
  - The pipeline never raises an unhandled exception on a known
    pattern.
"""

from __future__ import annotations

from typing import Any

import pytest

from framegraph._patterns import (
    PatternZone,
    SlidePattern,
    load_pattern_catalog,
)
from framegraph.patterns import (
    SIDECAR_DIR,
    compose_document,
    compute_boxes,
    derive_default_fill_schema,
    derive_fill_schema_with_sidecar,
    find_sidecar,
    load_sidecar,
    render_pattern_svg,
)

CANVAS_W = 1920.0
CANVAS_H = 1080.0


# ─────────────────────────────────────────────────────────────────
# Default-fill generator — minimal valid payload per content_type
# ─────────────────────────────────────────────────────────────────


def _default_value_for_content_type(ct: str) -> Any:
    """Generate a minimal valid value for one zone's content type.

    Mirrors the default Pydantic shapes in ``framegraph.patterns.fill``.
    Phase 6 adds a sidecar-aware variant in ``_default_value_for_zone``
    that consults ``item_kind`` / ``item_fields`` overrides.
    """
    if ct == "title_body":
        return {"title": "T", "body": "B"}
    if ct == "metric":
        return {"label": "L", "value": "V"}
    if ct == "list_items":
        return ["item one", "item two"]
    if ct == "key_value":
        return {"k": "v"}
    if ct == "comparison":
        return {"left": "L", "right": "R"}
    if ct == "chart_data":
        return {"type": "bar", "series": []}
    if ct == "table_data":
        return {"headers": ["H"], "rows": [["v"]]}
    if ct == "image":
        return {"src": "placeholder.png"}
    if ct == "axis_label":
        return {"title": "T"}
    if ct == "decorative":
        return None
    raise AssertionError(f"unknown content_type {ct!r}")


def _default_value_for_zone(zone: PatternZone, sidecar) -> Any:
    """Return a default payload for one zone, honoring sidecar overrides.

    When a sidecar declares ``item_kind: object`` for a list_items
    zone, the default must be a list of objects with the declared
    fields rather than a list of strings.
    """
    if sidecar is not None and zone.role in sidecar.zones:
        override = sidecar.zones[zone.role]
        if override.item_kind == "object":
            assert override.item_fields is not None
            obj: dict[str, Any] = {}
            for fname in override.item_fields:
                # All v1 fields are typed `string`; supply a placeholder.
                obj[fname] = "x"
            return [obj, obj]
        # item_kind == "string" → default list[str].
        return ["a", "b"]
    return _default_value_for_content_type(zone.content_type or "title_body")


# ─────────────────────────────────────────────────────────────────
# Coverage test — every pattern builds without errors
# ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def catalog():
    return load_pattern_catalog()


@pytest.fixture(scope="module")
def all_patterns(catalog) -> list[SlidePattern]:
    return list(catalog.slide_template_patterns)


def _sidecar_for(pattern_id: int):
    """Locate and load a sidecar by pattern id, or return None.

    Resolves through the package's canonical `find_sidecar` so this test can
    never again silently miss the whole sidecar set by pointing at a stale
    directory (drift-risk-map Finding C2).
    """
    path = find_sidecar(pattern_id)
    return load_sidecar(path) if path is not None else None


def test_sidecar_dir_is_present_and_nonempty() -> None:
    """The canonical sidecar dir must exist and actually ship sidecars.

    drift-risk-map Finding C2: this suite previously resolved sidecars from a
    stale `static/refs/fills/` path that no longer existed, so `_sidecar_for`
    always returned ``None`` and every pattern rendered with *defaults* — the
    sidecar branch (`derive_fill_schema_with_sidecar`, object-item overrides)
    was dead code in the test while reading as "covered". If the directory
    moves again, fail loudly here instead of silently degrading coverage.
    """
    assert SIDECAR_DIR.is_dir(), f"canonical sidecar dir is missing: {SIDECAR_DIR}"
    assert any(SIDECAR_DIR.glob("*.yml")), f"no sidecars shipped under {SIDECAR_DIR}"
    # The resolver must actually find a known sidecar (BMC #44).
    assert _sidecar_for(44) is not None, "BMC sidecar (#44) not resolved via find_sidecar"


def test_every_pattern_builds_to_svg(all_patterns: list[SlidePattern]) -> None:
    """Roadmap acceptance: every catalog pattern builds end-to-end.

    Per-pattern steps:
      1. Resolve sidecar (optional).
      2. Build effective fill schema.
      3. Generate default-fill payload (one minimal value per zone).
      4. Validate the payload against the schema.
      5. Compute layout boxes.
      6. Render to SVG.
    Any failure on any pattern is reported with id + name + reason.
    """
    failures: list[tuple[int, str, str]] = []
    for p in all_patterns:
        try:
            sidecar = _sidecar_for(p.id)
            if sidecar is not None:
                Model = derive_fill_schema_with_sidecar(p, sidecar)
            else:
                Model = derive_default_fill_schema(p)
            payload = {z.role: _default_value_for_zone(z, sidecar) for z in p.zones}
            fill = Model.model_validate(payload)
            layout = compute_boxes(p, CANVAS_W, CANVAS_H)
            svg = render_pattern_svg(p, fill, layout, CANVAS_W, CANVAS_H)
            if not svg or len(svg) < 100:
                failures.append((p.id, p.name, "SVG too short or empty"))
        except Exception as exc:
            failures.append((p.id, p.name, f"raised {type(exc).__name__}: {exc}"))

    if failures:
        # Report the first 10 failures, then total count.
        msg = "\n".join(
            f"  #{fid:3d}  {name!r:50s}  {reason}" for fid, name, reason in failures[:10]
        )
        pytest.fail(
            f"{len(failures)} pattern(s) failed to build:\n{msg}"
            + (f"\n  ... (showing first 10 of {len(failures)})" if len(failures) > 10 else "")
        )


def test_corpus_render_uses_compose_document(
    all_patterns: list[SlidePattern],
) -> None:
    """`compose_document` must produce a Document-shaped dict for every pattern."""
    failures: list[tuple[int, str, str]] = []
    for p in all_patterns:
        try:
            sidecar = _sidecar_for(p.id)
            if sidecar is not None:
                Model = derive_fill_schema_with_sidecar(p, sidecar)
            else:
                Model = derive_default_fill_schema(p)
            payload = {z.role: _default_value_for_zone(z, sidecar) for z in p.zones}
            fill = Model.model_validate(payload)
            layout = compute_boxes(p, CANVAS_W, CANVAS_H)
            doc = compose_document(p, fill, layout, CANVAS_W, CANVAS_H)
            assert doc["dsl"] == "FrameGraph"
            assert doc["scene"]["canvas"]["size"] == [CANVAS_W, CANVAS_H]
            assert len(doc["visual"]["layers"]) >= 1
            objects = [o for layer in doc["visual"]["layers"] for o in layer["objects"]]
            # At least one visual object per zone.
            assert len(objects) >= len(p.zones)
        except Exception as exc:
            failures.append((p.id, p.name, f"compose failed: {exc}"))
    if failures:
        msg = "\n".join(f"  #{fid:3d}  {name!r}: {reason}" for fid, name, reason in failures[:10])
        pytest.fail(f"{len(failures)} pattern(s) failed compose:\n{msg}")


def test_no_pattern_has_unannotated_zones(catalog) -> None:
    """Phase 6 commits to 100% content_type coverage. This is the guard."""
    missing: list[tuple[int, str, str]] = []
    for p in catalog.slide_template_patterns:
        for z in p.zones:
            if z.content_type is None:
                missing.append((p.id, p.name, z.role))
    assert not missing, (
        f"{len(missing)} zones lack content_type; Phase 6 commits to "
        f"100% coverage. First offenders: {missing[:5]}"
    )
