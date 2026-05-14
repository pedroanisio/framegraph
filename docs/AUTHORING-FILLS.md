---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-07"
---

# Authoring fills and sidecars

This guide covers two distinct workflows:

- **A. Filling a pattern** (per-render task, performed by humans
  *or* AI agents on every slide they produce). Pure CLI, no Python.
- **B. Authoring a sidecar** (rare maintainer task, performed once
  per pattern that needs a richer fill shape than the defaults).

If you're an AI agent producing a deck, you almost always want
section A. Skip to it.

---

## Section A — Filling a pattern (CLI-only workflow)

The fill workflow has four CLI verbs, ordered by the agent's loop:

| Verb | Purpose |
|---|---|
| `framegraph patterns list [--has-sidecar] [--json]` | Discover available patterns. `--has-sidecar` filters to patterns with a curated example. `--json` emits machine-readable records. |
| `framegraph patterns show <id>` | Print one pattern's zones, content_types, sizes, placements, and whether a sidecar exists. |
| `framegraph patterns example <id> [-o fill.yml] [--format=yaml\|json]` | Emit the sidecar's curated `example_fill` as a flat `{role: content}` payload — exactly the shape `patterns build --fill` expects. |
| `framegraph patterns build <id> --fill content.yml [-o out.svg]` | Validate the fill against the pattern's effective schema (default + sidecar overrides) and render to SVG. |

### Agent recipe — render one slide from a curated example

```sh
framegraph patterns example 10 -o swot.fill.yml
framegraph patterns build 10 --fill swot.fill.yml -o swot.svg
```

That's the entire happy path. No Python glue.

### Agent recipe — render an entire deck from sidecar examples

```sh
framegraph patterns deck --pdf -o ./deck-output
```

Renders every pattern that ships a sidecar `example_fill` into one
multi-page PDF (and per-page SVGs + per-page fill YAMLs for audit).
Filter with `--category=consulting` or `--ids=10,44,91`.

### Agent recipe — author a fill from scratch

For a pattern *without* a sidecar (the majority of the catalog):

```sh
framegraph patterns show 7
# inspect the zones table; map each role to its content_type's default shape
# (see `Default content shapes` below)
$EDITOR my-fill.yml
framegraph patterns build 7 --fill my-fill.yml -o out.svg
```

### Fill payload shape (the contract)

A fill file is a **flat top-level mapping** from zone role to
content. It is *not* a sidecar — it has no `pattern_id`, no
`zones:` wrapper, no `example_fill:` key.

Sidecar (lives in `framegraph/data/fills/`):

```yaml
pattern_id: 10
zones: {}
example_fill:
  strengths: ["Brand", "Team"]
  weaknesses: ["Mobile UX"]
  opportunities: ["AI"]
  threats: ["Macro"]
```

Fill (what an agent passes to `--fill`):

```yaml
strengths: ["Brand", "Team"]
weaknesses: ["Mobile UX"]
opportunities: ["AI"]
threats: ["Macro"]
```

Conflating these is the most common authoring error. `patterns
example` always emits the latter shape.

### Predictable validation errors

`patterns build` prints `pydantic.ValidationError` on bad fills.
Common message fragments and their cause:

| Error fragment | Cause | Fix |
|---|---|---|
| `extra inputs are not permitted` | Fill has a key not in the pattern's roles | Run `patterns show <id>` and remove the unknown role |
| `field required` | Fill is missing a required role | Add the missing role with a value matching its content_type |
| `Input should be a valid string` | Wrong shape for a `list_items` zone (e.g. dict instead of string) | Either the zone is `list[str]` and you sent objects, or the sidecar declares object items and you sent strings — `patterns show` flags the sidecar; the override schema is in the sidecar file |
| `Input should be a valid list` | Wrong top-level type (e.g. dict for a `list_items` zone) | Wrap the content in a YAML list |

### Discovering the catalog

```sh
framegraph patterns list                          # all 375
framegraph patterns list --category=consulting    # filter
framegraph patterns list --has-sidecar            # only the curated 17
framegraph patterns list --has-sidecar --json     # machine-readable
```

For machine consumption (agents wiring patterns into a planner):

```sh
framegraph patterns list --has-sidecar --json | jq '.[].id'
```

---

## Section B — Authoring a sidecar (maintainer workflow)

The rest of this document covers when and how to add a sidecar
under `framegraph/data/fills/`. This is rare: only do it when the
default content_type-derived schema is genuinely too loose for
agents to produce useful content, or when a worked example would
help agents understand the pattern.

## Concepts

| | |
|---|---|
| **Pattern** | A named slide template in the bundled catalog (`framegraph/data/patterns/slides-patter-a.yml`). 375 of them, ids 1–375. Each declares zones (named regions) with size, placement, optional shape, and a `content_type`. |
| **Fill** | The content payload an author supplies — one entry per zone, keyed by role. Validated against the pattern's *effective* fill schema. |
| **Default fill schema** | Auto-derived from each zone's `content_type` literal. Ten content types map to ten default Pydantic shapes (see [`framegraph.patterns.fill`](../framegraph/patterns/fill.py)). |
| **Sidecar** | A YAML file at `framegraph/data/fills/<id>-<slug>.yml` that overrides the default schema for specific zones of one pattern. Used when richer content shapes are needed than the defaults provide. |
| **Effective schema** | What you actually fill against: the default schema, with any sidecar overrides applied. Computed by `derive_fill_schema_with_sidecar(pattern, sidecar)`. |

## Default content shapes

Per [Phase 1](ROADMAP-FILL-RENDER.md#phase-1-fill-schema-foundation-xs):

| `content_type` | Default Pydantic shape |
|---|---|
| `title_body` | `{title: str, body: str | None}` |
| `metric` | `{label: str, value: str, trend: str | None}` |
| `list_items` | `list[str]` |
| `key_value` | `dict[str, str]` |
| `comparison` | `{left: str, right: str}` |
| `chart_data` | `{type: str, series: list[dict]}` |
| `table_data` | `{headers: list[str], rows: list[list[str]]}` |
| `image` | `{src: str, alt: str | None}` |
| `axis_label` | `{title: str, units: str | None}` |
| `decorative` | `None` |

`value` is typed as a string so authors pass formatted numbers
("$2.4M", "+12%") without coercion. Numeric typing belongs in
sidecars when pattern-specific.

## When to author a sidecar

Add a sidecar **only when**:

1. **Richer content per zone** than the default offers.
   *Example*: BMC's `revenue_streams` should be
   `list[{label, metric}]`, not `list[str]`.
2. **A representative example** would help agents understand the
   pattern. The schema may match the default, but the sidecar's
   `example_fill` shows what good content looks like.

A pattern with no sidecar uses the default schema for every zone.

## Filename convention

```
<id_zero_padded>-<slug>.yml
```

Examples:

```
010-swot-analysis.yml
044-business-model-canvas.yml
198-regulatory-compliance-matrix.yml
```

The 3-digit zero-padded id keeps `ls` sorted; the slug is the
catalog name lowercased, spaces → hyphens, punctuation removed.

## Sidecar mini-DSL (Phase 2 v1)

```yaml
pattern_id: <int>           # required, must match catalog id

zones:                      # zero or more per-zone overrides
  <role>:
    item_kind: object | string   # for list_items zones
    item_fields:                  # required when item_kind == object
      <field_name>:
        type: string              # only `string` supported in v1
        required: true | false

example_fill:               # optional but recommended
  <role>: <fill content>
```

Phase 2 supports overriding `list_items` zones with object items
(BMC's revenue_streams shape). Other content types accept the
default-derived shape; richer overrides for them are deferred to
later phases.

## Worked examples

### Example 1 — Simple (no overrides): SWOT Analysis (#10)

[`framegraph/data/fills/010-swot-analysis.yml`](../framegraph/data/fills/010-swot-analysis.yml)

SWOT has four `list_items` zones — one per quadrant. The default
`list[str]` shape is exactly right; the sidecar exists only to
ship a representative `example_fill`.

```yaml
pattern_id: 10
zones: {}   # all four zones use defaults
example_fill:
  strengths:
    - "Strong brand recognition in target segment"
    - "Proprietary data moat from 5+ years of usage"
  weaknesses:
    - "Mobile experience lags competitors"
  opportunities:
    - "Adjacent vertical with similar pain point"
  threats:
    - "Two well-funded entrants targeting our segment"
```

**Use the CLI:**

```sh
# Author your fill in a YAML file:
cat > swot.yml <<EOF
strengths: ["Brand", "Team"]
weaknesses: ["Mobile UX"]
opportunities: ["AI"]
threats: ["Macro"]
EOF

framegraph patterns build 10 --fill swot.yml -o swot.svg
```

### Example 2 — Medium (defaults + example_fill): Communications Plan (#91)

[`framegraph/data/fills/091-communications-plan.yml`](../framegraph/data/fills/091-communications-plan.yml)

This is a member of the 17-pattern comparison-table family — left
column is `list_items` (audience labels); the next 3 columns are
`table_data` (each headers + rows). All four zones use defaults;
the sidecar's value is purely the example_fill that shows how
the four zones compose into one coherent communications plan.

```yaml
pattern_id: 91
zones: {}
example_fill:
  audiences:
    - Executive sponsors
    - Department heads
    - Frontline employees
    - External partners
  key_messages:
    headers: [Audience, Core message]
    rows:
      - [Execs, "Why we're transforming and what success looks like"]
      - [Dept heads, "How responsibilities shift in your function"]
      ...
  channels_frequency:
    headers: [Channel, Frequency]
    rows:
      - [All-hands, Monthly]
      - [Manager cascade, "Weekly during cutover"]
      ...
  owner_timing:
    headers: [Owner, Timing]
    rows: [[CEO + CFO, Kickoff], [Function leads, "Weeks 1-4"]]
```

### Example 3 — Complex (real overrides): Business Model Canvas (#44)

[`framegraph/data/fills/044-business-model-canvas.yml`](../framegraph/data/fills/044-business-model-canvas.yml)

BMC has 9 `list_items` zones. Seven are short-bullet lists
(default `list[str]`); two — `revenue_streams` and `cost_structure`
— hold **named amounts**. The default `list[str]` would force
authors to write "Subscriptions: $2.4M" as a single string,
losing the structured shape. The sidecar overrides those two
zones to `list[{label, metric}]`.

```yaml
pattern_id: 44

zones:
  revenue_streams:
    item_kind: object
    item_fields:
      label:
        type: string
        required: true
      metric:
        type: string
        required: true

  cost_structure:
    item_kind: object
    item_fields:
      label:
        type: string
        required: true
      metric:
        type: string
        required: true

example_fill:
  key_partners:
    - "Cloud infrastructure provider"
    - "Logistics network"
  ...
  revenue_streams:
    - {label: "Subscription tiers",   metric: "$12.6M"}
    - {label: "Transaction fees",     metric: "$4.8M"}
    - {label: "Enterprise contracts", metric: "$7.0M"}
  cost_structure:
    - {label: "Engineering and product", metric: "$8.4M"}
    ...
```

**Use the CLI:**

```sh
framegraph patterns build 44 --fill bmc-content.yml -o bmc.svg
# wrote bmc.svg  (9.0 KB)
```

The renderer will pick up the sidecar automatically (it looks for
`fills/044-*.yml`); the fill YAML the author writes only needs the
top-level role keys.

## Validation

Before committing a sidecar:

```sh
python3 scripts/validate_fills.py
```

The script:
1. Parses every `*.yml` in `framegraph/data/fills/`.
2. Resolves the corresponding pattern from the bundled catalog.
3. Builds the effective schema.
4. Validates the `example_fill` against the schema.

Fails loudly if any sidecar is malformed or its example doesn't
match its declared shape.

## Authoring guidance

| Situation | Default shape works? | Sidecar needed? |
|---|---|---|
| List of bullet points | Yes (`list[str]`) | Maybe — only for example_fill |
| Single number with label | Yes (`metric` default) | No |
| List of `{label, metric}` items | No — defaults give `list[str]` | Yes (override `item_kind: object`) |
| Comparison "before / after" | Yes (`comparison` default) | Maybe — for example_fill |
| Heatmap / matrix table | Yes (`table_data` default) | Maybe — for example_fill |
| Custom field types (numeric, enums) | No | Phase 7+ — sidecars don't yet support these |

## What's *not* yet supported

- **Numeric / enum / nested object types** in `item_fields`. v1 only
  supports `type: string`. Phase 7+ will widen this.
- **Optional zones**. Phase 1 treats every zone as required;
  patterns with conditionally-rendered zones are a future concern.
- **Cross-zone validation** (e.g. "revenue_streams entries ≤
  cost_structure entries"). Manual today.
- **Theming / brand tokens applied at fill time**. The renderer's
  Tokens layer handles theming separately; sidecars are about
  content shape, not visual style.

## See also

- [`docs/ROADMAP-FILL-RENDER.md`](ROADMAP-FILL-RENDER.md) — the full
  six-phase roadmap.
- [`framegraph/patterns/fill.py`](../framegraph/patterns/fill.py) — Phase 1
  default-schema implementation.
- [`framegraph/patterns/sidecar.py`](../framegraph/patterns/sidecar.py) —
  Phase 2 sidecar loader and effective-schema builder.
- [`framegraph/patterns/render.py`](../framegraph/patterns/render.py) —
  Phase 4 pattern-to-SVG renderer bridge.
- [`framegraph/cli.py`](../framegraph/cli.py) — `patterns list / show /
  example / build / deck` agent surface.
- [`framegraph/data/fills/`](../framegraph/data/fills/) — the 17 shipped
  sidecars.

## Demonstrating the end-to-end flow

To verify the entire authoring surface in one CLI invocation:

```sh
framegraph patterns deck --pdf -o ./demo
# Rendering 17 pattern(s) → ./demo
#   ✓ pattern  10  SWOT Analysis ...
#   ✓ pattern  44  Business Model Canvas ...
#   ...
#   wrote patterns-deck.pdf  (~2 MB, 17 pages, raster, 150 DPI)
```

This single command exercises every CLI verb internally: discovers
sidecared patterns, fetches each `example_fill`, validates it
against the effective schema, renders the SVG, and assembles the
multi-page PDF. The output directory contains:

- `patterns-deck.pdf` — the assembled deck.
- `svgs/<pid>.svg` — one SVG per pattern.
- `fills/<pid>.fill.yml` — the flat fill payload an agent would
  write by hand to reproduce the same slide.
