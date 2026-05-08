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

### Added
- **ADR 0001 Phase 4** ([docs/adr/0001-frameset-reframe.md](docs/adr/0001-frameset-reframe.md))
  — Sitemap emission. The FrameSet's link graph **is** the sitemap.
  - `framegraph._frameset.emit_sitemap(fs, base_url, *, target_filter=…)`
    walks every Frame in declaration order and emits one URL per
    declared render target. URL pattern:
    `<base_url>/<target>/<frame_id>` with frame ids and target
    names URL-escaped via `urllib.parse.quote`. Output validates
    against the sitemap.org 0.9 schema
    (`http://www.sitemaps.org/schemas/sitemap/0.9`).
  - `framegraph._frameset.list_frameset_target_union(fs)` — union
    of every declared target name (defaults + per-Frame), in
    discovery order.
  - `framegraph sitemap <input.yml> --base-url <url> [-o <path>]
    [--target <name>]` CLI — accepts any FrameGraph YAML
    (frameset, deck, or legacy single-doc) by coercing through
    `coerce_to_frameset`. Writes to file with `-o` or to stdout.
  - 34 regression tests in
    `tests/integration/test_frameset_phase4.py` cover XML
    structure, URL escaping (spaces, `?`, `#`, `<`, `>`, `&`),
    deterministic ordering, target filter, base-URL validation,
    coerced inputs (legacy + deck), and the CLI surface.

- **ADR 0001 Phase 3** ([docs/adr/0001-frameset-reframe.md](docs/adr/0001-frameset-reframe.md))
  — Multi-target rendering. Same source FrameSet renders to
  multiple canvases (landscape, portrait, mobile, custom)
  deterministically.
  - `framegraph render --target <name>` renders at the named
    target's canvas dimensions via the FrameSet path.
  - `framegraph deck --target <name>` renders every slide at
    the target's canvas (per-Frame `targets:` first, then
    `frameset.defaults.targets`).
  - `framegraph deck --all-targets` loops over every declared
    target, writing per-target subdirectories
    (`<output>/landscape/`, `<output>/portrait/`, …).
  - `--target` and `--all-targets` are mutually exclusive.
  - `framegraph.library.list_frameset_targets(data)` enumerates
    the declared target set; `_resolve_frame_target_canvas`
    resolves the canvas dims with per-Frame override priority.
  - `FrameGraphDeckRenderer.render_all(out, *, target_name=…)` —
    the same target lookup wired into the public render API for
    non-CLI callers.
  - `build_slide_doc(slide, *, canvas=…)` and
    `_build_pattern_slide_doc(slide, *, canvas=…)` accept an
    optional canvas override; defaults preserve byte-identical
    Phase 2 output.
  - 21 regression tests in
    `tests/integration/test_frameset_phase3.py` cover the
    enumerator, the canvas resolver, the render_all target_name
    parameter, both CLI commands, the mutually-exclusive flag
    check, and the byte-identical no-target regression lock.

- **ADR 0001 Phase 2** — Renderer Graph Dispatch + Deck-Merge Lift.
  `FrameGraphDeckRenderer.render_all`
  now drives off the FrameSet view of the deck via `coerce_to_frameset`;
  per-slide enrichment continues to flow through
  `build_slide_doc` so SVG output is byte-identical to the
  pre-Phase-2 path. Native-FrameSet YAML gains a parallel
  enrichment path: `framegraph._frameset.build_frame_doc` lifts
  `library.build_slide_doc`'s deck-merge logic (token deep-merge,
  `extends` chain, symbol / component_def shallow-merge,
  canonical `rendering_contract` defaults) for `kind: frameset`
  documents.
- `framegraph._frameset.build_frame_doc(frameset, frame, target)` —
  enriches a `(FrameSet, Frame, FrameTarget)` triple into a
  legacy single-document dict ready for `FrameGraphRenderer`.
- `framegraph._frameset._resolve_extends_chain` — recursive
  `Frame.extends` resolver with cycle detection, mirroring
  `library.build_slide_doc`'s `$extends` semantics for native
  FrameSets.
- 19 Phase 2 regression tests in
  `tests/integration/test_frameset_phase2.py`:
  byte-identical deck SVG parity across every deck fixture; the
  `build_frame_doc` enrichment contract; multi-frame `extends`
  chain resolution; cycle rejection; `NotImplementedError` on
  pattern-composed Frames (Phase 7 scope).
- **Phase 1** ([2026-05-08]): `framegraph._frameset` module — new
  Pydantic models (`Frame`, `FrameLink`, `FrameTarget`,
  `FrameSetDocument`), `validate_frameset`, `coerce_to_frameset`,
  `render_frameset`, `project_frame_to_document`.
  `framegraph._schema.validate_any` single dispatch.
  70 regression tests pinning byte-identical SVG parity for every
  single-document fixture and structural equivalence for every
  deck fixture.

### Fixed
- `framegraph/library.py::FrameGraphDeckRenderer._build_pattern_slide_doc`
  — sidecar auto-discovery path was still pointing at the legacy
  `static/refs/fills/` location (sidecars moved into the package
  at `framegraph/data/fills/` in the publish-prep commit). Pattern-
  composed deck slides with `item_kind: object` sidecar overrides
  (BMC `revenue_streams` / `cost_structure`) failed validation
  pre-fix because the sidecar wasn't found.

### Planned
- Phase 3: `framegraph render --target <name>` and `framegraph deck
  --target <name>` flags for multi-target rendering.
- Phase 4: `framegraph sitemap <frameset.yml>` emitter.
- `grid` and `row` containers (schema already forward-compatible from `layout.kind`)
- Full v1.x backward-compat regression report
- `inner_box` reference syntax (`box: "$card.inner"`) for compound layouts
- `backdrop_blur` and `inner_ring` rendering support where the grammar already exposes them
- PowerPoint export bridge via `python-pptx` (Tier-1 of [`docs/ANALYSIS.md`](docs/ANALYSIS.md))
- `fonttools`-backed text-metric measurement to retire the per-character-class width tables
- Sidecar coverage scale-up from 17 → ~100 of 375 patterns

---

## [0.1.0] — 2026-05-08  (first public PyPI release)

First public release on PyPI. The package has been internal-only up
to this point under the `2.0.0.dev0` placeholder; renaming to a
clean `0.1.0` (per [PEP 440](https://peps.python.org/pep-0440/) for
publish-readiness) for the initial PyPI cut. Subsequent releases
follow the project's documented MAJOR/MINOR/PATCH semver contract.

### Public API
- `FrameGraphRenderer(doc).render_svg()` — render a parsed YAML
  document to SVG.
- `FrameGraphRenderer.from_yaml_file(path)` — load and render in
  one step.
- `FrameGraphLibrary(lib_path)` — discover token packs and symbol
  packs from a `lib/` directory.
- `FrameGraphDeckRenderer(data, library=lib).render_all(output_dir)`
   — render a multi-slide deck YAML to per-slide SVGs (and optional
  multi-page PDF via the `[pdf]` extra).

### CLI
- `framegraph render <doc.yml>` — single document → SVG / PDF / 4K PNG.
- `framegraph deck <deck.yml>` — multi-slide deck → per-slide SVGs +
  optional multi-page PDF, with `use:` + `fill:` pattern composition.
- `framegraph patterns list / show / example / build / deck` — slide
  catalog of 375 patterns (50 generic + 275 consulting + 50 expert);
  17 ship a curated `example_fill` sidecar.
- `framegraph docs -o catalog.json` — machine-readable Python API
  catalog (modules, classes, signatures, Pydantic JSON schemas) for
  AI-agent consumption.
- `framegraph version`.

### Diagram coverage
- 18 first-class visual object types (`rect`, `ellipse`, `text`,
  `bullet_list`, `line`, `polyline`, `path`, `image`, `connector`,
  `legend`, `group`, `container`, `bar_chart`, `line_chart`, `icon`,
  `use`, `chip_row`, `table`).
- 16 UML primitives + 14 UML 2.5.1 composer types: class, package,
  use-case, component, deployment, activity, state-machine,
  sequence, communication, composite-structure, object, profile,
  timing, interaction-overview.

### Layout
- Pure-Python four-stage Sugiyama (Eades cycle removal + longest-path
  layering + median-heuristic crossing minimization + Brandes-Köpf
  x-coordinate assignment).
- Pattern layout with span- and density-aware allocation, region
  handlers, and clamped relative placement.

### Output
- SVG (always — the rendering core, no extras needed).
- Raster PDF and 4K PNG via the `[pdf]` extra (cairosvg + Pillow).
- Vector PDF (selectable text) via the `[pdf-vector]` extra
  (weasyprint + pypdf).

### Quality gates
- 1283 tests pass; 90 % coverage gate (87 % current overall).
- Mypy strict mode: 0 errors. Ruff lint + format: clean on touched
  surface.
- Golden-snapshot regression suite under `python tests/run_tests.py`.

### Packaging
- Pattern catalog (`framegraph/data/patterns/*.yml`) and 17
  curated sidecars (`framegraph/data/fills/*.yml`) ship inside the
  wheel via `[tool.setuptools.package-data]`.
- Seven consulting token packs (`framegraph/lib/tokens/*.yml`) and
  the bundled default stylesheet (`framegraph/lib/styles/default.yml`).
- `LICENSE` file (MIT) added at repo root.
- `[project.urls]` declared so PyPI surfaces Homepage / Repository /
  Documentation / Issues / Changelog.

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
