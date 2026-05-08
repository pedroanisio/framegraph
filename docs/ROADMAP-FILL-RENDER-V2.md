---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-07"
---

# Fill-and-Render Roadmap — Round 2 (Visual Quality)

**Goal**: turn the working but visually-rough output from Round 1
into renders that don't need manual cleanup. The Round 1 roadmap
[`ROADMAP-FILL-RENDER.md`](ROADMAP-FILL-RENDER.md) explicitly
deferred visual quality. This roadmap closes that gap.

## What Round 1 delivered (do not redo)

- 375-pattern catalog with 100% `content_type` coverage.
- Fill-and-render pipeline: `framegraph patterns build <id> --fill
  content.yml -o out.svg` works end-to-end for every catalog
  pattern.
- 17 sidecars covering BMC + the 4-quadrant family + the
  comparison-table family.
- Corpus-wide CI test that asserts every pattern renders.
- Authoring guide.

## What Round 1 did *not* deliver (the targets here)

| Visible problem (corpus survey, May 2026) | Severity |
|---|---|
| Same-cell siblings get equal-fraction widths even when content density differs (3 tables in 1 cell get 33% each → cramped) | High |
| `list[object]` sidecar overrides flatten to bullet text (BMC's `revenue_streams` becomes `"Subs: $12.6M"` strings) | High |
| `chart_data` zones with empty `series` render as visual holes | Medium |
| `image` zones with placeholder `src` render as broken images | Medium |
| Patterns can't claim multiple cells; comparison-table family is stuck in cramped quadrants | High |
| No content-density signal from zones; layout has to guess | Medium |
| No golden snapshots beyond BMC | Medium |

## Architectural decisions (locked in, debated upfront)

| # | Decision | Why |
|---|---|---|
| **D1** | Add `span: {h: int, v: int}` to `PatternZone` so a zone can claim multiple grid cells | Solves the comparison-table cramping at the source. Without it, no amount of layout cleverness fixes 3 tables in 1 cell. |
| **D2** | `list[object]` sidecar overrides render as **2-column tables**, not flattened bullet text | Direct visual win for BMC and value-driver patterns. Bridge change only — no new content_type, no schema change. |
| **D3** | Auto-generate placeholder content for `chart_data` and `image` zones with empty/placeholder fills | An agent (or human) can preview a pattern with realistic-looking content before having real data. Bridge change only. |
| **D4** | Layout engine becomes **content-aware**: each zone declares an estimated content density; layout allocates per-cell space accordingly | Replaces the current uniform-fraction subdivision when same-cell siblings differ. |
| **D5** | The renderer is the existing `FrameGraphRenderer` (unchanged). All Round 2 work lives in `framegraph.patterns.*` and the bundled YAML schema. | Don't redesign rendering; compose better Documents. |
| **D6** | Visual contract pinned by **golden SVG snapshots** for the top-15 patterns | Drift surfaces as a diff in CI; deliberate visual changes get reviewed by snapshot update. |

---

## Phase 1 — Span schema + corpus annotation (S)

**Goal**: add the `span` field to `PatternZone`; identify and
annotate the catalog patterns where same-cell sibling cramping is
visible.

### Deliverables

| | |
|---|---|
| `framegraph/_patterns.py` | `Span` Pydantic model: `{h: int = 1, v: int = 1}` (default = single cell). `PatternZone.span: Span = Field(default_factory=Span)`. Identity-neutral — does not participate in structural fingerprint. |
| `tests/unit/test_patterns_schema.py` | + tests: span defaults, span ≥ 1, span participates in zone serialization, two patterns differing only in span are still structural duplicates (span is layout, not identity) |
| `scripts/annotate_spans.py` | Heuristic pass: for patterns where 3+ zones share a cell, flag them; for the comparison-table family specifically, set `span: {h: 2}` on the data-column zones so they get full-row width |
| Bundled YAML | Updated for the top ~30 patterns where a span change is clearly correct (manual review of generated annotations) |

### Acceptance criteria

- [ ] All zones default `span: {h: 1, v: 1}` if absent — backwards-compatible with existing fills.
- [ ] Catalog re-validates after the corpus annotation pass.
- [ ] `compute_boxes` (Phase 2) honors the span field; no zone's box exceeds `cell_w × span.h` (or the canvas).
- [ ] Test asserting two patterns identical except for `span` are structurally duplicates (Round 1 invariant preserved).

### Dependencies

None.

### Risks

- **Span values may conflict with same-cell siblings**: if zone A claims `span: {h: 2}` starting at cell `(left, middle)`, it overlaps cell `(center, middle)` — any zone there must coexist. Mitigation: layout engine handles overlap by giving the spanning zone its declared width and stacking the colliding zone below; warn (not error) when it happens.
- **Annotating 30 patterns by hand is error-prone**: use a script to suggest spans, then review the diff before applying.

---

## Phase 2 — Content-density layout (M)

**Goal**: replace uniform same-cell subdivision with density-aware
allocation that honors `span`.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/layout.py` | New `_density(zone, fill) -> tuple[float, float]` — estimates `(width_demand, height_demand)` per zone based on content_type + actual fill content. Tables get `cols × col_width_est`; lists get `max_line_chars`; metrics get `max(label, value) × glyph_width`. |
| `compute_boxes` updated | Two-pass: (1) compute span-aware base cells; (2) for each multi-zone cell, allocate by relative density rather than equal split. Tables and chart_data get higher density weight than list_items. |
| `tests/unit/test_pattern_layout.py` | + tests: `span: {h: 2}` produces a wider box; same-cell siblings with different content types get proportional widths; corpus regression (every pattern still lays out cleanly). |
| New compute signature | `compute_boxes(pattern, canvas_w, canvas_h, fill=None, *, margin=24.0)`. Backwards-compatible: `fill=None` falls back to uniform allocation (current behavior). |

### Acceptance criteria

- [ ] BMC `revenue_streams` zone (declared with `span: {h: 1}`) keeps current width.
- [ ] Communications Plan #91 with `span: {h: 2}` on data-column zones lays them out wider than the current 33%-of-cell width.
- [ ] When `fill` is supplied, density weighting kicks in; when None, behavior matches Round 1 exactly (no regression for old call sites).
- [ ] Layout is still deterministic.
- [ ] Layout is still total — every zone gets a non-zero box.
- [ ] Same-cell siblings still don't overlap.

### Dependencies

Phase 1 (span field).

### Risks

- **Density estimation is heuristic**: a long bullet list might overflow even after density-aware allocation. Mitigation: layout produces a *target* size; the renderer's existing `overflow: clip` / `shrink_to_fit` text policies handle the residual.
- **Backwards compatibility on `compute_boxes` signature**: `fill` becomes optional kw-only; existing callers (corpus coverage test, BMC golden) pass `fill=None` implicitly. Verify all callsites pre-merge.

---

## Phase 3 — list[object] renders as 2-column table (S)

**Goal**: when a sidecar declares `item_kind: object` for a
`list_items` zone, emit a `table` object instead of flattening to
bullet text.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/render.py` | `_emit_list_items` becomes context-aware: if the fill content is `list[BaseModel]` (Pydantic-ified `item_kind: object`), emit a `table` object with one row per item and one column per field. Otherwise (list of strings), keep current `bullet_list` emission. |
| Renderer tests | New tests for BMC: `revenue_streams` zone now emits `data-type="table"` not `data-type="bullet_list"`; verify column headers come from the sidecar's `item_fields` keys. |
| Golden update | Re-capture `tests/goldens/bmc-example.svg` with the new table rendering. |

### Acceptance criteria

- [ ] BMC `revenue_streams` and `cost_structure` zones render as 2-column tables in the SVG.
- [ ] Table column headers match the sidecar's `item_fields` keys (`label`, `metric`).
- [ ] BMC golden snapshot updated and tracked.
- [ ] No regression on patterns that don't have `item_kind: object` overrides — they keep the bullet_list rendering.

### Dependencies

None on Phase 1/2 (renderer-only change). Can run in parallel with Phase 1.

### Risks

- **Existing fills that pass `list[dict]` instead of `list[BaseModel]`**: detect both shapes (the validated Pydantic objects and raw dicts that came through some unvalidated path).
- **Tables in narrow boxes still cramped**: this Phase 3 fix lands inside the box layout gives it. Phase 1+2 (span + density) is what actually makes the boxes wide enough.

---

## Phase 4 — Auto-generate placeholders for empty fills (XS)

**Goal**: chart_data and image zones with empty/placeholder
content render visibly so an agent can preview a pattern before
having real data.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/render.py` | `_emit_chart_data`: if `series` is empty, emit a 3-bar placeholder chart with sample labels. `_emit_image`: if `src` is empty/placeholder, emit a labeled rectangle ("image: <role>") instead of a broken image. |
| Tests | Smoke test: a pattern with chart_data and image zones produces visible content (non-empty rendered area, recognizable placeholder text) when filled with empties. |

### Acceptance criteria

- [ ] A pattern with only chart_data + image zones, filled with empties, produces a non-empty SVG with visible placeholder content.
- [ ] Real data (non-empty `series`, real image `src`) still renders correctly — placeholders only kick in for emptiness.

### Dependencies

None. Can run in parallel.

### Risks

- **Placeholders may mask "user forgot real data"**: mitigate by tagging placeholder objects with `decorative: true` and a `data-placeholder="true"` attribute so callers can detect / remove them.

---

## Phase 5 — Golden snapshots for top-15 patterns (S)

**Goal**: pin the visual contract for the highest-leverage
patterns. Drift surfaces as a CI diff.

### Deliverables

| | |
|---|---|
| `tests/goldens/` | One golden SVG per top-15 pattern, covering BMC + 4-quadrant family + 10 comparison-table family members. |
| `tests/integration/test_pattern_goldens.py` | Iterates the 15 fixtures + golden pairs; asserts byte-identical SVG output. Capture-on-missing (matches Round 1's BMC golden behavior). |
| Golden capture script | `scripts/capture_pattern_goldens.py` — for each fixture, build SVG via `render_pattern_svg`, save to `tests/goldens/<id>-<slug>.svg`. |

### Acceptance criteria

- [ ] 15 goldens captured.
- [ ] Test passes byte-identical comparison on subsequent runs.
- [ ] To re-capture (after a deliberate visual change): delete the golden, rerun. Documented in the test docstring.

### Dependencies

Phases 1, 2, 3, 4 — golden quality reflects the visual improvements.

### Risks

- **Golden churn**: every visual tweak triggers all 15 goldens to need re-capture. Mitigate by only capturing top-15 (not all 375) — narrow blast radius.

---

## Phase 6 — Update Round 1 BMC golden + corpus regression (XS)

**Goal**: refresh the BMC golden with Round 2 improvements, and
extend the corpus-coverage test to assert visual quality
properties (not just "doesn't crash").

### Deliverables

| | |
|---|---|
| `tests/goldens/bmc-example.svg` | Re-captured with Round 2 rendering (revenue_streams as table; density-aware layout). |
| `tests/integration/test_corpus_render_coverage.py` | + assertions: every pattern's SVG has at least one visible content element (not empty); SVG size is within a sane range (≥ 500 bytes, ≤ 100 KB). |
| Updated `docs/AUTHORING-FILLS.md` | Note that `list[object]` sidecars now render as tables; document the placeholder behavior. |

### Acceptance criteria

- [ ] BMC golden refreshed.
- [ ] Corpus test catches "renders to nothing" failures.
- [ ] Authoring guide reflects Round 2 behavior.

### Dependencies

Phases 1–5.

### Risks

- Low. Mostly mechanical updates after the substance is in.

---

## Out of scope (Round 3+ candidates)

- **Promote 17-member comparison-table base pattern** (`inherits_from: <id>`). Schema change + corpus migration. Deferred because Round 2 fixes the visible problem (cramped tables); promotion is structural cleanup.
- **Discovery / picker** ("I have a comparison story → which pattern?"). A genuinely separate problem.
- **Multi-pattern decks**. FrameGraph already supports decks; the bridge could compose deck.yml documents from N (pattern, fill) pairs. Useful but a different scope.
- **Theming / brand tokens applied to pattern renders**. Existing Tokens layer supports this; bridge can pass tokens through. Worth doing once Round 2 visual quality is in place.
- **Sidecar mini-DSL extensions** (numeric types, enums, nested objects). Useful when a real pattern needs them — none does today.
- **Interactive editing of generated SVG**. Different product.

---

## Phase ordering and complexity

| Phase | Complexity | Blocking phases |
|---|---|---|
| 1 — Span schema + annotation | S | — |
| 2 — Content-density layout | M | 1 |
| 3 — list[object] → table | S | — (parallel with 1+2) |
| 4 — Auto-placeholders | XS | — (parallel) |
| 5 — Top-15 goldens | S | 1, 2, 3, 4 |
| 6 — Refresh + corpus assertions | XS | 1–5 |

**Critical path**: 1 → 2 → 5 → 6.
**Parallel-able**: Phase 3 and Phase 4 can land any time; Phase 5
captures the visual contract after they're in.

**Smallest valuable demo** (end of Phase 3): BMC's `revenue_streams`
visibly renders as a 2-column table. Re-running `framegraph
patterns build 44 --fill bmc.yml -o canvas.svg` produces a
visibly-improved BMC.

---

## Definition of "done" for Round 2

The roadmap is complete when:

1. The 17-member comparison-table family no longer renders with
   cramped same-cell tables. (Fix: span on data-column zones.)
2. BMC's `revenue_streams` and `cost_structure` render as
   2-column tables instead of bullet text.
3. Patterns with `chart_data` or `image` zones render visibly when
   filled with placeholder content.
4. The top-15 patterns have golden SVG snapshots tracked in CI.
5. The corpus-coverage test asserts visual properties (non-empty
   render), not just "doesn't crash".

What this roadmap does **not** promise:

- Pixel-perfect typography / brand styling. That's theming
  (Round 3+).
- Visually-balanced layouts for the 358 patterns without a
  sidecar. They'll render correctly via the engine, but only the
  top-15 get their visual contract pinned.
- Discovery, decks, or any non-rendering concern.

The success criterion is: **agents producing slides via
`framegraph patterns build` get output that doesn't need manual
cleanup for the patterns most users will actually request**.
