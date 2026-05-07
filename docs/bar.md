---
disclaimer: >
  This document contains design decisions and heuristic estimates.
  Effort figures are T-shirt-size approximations, not measurements.
  All claims should be verified against the actual rendering pipeline
  before acting on them.
document: bar.md
version: 1.0
status: draft — pending user sign-off
phase: 0 (pre-flight gate for FrameGraph v1.4 → v2.0 roadmap)
---

# FrameGraph — Phase 0 Bar Definition

This document settles the three decisions that the deliberation
identified as user-gated before Phase 1 can begin.  It also records
the ground-truth facts about the current codebase that the
deliberation estimated but did not inspect.

---

## Decision 1 — Primary Surface

**Declared: Presentations**

Rationale: every artefact produced so far is presentation-shaped —
7 firm token packs keyed to consulting slide decks, `FrameGraphDeckRenderer`
for multi-slide `deck.yml` files, the Ginga One 15-slide pitch storyboard,
the McKinsey/BCG/Bain/EY 7S diagrams.  The renderer's text model
(slide chrome, speaker-facing layout) is oriented toward 16:9 canvas
at 960×540 px.

**Consequence for prioritisation**: when a gap choice forces a
trade-off between presentation utility and diagram utility, presentations
win through v2.0.  Diagram-only features (e.g. connector routing,
orthogonal edge layout) are deferred indefinitely unless they also
serve presentations.

---

## Decision 2 — Acceptance Bar

**Declared: Consulting-deck bar**

A version is accepted if **all** of the following hold:

1. **Reference deck renders end-to-end.**  
   The Ginga One reference deck (target: 15 slides; currently 3 slides
   in `ginga_one.deck.yml`) renders via `FrameGraphDeckRenderer` without
   errors, warnings, or skipped objects.

2. **Render time ≤ 5 seconds** for the full 15-slide deck on a
   single-core baseline (Apple M-series or equivalent x86).  Measured
   as wall time from `yaml.safe_load` to last SVG written.

3. **Visual regression within tolerance** (see Decision 3).

4. **No v1.x breakage** within the backward-compat tolerance defined
   in Decision 3.

**Benchmark deliverable**: the 15-slide Ginga One deck in `ginga_one.deck.yml`
is the reference deck.  Completing all 15 slides is a v1.4 milestone
prerequisite — it also serves as the primary fixture for surfacing
unknown gaps (OBJ-9 mitigation).

---

## Decision 3 — Backward-Compatibility Tolerance

**Declared: 1 % pixel tolerance, not byte-identical**

Definition: a rendered SVG passes the regression test if, for every
pixel in the rasterised output, the maximum channel delta is ≤ 1 %
(≤ 2.55 / 255).  Rasterisation is performed at 2× scale (1920×1080
for a 960×540 canvas) using `cairosvg` or `resvg`.  Any drift above
this threshold is a blocking regression.

Rationale for tolerance-based rather than byte-identical:

- Float formatting in SVG attributes produces sub-pixel differences
  across Python versions and platforms.
- The `text_svg` char-class width tables produce heuristic metrics
  that may shift by < 1 px as the tables are refined; this should not
  block a release.
- Byte-identical would require fixing SVG attribute ordering and
  float precision globally before any feature work begins — a
  multi-week distraction with zero user-visible benefit.

**Noise floor caveat**: the 1 % threshold is a common default in
graphics regression tooling.  It must be validated empirically once
the golden-snapshot harness (SP-6, Phase 1 weeks 1–2) is built.
If the actual noise floor of the pipeline exceeds 1 %, the threshold
will be raised to the next power of 2 (2 %, then 4 %) until it
clears clean on an unchanged renderer.  The threshold is recorded in
`tests/tolerance.cfg` and versioned.

---

## Ground-Truth Codebase Facts

These are verified values that the deliberation estimated from the
problem statement.  They replace the heuristic figures in the plan.

| Claim in plan | Verified value | Notes |
|---|---|---|
| Renderer "~950 LOC" | **1001 lines** | `wc -l framegraph_to_svg_v3.py` |
| `render_image` gap (G8) | **Partially implemented** | `render_image` passes `href` directly to SVG `<image>`. File-path → base64 embedding at render time is **not** implemented. G8 is still open. |
| Existing YAML fixtures | **11 YAML files** in outputs | 4× 7S themed, 2× GenAI system, 1× McKinsey 7S, 1× McKinsey 7S v2, 1× Ginga storyboard, 1× Ginga deck (3 slides), 1× 7S library diagram |
| No test suite | **Confirmed** | Zero golden snapshots, zero CI |
| Ginga deck slides | **3 of 15** | slides 01, 09, 14 only; remainder to be built in Phase 1 |

**Additional gap not in the deliberation's list:**

- `backdrop_blur` on rect/ellipse: grammar-defined in v1.2 EBNF but
  not implemented in the renderer.  Marked `# PENDING` in the
  v1.2 design session.  Status: **unimplemented**.  Assigned to
  v1.4 alongside `inner_ring` on rect (also unimplemented).

---

## Scope Cuts Applied Upfront

Per the deliberation's recommendation and the 6-month constraint:

| Item | Decision | Rationale |
|---|---|---|
| `sparkline` object | **Cut from v1.5; deferred to v2.0 or later** | Saves ~1 week; low regret — sparklines are derivable from `line_chart` with reduced options |
| `row` container | **Cut from v2.0; ship `grid` only** | Saves ~2 weeks; `row` = `grid` with `columns: N`; authors can use grid directly |
| Slide transition metadata | **Deferred indefinitely** | No interactive runtime in scope |
| Property-based testing | **Deferred; golden snapshots only for v1.4** | 80 % coverage at low cost |

Adjusted total timeline: **~26–27 weeks ≈ 6 months**.

---

## Phase 1 Entry Checklist

Phase 1 (v1.4) may begin when all of the following are true:

- [ ] This document (`bar.md`) is signed off by the user
- [ ] `ginga_one.deck.yml` expanded to at least 8 slides (enough to
      drive SP-6 fixture diversity before all 15 are complete)
- [ ] Python environment confirmed: `pyyaml`, `cairosvg` or `resvg`
      available for snapshot rasterisation
- [ ] `pyproject.toml` skeleton created (SP-7 can start in parallel
      with SP-6 in week 1)

---

## Sign-off

| Role | Name / Handle | Date | Status |
|---|---|---|---|
| Author | FrameGraph session | 2026-05-06 | Draft |
| User | — | — | **Pending** |
