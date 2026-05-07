# framegraph

YAML-first hybrid semantic-visual diagram DSL that renders to clean SVG.

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
| `text` | Text with `wrap`, `v_align`, `style` reference |
| `line` | Straight line with optional arrowhead |
| `polyline` | Multi-segment line |
| `path` | SVG path data |
| `image` | Raster image via `href` |
| `component` | Styled box from `component_defs` |
| `chip_row` | Horizontal row of pill chips |
| `connector` | Semantic edge between bound objects |
| `legend` | Auto-generated colour legend |
| `group` | Container for nested objects |
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

## Roadmap

| Version | Target | Key features |
|---|---|---|
| v1.4 | Q3 2026 | Rich inline spans, `bullet_list`, `image` embed, `stack` container |
| v1.5 | Q4 2026 | `bar_chart`, `line_chart`, `$extends` in deck, speaker notes |
| v2.0 | Q1 2027 | `grid`/`row` containers, modular renderer, full v1.x compat audit |

---

## License

MIT
