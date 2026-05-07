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
status: archived
archived_on: 2026-05-07
archive_reason: Superseded by the shipped repository state and retained for provenance only.
---

# Archived: Solution Plan — FrameGraph v1.3 -> Production-Capable Roadmap

This document is preserved as historical planning context. It is not the
current source of truth for package status or roadmap state.

---

## Original Document

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
