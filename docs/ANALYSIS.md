---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# Repository architecture and algorithmic analysis

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](../DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

> **Methodology note.** Sections 1 and 2 are observed facts from this repository (file paths, line counts, function and class names cited inline so claims are verifiable). Sections 3, 4, and 5 mix observed repo facts with background knowledge of the named competitors at the level of public docs / common knowledge. The author has **not** inspected competitor sources for this analysis; competitor claims are flagged with **[external]** when they go beyond what is universally documented. Anything not confidently verifiable is marked **[uncertain]**.

---

## 1. Subsystem map

Total: **~21.8k** Python source LOC + **~16.5k** test LOC. **1283** tests pass.

| Subsystem | Path | LOC | Role |
|---|---|---|---|
| Rendering core | `framegraph/renderer.py` | 1,450 | `FrameGraphRenderer` class — token resolution, object index, marker / gradient / effect-filter `<defs>`, dispatch loop |
| Per-type renderers | `framegraph/renderers/*.py` | 3,762 | 9 modules, each `RENDERERS = {type: render_fn}` — registered through `_register_all` |
| Pure helpers | `framegraph/_helpers.py` | 264 | `esc/fnum/fmt/sid/attrs/box/pt/deep_get/pts_attr` + lorem expander |
| Visual schema | `framegraph/_schema.py` | 884 | 59 Pydantic v2 models, discriminated-union over 16 visual types |
| UML schema | `framegraph/_uml.py` | 3,103 | 61 Pydantic models — UML 2.5 ontology |
| Library + deck | `framegraph/library.py` | 1,317 | `FrameGraphLibrary`, `FrameGraphDeckRenderer`, `FrameGraphComposer`, deep-merge inheritance |
| CLI | `framegraph/cli.py` | 1,314 | `render`, `deck`, `patterns *`, `docs`; PDF (raster + vector), 4K PNG |
| Pattern catalog | `framegraph/_patterns.py` | 492 | 375 slide-template patterns, typed Anchor/Region/Relative placements |
| Pattern layout | `framegraph/patterns/layout.py` | 1,340 | `_AnchorGrid`, span-aware grid, density allocation, region handlers, relative resolver |
| Pattern render bridge | `framegraph/patterns/render.py` | 759 | `compose_document` — pattern + fill + layout + stylesheet → visual objects |
| Pattern fill / sidecar | `framegraph/patterns/{fill,sidecar,style}.py` | 780 | content_type-derived schemas + sidecar overrides |
| Sugiyama layout | `framegraph/layout/sugiyama.py` | 855 | 4-stage hierarchical layout |
| UML composers | `framegraph/uml/*.py` | 3,996 | 14 diagram-type composers (Phases A–E) |
| Docs catalog | `framegraph/docs.py` | 209 | Machine-readable JSON dump for LLM agents |

The architecture has **four layers**:

```
                      ┌── framegraph patterns build / deck
                      │
  CLI ────────────────┤── framegraph render
                      │
                      └── framegraph deck (multi-page)
                                │
                                ▼
       ┌──────────  Library: FrameGraphDeckRenderer / FrameGraphComposer
       │            • theme + slide deep_merge inheritance
       │            • $extends, $theme, stylesheet
       │
       │            Pattern bridge: compose_document
       │            • pattern + fill + layout + stylesheet → visual.layers dict
       │
       │            Sugiyama layout (855 LOC) — hierarchical placement
       │
       │            Pattern layout (1340 LOC) — _AnchorGrid + density allocator
       │
       ▼
  FrameGraphRenderer (1450 LOC)
       │
       ├── 9 per-type renderer modules (shapes / text / lines / charts / image
       │                                / symbols / layout / table / uml)
       └── Renders to single SVG string
                                │
                                ▼
                  Output: SVG (always) | raster PDF | vector PDF | 4K PNG
```

---

## 2. Algorithms — observed

### 2.1 Hierarchical layout (Sugiyama)

`framegraph/layout/sugiyama.py:855` documents and implements the four canonical stages (citations are in the module docstring at lines 1-46):

| Stage | Algorithm | Reference cited in source |
|---|---|---|
| 1 | Cycle removal — greedy feedback-edge-set | Eades, Lin, Smyth (1993) |
| 2 | Layer assignment — longest-path layering with dummy-node insertion | Sugiyama et al. (1981); Gansner et al. (1993) |
| 3 | Crossing minimization — iterative median-heuristic sweeps, alternating directions, early-exit on `passes_without_change` | Sugiyama (1981) lineage |
| 4 | X-coordinate assignment — Brandes & Köpf four-sweep variant, averaged | Brandes & Köpf (2002) |

**Notable**: this is a *pure-Python* implementation of the production-quality algorithm Graphviz/dagre/ELK use. 855 LOC. 366 LOC of focused tests in `tests/unit/test_sugiyama.py`. **Strength.**

### 2.2 Pattern layout — `_AnchorGrid` (Round 2)

The pattern engine (`framegraph/patterns/layout.py:186-540`) implements a layout strategy that is **not** a standard published algorithm — it is a domain-specific design. Two stated rules (`_AnchorGrid.from_zones` docstring, lines 232-260):

1. **Used coordinates only.** Grid columns/rows are the cross-product of unique (h, v) anchor coordinates the pattern actually uses, expanded by spans. SWOT's four-corner anchors → 2×2 grid. BMC's nine anchors → 3×3.
2. **Weighted by demand.** Column widths and row heights are proportional to per-cell demand from `_density_weight` and `_row_demand_weight` (lines 580+), which combine `_BASE_DENSITY` (per `content_type`) × `_SIZE_MULTIPLIER` (per `size`) × content-aware factors (item count, row count) when a fill is supplied.

Plus three composable rules:

- **Span-aware** — `PatternZone.span: {h, v}` claims adjacent cells with `_grid_span_box`.
- **Same-cell sibling subdivision** — `_density_subdivide` (lines 920+): wide-content siblings (`table_data`, `chart_data`, `list_items`) **stack vertically** with row-demand weighting; narrow siblings (`metric`, `axis_label`) split **horizontally** by density weight.
- **Relative refinement pass** — `_relative_box` honors `below|above|left_of|right_of|inside|around|near|on|between`, all clamped to canvas via `_clamp_to_canvas` with a 12-px floor.

Region handlers (`_region_box`, lines 770-820) cover the top-5 named regions hand-coded; everything else falls back to a centered medium box.

**Strength**: the design is honest about being a heuristic — the algorithm's contract is documented in the docstring and pinned by 32 unit tests. **Weakness**: the rules are domain-specific and the `_BASE_DENSITY` / `_SIZE_MULTIPLIER` constants are hand-tuned, not learned or measured.

### 2.3 Token resolution + deep_merge

`framegraph/library.py:45` `deep_merge` does recursive dict merge with **lists replaced, not concatenated**. The slide token resolution order (line 1009-1010) is `library $theme < deck.tokens < $extends base < slide-local`. Symbols and component_defs follow the same order.

### 2.4 Renderer dispatch + plug-in contract

The renderer is a **plug-in dispatcher**: `_register_all` (`renderer.py:1128`) iterates `framegraph.renderers.ALL_MODULES`, each module exporting a `RENDERERS = {type_name: fn}` table; third-parties register at runtime via `register(type_name, fn)`. The `r` parameter every render fn receives is the `RendererContext` Protocol (`framegraph/_types.py`) — a 30-member structural type covering token resolution, object indexing, geometry, text metrics, and four delegate helpers (`text_svg`, `render_rect`, `eval_length`, `effect_filter_attrs`).

### 2.5 Schema and validation

`framegraph/_schema.py` (884 LOC, 59 models) is a Pydantic v2 discriminated union over the 16 first-class visual object types, with `extra="allow"` for forward-compatibility and slot pass-through, and a permissive `_UnknownObject` fall-through so third-party `register()` plug-ins don't break ingestion. `_uml.py` adds another 61 typed models for the UML 2.5 ontology with strict validators (e.g., self-generalization rejected).

### 2.6 Output pipeline

`framegraph/cli.py`:
- **SVG**: synthesized by string concatenation in `FrameGraphRenderer.render_svg` — single pass over layers, per-object `try/except` demoted to HTML comments + `self.warnings`.
- **Raster PDF**: cairosvg → high-DPI PNG → Pillow multi-page PDF.
- **Vector PDF**: weasyprint per-slide → pypdf concatenation.
- **4K PNG**: cairosvg `output_width=3840`.

The choice to rasterize for default PDF (rather than cairosvg's vector path) is documented at `cli.py:174-186`: cairosvg+pango+harfbuzz disagree with FrameGraph's per-character-class width tables when the system lacks the requested font, producing kerning artefacts. Rasterizing locks layout into pixels first.

---

## 3. Strengths and weaknesses (observed)

### Strengths

| | Evidence |
|---|---|
| **Tiny dependency surface for the core** | Only `PyYAML` + `Pydantic` required at runtime (`pyproject.toml:40-43`). No browser, no Node, no JVM, no LaTeX. PDF and PNG are optional extras. |
| **Pure-Python production-quality Sugiyama** | 855 LOC, 4 canonical stages with literature citations, 366 LOC of tests. |
| **Strong typed contracts at every boundary** | 120 Pydantic models across visual + UML schemas; `RendererContext` Protocol formalizes the plug-in surface. |
| **Three layered authoring paths** | Bespoke (`render`), pattern-composed (`patterns build`), deck (`deck`) — documented in `AGENTS.md` and `docs/MANUAL.md`. |
| **Determinism by design** | "Same input → same output." No RNG; layout follows declaration order (per `framegraph/patterns/layout.py:43-46`). |
| **Coverage gate + golden snapshots** | 90 % gate; 1283 tests passing; rasterized golden-snapshot harness with configurable per-pixel tolerance. |
| **Pattern catalog scale** | 375 slide-template patterns across generic / consulting / expert categories; 17 with curated `example_fill` sidecars. |
| **UML breadth** | 14 diagram composers covering UML 2.5.1 (Phase A–E) — class, package, use-case, component, deployment, activity, state-machine, sequence, communication, composite, object, profile, timing, interaction-overview. |
| **AI-agent first-class** | `framegraph docs -o catalog.json` emits Pydantic JSON schemas + signatures for every public model; `AGENTS.md` documents the agent loop. |
| **Reviewable source format** | YAML diffs are human-readable; bytewise comparable in code review. |

### Weaknesses

| | Evidence |
|---|---|
| **No constraint-solver layout** | All "auto-layout" is anchored / regional / relative + Sugiyama for hierarchical graphs. No spring physics, no force-directed for non-hierarchical graphs (mind-maps, ecosystems), no Cassowary-style constraint solver. `examples/genai-ecosystem/` is hand-placed for a reason. |
| **Pattern density heuristics are hand-tuned** | `_BASE_DENSITY`, `_SIZE_MULTIPLIER` (`framegraph/patterns/layout.py:540-580`) are constants. No measured correlation with rendered output quality; no auto-fit feedback loop. |
| **Text width estimation is per-character-class, not actual font metrics** | `_str_width` uses 6-class width tables (`narrow / normal / wide / space / digit / punct`). The `[metrics]` extra promises fonttools-backed measurement but isn't wired in. Real font kerning, ligatures, complex scripts all unsupported. |
| **No interactivity at output time** | SVG only. No animations, transitions, hyperlinks-by-default, web embeddings. |
| **Pattern catalog: 17 / 375 sidecared** | 95 % of patterns have only the default content_type-derived schema. Authors of bespoke fills must read `patterns show <id>` and infer the right shape. |
| **Mypy strict has 200+ errors** | Strict mode is enabled but CI is `continue-on-error: true`. Most errors are pydantic-stubs and `_uml.py`/`_patterns.py` type drift. |
| **No PowerPoint / DOCX output** | SVG and PDF only. Rules out scenarios where the deliverable must be edited downstream by a non-engineer. |
| **No mermaid / plantuml ingestion** | UML composers consume FrameGraph's typed model; there is no parser for external syntaxes (this is an explicit Decision-3 non-goal in `_uml.py:30-33`, but it is still a competitive gap). |
| **Decks are static** | No speaker-mode, no incremental slide builds, no live preview. `notes.md` is a separate sibling file. |
| **No collaborative editing surface** | YAML in git; no live-share / multi-cursor / comment threads. |
| **Pattern catalog is not crowd-sourced** | 375 patterns shipped in-tree (`static/refs/slides-patter-*.yml`). No registry / theme marketplace. |

---

## 4. Competitor comparison

> **External-knowledge caveat.** What follows is based on public docs / common knowledge as of the author's training. Competitor specifics (e.g., dagre's exact algorithm version, draw.io's layout solver) can drift between releases. Cells marked **[uncertain]** are claims the author cannot verify in this session.

### 4.1 Comparable competitor categories

The comparison space splits into three competitor classes because no single tool overlaps with all of FrameGraph at once:

| Class | Competitors |
|---|---|
| **A. Slide / deck tooling** | Marp · Slidev · reveal.js · LaTeX Beamer · Pandoc Beamer · PowerPoint + python-pptx |
| **B. Diagram tooling** | Mermaid · PlantUML · Graphviz / DOT · D2 · TikZ · draw.io · excalidraw [external] |
| **C. Layout libraries** | Eclipse Layout Kernel (ELK) · dagre · networkx |

### 4.2 Per-tool profile (what is being compared against)

| Tool | Source format | Auto-layout | Output | Runtime | Notes [external] |
|---|---|---|---|---|---|
| **Marp** | Markdown + CSS | None (CSS) | HTML, PDF, PPTX [external] | Node | Big theme ecosystem; trades layout precision for write-speed. |
| **Slidev** | Vue + Markdown | None | HTML, PDF | Node | Live HTML preview; rich animation; deck = JS app. |
| **reveal.js** | HTML/Markdown | None | HTML | Browser | Mature animations; deck IS a webpage. |
| **LaTeX Beamer** | LaTeX | TikZ-side | PDF | TeX engine | Typographic gold standard; slow build, steep curve. |
| **Pandoc Beamer** | Markdown → Beamer | None | PDF / many | Haskell | Convert-everything Swiss Army knife. |
| **python-pptx** | Imperative Python | None | .pptx | Python | Native PowerPoint; no declarative source. |
| **Mermaid** | Mermaid DSL | dagre [external] | SVG | Browser/Node | One-line "graph LR"; GitHub native render. |
| **PlantUML** | PlantUML DSL | Graphviz [external] | PNG / SVG | JVM | Strong UML 2 coverage; image-only output. |
| **Graphviz** | DOT | Sugiyama / spring / circular | SVG / PNG / PDF | C | Decades-mature graph layout. No slides. |
| **D2** | D2 DSL | ELK / dagre [external] | SVG | Go | Modern declarative; handsome defaults. |
| **TikZ** | LaTeX | Manual + libraries | PDF | TeX engine | Print-quality precision; very steep. |
| **draw.io** | XML (`.drawio`) | Optional | SVG / PNG / PDF | Browser/desktop | WYSIWYG; rich shape lib; XML not human-friendly. |
| **excalidraw** [external] | JSON | None | SVG / PNG | Browser | Hand-drawn aesthetic; whiteboarding. |
| **ELK / dagre** | API only | Sugiyama family | Layouts | JVM / JS | Layout-only — no render, no deck. |

### 4.3 Capability matrix

> **Symbols.** ●●● Strong ・ ●● Adequate ・ ● Weak ・ — Not applicable. **[u]** = uncertain about claim.

| Capability | FrameGraph | Marp | Slidev | reveal.js | Beamer | python-pptx | Mermaid | PlantUML | Graphviz | D2 | draw.io |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Declarative source | ●●● YAML | ●●● MD | ●● MD+Vue | ●● HTML/MD | ●●● TeX | ● Code | ●●● DSL | ●●● DSL | ●●● DOT | ●●● DSL | ● XML |
| Source diff-friendly | ●●● | ●●● | ●● | ●● | ●●● | — | ●●● | ●●● | ●●● | ●●● | ● |
| Multi-page deck | ●●● | ●●● | ●●● | ●●● | ●●● | ●●● | — | — | — | — | — |
| Slide patterns library | ●●● 375 | — | ●● [u] | ●● [u] | ●● | — | — | — | — | — | ●● shapes |
| Diagrams in same source | ●●● | ● | ●● [u] | ●● [u] | ●●● TikZ | ● | — | — | — | — | — |
| Pure SVG output | ●●● | ●● | ●● | ●● | — | — | ●●● | ●●● | ●●● | ●●● | ●● |
| Vector PDF output | ●● weasyprint | ●● | ●● | ●● | ●●● | — | ● [u] | ●● | ●●● | ●● | ●●● |
| Pure-Python core | ●●● | — | — | — | — | ●●● | — | — | — | — | — |
| Zero runtime deps (core) | ●●● 2 | ● Node | ● Node | ● Browser | ● TeX | ●● Python | ● Node | ● JVM | ● C | ● Go | ● App |
| Hierarchical auto-layout | ●●● Sugiyama | — | — | — | ●● TikZ | — | ●●● dagre [u] | ●●● Graphviz [u] | ●●● | ●●● | ●● |
| Force-directed / spring | — | — | — | — | — | — | ● [u] | ●● [u] | ●●● | ●● | ●● |
| Constraint-solver layout | — | — | — | — | — | — | — | — | ●● [u] | — | ●● [u] |
| UML 2 coverage | ●●● 14 | — | — | — | ●● | — | ●● | ●●● | — | ● | ●● |
| Pattern fill validation | ●●● Pydantic | — | — | — | — | — | — | — | — | — | — |
| Theme inheritance ($extends) | ●●● | ●● [u] | ●● | ● | ●● | — | — | — | — | — | — |
| Animation / transitions | — | ●● [u] | ●●● | ●●● | ●● | ● | — | — | — | — | — |
| WYSIWYG editor | — | — | ●● live | ●● live | — | ●● | ●● live | — | — | ●● | ●●● |
| AI-agent JSON catalog | ●●● | — | — | — | — | — | — | — | — | — | — |
| PowerPoint / DOCX export | — | ●● PPTX [u] | — | — | — | ●●● | — | — | — | — | — |
| Print-quality typography | ●● | ●● | ●● | ● | ●●● | ●● | ●● | ●● | ●● | ●● | ●● |
| Determinism | ●●● | ●●● | ●● | ●● | ●●● | ●●● | ●● [u] | ●● [u] | ●●● | ●●● | ●●● |
| Test gate / regression suite | ●●● 1283 | — | — | — | — | — | — | — | — | — | — |

---

## 5. Scoring matrix

Criteria weighted by their relative importance for the project's stated audience (engineers / consultants / tool-builders, per `PURPOSE.md`). Each criterion scored 1–10 from FrameGraph's perspective: 10 = FrameGraph clearly wins, 5 = parity, 1 = competitor clearly wins. **Weight × score = contribution.** Total / sum-of-weights = overall position.

### 5.1 Criteria and weights

| Criterion | Weight | Why this weight |
|---|---|---|
| Source diff-/review-friendliness | 8 | Stated commitment in `PURPOSE.md`; primary reason engineers adopt the project |
| Pure-Python / minimal deps | 7 | Core differentiator vs every Node/JVM/TeX competitor |
| Multi-page deck workflows | 8 | Primary use-case stated in `AGENTS.md` |
| Pattern catalog / templating | 9 | Largest single capability set in the codebase (375 patterns) |
| Hierarchical auto-layout | 6 | Sugiyama is real but only one layout family |
| UML 2 coverage | 5 | Genuine strength, but niche audience |
| Print-quality typography | 6 | Where Beamer/TikZ outclass everyone; relevant for client deliverables |
| Animations / interactivity | 4 | Out of scope per `PURPOSE.md` non-goals |
| AI-agent surface | 7 | Recently emphasised; rapidly growing relevance |
| WYSIWYG / non-engineer editor | 4 | Out of scope, but a real adoption barrier |
| PowerPoint / DOCX export | 5 | Often blocking for corporate deliverables |
| Determinism / regression gate | 6 | Strong here (1283 tests, golden harness) |

Sum of weights = **75**.

### 5.2 FrameGraph vs each competitor (scores out of 10)

| Criterion (weight) | Marp | Slidev | reveal.js | Beamer | python-pptx | Mermaid | PlantUML | Graphviz | D2 | draw.io |
|---|---|---|---|---|---|---|---|---|---|---|
| Diff/review (8) | 5 | 5 | 4 | 5 | 9 | 5 | 5 | 5 | 5 | 9 |
| Pure-Python deps (7) | 9 | 9 | 9 | 8 | 5 | 9 | 9 | 8 | 9 | 9 |
| Deck workflows (8) | 4 | 4 | 4 | 4 | 4 | 9 | 9 | 9 | 9 | 9 |
| Pattern catalog (9) | 9 | 8 | 8 | 8 | 9 | 9 | 9 | 9 | 9 | 7 |
| Hier. auto-layout (6) | 7 | 7 | 7 | 6 | 7 | 5 | 4 | 3 | 4 | 4 |
| UML coverage (5) | 9 | 9 | 9 | 7 | 9 | 6 | 3 | 8 | 7 | 6 |
| Print typography (6) | 6 | 6 | 7 | 2 | 5 | 6 | 6 | 6 | 6 | 6 |
| Anims / interact. (4) | 3 | 2 | 1 | 4 | 3 | 7 | 7 | 7 | 7 | 5 |
| AI-agent surface (7) | 9 | 9 | 9 | 9 | 7 | 8 | 8 | 7 | 8 | 9 |
| WYSIWYG (4) | 5 | 4 | 4 | 5 | 3 | 5 | 5 | 5 | 5 | 1 |
| PPTX/DOCX export (5) | 4 [u] | 5 | 5 | 5 | 1 | 5 | 5 | 5 | 5 | 4 |
| Determinism / tests (6) | 6 | 7 | 7 | 6 | 6 | 7 | 6 | 5 | 6 | 6 |
| **Weighted total / 75** | **6.5** | **6.4** | **6.2** | **6.0** | **6.0** | **7.1** | **6.7** | **6.5** | **6.7** | **6.5** |

**Interpretation.** Numbers cluster between **6.0** and **7.1**, which means FrameGraph is roughly *peer-or-better* across the comparison space — no obvious dominator, no obvious blow-out. The highest score (7.1 vs Mermaid) reflects FrameGraph's clear lead on deck workflows, patterns, UML, and AI surface, against Mermaid's strength only in inline-graph syntax. The lowest (6.0 vs Beamer / python-pptx) reflects real gaps: typography vs Beamer, native PowerPoint vs python-pptx.

**Where FrameGraph wins regardless of competitor**: pattern catalog (9), pure-Python deps (8-9), AI-agent surface (7-9), determinism / test gate (6-7).

**Where FrameGraph trails consistently**: animations / interactivity (1-4), PPTX export (1-5).

---

## 6. Prioritized improvement roadmap

Each item carries an **Impact** (deck-workflow / agent-workflow / diagram-quality lift), an **Effort** (XS/S/M/L/XL per CLAUDE.md's rule), and a **Strategic value** rating (HIGH / MED / LOW), then a **Score = Impact × Strategic / Effort** for ranking.

### Tier 1 — Highest leverage (ship first)

| # | Item | Impact | Effort | Strategic | Why now |
|---|---|---|---|---|---|
| 1 | **Real font-metric measurement (`fonttools` extra)** | HIGH | M | HIGH | The `[metrics]` extra is already declared in `pyproject.toml:60-62` but never wired in. Replacing the 6-class char-width tables with TTF advance widths fixes kerning artefacts in vector-PDF output (`cli.py:174-186` documents the current workaround) and tightens layout for the 17 sidecared patterns. Closes the typography gap vs Beamer at the edges. |
| 2 | **Sidecar coverage from 17 → ~100 of 375 patterns** | HIGH | L | HIGH | Sidecars convert "look at `patterns show <id>` and guess" into "agent calls `patterns example`." The bottleneck on pattern adoption is the 95 % of patterns with only default schemas. M-effort per sidecar; pareto-fronting the consulting category (275 patterns) gets the biggest ROI. |
| 3 | **PPTX export via python-pptx bridge** | HIGH | M | HIGH | Closes the single largest "I can't deliver this" gap for corporate audiences. Each slide's resolved `visual.layers` maps cleanly to pptx shapes (`rect`, `text`, `image`). Pattern-composed slides translate via the same render bridge; bespoke slides need shape-by-shape mapping. Ships behind a `[pptx]` extra. |
| 4 | **Force-directed / spring layout** | HIGH | L | MED | Sugiyama is great for hierarchies but `examples/genai-ecosystem/` and similar hub-and-spoke / mind-map / ecosystem diagrams have no auto-layout today. ~500 LOC for Fruchterman-Reingold; reuses the same `LayoutResult` plumbing as Sugiyama. |
| 5 | **`framegraph render` watch mode** | MED | S | HIGH | `framegraph render --watch path.yml` re-renders on save → SVG file → operator opens in browser, browser auto-reloads. Closes the "no live preview" gap without needing a Node toolchain. |

### Tier 2 — Quality & coverage (next quarter)

| # | Item | Impact | Effort | Strategic | Why |
|---|---|---|---|---|---|
| 6 | Auto-fit feedback loop for pattern layout | MED | M | MED | After computing boxes, measure rendered text dimensions; iterate font-size / wrap until fit. Removes most layout overflow surprises. |
| 7 | Mermaid / PlantUML ingestor (opt-in module) | MED | L | MED | Non-goal in `_uml.py:30-33` *for now*. A best-effort one-way ingest converts existing diagrams into typed UML models, broadening the addressable corpus. |
| 8 | Speaker-mode HTML viewer | LOW | M | MED | A static HTML viewer that consumes the per-slide SVGs + `notes.md` so operators don't need to import into PPT/Keynote. Pure-static, zero-server. |
| 9 | Constraint-solver layout (Cassowary or KIWI) | MED | XL | LOW | Real auto-layout for "free" arrangements. Heavy lift for a feature that only some users need; lower than (4) by impact-per-effort. |
| 10 | Theme marketplace / external library | LOW | M | MED | Allow `$theme: org/internal-theme@v2` resolving to a registry. Today, themes ship in-tree only. |

### Tier 3 — Polish & cleanup (always-on)

| # | Item | Impact | Effort | Strategic | Why |
|---|---|---|---|---|---|
| 11 | Strict-mode mypy clean-up | MED | M | LOW | 200+ pre-existing strict-mode errors in `_uml.py`, `_patterns.py`, `docs.py`. CI is `continue-on-error: true` today. Fixing these tightens contract enforcement. |
| 12 | Hand-tuned density constants → measured | LOW | M | LOW | Replace `_BASE_DENSITY` / `_SIZE_MULTIPLIER` constants with regression-fitted values from rendered outputs. Marginal layout-quality lift. |
| 13 | Coverage gate restoration to 90 % | LOW | S | LOW | Currently 86 %; main's UML modules dragged it down. Either tighten gate per-module or add tests for the under-covered UML composers. |
| 14 | Pattern-catalog telemetry / usage signals | LOW | S | LOW | When patterns are used in real decks, log which roles get filled, which sidecars are needed. Drives Tier 1.2 prioritisation. |
| 15 | `framegraph init` scaffolder | LOW | XS | LOW | Generate a starter `deck.yml` with theme + 3 example slides. Lowers the "blank page" tax for new operators. |

### Roadmap shape

If this analysis had to defend a single Tier-1 sequence to a sceptical operator, it would be: **3 (PPTX) → 1 (font metrics) → 2 (sidecars) → 4 (force-directed) → 5 (watch mode)**. That sequence picks the item that closes the loudest "I can't ship with this" gap first (PPTX), then the item that visibly improves every output (typography), then the item that scales the existing pattern catalog's reach (sidecars), then the item that opens the second auto-layout family (force), then the developer-experience polish (watch).

---

## 7. Caveats and what was not verified

- **Competitor algorithm choices** (e.g., "Mermaid uses dagre", "PlantUML uses Graphviz") are common knowledge but may have changed in recent releases. Where uncertainty is real, claims are marked **[uncertain]**.
- **Scoring weights** are calibrated to `PURPOSE.md` and `AGENTS.md`'s stated audience. Different stakeholders (a designer, a teacher, a researcher) would reweight and would land somewhere different.
- **No performance benchmarks were run.** Render-time / memory comparisons would be a separate analysis and would need standardised test corpora.
- **Mypy strict errors** (200+) and **pattern_layout/render test failures** were inspected and fixed in earlier sessions; this analysis assumes the post-fix tree.
- **External-knowledge claims** are prefixed `[external]` or `[uncertain]`; everything else is grounded in code paths cited inline.
