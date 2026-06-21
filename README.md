---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "GPT-5 via Codex"
  date: "2026-05-07"
---

# framegraph

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](./DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

YAML-first hybrid semantic-visual diagram DSL that renders to clean SVG.

Current package version: `0.1.0` (first public PyPI release).

```yaml
dsl: FrameGraph
version: 1.3
kind: hybrid-semantic-visual-diagram
scene:
  id: hello
  canvas: {size: [960, 540]}
  rendering_contract:
    coordinate_mode: absolute
    text: {min_font_size: 7}
    semantics: {decorative_objects_may_omit_bind: true}
semantic:
  ontology: {node_types: {}, edge_types: {}}
  nodes: []
  edges: []
visual:
  tokens:
    colors:  {bg: "#FFFFFF", ink: "#1A1A1A"}
    fonts:   {primary: "Arial, sans-serif"}
    text_styles:
      h1: {font: primary, size: 32, weight: 700, color: ink, align: center}
  layers:
    - id: content
      z: 0
      objects:
        - {type: rect, id: bg, decorative: true, box: [0,0,960,540], fill: bg}
        - {type: text, id: title, decorative: true,
           text: "Hello, FrameGraph", box: [80,220,800,100], style: h1}
```

```bash
framegraph render hello.yml -o hello.svg
```

---

## Install

```bash
pip install framegraph
```

For the golden-snapshot test harness:

```bash
pip install "framegraph[test]"
```

To build the documentation portal locally:

```bash
pip install -e ".[docs]"
make portal-serve   # live-reload dev server, or `make portal` for a static ./site
```

---

## Quick start

### Single diagram

```python
import yaml
from framegraph import FrameGraphRenderer

doc = yaml.safe_load(open("diagram.yml"))
svg = FrameGraphRenderer(doc).render_svg()
open("diagram.svg", "w").write(svg)
```

### Multi-slide deck

```python
import yaml
from pathlib import Path
from framegraph import FrameGraphLibrary, FrameGraphDeckRenderer

lib  = FrameGraphLibrary(Path("framegraph/lib"))
data = yaml.safe_load(open("deck.yml"))
deck = FrameGraphDeckRenderer(data, library=lib)
deck.render_all(Path("output/"))
# → output/slide_01_<id>.svg, slide_02_<id>.svg, …
```

### CLI

```
framegraph render   diagram.yml [-o output.svg] [--pdf] [--4k]
framegraph deck     deck.yml    [-o output_dir/] [--pdf] [--4k]
framegraph from-markdown doc.md [-o deck.yml] [--theme T] [--canvas a4|a3|letter]
framegraph validate input.yml   [--kind=auto|framegraph|pattern-sidecar|pattern-catalog]
framegraph patterns list [--has-sidecar] [--json]
framegraph patterns show    <id>
framegraph patterns example <id> [-o fill.yml]
framegraph patterns build   <id> --fill content.yml [-o out.svg]
framegraph patterns deck    [-o output_dir/] [--ids=10,44,91] [--pdf]
framegraph docs     [-o catalog.json]   # machine-readable API for agents
framegraph sitemap  input.yml   --base-url https://example.com [-o sitemap.xml]
framegraph version
```

---

## Documentation map

| If you want… | Read |
|---|---|
| Concept overview + install + quick start | this file |
| **Browsable API / schema / CLI reference + example gallery** (generated from docstrings) | the documentation portal — `make portal-serve`, or the published GitHub Pages site |
| **Comprehensive human user manual** (multi-page workflows, theming, comparison with alternatives) | [`docs/MANUAL.md`](docs/MANUAL.md) |
| Agent-oriented CLI reference (entry points, fill contract, error recovery) | [`AGENTS.md`](./AGENTS.md) |
| Fill / sidecar authoring depth | [`docs/AUTHORING-FILLS.md`](docs/AUTHORING-FILLS.md) |
| Mission, audience, non-goals | [`PURPOSE.md`](./PURPOSE.md) |
| Project conventions and constraints | [`CLAUDE.md`](./CLAUDE.md) |
| End-to-end worked single-slide example | [`examples/genai-ecosystem/`](examples/genai-ecosystem/) |

### Documentation portal

A MkDocs-Material site is generated **from the package's own docstrings,
Pydantic schema, and bundled examples** — there is no hand-maintained API
reference to drift. The pipeline (`framegraph._docsite`) renders the API,
schema, and CLI reference plus a gallery of framegraph rendering its own
examples, and is gated in CI: the build fails unless every public symbol is
documented (100 % coverage) and every gallery example validates against the
schema.

```bash
make portal-gen     # materialize docs/portal/ from source
make portal         # generate + build the static site into ./site
make portal-check   # CI gate: coverage + strict build (warnings are errors)
```

The site deploys to GitHub Pages from `main` via `.github/workflows/docs.yml`.

#### Serving the built site with Docker

To serve the rendered `./site` from a container (non-root nginx, host port
`8085` → container `8080`):

```bash
make portal              # regenerate ./site first — it is a build artifact
docker compose up -d     # http://localhost:8085/
```

`./site` is git-ignored and must exist in the build context before the image
is built (Docker reads `.dockerignore`, not `.gitignore`, so the ignored
directory is still copied in). Override the host port without editing the
compose file: `PORT=9000 docker compose up -d`. To build and run the image
directly without Compose:

```bash
docker build -t framegraph-docs .
docker run --rm -p 8085:8080 framegraph-docs
```

## For AI agents

If you are an AI agent producing slides or diagrams, start with
[`AGENTS.md`](./AGENTS.md). It lists the four entry points
(`render`, `deck`, `patterns *`, `docs`), the fill contract, and
the validation error recovery patterns. The shortest agent path is:

```sh
# Discover sidecared patterns
framegraph patterns list --has-sidecar --json

# Pull a curated example fill, render it
framegraph patterns example 10 -o swot.fill.yml
framegraph patterns build   10 --fill swot.fill.yml -o swot.svg

# Or assemble a deck where each slide is a one-liner pattern reference
framegraph deck deck.yml -o ./out --pdf
```

A deck slide composed from a pattern looks like:

```yaml
slides:
  - use: 10                  # pattern id (or slug, e.g. "swot-analysis")
    fill:
      strengths:    ["Brand", "Team"]
      weaknesses:   ["Mobile UX"]
      opportunities: ["AI"]
      threats:      ["Macro"]
```

For a full corpus walk-through:

```sh
framegraph patterns deck --pdf -o ./demo
# → demo/svgs/<pid>-<slug>.svg
# → demo/fills/<pid>-<slug>.fill.yml
# → demo/patterns-deck.pdf
```

For a pattern *without* a sidecar, run `framegraph patterns show <id>`
to read its zones and content_types, then write a flat
`{role: content}` fill from the [default content shapes](docs/AUTHORING-FILLS.md#default-content-shapes).

For a slide that **doesn't fit any catalog pattern** (a custom
hub-and-spoke diagram, an architecture map, etc.), see the bespoke
single-slide walk-through under [`examples/genai-ecosystem/`](examples/genai-ecosystem/) —
YAML source, rendered SVG, rendered PDF, and the exact CLI commands.

---

## Object types

| Type | Description |
|---|---|
| `rect` | Rectangle with optional `radius`, `stroke`, `fill` |
| `ellipse` | Ellipse with optional `outer_ring` |
| `text` | Text with `wrap`, `v_align`, `style`, and inline `spans` |
| `bullet_list` | Structured bullet or ordered list object |
| `line` | Straight line with optional arrowhead |
| `polyline` | Multi-segment line |
| `path` | SVG path data |
| `image` | Raster image object with SVG `<image>` output |
| `component` | Styled box from `component_defs` |
| `chip_row` | Horizontal row of pill chips |
| `connector` | Semantic edge between bound objects |
| `legend` | Auto-generated colour legend |
| `group` | Container for nested objects |
| `container` | Auto-layout container with `layout.kind: stack` |
| `bar_chart` | Single- or multi-series bar chart |
| `line_chart` | Multi-series line chart |
| `icon` | Unicode glyph or icon-font character |
| `use` | Stamp a `symbol` with slot/param substitution |

---

## Consulting firm token packs

Seven pre-built token packs are included:

```python
from framegraph import FrameGraphLibrary
from pathlib import Path

lib = FrameGraphLibrary(Path("framegraph/lib"))
lib.list_themes()
# → ['bain', 'bcg', 'deloitte', 'ey', 'kpmg', 'mckinsey', 'pwc']
```

Use via `$theme` in a deck:

```yaml
$theme: mckinsey
deck:
  canvas: {size: [960, 540]}
slides:
  - slide: 1
    …
```

---

## Regression tests

```bash
# Bless goldens (first run or after intentional change)
python tests/run_tests.py --bless

# Run regression suite
python tests/run_tests.py

# Single fixture
python tests/run_tests.py --fixture ginga_one_full.deck

# Override tolerance
python tests/run_tests.py --tolerance 2.0
```

---

## Versioning

`MAJOR.MINOR.PATCH` per [Semantic Versioning 2.0](https://semver.org/).

- **MAJOR** — schema break: a v1.x YAML no longer renders correctly
- **MINOR** — new YAML surface, backward-compatible
- **PATCH** — bug fixes only; all goldens must pass before release

See `CHANGELOG.md` for full history.

---

## Current development line

| Version | Status | Notes |
|---|---|---|
| `0.1.0` | Current — first public PyPI release | Modular renderer, 375-pattern catalog, 14 UML composers, mypy-strict-clean |
| Next minor | In progress | PowerPoint export bridge, `fonttools`-backed text metrics, sidecar coverage scale-up |

---

## License

[MIT](./LICENSE). See [`docs/PUBLISHING.md`](docs/PUBLISHING.md) for the
release-cutting procedure.
