---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "GPT-5 via Codex"
  date: "2026-05-07"
---

# Changelog

All notable changes to `framegraph` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning 2.0.0](https://semver.org/).

**Semver contract:**
- **MAJOR** — any v1.x YAML stops rendering correctly (schema break).
  Authors must migrate.
- **MINOR** — new YAML keys, object types, or renderer features.
  All prior MINOR-version YAML renders unchanged.
- **PATCH** — bug fixes, renderer corrections, docs.
  No new YAML surface. All golden snapshots must pass before release.

---

## [Unreleased]

### Planned (v2.0 line)
- `grid` and `row` containers (schema already forward-compatible from `layout.kind`)
- Full v1.x backward-compat regression report
- `inner_box` reference syntax (`box: "$card.inner"`) for compound layouts
- File-path image embedding to data URI at render time
- `backdrop_blur` and `inner_ring` rendering support where the grammar already exposes them

---

## [2.0.0.dev0] — 2026-05-07  (modular renderer complete)

### Changed (breaking for contributors, not for YAML authors)
- **Renderer split into per-object-type modules** (`framegraph/renderers/`)
  All render functions moved to 7 modules; `renderer.py` shrunk from 1934 → 873 lines.
  YAML authors: zero breaking changes. All 35 golden snapshots pass at 1% tolerance.

  | Module | Types |
  |---|---|
  | `shapes.py` | `rect`, `ellipse` |
  | `symbols.py` | `icon`, `use` |
  | `image.py` | `image` |
  | `lines.py` | `line`, `polyline`, `path`, `connector`, `legend` |
  | `text_objects.py` | `text`, `bullet_list` |
  | `charts.py` | `bar_chart`, `line_chart` |
  | `layout.py` | `container`, `group`, `component`, `chip_row` |

### Added
- **`register(type_name, fn)` API** — register custom object-type renderers at runtime.
  Function signature: `fn(renderer: FrameGraphRenderer, obj: Mapping) -> str`

  ```python
  def render_callout(r, obj):
      x, y, w, h = box(obj.get("box", [0,0,0,0]))
      return f'<g id="{obj.get("id")}"><rect x="{x}"…/></g>'

  r = FrameGraphRenderer(doc)
  r.register("callout", render_callout)
  ```

- **`framegraph._helpers`** module — all module-level pure functions (`esc`, `fmt`,
  `box`, `pt`, `fnum`, `attrs`, `sid`, `deep_get`, `_lorem`, `_expand_lorem`).
  Importable by third-party renderer modules without circular import risk.

- **`framegraph/renderers/__init__.py`** — `ALL_MODULES` list for auto-discovery.
  Adding a new module and appending to `ALL_MODULES` is the full contribution path.

---

## [1.5.0] — 2026-05-07

### Added
- **`bar_chart` object** (SP-3) — single and multi-series bar charts.
  `data.values` + `data.labels` for single series; `data.series: [{label, values, color}]`
  for grouped multi-series. Options: `value_labels`, `grid_lines`, `bar_width`,
  `baseline`, legend auto-generated for multi-series. `data.note` renders as italic caption.

- **`line_chart` object** (SP-3) — multi-series line charts.
  `data.series: [{label, values, color, dash}]`. Options: `stroke_width`,
  `point_radius`, `show_legend`, `grid_lines`. Dashed series via `dash: true`.

- **`$extends` in deck format** (SP-5) — slide-level inheritance.
  Merge chain: `$theme` → `deck.tokens` → base slide tokens → child slide tokens.
  Layer merge: base layers dict-keyed by id; child layers override by id or append.
  `_slide_index` built at `__init__` for O(1) lookup.

- **Speaker notes** (SP-5) — `notes:` field on deck slides.
  Excluded from SVG output. `collect_notes()` → `{slide_id: text}`.
  `render_all()` auto-calls `render_notes()` → `notes.md` alongside SVGs.

- **`outer_ring` on `rect`** — concentric ring stroke outside the declared box.
  Schema matches ellipse `outer_ring` but uses `gap` instead of `offset`
  (same semantics; `gap` is the more accurate name for rectilinear shapes).
  Ring expands by `gap + width/2` on all sides. Corner radius auto-scaled:
  ring `rx = shape_radius + expand` so the ring follows the rect's rounded corners.
  Supports `dash`, `opacity`. Zero regressions across all 35 golden snapshots.

### Notes
- All v1.4.x YAML renders within 1% tolerance under v1.5.0
- Test suite: 21 fixtures, 35 golden slides, 1.0% tolerance

---

## [1.4.0-dev] — 2026-05-07  (SP-1a — auto-layout complete)

### Added
- **`type: container` with `layout.kind: stack`** (SP-1a)
  Auto-layout container that distributes children along a main axis.
  Schema designed for backward-compatible extension to `grid`/`row` in v2.0.

  Layout options:
  - `direction: vertical | horizontal`
  - `gap:` — px between children
  - `align: stretch | start | center | end` — cross-axis alignment
  - `justify: start | center | end | space_between` — main-axis distribution
  - `padding: [h, v]` or scalar — inner padding

  Child sizing:
  - Explicit `box` size in the main-axis dimension → used as-is
  - `flex: N` → proportional share of remaining space
  - Neither → equal share of remaining space

  Resolved child boxes are written back into `object_index` so connectors
  can target ports on container children using dot-notation.

  `kind: grid` and `kind: row` are reserved in the schema; the renderer
  emits a comment placeholder if encountered (no error, forward-compatible).

---

## [1.4.0-dev] — 2026-05-07  (SP-2 rich text family)

### Added
- **Inline spans** (`text.spans: [{text, weight?, color?, italic?, size?}]`)
  Allows mixed weight, color, italic, and size within a single text object.
  Spans are word-wrapped to box width when `style.wrap: true`.
  Falls back to plain `text:` rendering when `spans:` key is absent —
  fully backward-compatible.

- **`bullet_list` object** (`type: bullet_list`)
  First-class list rendering. Fields:
  - `items:` — list of strings or `{text, indent}` maps
  - `marker:` — bullet character (default `"•"`); `"1."` for ordered lists
  - `gap:` — extra px between items (default `0.3 × line_height`)
- `indent:` — px per indent level (default 12)
- `style:` — standard text style reference
  Items are word-wrapped to available width. Multi-level indentation supported.

---

## [1.3.0] — 2026-05-07

### Added
- Word wrap: `style.wrap: true` on any text object word-wraps content to box width
- Vertical text alignment: `style.v_align: top | middle | bottom`
- Per-character-class width tables replacing the flat 0.55× heuristic.
  Bold uses `{narrow: 0.38, normal: 0.56, wide: 0.72, space: 0.28, digit: 0.58, punct: 0.34}` em-units.
  Normal weight scales at 0.90×.
- `FrameGraphDeckRenderer` (v1.2 deck format with multi-page `slides:` array)
- SP-6 golden-snapshot test harness (`tests/run_tests.py`):
  23 goldens across 12 fixtures at 2× scale (1920×1080), 1% pixel tolerance
- SP-7 packaging: `pyproject.toml`, CLI (`framegraph render` / `framegraph deck`),
  GitHub Actions CI (golden regression + lint + PyPI publish on tag)
- 7 consulting firm token packs: McKinsey, BCG, Bain, Deloitte, PwC, EY, KPMG

### Fixed
- `text_svg` shrink-to-fit was using a single flat coefficient (0.55) regardless
  of font weight. Bold text was over-shrunk by ~10–15%. Now uses per-weight tables.

### Notes
- Renderer: 1001 lines (`framegraph/renderer.py`)
- All v1.0–v1.2 YAML files render within 1% pixel tolerance of their v1.2 reference SVGs

---

## [1.2.0] — 2026-04-xx

### Added
- `FrameGraphDeckRenderer`: `kind: presentation-deck` with shared `deck.tokens`,
  `deck.symbols`, and per-slide token merge chain
- `layer.opacity`
- `outer_ring` on ellipses

---

## [1.1.0] — 2026-04-xx

### Added
- `visual.symbols` + `type: use` — reusable multi-shape templates (SVG `<symbol>/<use>`)
- Slot params (`$slotname`, `$paramname`) resolved at use-site
- `tokens.glyph_map` for named glyph aliases
- `type: icon` object (icon-font or Unicode glyph, rendered as centred `<text>`)
- `tokens.fill_styles` gradients: `LinearGradient`, `RadialGradient`

---

## [1.0.0] — 2026-03-xx

### Added
- Initial release of the FrameGraph DSL renderer
- Object types: `rect`, `ellipse`, `text`, `component`, `chip_row`, `line`,
  `polyline`, `path`, `connector`, `legend`, `group`, `image`
- Semantic block: typed nodes/edges with ontology support
- Token system: `colors`, `fonts`, `text_styles`, `stroke_styles`, `fill_styles`
- CLI: `python renderer.py input.yml -o output.svg [--strict] [--quiet]`
