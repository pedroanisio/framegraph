---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 (1M context) via Claude Code"
  date: "2026-05-07"
---

# FrameGraph DSL — Document Schema

This document is the human-readable companion to the **executable
schema** at [framegraph/_schema.py](../../framegraph/_schema.py).
The Pydantic models in `_schema.py` are the normative contract. This
file exists to capture conventions, invariants, and design rules
that don't survive a JSON-Schema export — but should still bind
authors and reviewers.

When this document and `_schema.py` disagree, **`_schema.py` wins**.
File a docs issue against this file.

---

## Document anatomy

A FrameGraph document is one of two shapes, both keyed by `dsl: FrameGraph`:

- **Standalone diagram** — top-level `scene` + `semantic` + `visual`. Validated by `framegraph._schema.Document`.
- **Multi-slide deck** — top-level `deck` + `slides`. Validated by `framegraph._schema.DeckDocument`.

Every standalone document carries:

| Block | Role |
|---|---|
| `scene` | Canvas size + rendering contracts (`coordinate_mode`, `text`, `semantics`, `debug_boxes`, `preserve_manual_line_breaks`). |
| `semantic` | Typed graph: `ontology.{node_types,edge_types}` + `nodes` + `edges`. Property bags on entries are open. |
| `visual` | `tokens` (colors / fonts / styles / glyphs) + `symbols` + `component_defs` + `layers`. |

---

## Token-substitution invariant

> Anywhere a `COLOR` is accepted, a token id from
> `visual.tokens.colors` is also accepted; the renderer resolves the
> id through the active token table and falls back to the literal
> string when no token matches.

The same substitution rule holds for `text_style`, `stroke_style`,
and `fill_style` references. These always accept either an inline
mapping or an id resolved through the corresponding token table.
This is what makes design-system substitution work uniformly across
the document.

---

## Symbols vs Components — when to use which

FrameGraph offers two reuse mechanisms. The schema enforces the
structural distinction at the model level (a `SymbolDef` is not a
`ComponentDef`), but choosing between them is the author's call.

**Use a Symbol when:**

- The reusable unit is a **free-form arrangement** of FrameGraph
  objects (rect + text + line + nested `use`, in any combination).
- Per-instance content lives in named text/value **slots**.
- Per-instance connection points are exposed as named **ports**.
- Styling lives **inside** the symbol's child objects (not on the
  symbol itself).

Symbols are SVG-`<use>`-style stamps. Authoring substrate.

**Use a Component when:**

- The reusable unit is a **styled product widget** (a card, a chip,
  a labelled box) with one well-defined geometry.
- Its visual identity (`fill`, `stroke`, `radius`, `text_style`)
  should swap as a unit via theme `variants`.
- Layout of slot content is **positional and uniform** across the
  `internal_layout` map, not free-form.

Components are React-style typed templates. Design-system surface.

**Rule of thumb:** if your reusable thing has more than one
rect/text pair or any nested `use`, it is a Symbol. If it is one
shape with variant-styling and slot-positioned text, it is a
Component.

---

## Layer ordering

`Layer.z` controls **inter-layer painter order**: layers are sorted
ascending by `z`, so higher `z` paints on top. Layers without `z`
sort as `z = 0`. Concretely:

```yaml
layers:
  - {id: bg, z: 0,  objects: [...]}     # painted first
  - {id: fg, z: 10, objects: [...]}     # painted on top
```

**Intra-layer order is list position.** `CommonFields` has no `z`
on individual objects. To control front/back inside a single layer,
reorder the list. To lift an object above a layer, move it into a
higher-`z` layer.

---

## Authoring utilities

These behaviors are implemented in the renderer; the schema does not
constrain them beyond accepting their input shapes.

### Lorem ipsum expansion

Any `text:` field accepts:

- `"lorem"` — expands to 30 words of deterministic lorem ipsum.
- `"lorem:N"` — expands to N words.

### Image placeholder

`type: image` with **any** of these triggers a placeholder render
(grey box with diagonal X lines + a dimension label):

- `placeholder: true` — **canonical** form.
- `href: "placeholder"` — DEPRECATED legacy form.
- `href` absent or empty — DEPRECATED legacy form.

### Debug boxes

In `scene.rendering_contract`:

```yaml
debug_boxes: true
```

Adds a `<g id="_debug_boxes">` overlay showing dashed outlines of
every object's declared box, color-coded by type:

| Color | Type |
|---|---|
| Orange | text, bullet_list |
| Green | image |
| Navy | container |
| Purple | use |
| Grey | all others |

### Overflow clipping

On any text style:

```yaml
overflow: clip
```

Wraps the text element in an SVG `<clipPath>` enforcing the declared
box as a hard boundary. Default is `visible`.

---

## Connector endpoints

`Endpoint` accepts three forms with escalating expressiveness:

1. **Literal coordinate:** `[x, y]`.
2. **Dot notation** (v1.4): `"object_id.port_name"`.
3. **Object form** with `object`, optional `port`, optional `side`,
   optional `offset`.

The `side` enum accepts both compass and screen aliases — `north =
top`, `south = bottom`, `east = right`, `west = left`. Both are
deliberately supported; pick the vocabulary that reads better in
context.

---

## Reserved fields

Some schema fields exist with single-value enums or stub semantics
because they reserve a future MAJOR-version expansion. Authors
should set them to the documented value or omit them.

- `scene.rendering_contract.coordinate_mode` — only `"absolute"` is
  implemented. `"relative"` and `"polar"` are reserved.
- `container.layout.kind` — `"stack"` is implemented. `"grid"` and
  `"row"` are forward-compatible reservations.

---

## Open property bags

`semantic.nodes[]` and `semantic.edges[]` accept arbitrary
user-defined keys beyond `id`/`type`/`label`/`from`/`to`. The schema
layer does not constrain those property values; their type and
meaning are defined by the consuming renderer or downstream tool.

A future MAJOR version may extend `node_types[T]` and
`edge_types[T]` with a `properties: { name: TypeRef }` map to
declare per-type property schemas the grammar can check. Until
then, treat the property bag as opaque and validate it in your own
pipeline.

---

## Deck-mode cascade

Token resolution for slides in a deck follows a layered chain:

```
library $theme tokens
  → deck.tokens
    → base slide tokens ($extends target)
      → this slide tokens
```

Each layer's values override the previous. The base slide is named
via `$extends: <slide-id>` on a child slide; only one level of
inheritance is supported.

**Layer merge:** within `visual.layers`, base layers are dict-keyed
by id. A child layer with the same id **replaces** the base layer.
A child layer with a new id **appends** after the base layers.

**Speaker notes:**

- Stored under `notes:` on each slide.
- Never written to SVG output.
- Exported to `notes.md` by `FrameGraphDeckRenderer.render_notes()`.

---

## Backward-compatibility notes

Per [PURPOSE.md](../../PURPOSE.md), v1.x backward compatibility is a
load-bearing constraint. Two places where the schema is more
permissive than the original EBNF documented:

- **`directionality`** on edge-type definitions accepts
  `bidirectional` in addition to `directed | undirected`.
  Production fixtures have used `bidirectional` since v1.x; the
  EBNF was wrong, not the fixtures.
- **`from` / `to`** on edge entries accept either a single id (the
  EBNF default) or a list of ids (multi-target / multi-source
  edges). Production fixtures use list-valued endpoints for
  cross-cutting control flows.
- **`SlotLayout.box_offset`** elements may be numbers, percent
  strings (`"100%"`), or `calc()` expressions
  (`"calc(100% - 16)"`). The renderer's `eval_length` resolves
  them at paint time.

---

## Validation gate behavior

`FrameGraphRenderer.__init__` and `FrameGraphDeckRenderer.__init__`
both validate the input when it carries `dsl: FrameGraph`. Inputs
without that marker pass through unvalidated — this is required so:

- Unit tests can construct `FrameGraphRenderer({})` for renderer-
  internal probing.
- The deck composer can pass intermediate slide-doc dicts that
  haven't yet been re-stamped with the marker.

Real FrameGraph documents always carry the marker per the schema.
Anything without it is by definition not a FrameGraph document, and
the gate correctly skips it.

---

## Where the executable contract lives

| Concern | File |
|---|---|
| Top-level document model | [framegraph/_schema.py — `Document`](../../framegraph/_schema.py) |
| Deck document model | [framegraph/_schema.py — `DeckDocument`](../../framegraph/_schema.py) |
| Object discriminated union | [framegraph/_schema.py — `KnownObject`](../../framegraph/_schema.py) |
| Plug-in fall-through type | [framegraph/_schema.py — `_UnknownObject`](../../framegraph/_schema.py) |
| Validation entry points | [framegraph/_schema.py — `validate_document`, `validate_deck`, `validate_object`](../../framegraph/_schema.py) |
| Renderer contract (Protocol) | [framegraph/_types.py — `RendererContext`](../../framegraph/_types.py) |
| Project purpose & invariants | [PURPOSE.md](../../PURPOSE.md) |

---

## History

- **2026-05-07** — Migrated from `GRAMMAR.ebnf` to Pydantic
  `framegraph._schema`. EBNF removed; this file salvages prose that
  doesn't survive JSON-Schema export. The byte-identical-SVG
  regression suite at
  [tests/integration/test_schema_migration.py](../../tests/integration/test_schema_migration.py)
  proves the migration changed nothing visible to renderers.
