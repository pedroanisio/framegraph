---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# FrameGraph User Manual

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](../DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

---

This is the comprehensive human reference for FrameGraph. It explains
what the package can do, the three authoring paths an operator
chooses between, the deck format used to assemble multi-page
documents (PDF, slide-deck SVGs, or both), and how the project
positions against neighbouring tools (Marp, Slidev, reveal.js,
Pandoc/Beamer, draw.io, Mermaid, PowerPoint + python-pptx).

For the agent-oriented quick reference, see [`AGENTS.md`](../AGENTS.md).
For the README's executive summary, see [`README.md`](../README.md).
For sidecar / fill authoring depth, see [`AUTHORING-FILLS.md`](AUTHORING-FILLS.md).

---

## 1. What FrameGraph is — and isn't

**FrameGraph is** a YAML-first, pure-Python rendering core that
turns structured scene descriptions into static SVG (and, via
optional dependencies, PDF and PNG). It targets two overlapping
problem classes:

1. **Architecture and systems diagrams** — versioned, reviewable,
   reproducible. The author writes YAML; the renderer emits SVG
   with no browser, no GUI, no headless Chromium.
2. **Slide-grade presentations** — multi-page decks composed from
   either a 375-pattern catalog (`use: <id>` + `fill: {…}`) or
   bespoke `visual.layers` blocks, themed by one of seven bundled
   consulting token packs or by a project-local theme.

**FrameGraph is not** a WYSIWYG editor, a browser-only animation
runtime, an interactive presentation player, or a general-purpose
charting replacement for matplotlib / plotly. The rendering core
is deterministic SVG; if you need scientific plots, animations, or
live web layout, reach for those tools and embed the result via
`type: image`.

---

## 2. Install

Required runtime dependencies are tiny — PyYAML and Pydantic.
Optional extras unlock raster and vector PDF output, the
golden-snapshot regression suite, and font-metric refinement.

```sh
pip install framegraph                      # core + SVG output
pip install "framegraph[pdf]"               # adds raster PDF + 4K PNG
pip install "framegraph[pdf-vector]"        # adds weasyprint vector PDF
pip install "framegraph[test]"              # golden-snapshot harness
pip install "framegraph[dev]"               # everything above + ruff + mypy
```

The package ships with seven consulting token packs, a default
stylesheet, two shared symbol packs, the 375-pattern slide
catalog, 17 curated sidecars, and 14 UML diagram composers. All
are available offline; nothing in the rendering core requires
network access.

---

## 3. The three authoring paths

When you sit down to produce a deliverable, decide first which
path applies:

| Path | When | Tooling |
|---|---|---|
| **A. Single bespoke diagram** | A custom architecture, hub-and-spoke, scope boundary, or one-off illustration | `framegraph render diagram.yml -o out.svg` |
| **B. One pattern + a fill** | The slide matches a catalog pattern (SWOT, BMC, Communications Plan, etc.) | `framegraph patterns build <id> --fill content.yml -o out.svg` |
| **C. Multi-page deck** | Two or more slides, themed and assembled into one PDF | `framegraph deck deck.yml -o ./out --pdf` |

Decks (path C) are the highest-leverage surface — slides can be
either bespoke (`visual.layers` blocks, like path A) or
pattern-composed (`use:` + `fill:`, like path B), in any mix, all
themed and rendered in one pass.

---

## 4. Path A — Single bespoke diagram

Use when the slide does not match a catalog pattern. The author
writes a `hybrid-semantic-visual-diagram` document with a
`scene`, an optional `semantic` graph layer, and a `visual`
block of layers + objects.

Minimal example:

```yaml
dsl: FrameGraph
version: 1.5
kind: hybrid-semantic-visual-diagram

scene:
  id: hello
  canvas: {size: [960, 540]}
  rendering_contract:
    coordinate_mode: absolute

visual:
  tokens:
    colors: {bg: "#FFFFFF", ink: "#1A1A1A", brand: "#2563EB"}
    fonts:  {primary: "Arial, sans-serif"}
    text_styles:
      h1: {font: primary, size: 32, weight: 700, color: ink, align: center}

  layers:
    - id: content
      z: 0
      objects:
        - {type: rect, id: bg, decorative: true, box: [0, 0, 960, 540], fill: bg}
        - {type: text, id: title, decorative: true,
           text: "Hello, FrameGraph", box: [80, 220, 800, 100], style: h1}
```

```sh
framegraph render hello.yml -o hello.svg
framegraph render hello.yml -o hello.svg --pdf            # also emit hello.pdf (raster, 300 DPI)
framegraph render hello.yml -o hello.svg --pdf --vector   # vector PDF (selectable text)
framegraph render hello.yml -o hello.svg --4k             # also emit hello.png (3840-wide)
```

A complete worked end-to-end example, including a hub-and-spoke
ecosystem diagram with dashed connectors and seven semantic node
types, lives at [`examples/genai-ecosystem/`](../examples/genai-ecosystem/).

---

## 5. Path B — One pattern + a fill

Use when the slide matches one of the 375 catalog patterns. The
author writes a flat `{role: content}` payload; the catalog and
the bundled stylesheet do the layout and theming.

```sh
# Discover sidecared patterns (17 ship with curated examples)
framegraph patterns list --has-sidecar --json | jq '.[].id'

# Inspect one — zone roles, content_types, sizes, placements
framegraph patterns show 10                    # SWOT Analysis

# Pull the curated example fill (a flat YAML)
framegraph patterns example 10 -o swot.fill.yml

# Render it — validate against the pattern's effective schema, emit SVG
framegraph patterns build 10 --fill swot.fill.yml -o swot.svg
```

The fill payload is **flat** — keys are zone roles, values are
content. Default content shapes per content_type:

| `content_type` | Default Pydantic shape |
|---|---|
| `title_body` | `{title: str, body: str \| None}` |
| `metric` | `{label: str, value: str, trend: str \| None}` |
| `list_items` | `list[str]` |
| `key_value` | `dict[str, str]` |
| `comparison` | `{left: str, right: str}` |
| `chart_data` | `{type: str, series: list[dict]}` |
| `table_data` | `{headers: list[str], rows: list[list[str]]}` |
| `image` | `{src: str, alt: str \| None}` |
| `axis_label` | `{title: str, units: str \| None}` |
| `decorative` | `None` |

For richer per-zone shapes (e.g. BMC's `revenue_streams` is
`list[{label, metric}]` rather than `list[str]`), patterns ship a
**sidecar** under `framegraph/data/fills/` that overrides the default
schema. See [`AUTHORING-FILLS.md`](AUTHORING-FILLS.md) for the
sidecar mini-DSL.

To smoke-check the entire sidecared corpus end-to-end:

```sh
framegraph patterns deck --pdf -o ./demo
# → demo/svgs/<pid>-<slug>.svg     (one SVG per pattern)
# → demo/fills/<pid>-<slug>.fill.yml (one fill payload per pattern)
# → demo/patterns-deck.pdf          (assembled multi-page PDF)
```

---

## 6. Path C — Multi-page decks (the primary surface)

A deck is a YAML document of `kind: presentation-deck` with a
`deck:` block (canvas, theme tokens, deck-global symbols and
component defs) and a `slides:` list. Each slide can be:

- **Bespoke** — a full `scene` + `visual.layers` block (everything
  path A can do).
- **Pattern-composed** — a one-line `use: <pattern>` reference
  with a flat `fill:` payload (everything path B can do).
- **A blend** — a slide may carry both `use:` and bespoke layer
  additions / overrides.

### 6.1 Deck YAML structure

```yaml
dsl: FrameGraph
version: 1.5
kind: presentation-deck

$theme: mckinsey            # one of bain, bcg, deloitte, ey, kpmg, mckinsey, pwc
                            # (omit to use deck-local tokens only)
stylesheet: default         # bundled `framegraph/lib/styles/<name>.yml` (optional)

deck:
  canvas:
    size: [1920, 1080]      # pixels; 16:9 native at 1080p
    units: px

  tokens:                   # deck-wide overrides on top of $theme
    colors:
      accent: "#2563EB"
    fonts:
      primary: "Helvetica, Arial, sans-serif"
    text_styles:
      slide_title: {font: primary, size: 36, weight: 700, color: ink}

  symbols:                  # deck-wide reusable <symbol>/<use> templates
    icon_check:
      shape: path
      d: "M 0 6 L 4 10 L 12 0"

  component_defs:           # deck-wide reusable composite objects
    badge:
      slots:
        - {role: label, type: text}
      template: {...}

slides:
  # 1. Bespoke slide (full visual.layers)
  - slide: 1
    id: cover
    title: "Executive Summary"
    notes: "Open with the headline metric. Tone: confident, brief."
    visual:
      layers:
        - id: bg
          z: 0
          objects:
            - {type: rect, decorative: true, box: [0, 0, 1920, 1080], fill: page_bg}
            - {type: text, decorative: true, text: "Executive Summary",
               box: [120, 80, 1680, 120], style: slide_title}

  # 2. Pattern-composed slide
  - slide: 2
    id: swot
    title: "Market SWOT"
    use: 10                                # by pattern id …
    fill:
      strengths:    ["Brand recognition", "Data moat"]
      weaknesses:   ["Mobile UX lag"]
      opportunities: ["Adjacent vertical"]
      threats:      ["Two well-funded entrants"]

  # 3. Pattern by slug
  - slide: 3
    use: business-model-canvas             # … or by slug
    fill:
      key_partners:    [...]
      key_activities:  [...]
      # all 9 BMC zones

  # 4. Slide that extends a base slide
  - slide: 4
    id: deep_dive_a
    $extends: cover                        # inherit tokens, layers, contract
    title: "Deep Dive — Channel A"
    visual:
      layers:                              # added on top of the base layers
        - id: chart
          z: 5
          objects:
            - {type: bar_chart, ...}
```

### 6.2 Render the deck

```sh
# Per-slide SVGs (one file per slide)
framegraph deck deck.yml -o ./out

# Multi-page PDF (raster, 300 DPI by default)
framegraph deck deck.yml -o ./out --pdf

# Vector PDF (weasyprint backend; selectable / searchable text)
framegraph deck deck.yml -o ./out --pdf --vector

# Pair with 4K PNG per slide
framegraph deck deck.yml -o ./out --pdf --4k
```

Output structure:

```
out/
  slide_01_cover.svg
  slide_02_swot.svg
  slide_03_<slug>.svg
  slide_04_deep_dive_a.svg
  notes.md            # speaker notes from `slide.notes`
  deck.pdf            # only when --pdf is passed
```

### 6.3 Theming and the inheritance order

A slide's effective tokens are the merge of, in order (later wins):

1. Library `$theme` tokens (`framegraph/lib/tokens/<name>.yml`).
2. Deck-global `deck.tokens`.
3. `$extends` base-slide tokens.
4. Slide-local `tokens`.

Symbols and component defs follow the same merge order. This is
how a deck stays visually coherent (one `$theme:` line at the top)
while individual slides can still override one specific token.

### 6.4 Speaker notes and `$extends`

- Add `notes: "…"` to any slide; `framegraph deck` writes them
  into a sibling `notes.md` so the operator can paste them into a
  speaker view or a teleprompter.
- `$extends: <slide_id>` lets a slide inherit its base's tokens,
  symbols, component defs, and layers. The child's layers append
  to the base layers; same-id child layers replace base layers.

### 6.5 Real worked decks in the repo

- [`static/fixture/decks/framegraph-overview-deck.yml`](../static/fixture/decks/framegraph-overview-deck.yml) —
  12 bespoke slides documenting the project itself.
- [`static/fixture/faz-ai-manifesto-deck.yml`](../static/fixture/faz-ai-manifesto-deck.yml) —
  ~17 slides mixing bespoke and pattern-composed (SWOT, BMC,
  Communications Plan).
- [`static/fixture/framegraph-uml-deck.yml`](../static/fixture/framegraph-uml-deck.yml) —
  UML composer integration, every diagram type.

---

## 7. Concepts

### 7.1 Document blocks

| Block | Required? | Purpose |
|---|---|---|
| `dsl: FrameGraph` | yes | Identifier — the validation gate keys on this |
| `version` | yes (≥ 1.x) | DSL minor version (currently 1.5) |
| `kind` | yes | `hybrid-semantic-visual-diagram` (single doc) or `presentation-deck` (multi-page) |
| `scene` | single docs | id, name, canvas, rendering_contract |
| `semantic` | optional | typed `nodes`/`edges` graph + `ontology` (drives `bind:` checks) |
| `visual` | yes | tokens + layers (the rendered surface) |
| `deck` | decks | canvas, tokens, symbols, component_defs (deck-global) |
| `slides` | decks | ordered list of slide records |
| `$theme` | optional | reference to a bundled token pack |
| `stylesheet` | optional | reference to a bundled stylesheet |

### 7.2 Tokens

`visual.tokens` (or `deck.tokens` for decks) defines the named
values referenced by every object in the slide:

| Token table | Example | Used for |
|---|---|---|
| `colors` | `brand: "#2563EB"` | every object's `fill`, `stroke`, `color` |
| `fonts` | `primary: "Helvetica, Arial, sans-serif"` | every text style's `font` |
| `text_styles` | `slide_title: {font: primary, size: 36, weight: 700, color: ink}` | every `text` / `bullet_list` object's `style` |
| `stroke_styles` | `arrow: {color: ink, width: 1.5, dash: [4,4]}` | every `line` / `connector` / `path` `stroke_style` |
| `fill_styles` | `fade: {type: linear_gradient, from: [0,0], to: [1,1], stops: [...]}` | every object's `fill` (resolves to `url(#…)`) |
| `glyph_map` | `check: "✔"` | `icon` objects |

Object fields refer to tokens by name; the renderer dereferences
them at paint time. Hex literals and `none` pass through.

### 7.3 Layers

`visual.layers` is an ordered list of layer mappings. Each layer
has an `id`, a `z` (paint order), an optional `opacity`, and an
`objects` list. Objects are drawn back-to-front per layer; layers
are drawn back-to-front per `z`.

```yaml
layers:
  - id: bg
    z: 0
    objects: [...]
  - id: content
    z: 1
    objects: [...]
  - id: foreground
    z: 2
    opacity: 0.92
    objects: [...]
```

### 7.4 The semantic layer

Optional but recommended: declare typed `nodes` and `edges` with
an `ontology`. Visual objects then `bind:` to a node/edge id, so
the YAML is simultaneously a typed graph and a rendered diagram.

```yaml
semantic:
  ontology:
    node_types:
      service:  {description: "A long-running runtime"}
      database: {description: "A persistent store"}
    edge_types:
      reads_from: {}
      writes_to:  {}
  nodes:
    - {id: api,  type: service}
    - {id: pgdb, type: database}
  edges:
    - {id: e1, type: reads_from, from: api, to: pgdb}

visual:
  layers:
    - id: nodes
      z: 1
      objects:
        - {type: rect, id: api_rect,  bind: api,  box: [80, 200, 240, 80]}
        - {type: rect, id: pgdb_rect, bind: pgdb, box: [560, 200, 240, 80]}
        - {type: connector, id: e1_arrow, bind: e1, from: "api_rect.east", to: "pgdb_rect.west"}
```

A `decorative: true` object opts out of the `bind:`-required check
in `rendering_contract.semantics.decorative_objects_may_omit_bind`.

---

## 8. Object type reference

Every object has at minimum `type`, `id`, and (usually) `box`. The
full set:

| Type | Required keys | Notable optional keys |
|---|---|---|
| `rect` | `box` | `radius`, `fill`, `stroke`, `stroke_style`, `outer_ring`, `effect` |
| `ellipse` | `box` or `center+rx+ry` | `outer_ring`, `fill`, `stroke` |
| `text` | `text` (or `spans`), `box` | `style`, `rotation`, `wrap`, `v_align`, `align` |
| `bullet_list` | `items`, `box` | `marker`, `indent`, `gap`, `style` |
| `line` | `from`, `to` | `stroke_style`, `stroke` |
| `polyline` | `points` | `stroke_style` |
| `path` | `d` | `fill`, `stroke`, `stroke_style` |
| `image` | `href` (or `src`/`uri`) | `box`, `placeholder`, `preserve_aspect_ratio` |
| `connector` | `from`, `to` | `route: {type: straight\|orthogonal\|bezier, points: [...]}` |
| `legend` | `items: [{sample, label, ...}]` | `box` |
| `group` | `children: [...]` | `transform`, `opacity` |
| `container` | `box`, `children: [...]` | `layout: {kind: stack, direction, align, padding}` |
| `bar_chart` | `data`, `box` | `style: {bar_width, baseline, ...}` |
| `line_chart` | `data`, `box` | `style: {smooth, marker, ...}` |
| `icon` | `glyph` (or `code`) | `style`, `box` |
| `use` | `symbol`, `box` | `slots: {…}`, `params: {…}` |
| `chip_row` | `items`, `box` | `style`, `gap` |
| `table` | `headers`, `rows`, `box` | `style: {alt_row_fill, header_fill, ...}` |

UML primitives (16 more types, prefix `uml.`):

`uml.classifier_box`, `uml.actor`, `uml.component_box`, `uml.lollipop`,
`uml.socket`, `uml.node_box`, `uml.artifact_box`, `uml.activity_node`,
`uml.action`, `uml.swimlane`, `uml.state_box`, `uml.pseudostate`,
`uml.lifeline`, `uml.activation_bar`, `uml.fragment_frame`, `uml.timing_lane`.

For machine-consumable signatures (Pydantic JSON schemas, full
docstrings), run:

```sh
framegraph docs -o catalog.json
```

---

## 9. The pattern catalog

`framegraph/_patterns.py` ships 375 slide-template patterns,
keyed by integer id and by slug (lowercase, hyphenated):

| Category | Count | Examples |
|---|---|---|
| `generic` | 50 | Title Slide, SWOT Analysis, BMC, Comparison Matrix |
| `consulting` | 275 | Communications Plan, RAID Log, Diagnostic Summary, Skills-Gap Matrix |
| `expert` | 50 | Stakeholder Heat-Map, Theory-of-Change, Value Chain |
| `with sidecar` | 17 | the curated subset shipped with worked `example_fill`s |

Each pattern declares **zones** — named regions with a `role`,
`content_type`, `size`, `placement`, and optional `shape` /
`span`. The layout engine (`framegraph.patterns.layout`) turns
those into pixel boxes; the render bridge
(`framegraph.patterns.render`) emits the SVG.

```sh
framegraph patterns list                              # human table
framegraph patterns list --category=consulting        # filter
framegraph patterns list --has-sidecar --json         # machine-readable
framegraph patterns show 10                           # zones for SWOT
```

---

## 10. UML diagrams

FrameGraph ships **14 UML 2.5.1 composers** (Phases A–E):

| Phase | Diagram type |
|---|---|
| A | Class diagram (Sugiyama auto-layout) |
| B | Package diagram, Use-case diagram |
| C | Component, Deployment, Activity, State-machine |
| D | Sequence diagram |
| E | Communication, Composite-structure, Object, Profile, Timing, Interaction-overview |

Composers consume a typed model (`framegraph._uml`) and emit a
FrameGraph document with the appropriate `uml.*` primitives. See
`framegraph/uml/` for the per-type API and
`static/fixture/framegraph-uml-deck.yml` for a full demo deck.

---

## 11. Themes and stylesheets

### 11.1 Bundled themes

Seven consulting token packs ship under `framegraph/lib/tokens/`:

| Theme | File | Notes |
|---|---|---|
| `bain` | `bain.yml` | Bain & Company palette + typography |
| `bcg` | `bcg.yml` | Boston Consulting Group |
| `deloitte` | `deloitte.yml` | Deloitte |
| `ey` | `ey.yml` | EY |
| `kpmg` | `kpmg.yml` | KPMG |
| `mckinsey` | `mckinsey.yml` | McKinsey & Company |
| `pwc` | `pwc.yml` | PwC |

Reference one with `$theme: <name>` at the top of a deck.

### 11.2 Stylesheets

`framegraph/lib/styles/default.yml` is the bundled stylesheet —
it declares per-zone rendering decisions (corner radius, padding,
typography accents) that the pattern renderer uses. Reference one
with `stylesheet: <name>` in the deck header.

### 11.3 Custom themes

Drop a YAML at `framegraph/lib/tokens/<name>.yml` with shape:

```yaml
_meta: {id: <name>, name: "Display Name"}
colors: {...}
fonts: {...}
text_styles: {...}
stroke_styles: {...}
```

`FrameGraphLibrary(Path("framegraph/lib")).list_themes()` will pick it up.

---

## 12. Custom symbols and components

### 12.1 Symbols (low-level reusable shapes)

```yaml
visual:
  symbols:
    server_icon:
      shape: path
      d: "M 0 0 L 24 0 L 24 16 L 0 16 Z"
      ports:
        in:  [0, 8]
        out: [24, 8]

  layers:
    - id: arch
      objects:
        - {type: use, symbol: server_icon, box: [80, 80, 48, 32]}
```

### 12.2 Component defs (composite, slot-based)

```yaml
visual:
  component_defs:
    metric_card:
      slots:
        - {role: label, type: text}
        - {role: value, type: text}
      template:
        - {type: rect,  box: [0, 0, 200, 80], fill: card_bg, radius: 8}
        - {type: text,  box: [16, 12, 168, 20], style: card_label, slot: label}
        - {type: text,  box: [16, 36, 168, 32], style: card_value, slot: value}

  layers:
    - id: kpis
      objects:
        - {type: component, id: rev,
           component: metric_card, box: [80, 80, 200, 80],
           slots: {label: "Revenue", value: "$2.4M"}}
```

---

## 13. Output formats

| Format | Backend | Requires | Notes |
|---|---|---|---|
| SVG | core | — | Always emitted; vector, lossless, browser-native |
| PNG (4K) | cairosvg | `[pdf]` | 3840-wide rasterization |
| PDF (raster) | cairosvg + Pillow | `[pdf]` | Pixel-perfect, text not selectable, robust to font config |
| PDF (vector) | weasyprint + pypdf | `[pdf-vector]` | Selectable text, smaller files, needs system fonts that match layout |

Default DPI for raster PDF is 300; override with `--dpi`.

---

## 14. Comparison with neighbouring tools

FrameGraph occupies a specific corner of the design space — pure-Python,
YAML-first, semantic-graph-aware, slide-grade SVG. It overlaps with
several adjacent tools on subsets of features. The honest comparison:

### 14.1 Versus presentation tools

| Tool | Strengths over FrameGraph | Weaknesses vs FrameGraph |
|---|---|---|
| **Marp** (markdown + CSS) | Lower learning curve; markdown is universal; rich theme ecosystem | No semantic graph; layout is CSS-driven (CSS engine constraints, less precise); harder to programmatically generate from a planner |
| **Slidev** (Vue + markdown) | Live HTML preview; rich animations; large template community | Browser/Node runtime; slide output is HTML, not vector; harder to diff in code review |
| **reveal.js** | Mature browser deck format; JS plugin ecosystem | HTML output; no first-class diagram authoring; presentations need a server / HTML viewer |
| **PowerPoint + python-pptx** | Native .pptx, opens anywhere; rich object library | Imperative Python authoring (no declarative source); diff/review unfriendly; layout in code |
| **LaTeX Beamer** | Typographic precision; strong publishing tradition | Steep learning curve; slow build; weak diagram authoring without TikZ |
| **Pandoc + Beamer/HTML** | Markdown source; many output formats | Slide-as-markdown is constrained; no semantic graph; no patterns catalog |

**FrameGraph wins** on: typed semantic layers, pattern-driven slide
authoring (375 catalog patterns + sidecar contracts), pure-Python
rendering (no browser, no Node), bytewise-reviewable YAML source,
and a CLI surface designed for AI-agent consumption.

### 14.2 Versus diagram tools

| Tool | Strengths over FrameGraph | Weaknesses vs FrameGraph |
|---|---|---|
| **Mermaid** | One-line "graph LR" syntax; native GitHub render; huge popularity | Auto-layout only — limited pixel control; styling is CSS-bound; no slide / deck concept |
| **PlantUML** | Strong UML semantics; broad UML diagram coverage | JVM runtime; image output, not editable SVG; no slide composition |
| **Graphviz / DOT** | Best-in-class graph layout (Sugiyama, neato, fdp) | Plain graphs only; no slides, no chrome, no theming |
| **draw.io / diagrams.net** | WYSIWYG editor; rich shape library; .drawio source | UI-driven; XML source not human-friendly; no programmatic deck workflow |
| **D2** | Modern declarative syntax; auto-layout | Newer ecosystem; no slide/deck concept; less granular pixel control |
| **TikZ** (LaTeX) | Typographic + diagram precision; print-quality | LaTeX runtime; very steep; slow |

**FrameGraph wins** on: pixel-precise control when you want it
(coordinate_mode: absolute), auto-layout when you don't (`container`
with `layout.kind: stack`, Sugiyama for class diagrams), seamless
integration into deck composition, and a 14-composer UML surface
that sits in the same renderer pipeline as everything else.

### 14.3 Where FrameGraph is not the right tool

- **Animated / interactive presentations**: use Slidev or reveal.js.
- **Scientific plots with millions of points**: use matplotlib +
  embed via `type: image`.
- **Hand-edited WYSIWYG slides** for non-technical authors:
  PowerPoint or Google Slides will be faster.
- **One-off Mermaid-style flowcharts** in a README:
  Mermaid renders inline on GitHub; FrameGraph emits a separate
  SVG file.
- **PDF printing for typesetting / publishing**: LaTeX is still
  best.

---

## 15. Limitations and non-goals

The package is honest about what it does and doesn't do — see
[`PURPOSE.md`](../PURPOSE.md) for the authoritative list. Highlights:

- **No browser runtime.** SVG is the output. If you need
  animations, embed the SVG in a viewer that supports them.
- **No constraint-solver layout.** Layouts are anchored, regional,
  relative, or via the simple stack `container`. Free-form
  spring-physics layout is out of scope; the `class_diagram`
  composer's Sugiyama is the only auto-layout in tree.
- **No DOCX / PowerPoint export.** SVG and PDF only.
- **No general-purpose charting.** `bar_chart` and `line_chart` are
  intentionally limited to slide-grade KPIs; for analytical plots,
  use matplotlib / plotly and embed.
- **YAML 1.2 strict.** No template engines, no Jinja, no `!include`.
  Composition happens via deck merging, `$extends`, sidecars, and
  `component_defs` — all declarative, all reviewable.

---

## 16. Quality and verification

The package ships with three layers of automated verification:

1. **Unit + integration tests** (`tests/unit/`, `tests/integration/`)
   exercise the renderer, library, patterns, layout, and CLI.
   Coverage gate: 90% (currently ~94%).
2. **Golden-snapshot regression suite** (`tests/run_tests.py`)
   raster-compares every fixture against blessed PNGs at 2× scale,
   with per-pixel tolerance configurable via `tests/tolerance.cfg`.
3. **Schema validation** at every public entry point — every YAML
   that declares `dsl: FrameGraph` is validated against the
   Pydantic models in `framegraph/_schema.py` before rendering.

```sh
python -m pytest                         # full suite
python tests/run_tests.py                # golden snapshots
python tests/run_tests.py --bless        # re-bless after intentional changes
ruff check . && ruff format --check .
```

---

## 17. See also

- [`README.md`](../README.md) — package overview, install, quick start.
- [`AGENTS.md`](../AGENTS.md) — programmatic CLI reference for AI agents.
- [`AUTHORING-FILLS.md`](AUTHORING-FILLS.md) — fill / sidecar workflow depth.
- [`ROADMAP-FILL-RENDER.md`](ROADMAP-FILL-RENDER.md),
  [`ROADMAP-FILL-RENDER-V2.md`](ROADMAP-FILL-RENDER-V2.md) — internal roadmaps.
- [`CLAUDE.md`](../CLAUDE.md) — project-wide conventions.
- [`PURPOSE.md`](../PURPOSE.md) — mission, audience, and non-goals.
- [`examples/genai-ecosystem/`](../examples/genai-ecosystem/) —
  end-to-end bespoke single-slide example with YAML, SVG, and PDF.
- [`static/fixture/decks/framegraph-overview-deck.yml`](../static/fixture/decks/framegraph-overview-deck.yml) —
  worked 12-slide deck (bespoke).
- [`static/fixture/faz-ai-manifesto-deck.yml`](../static/fixture/faz-ai-manifesto-deck.yml) —
  worked deck mixing bespoke and pattern-composed slides.
- [`static/fixture/framegraph-uml-deck.yml`](../static/fixture/framegraph-uml-deck.yml) —
  UML composer integration deck.
