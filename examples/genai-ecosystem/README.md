---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# Example — The Generative AI Ecosystem

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](../../DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

---

End-to-end example: a single bespoke slide rendered to SVG and PDF.
The deliverable in this folder is everything an AI agent needs to
**reproduce, modify, or use this slide as a template** for similar
hub-and-spoke ecosystem diagrams.

| File | Role |
|---|---|
| `genai-ecosystem.yml`  | YAML source — the document an agent edits |
| `genai-ecosystem.svg`  | Rendered SVG (1280 × 720 canvas, vector) |
| `genai-ecosystem.pdf`  | Rendered single-page PDF (raster, 300 DPI) |
| `README.md` (this file) | Walk-through + CLI commands |

The output:

![rendered slide](genai-ecosystem.svg)

---

## When to use this kind of example

Use it as a starting point when:

- The slide does **not** match a catalog pattern (run
  `framegraph patterns list --has-sidecar --json` to confirm).
- You need precise pixel control over a hub-and-spoke /
  ecosystem / matrix layout.
- You want to keep the document self-contained — no `$theme:`,
  no library, no deck wrapper.

If a catalog pattern does fit (SWOT, BMC, Communications Plan, etc.),
**prefer `framegraph patterns build` or a deck with `use:` /
`fill:`** instead. The catalog handles theming, layout, and
accessibility metadata for you. See [`AGENTS.md`](../../AGENTS.md)
for the decision tree.

---

## Reproduce in three commands

```sh
# 1. Render to SVG (always works)
framegraph render examples/genai-ecosystem/genai-ecosystem.yml \
    -o examples/genai-ecosystem/genai-ecosystem.svg

# 2. Render to SVG + PDF (requires the [pdf] extra: cairosvg + Pillow)
framegraph render examples/genai-ecosystem/genai-ecosystem.yml \
    -o examples/genai-ecosystem/genai-ecosystem.svg \
    --pdf

# 3. Render to SVG + 4K-wide PNG (also requires cairosvg)
framegraph render examples/genai-ecosystem/genai-ecosystem.yml \
    -o examples/genai-ecosystem/genai-ecosystem.svg \
    --4k
```

Expected output for command 2:

```
wrote examples/genai-ecosystem/genai-ecosystem.svg  (10.0 KB)
wrote examples/genai-ecosystem/genai-ecosystem.pdf  (249 KB, raster 300 DPI)
```

To install the optional PDF and 4K dependencies once:

```sh
pip install "framegraph[pdf]"           # cairosvg + Pillow → raster PDF, 4K PNG
pip install "framegraph[pdf-vector]"    # weasyprint + pypdf → vector PDF (selectable text)
```

For a vector PDF (selectable / searchable text):

```sh
framegraph render examples/genai-ecosystem/genai-ecosystem.yml \
    -o examples/genai-ecosystem/genai-ecosystem.svg \
    --pdf --vector
```

---

## How the YAML is structured

`genai-ecosystem.yml` is a standard FrameGraph document:

```yaml
dsl: FrameGraph
version: 1.5
kind: hybrid-semantic-visual-diagram

scene:    {id, name, description, canvas, rendering_contract}
semantic: {ontology, nodes, edges}        # typed graph layer
visual:   {tokens, layers}                 # rendered objects
```

The slide is composed in **six layers**, drawn back-to-front:

| z | layer | Purpose |
|---|---|---|
| 0 | `bg` | Page background |
| 1 | `connectors` | Dashed lines from hub to pillars and use-cases (drawn before cards so they tuck under) |
| 2 | `title` | "The Generative AI Ecosystem" + accent underline |
| 3 | `left_pillar`, `right_pillar`, `use_cases` | The five surrounding card groups |
| 4 | `hub` | Central blue GenAI rectangle (drawn last so connectors disappear under it) |

Tokens (`visual.tokens`) define the colors, fonts, text styles, and
stroke styles once at the top, so the geometry blocks reference
names like `brand`, `panel_bg`, `card_thin` rather than repeating
hex codes inline.

Every node-bearing card is `bind:`-ed to a corresponding `semantic.nodes`
entry, so the document doubles as a small typed graph. Connectors
and decorative chrome are explicitly marked `decorative: true` to
opt out of the bind-required check.

---

## Modifying the slide

Common edits and where to make them:

| Change | Edit |
|---|---|
| Rename the slide | `scene.name`, `visual.layers.title.objects[0].text` |
| Change brand color | `visual.tokens.colors.brand` (one place; underline + hub fill + accents follow) |
| Add a sixth use-case card | Append to `visual.layers.use_cases.objects` and add a `connector` entry in `visual.layers.connectors.objects` |
| Resize the canvas | `scene.canvas.size` (then re-flow the boxes — there is no auto-layout for this bespoke geometry) |
| Highlight a different bottom card | Move the `brand_soft` fill / `uc_label_b` style from `uc3_*` (Media Creation) to another card |

After any edit, re-run the `framegraph render` command above.

---

## Validation

The document passes the bundled regression suite:

```sh
python -m pytest tests/integration/test_render_fixtures.py -q
```

To verify the YAML alone (no render):

```sh
python -c "
import yaml; from framegraph import FrameGraphRenderer
doc = yaml.safe_load(open('examples/genai-ecosystem/genai-ecosystem.yml'))
r = FrameGraphRenderer(doc)
for w in r.validate():
    print('warning:', w)
print('ok' if not r.warnings else 'render warnings present')
"
```

---

## See also

- [`../../AGENTS.md`](../../AGENTS.md) — agent-oriented entry point.
- [`../../docs/AUTHORING-FILLS.md`](../../docs/AUTHORING-FILLS.md) —
  the fill / sidecar workflow for catalog patterns.
- [`../../static/fixture/decks/framegraph-overview-deck.yml`](../../static/fixture/decks/framegraph-overview-deck.yml) —
  a 12-slide deck composed entirely from bespoke `visual.layers`
  (no patterns), useful as a longer reference.
- [`../../static/fixture/faz-ai-manifesto-deck.yml`](../../static/fixture/faz-ai-manifesto-deck.yml) —
  a deck mixing bespoke and pattern-composed slides.
