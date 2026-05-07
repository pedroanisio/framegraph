---
title: "FrameGraph — Competitive Landscape & Roadmap"
version: "2.0.0.dev0"
date: "2026-05-07"
status: "working document"
last_verified_against_repo: "2026-05-07"
generated_by: "Claude Opus 4.7 via Claude Code"
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  scope: >-
    This document contains analysis, positioning claims, and roadmap proposals.
    No statement herein should be taken as a verified market fact unless accompanied
    by a cited source. Competitive assessments are directional. Roadmap items are
    proposals, not commitments.
---

# FrameGraph — Competitive Landscape & Roadmap

> **Disclaimer:** This is a working analysis document. Competitive data is sourced
> from public GitHub repositories, search results, and published articles as of
> May 2026. Star counts and ecosystem claims are approximate. Roadmap items are
> proposals based on observed gaps; they are not commitments.

---

## 1. What We Built

FrameGraph is a YAML-first hybrid semantic-visual DSL that renders to clean SVG.
It is the only open tool that combines all four of:

- **Absolute layout control** — explicit coordinate system, no forced auto-layout
- **Semantic model** — visual objects bind to typed nodes and edges in an ontology
- **Presentation deck format** — `$extends` inheritance, token cascade, speaker notes
- **Firm design token packs** — McKinsey, BCG, Bain, Deloitte, PwC, EY, KPMG built-in

### Codebase snapshot (v2.0.0.dev0, verified 2026-05-07)

| Artefact | Detail |
|---|---|
| Python LOC | 3 623 (non-comment, non-blank) across [framegraph/](../framegraph/) |
| Runtime dependencies | PyYAML only ([pyproject.toml:40-42](../pyproject.toml#L40-L42)); cairosvg / Pillow / numpy in `[test]` extras |
| Object types | 18 registered: `rect`, `ellipse`, `icon`, `use`, `image`, `line`, `polyline`, `path`, `connector`, `legend`, `text`, `bullet_list`, `bar_chart`, `line_chart`, `group`, `container`, `component`, `chip_row` (verified by enumerating each module's `RENDERERS` dict). `spans` is an inline-rich-text element of `text`, not a top-level object type. |
| Renderer modules | 7: [shapes](../framegraph/renderers/shapes.py), [symbols](../framegraph/renderers/symbols.py), [image](../framegraph/renderers/image.py), [lines](../framegraph/renderers/lines.py), [text_objects](../framegraph/renderers/text_objects.py), [charts](../framegraph/renderers/charts.py), [layout](../framegraph/renderers/layout.py) |
| Registration API | `renderer.register(type_name, fn)` — third-party custom types |
| Token packs | 7 firm packs ([framegraph/lib/tokens/](../framegraph/lib/tokens/)): bain, bcg, deloitte, ey, kpmg, mckinsey, pwc |
| Symbol packs | 2: `shared/s_node.sym.yml`, `shared/insight_box.sym.yml` |
| Golden harness | [tests/run_tests.py](../tests/run_tests.py) — 21 fixtures · 48 golden PNGs · 1 % pixel tolerance ([tests/tolerance.cfg](../tests/tolerance.cfg)). **33 of 35 slides pass** as of commit `1bc5547`. The two remaining failures both live under `framegraph_genai_mediated_system_v2*` (max delta 100 %, suggesting a layer/object that fails to render at all) — see Section 4 v2.0 backlog. |
| Pytest suite | 352 unit + integration tests at [tests/unit/](../tests/unit/) and [tests/integration/](../tests/integration/) · 90.65 % line + branch coverage · `--cov-fail-under=90` enforced in [pyproject.toml](../pyproject.toml) |
| Document schema | Pydantic v2 models at [`framegraph/_schema.py`](../framegraph/_schema.py) — normative. Human-readable companion at [`static/specs/SCHEMA.md`](../static/specs/SCHEMA.md). The previous `GRAMMAR.ebnf` was removed in the schema migration (2026-05-07); see SCHEMA.md history. |
| CLI | `framegraph render` · `framegraph deck` · `framegraph version` ([framegraph/cli.py](../framegraph/cli.py)) |

### Feature surface

**Layout engine**
- `type: container` with `layout.kind: stack` (vertical / horizontal)
- `direction`, `gap`, `align`, `justify`, `padding` — flex-like sizing
- `flex: N` children, explicit box children, equal-split auto
- Resolved boxes written to `object_index` for connector targeting

**Rich text**
- Inline spans: `text.spans: [{text, weight, color, italic, size}]`
- `bullet_list` with markers (`•`, `1.`, `–`), multi-level indent, word-wrap
- `overflow: clip` — SVG `<clipPath>` enforcing declared box as hard boundary

**Data visualisation**
- `bar_chart` — single/multi-series, value labels, legend, baseline, grid
- `line_chart` — multi-series, dashed lines, point radius, legend

**Deck format**
- `$theme` library inheritance
- `$extends` slide inheritance — 4-layer token merge + layer dict-merge
- Speaker notes → `notes.md` export via `FrameGraphDeckRenderer.render_notes()`

**Authoring utilities**
- `text: "lorem"` / `text: "lorem:N"` — deterministic lorem ipsum
- Image placeholder — `href: "placeholder"`, `placeholder: true`, or absent href
- `debug_boxes: true` — dashed overlay on all object boxes, colour-coded by type
- `outer_ring` on rect and ellipse — concentric stroke with configurable gap

---

## 2. Competitive Landscape

Sources: GitHub topics search, Nimbalyst 2026 AI diagram tool comparison,
Mermaid.js history article (Taskade, March 2026), DEV Community token-efficiency
analysis (February 2026), C4 tooling comparison (Optimal Relations, November 2025).

### Tool comparison

| Tool | Category | Layout | Semantic model | Deck format | Design tokens | LLM readiness | Output |
|---|---|---|---|---|---|---|---|
| **Mermaid.js** | Diagram-as-code | Auto only | None | None | None | Native (85 K ★) | Browser SVG |
| **D2** | Diagram-as-code | Auto only | None | None | Themes | Partial | SVG / PNG |
| **Structurizr** | Architecture DSL | Auto only | C4 model | None | CSS-like | Partial | SVG / HTML |
| **Slidev** | Code-first slides | CSS only | None | Markdown | Vue themes | Partial | Web / PDF |
| **Reveal.js** | Code-first slides | CSS only | None | HTML | CSS | Partial | Web / PDF |
| **Excalidraw** | Visual canvas | Manual | None | None | None | MCP (2026) | PNG / SVG |
| **Marp** | Markdown slides | CSS only | None | Markdown | CSS themes | Partial | PDF / HTML |
| **FrameGraph** | Hybrid DSL | **Both** | **Full** | **Yes** | **7 firm packs** | Ideal target | **Pure SVG** |

### What each tool does that FrameGraph does not

| Tool | Their advantage over FrameGraph |
|---|---|
| Mermaid.js | Graph auto-layout; 85 K GitHub stars; native LLM familiarity; VS Code extension; renders in Notion, GitHub, Obsidian |
| D2 | Cleaner auto-layout output; modern Go binary; growing ecosystem |
| Structurizr | Mature C4 model; change-once-update-everywhere semantic consistency |
| Slidev / Reveal.js | Live browser preview; hot reload; animations; large user base |
| Excalidraw | WYSIWYG editing; hand-drawn aesthetic; MCP server; collaboration |

### What FrameGraph does that nothing else does

1. **Hybrid semantic-visual model.** Objects bind to typed semantic nodes/edges.
   The visual layer is a *view* over a semantic graph, not a set of decorative shapes.
   No other open tool has this outside C4-specific Structurizr.

2. **Absolute layout with auto-layout.** Explicit coordinates for
   presentation-grade control, plus `container/stack` for repeating components.
   Mermaid only does auto. Excalidraw only does manual.

3. **Consulting firm token packs.** McKinsey, BCG, Bain, Deloitte, PwC, EY, KPMG
   design identities baked in as YAML-selectable themes.
   No other tool ships these.

4. **Deck format with inheritance.** `$extends` with 4-layer token merge and
   layer dict-merge. Speaker notes exported to `notes.md`.
   No other diagram DSL has a presentation deck format at all.

5. **YAML-first → LLM-efficient.** Structured, token-efficient,
   git-diffable. YAML sits in the same efficiency tier as Mermaid's ABNF
   grammar for LLM generation — unlike JSON-heavy Excalidraw
   (reported 24× more tokens than text-based formats for equivalent content).

### Identified gaps

| Gap | Impact | Addressed in |
|---|---|---|
| No graph auto-layout engine | Cannot auto-place semantic graphs | v2.2 |
| No live preview / hot reload | Slow authoring feedback loop | v3.0 |
| No MCP server / LLM interface | Invisible to LLM agents | v2.1 |
| No JSON Schema / IDE integration | No autocomplete in editors | v2.0 / v2.1 |
| Not published on PyPI | Not installable without source | v3.0 |
| No web playground | No zero-install path | v3.0 |
| `grid` / `row` containers unrendered | Schema reserved but not implemented | v2.0 |
| `inner_box` / `padding` on objects | Manual coordinate arithmetic | v2.0 |

---

## 3. Strategic Context (May 2026)

The diagramming tool market is converging on two poles:

**Pole 1 — LLM-native, auto-layout, developer-facing.**
Mermaid leads with ~85 K stars and native LLM familiarity. D2 is the modern
challenger. Both are git-diffable, integrate into every major code editor, and
LLMs generate valid syntax with low hallucination rates because their grammars
are constrained and well-represented in training data.
Excalidraw + MCP is emerging as the default AI canvas for visual collaboration.

**Pole 2 — Consulting and presentation authoring.**
No open tool currently targets this workflow. Existing options are proprietary
(PowerPoint, Keynote, Google Slides) or developer-centric without visual
precision (Slidev, Marp). PPTAgent, AutoPresent, and similar 2025 research
papers demonstrate LLM-driven slide generation, but none are code-first or
git-diffable.

**FrameGraph's lane:** structured authoring of consulting-grade visual
documents — decks, semantic diagrams, branded deliverables — where neither
Mermaid nor Excalidraw competes. The MCP server in v2.1 is the entry point
to that lane.

---

## 4. Roadmap

### v2.0 — Close the backlog
*Target: near-term. Schema already forward-compatible.*

- [x] **Repair v2.0 modular-split regression** — *Done in [`1bc5547`](#).*
  `FrameGraphRenderer` now exposes the three Protocol methods
  (`text_svg`, `render_rect`, `eval_length`) as thin delegates to the
  free functions in `renderers/text_objects.py`, `renderers/shapes.py`,
  and `renderers/layout.py`. 29 regression tests in
  [tests/unit/test_modular_split_regression.py](../tests/unit/test_modular_split_regression.py)
  guard the contract. Mypy strict mode (currently disabled in
  [pyproject.toml](../pyproject.toml#L156-L168) because of this regression) can now
  be re-enabled as a follow-up.
- [ ] **Investigate the remaining two golden-snapshot failures** —
  `framegraph_genai_mediated_system_v2.yml` and
  `framegraph_genai_mediated_system_v2.1.yml` both fail with
  `max delta 255.0px (100.00%)`. A 100 % delta means at least one full
  pixel block differs by the maximum value — typically a layer that
  rasterises in one path but not the other (e.g. an object dropped from
  the SVG, or a fill that resolved to `none` instead of a colour). The
  modular-split repair fixed 30 of 32 slides; these two need their own
  diagnosis. Then either fix the renderer or re-bless after confirming
  the output is correct.
- [ ] **Reconcile golden snapshots (final pass)** — once the two
  failures above are explained, run `python tests/run_tests.py --bless`
  to lock the current correct output as the new golden baseline. The
  release checklist in [pyproject.toml](../pyproject.toml) requires "all
  goldens pass" before a stable tag.
- [ ] `grid` container — `layout.kind: grid` with `columns: N`, `gap`, `align`, `padding`. Currently rejected at [framegraph/renderers/layout.py:188](../framegraph/renderers/layout.py#L188) with a `not yet implemented` comment.
- [ ] `row` container — syntactic sugar over grid (single-row auto-columns). Same rejection path.
- [ ] `inner_box` reference syntax — `box: "$card.inner"` for padding-aware child positioning. Zero matches in codebase today.
- [ ] `padding` on individual objects — exposes padded inner area to children.
- [ ] JSON Schema (`framegraph.schema.json`) — enables YAML LSP autocomplete in VS Code. No such file in the repo today.
- [ ] Re-enable mypy strict mode — possible now that the modular-split regression is gone. Update [pyproject.toml](../pyproject.toml#L156-L168) and remove the explanatory comment.
- [ ] Full backward-compat audit — run all pre-v1.4 YAML through v2.0 renderer, report pixel drift.
- [ ] Tag `2.0.0` stable release (currently `2.0.0.dev0` in [pyproject.toml](../pyproject.toml) and [framegraph/__init__.py](../framegraph/__init__.py)).

**Why this order:** The modular-split regression was the only item
silently corrupting output today; with it repaired, the golden harness
recovered from 3/35 passing to 33/35. The two remaining failures are
likely a single distinct bug — diagnose, fix or re-bless, then the
release checklist becomes passable. After that the layout-engine
extensions (`grid`/`row`/`inner_box`) and the JSON Schema are mostly
mechanical and can be parallelised.

---

### v2.1 — LLM Authoring Interface
*Target: after v2.0 stable. Highest strategic leverage.*

- [ ] **MCP server** — `render_framegraph(yaml: str) → svg: str` exposed over MCP
  - Makes FrameGraph directly addressable by Claude Code, Cursor, Windsurf, and any MCP client
  - Single endpoint: validate + render in one call; structured errors on failure
- [ ] `framegraph validate` — machine-readable JSON error output
  - Each error: `{object_id, field, message, suggestion}`
  - Gives LLMs the structured feedback they need to self-correct
- [ ] `framegraph lint` — warn on authoring issues without failing render
  - Overflow detection: text height vs declared box height
  - Zero-size or negative-size boxes
  - Connectors targeting unknown objects or ports
  - Unused symbol definitions
- [ ] **Few-shot prompt template** for LLM authoring
  - 5–8 example (prompt → YAML) pairs covering card layout, connector diagrams, deck slides, charts
  - Published as `PROMPTS.md` in the repo and embedded in the MCP server's system prompt
- [ ] JSON Schema IDE integration — `.framegraph.json` LSP config for VS Code
- [ ] `framegraph watch diagram.yml` — re-render on file save, write to `diagram.svg`

**Why this is the strategic priority:**
The 2026 diagramming landscape is splitting on LLM-native authoring.
Mermaid's advantage is that LLMs know its grammar from training data.
FrameGraph's advantage is that YAML is structurally identical to Mermaid in
LLM token efficiency — but without an MCP server and a prompt template,
that advantage is invisible to the agents.
An MCP server + validate command is the minimum viable LLM authoring interface.

---

### v2.2 — Graph Auto-Layout
*Target: after v2.1. Closes the capability gap vs Mermaid/D2.*

- [ ] **Auto-layout engine for semantic layers** — dagre or ELK-based
  - `layout.kind: graph` on a layer triggers automatic node placement + edge routing
  - Supports directed and undirected graphs, hierarchical layouts, force-directed
- [ ] **Hybrid layouts** — auto-layout semantic graph layer + absolute chrome layer
  - Presentation slides keep pixel-precise chrome; content graph auto-places
- [ ] **Pin overrides** — `pin: true` on any node fixes it to its declared box
  - Auto-layout respects pinned nodes; positions everything else around them
- [ ] Port routing — connectors routed around obstacles, not through them
- [ ] `framegraph layout --dry-run` — outputs resolved absolute coordinates
  - Allows authors to "bake" an auto-layout into explicit YAML for further manual refinement

**Why after v2.1:**
Auto-layout is a large engine dependency. It should land after the LLM authoring
interface is proven — an LLM that can generate valid FrameGraph YAML can also
describe graph topology that the auto-layout engine places. The combination is
more powerful than either alone.

---

### v3.0 — Platform
*Target: after v2.2. High effort; follows naturally once the render pipeline is an HTTP endpoint.*

- [ ] **VS Code extension** — live SVG preview panel, updates on save
  - Validates on keystroke (via JSON Schema + `framegraph lint`)
  - `Ctrl+Shift+P → FrameGraph: Open Preview`
- [ ] **Web playground** (`framegraph.live` or similar)
  - YAML editor left, SVG preview right
  - Built on the same HTTP endpoint that the MCP server uses
  - URL-shareable diagrams (YAML encoded in hash fragment)
- [ ] **PyPI publication** — `pip install framegraph`
  - Semantic versioning enforced
  - Changelog as release notes
- [ ] **Documentation site** — API reference, YAML syntax guide, examples gallery
- [ ] `framegraph diff file_a.yml file_b.yml` — visual delta between two documents
  - New, removed, and changed objects highlighted in a side-by-side SVG
- [ ] **Export pipeline**
  - `framegraph export --format pptx` — render deck to PPTX via python-pptx
  - `framegraph export --format pdf` — headless Chromium PDF via cairosvg or Playwright
- [ ] **Ecosystem seed**
  - Community symbol library (shareable `.sym.yml` files)
  - Third-party token packs via `framegraph install pack <name>`

**Platform risk note:**
v3.0 is high-effort and low-moat in isolation. The VS Code extension and web
playground are valuable because they reduce onboarding friction, but they do not
create durable advantage on their own. Prioritise v2.1 (MCP server, LLM
interface) first — that is where durable differentiation compounds. The
playground is essentially free once the MCP HTTP endpoint exists.

---

## 5. Priority Matrix

| Item | Strategic value | Effort | Do when | Status |
|---|---|---|---|---|
| Repair modular-split regression (`text_svg`, `render_rect`, `eval_length` on `FrameGraphRenderer`) | Very high (silent corruption) | Low–medium | v2.0 | ✅ done in `1bc5547` (2026-05-07) — 33/35 goldens recovered |
| **Diagnose 2 remaining golden failures** (`framegraph_genai_mediated_system_v2*`, 100 % pixel delta) | Very high (blocks stable tag) | Low if a known schema gap; medium if real bug | v2.0 — next | — |
| **Re-bless goldens** (final pass) | Very high (unblocks stable tag) | Trivial | v2.0 — after the failure above is resolved | — |
| **JSON Schema** (`framegraph.schema.json`) | Medium–high (prereq for v2.1 MCP `validate`) | Medium | v2.0 / v2.1 | — |
| Re-enable mypy strict mode | Medium (catches future drift) | Low | v2.0 | — |
| MCP server (v2.1) | Very high | Low | First after v2.0 stable | — |
| `framegraph validate` JSON output | High | Low | With MCP server | — |
| Few-shot LLM prompt template | High | Very low | With MCP server | — |
| `grid` / `row` containers | Medium | Medium | v2.0 — backlog commitment | — |
| `inner_box` / `padding` | Medium | Medium | v2.0 | — |
| Graph auto-layout engine | High | High | v2.2 — after v2.1 proven | — |
| VS Code extension | Medium | High | v3.0 | — |
| Web playground | Medium | Medium | v3.0 (built on MCP endpoint) | — |
| PyPI + docs site | Medium | Medium | v3.0 | — |
| PPTX / PDF export | Low–medium | Medium | v3.0 | — |

---

## 6. Summary

FrameGraph v2.0.0.dev0 is a working DSL with **352 tests, 90.65 % line+branch
coverage** and a per-type renderer dispatch that — as of commit `1bc5547`
(2026-05-07) — no longer silently drops legend rect-samples, connector
labels, or component slot text. The golden harness recovered from 3/35
passing to 33/35 from that single fix.

The actions with the highest near-term leverage, in order:

1. **Diagnose the two remaining golden failures**
   (`framegraph_genai_mediated_system_v2*`, max delta 255.0 px = 100 %).
   A 100 % pixel delta means at least one whole rasterised region differs
   by the maximum value — typically a layer or object that fails to render
   at all. Likely a schema construct exercised only by these two
   GenAI-system fixtures. Once explained, fix or re-bless. This is the
   last blocker on the v2.0 release checklist.

2. **Ship the JSON Schema** (`framegraph.schema.json`). It's the smallest
   v2.0 backlog item with the largest authoring-experience payoff and a
   hard prerequisite for v2.1's MCP `validate` endpoint. The 18 registered
   object types and their per-type fields can be enumerated mechanically
   from each renderer module's `obj.get(...)` calls.

3. **Build the MCP server (v2.1).** A single endpoint that accepts YAML
   and returns SVG, exposed over MCP. Becomes valuable the moment the
   JSON Schema lands (free structured validation). Makes FrameGraph
   directly addressable by every LLM agent in the 2026 ecosystem.

After (1), the v2.0 stable tag becomes possible. After (2) and (3),
FrameGraph occupies the consulting-authoring lane that no current
open-source tool currently fills. The remaining backlog
(`grid`/`row`/`inner_box`/compat audit, mypy strict, VS Code extension,
web playground, PyPI publication) is mostly mechanical and parallelisable
once the items above land.
