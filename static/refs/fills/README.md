---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-07"
---

# Pattern fill sidecars

This directory holds **per-pattern fill schemas** that override the
defaults derived from `PatternZone.content_type`.

## When to add a sidecar

The default fill schema (built from `content_type`) covers most cases.
Add a sidecar **only when** a pattern needs:

1. **Richer content per zone** than the default offers.
   Example: BMC's `revenue_streams` should be
   `list[{label, metric}]`, not the default `list[str]`.
2. **A zone marked optional** (default treats every zone as required).
3. **A custom validator** (e.g. cross-zone constraints).

## Filename convention

```
<id_zero_padded>-<slug>.yml
```

Examples:

```
001-title-slide.yml
044-business-model-canvas.yml
276-claim-evidence-reasoning-slide.yml
```

The 3-digit zero-padded id keeps `ls` sorted by id; the slug is the
catalog name lowercased with spaces → hyphens.

## File format (Phase 2 will formalize)

```yaml
pattern_id: 44
zones:
  revenue_streams:
    type: list
    item_type: object
    item_fields:
      label: {type: string, required: true}
      metric: {type: string, required: true}
  # ... only zones whose schema differs from the default need entries
example_fill:
  revenue_streams:
    - {label: "Subscriptions", metric: "$2.4M"}
    - {label: "Services",      metric: "$0.8M"}
  # ... other zones can use defaults
```

A pattern with no sidecar uses the default content_type-derived
schema for every zone.

## Validation

Sidecars are validated by `scripts/validate_fills.py` (Phase 2).
The Pydantic models in `framegraph.patterns.fill` consume them at
runtime via `load_fill(pattern_id, payload)`.

## Coverage status

- **Phase 1 (current)**: 0 sidecars. All patterns use defaults.
- **Phase 2**: BMC (#44) gets the first sidecar as the proof.
- **Phase 6**: top-15 highest-leverage patterns get sidecars; the
  rest stay on defaults unless rendering surfaces a need.

See [`docs/ROADMAP-FILL-RENDER.md`](../../../docs/ROADMAP-FILL-RENDER.md)
for the full phased plan.
