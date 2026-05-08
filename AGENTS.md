---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# AGENTS.md — Programmatic CLI reference for AI agents

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](./DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

---

This file is the **first thing an AI agent should read** when asked to
generate a presentation, slide, or diagram with FrameGraph. It lists
the entry points an agent will actually call, the contracts those
entry points enforce, and the failure modes the agent must handle.

`CLAUDE.md` covers project conventions and behavioral constraints;
this file covers operational tooling. They are complementary.

---

## When to use which command

Decide by what the agent has been asked to produce:

| Agent task | Use |
|---|---|
| One slide from a curated example, no editing | `framegraph patterns example <id>` → `framegraph patterns build <id> --fill …` |
| Smoke-check the whole pattern catalog | `framegraph patterns deck --pdf -o ./out` |
| A multi-slide deck themed and assembled into one PDF | `framegraph deck deck.yml -o ./out --pdf` (deck composed from `use:`/`fill:` slides) |
| A bespoke single diagram (architecture, flow, swimlane) | `framegraph render diagram.yml -o out.svg` |
| Discover what's available before authoring | `framegraph patterns list --has-sidecar --json`, `framegraph docs -o catalog.json` |

If you are unsure which path applies, **default to the deck path
(`framegraph deck`) with pattern-composed slides** — it scales from
one slide to many, themes are deck-wide, and the agent only writes
flat `{role: content}` payloads.

---

## Golden path: render one slide from a sidecared pattern

```sh
# 1. Discover patterns the catalog ships an example for
framegraph patterns list --has-sidecar --json

# 2. Inspect one to read its zone roles and content_types
framegraph patterns show 10           # SWOT Analysis

# 3. Pull the curated example fill (a flat {role: content} YAML)
framegraph patterns example 10 -o swot.fill.yml

# 4. Render it to SVG
framegraph patterns build 10 --fill swot.fill.yml -o swot.svg
```

Step 4 also accepts `--canvas-w` / `--canvas-h` (default 1920 × 1080).

---

## Golden path: a deck composed from patterns

The deck file format is:

```yaml
dsl: FrameGraph
version: 1.5
kind: presentation-deck

$theme: mckinsey            # optional library theme (bain, bcg, deloitte,
                            # ey, kpmg, mckinsey, pwc) — pick one
deck:
  canvas: {size: [1920, 1080]}

slides:
  - use: 10                 # by id …
    fill:
      strengths:    ["Brand recognition", "Data moat"]
      weaknesses:   ["Mobile UX lag"]
      opportunities: ["Adjacent vertical"]
      threats:      ["Two well-funded entrants"]

  - use: business-model-canvas   # … or by slug
    fill:
      key_partners:   [...]
      key_activities: [...]
      # all 9 BMC zones
```

Render:

```sh
framegraph deck deck.yml -o ./out --pdf       # raster PDF (default)
framegraph deck deck.yml -o ./out --pdf --vector  # vector PDF (selectable text)
```

The `fill:` block is **flat** — keys are zone roles, values are the
content. There is no `zones:` wrapper and no `pattern_id:` field —
those belong to *sidecars* (a maintainer artefact), not fills.
Conflating them is the most common authoring error.

---

## The fill contract

The fill payload is validated against the pattern's *effective*
schema — the default content_type-derived schema, with any
sidecar overrides applied.

Default content shapes (used when no sidecar overrides apply):

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

Numeric values are typed as **strings** (`"$2.4M"`, `"+12%"`) so
agents can format them without coercion. Numeric typing belongs in
sidecars when pattern-specific.

---

## Validation errors and how to recover

`patterns build`, `patterns deck`, and `deck` all emit
`pydantic.ValidationError` on bad fills. Common message fragments
and their cause:

| Error fragment | Cause | Recovery |
|---|---|---|
| `extra inputs are not permitted` | Fill has a key the pattern doesn't define | Run `patterns show <id>` and remove the unknown role |
| `field required` | A required role is missing | Add it; check the content_type for shape |
| `Input should be a valid string` | A `list_items` zone got dicts (or a sidecar overrode it to objects and you sent strings) | `patterns show <id>` flags sidecar overrides — match the override schema |
| `Input should be a valid list` | Top-level wrong shape (e.g. dict for a `list_items` zone) | Wrap content in a YAML list |

Always re-run `patterns show <id>` after a validation failure —
it lists the zone roles, content_types, and whether a sidecar is in
play.

---

## Discovering the API programmatically

For a planner / tool-use loop:

```sh
# Machine-readable list of all 375 patterns, with sidecar presence
framegraph patterns list --has-sidecar --json

# Full Python API catalog (modules, classes, signatures, JSON schemas)
framegraph docs -o catalog.json
```

`framegraph docs` is the right input when an agent needs to ground
its reasoning in the actual public surface — it dumps signatures,
docstrings, and Pydantic JSON schemas for every top-level model.

---

## Failure modes the agent must plan for

1. **Catalog id not found** — exit code 1 from `patterns *`. Recover by
   listing the catalog and picking a real id.
2. **Sidecar exists but `example_fill` is empty** — `patterns example`
   fails. Author a fill from the zone definitions in `patterns show`.
3. **Theme id unknown** — `framegraph deck` raises during
   `_build_globals`. Run `python -c "from framegraph import FrameGraphLibrary; from pathlib import Path; FrameGraphLibrary(Path('framegraph/lib')).list_themes()"` to enumerate.
4. **`<image>` href in a deck** — the deck renderer resolves relative
   paths against the directory of the deck YAML. Absolute paths and
   `data:` URIs pass through unchanged.
5. **PDF backends** — `--pdf` requires the `[pdf]` extra (cairosvg +
   Pillow). `--vector` requires the `[pdf-vector]` extra (weasyprint +
   pypdf). Without them, the SVG output is still produced; only the
   PDF step fails.

---

## Don't

- Don't author your own slide-template SVG when a catalog pattern
  fits — the catalog handles theming, layout, and accessibility
  metadata for you.
- Don't conflate fills with sidecars. Fills are flat
  `{role: content}`; sidecars are `pattern_id:` + `zones:` +
  `example_fill:`. `patterns example` always emits the fill shape.
- Don't reach into `framegraph._patterns` or
  `framegraph.patterns.*` from an agent loop unless you've already
  exhausted the CLI surface — the CLI is the supported contract;
  the Python API can change in MINOR versions.
- Don't rely on `framegraph render` for slides composed from
  catalog patterns — that path bypasses the deck-level theme and
  stylesheet binding. Use `framegraph deck` instead.

---

## See also

- [`docs/MANUAL.md`](docs/MANUAL.md) — comprehensive human user
  manual (concepts, multi-page deck format, theming, object-type
  reference, comparison with alternative tools).
- [`docs/AUTHORING-FILLS.md`](docs/AUTHORING-FILLS.md) — full reference
  for the fill / sidecar workflow, with worked examples.
- [`README.md`](README.md) — package overview and Python API quickstart.
- [`CLAUDE.md`](CLAUDE.md) — project-wide conventions and constraints.
- [`static/fixture/faz-ai-manifesto-deck.yml`](static/fixture/faz-ai-manifesto-deck.yml) —
  worked deck mixing bespoke and pattern-composed slides.
- [`examples/genai-ecosystem/`](examples/genai-ecosystem/) —
  end-to-end single-slide example (YAML + SVG + PDF + walk-through)
  for the "no catalog pattern fits, render bespoke" path.
