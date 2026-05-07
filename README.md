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

Current package version: `2.0.0.dev0`.

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
framegraph render  diagram.yml [-o output.svg]
framegraph deck    deck.yml    [-o output_dir/]
framegraph version
```

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
| `2.0.0.dev0` | Current | Modular renderer split is in tree; CLI, tests, and docs reflect the dev line |
| Next 2.0 goals | In progress | `grid`/`row` layout completion, full v1.x compatibility audit, remaining rendering gaps such as `backdrop_blur` and `inner_ring` |

---

## License

MIT metadata is declared in `pyproject.toml`. A repository `LICENSE` file has not yet been added.
