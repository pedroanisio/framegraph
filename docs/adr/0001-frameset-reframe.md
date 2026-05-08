---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# ADR 0001 — Collapse `Document` and `Deck` into a `FrameSet` graph

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](../../DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

| | |
|---|---|
| **Status** | Accepted (Phase 1: schema + coercion shim) |
| **Date** | 2026-05-08 |
| **Supersedes** | — |
| **Superseded by** | — |

---

## Context

Today FrameGraph carries two unrelated top-level shapes:

- `kind: hybrid-semantic-visual-diagram` — a single document with one `scene.canvas`, validated by `Document` in `framegraph/_schema.py`.
- `kind: presentation-deck` — a deck with `deck.canvas` plus a list of `slides`, each its own quasi-document; validated by `DeckDocument` and rendered by `FrameGraphDeckRenderer` in `framegraph/library.py`.

Five capabilities are repeatedly requested but have nowhere to live cleanly under this split:

1. **Multiple canvas sizes per piece of content** (landscape ↔ portrait ↔ mobile). Currently each requires a hand-edited copy of the document.
2. **Cross-document navigation** (`see also` / `appendix` / external links). The semantic graph supports typed edges between *content nodes*, but there is no first-class "this slide links to that slide" or "this slide links to that URL" concept.
3. **Sitemap emission**. With no link graph, no sitemap.
4. **Single document and deck unified**. Library functions, schema models, validation paths, and the CLI all duplicate logic by `kind:`.
5. **Mobile / responsive output**. Today's `canvas.size` is a single fixed pixel pair.

The renderer's plug-in dispatcher (`FrameGraphRenderer._register_all`, the per-type `RENDERERS = {…}` tables in `framegraph/renderers/*`) is fully reusable for any of these — the gap is at the *envelope* level, not the per-object level.

---

## Decision

Introduce a unifying abstraction: **`FrameSet`** — a graph of **`Frame`**s connected by **`FrameLink`**s, where each Frame may declare one or more **`FrameTarget`**s (each carrying its own canvas). Old `kind:` values are preserved as inputs and **lifted into FrameSets** at load time by a coercion shim. Rendering happens by traversing the FrameSet graph; the existing per-type renderer modules and the existing pattern composer stay unchanged.

```yaml
dsl: FrameGraph
version: 2.0
kind: frameset

frameset:
  $theme: mckinsey
  defaults:
    targets:
      - {name: landscape, canvas: [1920, 1080]}

frames:
  - id: cover
    title: "Executive Summary"
    next: market-swot           # implicit chain → deck-style navigation
    targets:                     # per-Frame override; falls back to frameset.defaults
      - {name: landscape, canvas: [1920, 1080]}
    visual: {...}                # existing structure, unchanged

  - id: market-swot
    use: 10
    fill: { strengths: [...], ... }
    next: bmc
    prev: cover
    links:
      - {to: appendix-data, label: "Source data", relation: see_also}

  - id: appendix-data
    use: business-model-canvas
    fill: { ... }
```

Concrete model:

| Concept | Today | Reframed |
|---|---|---|
| Single document | `kind: hybrid-semantic-visual-diagram`, `Document` model | A `FrameSet` with one `Frame` |
| Deck | `kind: presentation-deck`, `DeckDocument` model + `FrameGraphDeckRenderer` | A `FrameSet` whose link graph is a chain (`next`/`prev`) |
| Canvas | `scene.canvas.size: [W, H]` (single) | `Frame.targets[*].canvas` (multiple) |
| Cross-references | (no concept) | `Frame.links: list[FrameLink]` — first-class navigation |
| Sitemap | (no concept) | The link graph **is** the sitemap |
| Mobile | (no concept) | A `FrameTarget` with `name: mobile` and a `canvas: [375, 812]` |

---

## Migration model — old YAML keeps working

A **coercion shim** at `framegraph/_frameset.py::coerce_to_frameset` reads any of:

- `kind: frameset` — passed through
- `kind: presentation-deck` — wrapped: each `slide` becomes a `Frame`, the `deck.canvas` becomes the FrameSet's `defaults.targets[0].canvas`, and the linear slide order is materialized as `next`/`prev` links
- `kind: hybrid-semantic-visual-diagram` — wrapped: the whole document becomes a single `Frame`, `scene.canvas` becomes that Frame's sole `target`

The shim is total: every existing fixture loads under the new path. The rendering output for those existing fixtures is **byte-identical** to today's output (regression-locked by `tests/integration/test_frameset_render_parity.py`).

Existing models (`Document`, `DeckDocument`) and the existing CLI / library entry points stay valid. They become *coerced views* over a FrameSet under the hood.

---

## Phasing

| Phase | Scope | Effort | Status |
|---|---|---|---|
| **1** | **Pydantic models, coercion shim, renderer adapter, byte-identical regression locks for single-doc YAML** | **M** | ✅ Shipped (commit `c0d1615`, 2026-05-08) |
| **2** | **Renderer Graph Dispatch + Deck-Merge Lift — `FrameGraphDeckRenderer.render_all` iterates via FrameSet spine; `build_frame_doc` mirrors `build_slide_doc` semantics for native FrameSet YAML; byte-identical deck SVG parity locked across every deck fixture** | **M** | ✅ Shipped (commit `5aa2303`) |
| **3** | **Multi-Target Rendering — `framegraph render --target`, `framegraph deck --target`, `framegraph deck --all-targets`; `list_frameset_targets`; `_resolve_frame_target_canvas`; per-target output directories; byte-identical no-target regression lock** | **S** | ✅ Shipped (commit `bc8b66f`) |
| **4** | **Sitemap Emission — `emit_sitemap(fs, base_url, target_filter=…)`; `list_frameset_target_union`; `framegraph sitemap <input.yml> --base-url <url> [-o <path>] [--target <name>]`; one URL per (Frame × declared target); URL-escaping; sitemap.org 0.9 schema; works on any input via `coerce_to_frameset`** | **XS** | ✅ Shipped (this commit) |
| 5 | Per-target `adjustments` (font scale, padding deltas, hide-on-target) | M | Next |
| 6 | Link injection into HTML / SVG / PDF outputs (clickable navigation) | S–M | Depends on Tier B from `docs/ANALYSIS.md` |
| 7 | Pattern-composition (`Frame.use:` + `fill:`) through the FrameSet path — requires `FrameGraphLibrary` access for theme + stylesheet resolution; today raises `NotImplementedError` | S | Follow-up |

Each follow-up is independently shippable.

---

## Consequences

### Wins

1. **One mental model for "what FrameGraph renders."** Everything is a Frame; everything else is metadata or a relation.
2. **Multi-target rendering becomes free.** `compute_boxes(pattern, w, h)` already accepts canvas dims as parameters — looping over targets is a render-loop concern, not a schema one.
3. **Sitemap emission becomes free.** A walk of the FrameSet's link graph dumps `sitemap.xml`.
4. **Cross-frame navigation has a home.** `Frame.links` is a Pydantic model; renderers (HTML now, SVG/PDF later) can pick it up consistently.
5. **Backward-compatible.** Old YAML, old CLI commands, old library API all keep working; the shim does the lift transparently.

### Costs

1. **Two ways to author the same content** (old shape and new shape) live in the corpus until a deprecation cycle ships. Mitigation: the shim is total and order-preserving; corpus documents and tests cover both shapes; semver MAJOR is reserved for the eventual deprecation.
2. **A second source of truth for canvas size**. `Document.scene.canvas` and `Frame.targets[*].canvas` both exist for the migration window. The coercion shim resolves this; new code reads from `Frame.targets[…]` exclusively.
3. **Validation surface grows.** New Pydantic models add ~200 LOC. Mitigation: every new model is `extra="forbid"`; the existing strict-mode mypy gate covers them.

### Non-goals (for Phase 1)

- HTML output. Tier B from `docs/ANALYSIS.md` recommendations remains a separate decision.
- Constraint-solver layout. Out of scope per `PURPOSE.md`.
- Mermaid / PlantUML ingestion. Already a documented non-goal in `framegraph/_uml.py:30-33`.
- Live preview / WYSIWYG. Already a documented non-goal in `PURPOSE.md`.

---

## Tests committed with Phase 1

Locked in `tests/unit/test_frameset_schema.py`, `tests/unit/test_frameset_coerce.py`, and `tests/integration/test_frameset_render_parity.py`:

- Every Pydantic model accepts valid documents and rejects malformed ones with `extra="forbid"` errors at the boundary.
- Every existing single-document fixture under `static/fixture/*.yml` survives the round-trip through `coerce_to_frameset` unchanged in semantics.
- Every existing single-document fixture's rendered SVG output is **byte-identical** before and after the coercion is applied. `render_frameset(coerce_to_frameset(doc))[0].svg` equals `FrameGraphRenderer(doc).render_svg()`.
- For `presentation-deck` fixtures, `coerce_to_frameset` produces a **structurally** equivalent FrameSet (every slide becomes a Frame in declaration order, same ids, `next`/`prev` chain materialized). Byte-identical render parity for decks is **Phase 2** scope — `FrameGraphDeckRenderer` remains the authoritative renderer for deck-shape YAML in Phase 1, and any `render_frameset()` of a deck-coerced FrameSet is best-effort (skips the deck-merge enrichments that `library.build_slide_doc` adds).
- `next`/`prev` chains in coerced presentation-decks preserve slide order and link symmetry.
- A native frameset YAML with two targets renders both, each at the declared canvas dimensions.
- `validate_frameset` rejects duplicate frame ids, dangling `next`/`prev`/`extends`/`links.to` references, and unknown link relations.

---

## Alternatives considered

1. **Keep `Document` and `DeckDocument` separate; add `targets:` and `links:` to each independently.** Rejected — duplicates the schema, validation, and rendering surface. Every future capability has to be added in two places.
2. **Make Frame a subtype of Document via inheritance.** Rejected — Pydantic v2's discriminated unions and inheritance interact awkwardly with `extra="allow"` semantics. The "FrameSet-of-one" approach is cleaner and fully equivalent in expressive power.
3. **Build the FrameSet abstraction *only* at the renderer / library level, leave schemas alone.** Rejected — schema is the contract for AI-agent authoring (`framegraph docs -o catalog.json` emits schemas as JSON). The reframe has to live in the schema for agents to take advantage of it.
4. **Wait until HTML output is needed and design the abstraction then.** Rejected — every capability listed under "Wins" above is already requested today; HTML is one of five, not the only one.

---

## See also

- [`docs/MANUAL.md`](../MANUAL.md) — current public reference (will document FrameSets in a follow-up).
- [`docs/ANALYSIS.md`](../ANALYSIS.md) — competitive comparison and roadmap that motivated this reframe.
- [`framegraph/_frameset.py`](../../framegraph/_frameset.py) — implementation (lands with this ADR).
- [`framegraph/_schema.py`](../../framegraph/_schema.py) — extended with FrameSet validation dispatch.
