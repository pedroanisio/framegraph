---
disclaimer: >
  This document was produced by an automated multi-agent deliberation
  process running in single-context simulation mode (Mode B fallback).
  Independence between agent perspectives is approximated, not
  guaranteed by separate API calls. No information within should be
  taken for granted. Any statement or premise not backed by a real
  logical definition or verifiable reference may be invalid, erroneous,
  or a hallucination. All effort estimates are heuristic T-shirt sizes
  based on the gap descriptions in the input problem statement, not
  measurements. All claims require independent verification before
  acting on them.
generated_by: multi-agent-deliberation skill (Mode B)
rounds: 2
agents: [decomposer, strategist, critic, synthesizer, judge]
status: structurally converged; gated on user input (Phase 0)
---

# Solution Plan: FrameGraph v1.3 → Production-Capable Roadmap

## 1. Problem Statement

Produce a sequenced roadmap evolving FrameGraph from v1.3 into a
production-capable DSL for professional presentations and diagrams,
across three iterated, independently useful releases (v1.4, v1.5, v2.0).
Hard constraints: backward compatibility for all v1.x YAML; pure-Python
renderer; YAML-first authoring; ~6-month total cadence; single
developer.

10 actionable gaps (severity-ranked: 1 critical, 2 high, 4 medium, 3
low) plus 2 already shipped in v1.3 (word wrap, v_align).

## 2. Sub-Problem Decomposition

The deliberation reframed the gap list around **architectural locus**
rather than user-perceived severity, because release-plan sequencing
should follow architectural risk:

| ID | Sub-Problem | Gaps Covered | Complexity |
|---|---|---|---|
| SP-0 | Scope & bar definition (user-gated) | — | low |
| SP-1a | Auto-layout architecture + minimal `stack` | G1 (partial) | medium |
| SP-1b | Auto-layout full `grid`/`row` impl | G1 (remainder) | high |
| SP-2 | Rich text family (spans + bullet_list, grouped) | G3, G6 | high |
| SP-3 | Data-viz primitives | G4 | high |
| SP-4 | Asset & connectivity primitives | G8, G9 | medium |
| SP-5 | Deck format maturation | G7, G10 | low |
| SP-6 | Quality infrastructure | G12 | medium |
| SP-7 | Distribution & versioning (pypi, CI, semver) | — (NEW) | low |

**Dependency graph**

```
SP-0 ──► SP-1a
SP-6 ──► (SP-2, SP-4, SP-1a, SP-1b)
SP-2 ──► (SP-3, SP-1b)
SP-7 ⊥ all (parallel track)
```

**Hidden coupling worth flagging**: the v1.4 auto-layout schema
(SP-1a) must anticipate v2.0 `grid`/`row` (SP-1b) to avoid forcing
schema-breaking changes. The recommended namespace is
`layout: {kind: stack|grid|row, ...}` — designed in v1.4 even though
only `stack` is implemented.

**Explicitly out of scope** (deferred indefinitely):
- Programmatic API
- Alternative rendering backends (Cairo, browser, PDF)
- Interactive presentation runtime
- Render-time animations
- Slide transition metadata (G11 — cut to fit timeline)

## 3. Phased Roadmap

### Phase 0 — Pre-flight: Bar Definition (~1 week, user-gated)

**Objective**: Define "production-capable" acceptance bar and primary
surface declaration. **Until this is settled, downstream effort
estimates are conditional.**

**Three decisions required from the user**:

1. **Target persona**. Working hypothesis: *consulting analyst
   producing 20-slide pitch decks*, justified by the existing 7
   firm-token-pack inventory. Alternative: *engineering documentation
   author* (would re-prioritize diagrams over presentations).
2. **Acceptance bar**. Working hypothesis: *"a 20-slide reference
   consulting deck renders within 1% pixel tolerance of v1.3 reference,
   end-to-end YAML → SVG, in under 5 seconds."* Alternative bars are
   acceptable; this is a placeholder.
3. **Backward-compatibility definition**. Working hypothesis: *"v1.x
   YAML renders within 1% pixel tolerance of its v1.3 reference SVG."*
   Alternative: byte-identical (much costlier).

**Deliverable**: `bar.md` written by the developer, signed off by the
user.

### Phase 1 — v1.4 "Authoring Enrichment + Architecture Seed" (~10 weeks)

**Objective**: Close authoring-friction gaps; lock auto-layout schema
so v1.4/v1.5 authors aren't stranded; ship distribution infrastructure
so "production-capable" is actually deployable.

**Order of work** (dependency-respecting):

1. **Week 1–2: SP-6 quality infrastructure**. Golden-SVG snapshot
   harness, ≥30 reference YAMLs covering all v1.3 features. Diff tool
   reports pixel deltas with configurable tolerance. **Lands first**
   so all subsequent features have regression coverage.
2. **Week 1–3 (parallel): SP-7 distribution**. pypi packaging
   (`pyproject.toml`, version pinning); GitHub Actions CI running
   golden snapshots on every commit; semver policy documented.
3. **Week 3–6: SP-2 rich text family**.
   - Week 3–4: inline spans (`text: {spans: [...]}`); per-span text
     metrics via existing char-class width tables (extended for
     bold/italic weights).
   - Week 5–6: `bullet_list` object with `items[]`, `marker`,
     `indent`. `marker:"1."` enables ordered lists.
4. **Week 6–7 (parallel): SP-4 assets**.
   - `image` object: file path → base64 data URI embed at render.
   - Port resolution: track use→symbol transform stack at parse;
     expose ports through use boundary.
5. **Week 7–10: SP-1a auto-layout architecture + stack**. Design the
   `layout: {kind: stack|grid|row, gap, align, justify, padding}`
   namespace; implement only `kind: stack`. Schema must allow `grid`
   and `row` to be added in v2.0 without breaking changes.

**v1.4 deliverables**:
- ≥30 golden-snapshot tests in CI
- pypi package `framegraph` (or chosen name)
- Inline rich-span support
- `bullet_list` object
- `image` object (raster embed)
- Lifted port resolution through `use` boundary
- Auto-layout schema + `stack` container

**Decision points during Phase 1**:
- Span syntax: explicit list (recommended) vs markdown subset
- Auto-layout namespace: must anticipate v2.0 grid/row

**Risks specific to Phase 1**:
- Text-metric accuracy with mixed-weight spans (mitigation: consider
  `fonttools` integration if char-class tables prove insufficient)
- Stack schema design locks v2.0 grid/row options (mitigation:
  schema review before merge)

### Phase 2 — v1.5 "Data-Viz & Deck Polish" (~8 weeks)

**Objective**: Add chart primitives; mature deck format.

**Order of work**:

1. **Week 1–6: SP-3 data-viz primitives**. `bar_chart`,
   `line_chart`, `sparkline` as discrete object types sharing an
   internal chart-renderer module. Axis labels and legends use
   spans from v1.4. Inline data shape: `data: [{x:..., y:...}, ...]`.
2. **Week 6–8: SP-5 deck format maturation**.
   - `$extends`: deck-level base slide; child slides specify deltas.
   - `notes:` field on each slide (invisible to render, exposed to
     deck export).

**v1.5 deliverables**:
- 3 chart object types (`bar_chart`, `line_chart`, `sparkline`)
- `$extends` inheritance in deck format
- Speaker-notes export

**Decision points during Phase 2**:
- Chart data shape: inline arrays vs external file ref

**Risks specific to Phase 2**:
- Chart visual quality bar implicitly set high by matplotlib
  comparison (mitigation: define chart success criteria upfront —
  *"good enough for a consulting deck"* is the bar, not
  *"replaces matplotlib"*)

### Phase 3 — v2.0 "Architectural Pivot" (~10 weeks)

**Objective**: Full auto-layout, renderer modularization, full
backward-compat audit.

**Order of work**:

1. **Week 1–5: SP-1b auto-layout completion**. `grid` and `row`
   containers extending the v1.4 schema. Interop rules with
   absolute-coordinate children: a child object with `x:` or `y:`
   set inside an auto-layout container uses absolute positioning
   (escape hatch).
2. **Week 5–8: Renderer modularization**. Split the 950-LOC single
   file into per-object-type modules with a registration interface.
   Refactor must be golden-snapshot-clean.
3. **Week 8–10: Full backward-compat audit**. Run all v1.x YAML
   examples through v2.0 renderer; report any drift exceeding the
   tolerance defined in Phase 0.

**v2.0 deliverables**:
- `grid` and `row` containers
- Modular renderer (per-object-type modules + registration interface)
- Full v1.x backward-compat regression report

**Decision points during Phase 3**:
- Interop rules: nested absolute-coord children inside auto-layout
  containers

**Risks specific to Phase 3**:
- Modularization regressions in v1.x decks
- Scope creep on auto-layout (mitigation: defer constraint-solver
  features indefinitely)

## 4. Critical Path

```
Phase 0 (user gate, 1wk)
   │
   ▼
SP-6 test harness ──► all subsequent features
   │
   ▼
SP-7 distribution (parallel)
   │
   ▼
SP-2 rich text (spans → bullets)
   │
   ▼
SP-1a auto-layout schema + stack
   │
   ▼
v1.5 charts (depend on spans)
   │
   ▼
v2.0 grid/row (depend on stack schema)
```

**Total**: ~29 weeks ≈ 6.5 months. **Exceeds the stated 6-month
constraint by ~2 weeks.** The Strategist's "Cut A" (drop transition
metadata, defer property-based testing) brings it close. To hit
exactly 6 months, **further scope cuts would be required** — most
likely deferring `sparkline` from v1.5 (saves ~1 week) and shipping
`grid` only (no `row`) in v2.0 (saves ~2 weeks).

## 5. Trade-offs Accepted

| Trade-off | In favor of | Rationale |
|---|---|---|
| Transition metadata (G11) deferred indefinitely | Fitting within ~6.5-month budget | No interactive presentation runtime in scope; metadata serves a feature that won't exist. |
| Property-based testing deferred | Velocity | Golden snapshots cover the 80% case at low cost. |
| v1.4 stack-only schema constrains v2.0 grid/row | Author migration smoothness | Locking schema early avoids breaking changes; the constraint is acceptable because the design space is well-understood. |
| Charts as discrete public types (not generic `chart kind:`) | UX clarity | Three chart types is small enough to justify three public APIs; shared internals avoid code duplication. |

## 6. Risk Register

### Resolved during deliberation

| ID | Objection | Resolution |
|---|---|---|
| OBJ-2 | 6-month timeline overcommitted at full scope | Cut A applied; 6.5-month timeline with G11 dropped. |
| OBJ-3 | Auto-layout last → strands v1.4/v1.5 authors | SP-1 split: schema + stack in v1.4. |
| OBJ-5 | Spans + bullets entanglement | Grouped in SP-2, shipped together in v1.4. |
| OBJ-7 | No CI/pypi distribution story | SP-7 added; lands in v1.4. |
| OBJ-8 | 950-LOC renderer maintenance | Modularization in v2.0. |
| OBJ-10 | Font handling unspecified | Documented as runtime dependency; subset embedding deferred. |

### Open — gated on user input (Phase 0)

| ID | Objection | What's needed |
|---|---|---|
| OBJ-1 | "Production-capable" is undefined | User defines the bar (see Phase 0 decisions). |
| OBJ-4 | "Backward compatibility" is undefined | User picks: byte-identical vs. tolerance-based. |
| OBJ-6 | Presentations vs diagrams = different surfaces | User declares primary surface. |

### Open — non-blocking, monitor

| ID | Objection | Mitigation strategy |
|---|---|---|
| OBJ-9 | Gap list may not be exhaustive | Build a real reference deck during v1.4 to surface unknowns. |
| OBJ-11 | v1.4 stack schema design risk | Schema review before merge; namespace anticipates grid/row. |

## 7. Success Criteria

The roadmap succeeds if **all** of the following are true at v2.0 ship:

1. The user-defined bar from Phase 0 is met in each released version.
2. v1.x backward compatibility holds within the user-defined
   tolerance (default: 1% pixel drift).
3. Each release is pip-installable from pypi.
4. The reference 20-slide deck (built during v1.4) renders correctly
   in every released version.
5. Zero blocking objections remain at v2.0 ship.
6. Renderer is split into per-object-type modules; adding a new
   object type does not require modifying core dispatch code.

## 8. Deliberation Provenance

| Round | Key event | Source |
|---|---|---|
| R1 | Decomposer groups by architectural locus, surfaces SP-1↔SP-2 coupling | decomposer:R1 |
| R1 | Strategist proposes box-model auto-layout (rejecting cassowary) | strategist:R1 |
| R1 | Critic raises 8 objections, 2 blocking (production bar undefined; scope overcommitted) | critic:R1 |
| R1 | Synthesizer produces naive plan with auto-layout last | synthesizer:R1 |
| R2 | Decomposer splits SP-1 into v1.4 schema-seed and v2.0 full impl | decomposer:R2 (triggered by critic:R1 OBJ-3) |
| R2 | Decomposer adds SP-0 (user gate) and SP-7 (distribution) | decomposer:R2 (triggered by critic:R1 OBJ-1, OBJ-7) |
| R2 | Strategist accepts Cut A (drop transitions); raises effort estimates | strategist:R2 |
| R2 | Critic verifies all blocking objections resolved or partially-resolved (user-gated) | critic:R2 |
| R2 | Synthesizer produces converged plan with delta documentation | synthesizer:R2 |
| R2 | Convergence Judge: structurally converged, blocked only on user input → recommend accept | judge:R2 |

## 9. Unresolved Items (Explicit)

These items were **not** settled by deliberation and require user
decision before Phase 1 begins:

1. **Production-capable bar**: target persona, acceptance criterion,
   benchmark deliverable.
2. **Backward-compat tolerance**: byte-identical vs pixel tolerance.
3. **Primary surface**: presentations vs diagrams.

The synthesizer's working hypotheses (consulting analyst persona; 1%
pixel tolerance; presentations primary) are reasonable defaults but
are **not the deliberation's verdict** — they are the
synthesizer-originated assumptions used to keep planning moving, and
must be flagged as such per the skill's provenance constraint.

## 10. Items the Skill Could Not Verify

Per preference #2 (no hallucination), the following claims in this
plan are **heuristic** and need ground-truth verification:

- All effort estimates are T-shirt sizes converted to weeks via the
  rough mapping S=1, M=2-3, L=4-6, XL=8+. They are based on the gap
  descriptions in the input problem statement, not on measurements.
- The "950 LOC" for the renderer is taken from the problem statement;
  the deliberation did not inspect `framegraph_to_svg_v3.py`.
- The claim that span-aware text metrics may need `fonttools` is a
  reasonable hypothesis, not a verified necessity. The current
  per-character-class width tables may suffice; this should be tested
  empirically before adding the dependency.
- The "1% pixel tolerance" suggestion is a common default in
  graphics regression testing; the user should validate it against
  the actual rendering pipeline's noise floor.
