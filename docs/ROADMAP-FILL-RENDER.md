---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-07"
---

# Fill-and-Render Roadmap

**Goal**: turn the 375-pattern catalog into a working *consulting-canvas
fill-and-render pipeline*. An LLM agent (or human) addresses a pattern by
id, supplies typed content per zone, and gets a rendered SVG back.

## What's already in place (do not redo)

- **Pattern catalog** — 375 patterns with controlled vocabulary,
  validated by `framegraph._patterns.PatternCatalog`. Lives at
  [`static/refs/slides-patter-a.yml`](../static/refs/slides-patter-a.yml).
- **Per-zone metadata** — `role`, `size`, `placement`, optional `shape`,
  optional `content_type` (66% auto-annotated; 34% awaiting curation).
- **Existing SVG renderer** — `framegraph.FrameGraphRenderer` consumes a
  `Document` (validated by [`framegraph._schema.Document`](../framegraph/_schema.py))
  and emits SVG. The renderer expects objects with explicit
  `[x, y, w, h]` boxes. **The fill-and-render pipeline composes a
  Document; it does not reinvent SVG generation.**

## What's missing

| Layer | Owner |
|---|---|
| 1. Per-pattern fill schema (sidecar `fills/<id>.yml`) | This roadmap |
| 2. `PatternFill` runtime model (load + validate a fill payload) | This roadmap |
| 3. Layout engine (anchor + size → x/y/w/h) | This roadmap |
| 4. Renderer bridge (pattern + fill → FrameGraph `Document`) | This roadmap |
| 5. CLI (`framegraph patterns build <id> --fill content.yml`) | This roadmap |
| 6. Discovery / pattern picker | Out of scope (separate roadmap) |

## Architectural decisions (already locked in)

| # | Decision | Why |
|---|---|---|
| **D1** | Fill schemas live in **sidecar `fills/<id>.yml` files**, one per pattern | Allows per-pattern overrides (e.g. BMC's `revenue_streams: list[{label, metric}]`); decouples authoring cadence from the bundled YAML; missing files mean "use the default content_type-derived schema" |
| **D2** | First end-to-end render target is **Business Model Canvas (#44)** | 9 zones, region-based layout, structured grid — forces the layout engine to handle the hard cases on day one. Real consulting use case |
| **D3** | The renderer is the existing `FrameGraphRenderer`; this work composes a `Document` for it | Don't duplicate SVG generation; reuse the validated, tested pipeline |
| **D4** | The 9-cell anchor grid is the **primary** layout primitive | 80.7% of zones are anchor-placed; region/relative are second-pass refinements |

---

## Phase 1 — Fill schema foundation (XS)

**Goal**: define how a fill payload is shaped and validated. No rendering yet.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/fill.py` (new module) | `PatternFill` Pydantic model; `load_fill(pattern_id, payload)` resolver; `derive_default_fill_schema(pattern)` (uses `content_type` to compute the default Pydantic model when no sidecar override exists) |
| `static/refs/fills/.gitkeep` | Sidecar dir created; readme explaining override convention |
| `tests/unit/test_pattern_fill.py` | 1. Empty payload rejected when required zones unfilled. 2. Default schema for `content_type=title_body` accepts `{title, body}`. 3. Default for `metric` accepts `{label, value, trend?}`. 4. Default for `list_items` accepts `list[str \| {label, body?}]`. 5. Sidecar override loads instead of default when present. 6. Extra roles in payload rejected (no silent acceptance) |

### Acceptance criteria

- [ ] `PatternFill.model_validate({"pattern_id": 1, "content": {...}})` works for any catalog pattern that has all-`content_type`-annotated zones.
- [ ] Patterns with un-annotated zones (the 34% tail) raise an explicit `MissingContentTypeError` naming the offending role — not a silent fallback.
- [ ] `from framegraph.patterns import PatternFill` is exported.

### Dependencies

None. Builds on existing `framegraph._patterns`.

### Risks

- **Default content shapes may be wrong for some content_types**. Mitigation: `derive_default_fill_schema` is a starting point; sidecars override per-pattern. Wrong defaults surface during Phase 4 and get fixed in sidecars, not in the default function.

---

## Phase 2 — BMC sidecar (XS)

**Goal**: hand-author the first sidecar fill schema for the proof pattern.

### Deliverables

| | |
|---|---|
| `static/refs/fills/044-business-model-canvas.yml` | Per-zone field definitions overriding defaults where useful (e.g. `revenue_streams` as `list[{label: str, metric: str}]` rather than `list[str]`); illustrative example fill values |
| Pydantic-style schema embedded in YAML — `python3 scripts/validate_fills.py` validates the file against `PatternFill` round-trip |
| `tests/unit/test_pattern_fill.py` | + Test loading and validating BMC sidecar |

### Acceptance criteria

- [ ] `PatternFill.model_validate({"pattern_id": 44, "content": <bmc_example>})` validates the example fill in the sidecar.
- [ ] Removing any required role from the example fill raises a clear validation error naming the missing role.
- [ ] Adding an unknown role raises a clear error.

### Dependencies

Phase 1.

### Risks

- **The sidecar YAML format itself is a small DSL**. Mitigation: keep it minimal — only declare per-zone field shapes, defer formatting/validation rules to Pydantic types. If the format expands, formalize it in `framegraph._fill_schema`.

---

## Phase 3 — Layout engine (S)

**Goal**: turn pattern zones into `[x, y, w, h]` boxes on a canvas.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/layout.py` | `compute_boxes(pattern, canvas_w, canvas_h, *, margin) -> dict[role, Box]` — one box per zone |
| Anchor resolver | 9-cell + fullbleed → box; handles `equal` size by counting siblings in the same anchor cell |
| Region resolver | Named regions (`matrix_body`, `quadrant`, `ring`, `roadmap_body`, `timeline_body`) get hand-coded layouts; unknown regions fall back to anchor=center |
| Relative resolver | `inside`, `between`, `near`, `on`, `above`, `below`, `left_of`, `right_of`, `around` — applied as second-pass nudges relative to a `target` zone's box |
| `tests/unit/test_pattern_layout.py` | Per-cell anchor placement, fullbleed, equal-sibling distribution, matrix_body 4-cell layout for SWOT (#10), region+relative composition for BMC (#44), boundary cases (zero zones, single zone, max-zone pattern) |

### Acceptance criteria

- [ ] Every zone of every catalog pattern gets a non-zero box on a 1920×1080 canvas without errors.
- [ ] Boxes don't exceed canvas bounds; siblings in the same anchor cell don't overlap.
- [ ] BMC #44 produces a recognizable 9-block grid layout (manual visual inspection of golden SVG).
- [ ] SWOT #10 produces a recognizable 2×2 grid.
- [ ] Layout is deterministic — same input always yields same output.

### Dependencies

None on prior phases (operates on `SlidePattern` only).

### Risks

- **Region layouts are hand-coded per region name**. There are 19 distinct regions. Mitigation: cover the top 5 (matrix_body, highlighted, timeline_body, roadmap_body, ring) — 110 of 147 region-uses; the rest fall back to anchor=center until needed.
- **Relative-target dangling references** (52 zones identified in corpus assessment). Mitigation: when `target` doesn't resolve to a real role in the same pattern, fall back to a sensible default (e.g. for `between`, position at the centroid of all anchor-placed siblings).

---

## Phase 4 — Renderer bridge (S)

**Goal**: compose pattern + fill + computed boxes into a FrameGraph
`Document` and let the existing renderer produce SVG.

### Deliverables

| | |
|---|---|
| `framegraph/patterns/render.py` | `compose_document(pattern, fill, layout) -> Document` — emits a Document whose `visual.objects` carry the right `type`, `box`, and content per zone |
| Per-`content_type` object emitter | `title_body` → text-block object; `metric` → kpi-card object; `list_items` → text-list object; `chart_data` → chart object; `table_data` → table object; etc. Maps to the 16 first-class object types the renderer already supports |
| `tests/integration/test_pattern_render.py` | 1. BMC #44 + example fill → valid `Document` (round-trip through `framegraph._schema.Document`). 2. End-to-end: BMC #44 → SVG via `FrameGraphRenderer`. 3. Golden snapshot test for BMC SVG output |
| Golden fixture | `tests/goldens/bmc-example.svg` — the visual contract for BMC rendering |

### Acceptance criteria

- [ ] `compose_document(pattern_44, bmc_fill, layout)` produces a `Document` that passes `Document.model_validate` and has 9 visual objects.
- [ ] `FrameGraphRenderer(doc).render_svg()` returns valid SVG (parses with an XML parser, has nonzero size, contains expected text from the fill).
- [ ] Re-running the pipeline on the same fill produces a byte-identical SVG (determinism).
- [ ] At least one negative test: a fill with the wrong content_type for a zone (e.g. supplying `metric`-shaped data to a `title_body` zone) raises before rendering.

### Dependencies

Phase 1, 2, 3.

### Risks

- **Some content_types may not map cleanly to existing object types**. Mitigation: enumerate the gap explicitly during this phase; if `comparison` doesn't have a clean object type, propose one for `framegraph._schema` (separate change). Don't force-fit.
- **Existing renderer's object schema may not accept patterns-style box boundaries**. Mitigation: verify by composing a minimal Document early in the phase; if there's a gap, prefer a tiny shim in `compose_document` over modifying `_schema.py`.

---

## Phase 5 — CLI subcommand (XS)

**Goal**: ship the operator surface — `framegraph patterns build <id>`.

### Deliverables

| | |
|---|---|
| `framegraph/cli.py` | New `patterns` subcommand with `list`, `show <id>`, `build <id> --fill file.yml [-o out.svg]` |
| `framegraph patterns list [--category=consulting\|expert\|generic]` | Prints id, name, category, zone count |
| `framegraph patterns show <id>` | Prints the pattern definition + derived fill schema |
| `framegraph patterns build <id> --fill content.yml -o out.svg` | End-to-end render |
| `tests/integration/test_cli_patterns.py` | One smoke test per subcommand, plus an end-to-end build test for BMC |

### Acceptance criteria

- [ ] `framegraph patterns list --category=generic` prints exactly 50 patterns.
- [ ] `framegraph patterns show 44` prints the BMC definition without crashing.
- [ ] `framegraph patterns build 44 --fill <bmc_example_fill> -o /tmp/bmc.svg` produces a valid SVG file.
- [ ] All three subcommands exit 0 on success, non-zero on validation/render failure with a clear stderr message.

### Dependencies

Phase 4.

### Risks

- Low. CLI scaffolding is well-trodden in this codebase (`cmd_render`, `cmd_deck` already exist).

---

## Phase 6 — Coverage expansion (M)

**Goal**: extend from "BMC works" to "every pattern can render", with
sidecar curation following demand.

### Deliverables

| | |
|---|---|
| Manual curation pass | Annotate the 536 un-annotated zones with `content_type` (one batch per high-frequency role/shape combo from the corpus assessment) |
| Sidecars for the top-15 highest-leverage patterns | The 17-member comparison-table family + 4-member 4-quadrant family + the most-requested templates |
| Default-render coverage test | Iterate every catalog pattern: render with auto-generated example fill; assert no errors. Failures get sidecars or content_type fixes |
| Documented authoring guide | `docs/AUTHORING-FILLS.md` — how to write a sidecar; conventions; common patterns |

### Acceptance criteria

- [ ] 100% of catalog patterns either render successfully with default schemas or have a sidecar.
- [ ] Coverage CI test: `pytest -k test_render_all_patterns` runs all 375 patterns through the build pipeline and passes.
- [ ] Authoring guide includes 3 worked examples (one simple, one medium, one complex).

### Dependencies

Phase 5.

### Risks

- **Long tail.** The 536 un-annotated zones may surface vocabulary gaps. Mitigation: each gap becomes either a content_type addition (rare) or a sidecar override (common); curate as encountered, don't block on completeness.

---

## Out of scope (separate roadmaps)

- **Discovery / picker** — "I have a comparison story, which pattern fits?" Likely a small ML or rules-based classifier on (zone count, anchor mix, content_type mix). Different problem.
- **Promote 17-member comparison-table base pattern** — once Phase 4 ships, the 17 specializations all render the same way; promotion becomes mechanical.
- **Multi-pattern slide composition** — combining patterns in one canvas. Defer until single-pattern works.
- **Theming / brand templates** — colors, fonts, logo placement. The existing renderer's `Tokens` block supports this; a separate roadmap can layer themes on top of fills.
- **Interactive editing** — Phase 4 produces a Document; an editor would mutate that Document live. Out of scope here.

---

## Phase ordering and complexity

| Phase | Complexity | Blocking phases |
|---|---|---|
| 1 — Fill schema foundation | XS | — |
| 2 — BMC sidecar | XS | 1 |
| 3 — Layout engine | S | — (parallel with 1+2) |
| 4 — Renderer bridge | S | 1, 2, 3 |
| 5 — CLI subcommand | XS | 4 |
| 6 — Coverage expansion | M | 5 |

**Critical path**: 1 → 2 → 4 → 5 → 6. Phase 3 can run in parallel with
1+2.

**Smallest valuable demo** (end of Phase 5): an agent issues
`framegraph patterns build 44 --fill bmc.yml -o canvas.svg` and gets a
rendered Business Model Canvas. Everything from there is curation
(Phase 6) and breadth, not new architecture.

---

## Definition of "done"

The roadmap is complete when:

1. Any of the 375 patterns can be addressed by id and rendered to SVG.
2. An LLM agent can derive the fill contract for a pattern without
   reading source code (via `framegraph patterns show <id>` or
   `framegraph docs` output).
3. The fill-and-render pipeline has integration tests covering BMC
   plus at least one pattern per `content_type`.
4. The `static/refs/fills/` directory contains sidecars for every
   pattern whose default-derived fill schema is wrong or insufficient.

What this roadmap does **not** promise: that every pattern will look
beautiful. Layout quality is iterative; the architecture above lets
us improve layout and visual design without changing the fill
contract or the agent-facing API.
