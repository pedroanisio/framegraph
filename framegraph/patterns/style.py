"""Stylesheets — the framework's third orthogonal layer.

Patterns declare *structure* (zones with content_type, size, placement).
Themes declare *tokens* (colors, fonts, spacing). Stylesheets bind the
two: for every (content_type, size, placement) a zone might have, the
stylesheet declares which token-named typography, fills, strokes, and
treatments apply.

This separation is what makes patterns reusable. A deck of ten
patterns + one stylesheet + one theme renders as a coherent deck;
swap the stylesheet, swap the visual language; swap the theme, swap
the brand. Patterns themselves never change.

Resolution
----------

For one zone of one pattern, resolution proceeds:

  1. Walk `roles[]` in order. For each rule, check `match` against the
     zone's (content_type, size, placement.h, placement.v, role).
     A rule matches when *every* declared field matches. Omitted
     fields are wildcards. The first match wins.
  2. Resolve `typography` references through `text_styles`.
  3. Resolve `treatment` references through `treatments`.

The result is a fully-baked dict the emitter passes to FrameGraph
visual objects (with token names intact — the renderer's `color()`
and `text_style()` resolve those at draw time, against whichever
theme the deck loaded).

Public API
----------

- `Stylesheet`               — Pydantic model.
- `load_stylesheet(path)`    — load and validate a stylesheet YAML.
- `load_bundled_stylesheet`  — convenience for `framegraph/lib/styles/<id>.yml`.
- `resolve_zone_style(...)`  — resolve one zone's style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from framegraph._patterns import Anchor, PatternZone, RegionPlacement, RelativePlacement

__all__ = [
    "MatchSpec",
    "RoleRule",
    "Stylesheet",
    "load_bundled_stylesheet",
    "load_stylesheet",
    "resolve_zone_style",
]


# ─────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────


class MatchSpec(BaseModel):
    """A match predicate. Any omitted field is a wildcard."""

    model_config = ConfigDict(extra="forbid")
    content_type: str | None = None
    size: str | None = None
    h: str | None = None
    v: str | None = None
    placement_kind: Literal["anchor", "region", "relative", "fullbleed"] | None = None
    role: str | None = None


class RoleRule(BaseModel):
    """One row of the resolution table."""

    model_config = ConfigDict(extra="allow")
    match: MatchSpec
    # Anything else (typography, treatment, palette, fill_color, …) is
    # opaque to this layer — emitters consume it. Kept extra="allow"
    # so authors can add fields the emitters use without schema churn.


class Stylesheet(BaseModel):
    """A loaded, validated stylesheet."""

    model_config = ConfigDict(extra="allow")
    text_styles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    treatments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    roles: list[RoleRule] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────


_BUNDLED_DIR = Path(__file__).resolve().parent.parent / "lib" / "styles"


def load_stylesheet(path: Path | str) -> Stylesheet:
    """Load and validate a stylesheet YAML file."""
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    # Drop _meta — informational only.
    data.pop("_meta", None)
    return Stylesheet.model_validate(data)


def load_bundled_stylesheet(name: str = "default") -> Stylesheet:
    """Load a stylesheet bundled under `framegraph/lib/styles/<name>.yml`."""
    return load_stylesheet(_BUNDLED_DIR / f"{name}.yml")


# ─────────────────────────────────────────────────────────────────
# Resolver
# ─────────────────────────────────────────────────────────────────


def _placement_features(zone: PatternZone) -> dict[str, str | None]:
    """Extract h/v/kind features from a zone's placement."""
    p = zone.placement
    if isinstance(p, Anchor):
        if p.fullbleed:
            return {"placement_kind": "fullbleed", "h": None, "v": None}
        return {"placement_kind": "anchor", "h": p.h, "v": p.v}
    if isinstance(p, RegionPlacement):
        return {"placement_kind": "region", "h": None, "v": None}
    if isinstance(p, RelativePlacement):
        return {"placement_kind": "relative", "h": None, "v": None}
    return {"placement_kind": None, "h": None, "v": None}


def _matches(spec: MatchSpec, features: dict[str, Any]) -> bool:
    """True when every non-None field in `spec` equals the feature."""
    for field in ("content_type", "size", "h", "v", "placement_kind", "role"):
        want = getattr(spec, field)
        if want is None:
            continue
        if features.get(field) != want:
            return False
    return True


def _resolve_typography(typo: Any, text_styles: dict[str, dict[str, Any]]) -> Any:
    """Expand typography references into inline style dicts.

    Accepts:
      - a string token name → looked up in `text_styles`.
      - a dict — leaves dict-shape (for content_types like `metric`
        whose typography has multiple roles); each value is recursively
        resolved.
      - any other shape → returned unchanged.
    """
    if isinstance(typo, str):
        return dict(text_styles.get(typo, {}))
    if isinstance(typo, dict):
        return {k: _resolve_typography(v, text_styles) for k, v in typo.items()}
    return typo


def resolve_zone_style(
    zone: PatternZone,
    stylesheet: Stylesheet,
) -> dict[str, Any]:
    """Resolve the style for one zone against the stylesheet.

    Returns a fully-expanded style dict. Token names inside it
    (color/font references) are *not* resolved here — the renderer's
    theme-aware resolvers handle that downstream.

    Args:
        zone: The pattern zone (carries content_type, size, placement,
            role).
        stylesheet: The loaded stylesheet.

    Returns:
        A dict with at least `treatment`, `typography`, and any
        rule-declared extras. Empty dict when no rule matches (the
        emitter falls back to renderer defaults).
    """
    features: dict[str, Any] = {
        "content_type": zone.content_type,
        "size": zone.size,
        "role": zone.role,
        **_placement_features(zone),
    }

    matched: dict[str, Any] = {}
    for rule in stylesheet.roles:
        if _matches(rule.match, features):
            matched = rule.model_dump(exclude={"match"})
            break

    # Expand typography references.
    if "typography" in matched:
        matched["typography"] = _resolve_typography(matched["typography"], stylesheet.text_styles)

    # Expand treatment reference.
    treatment_name = matched.get("treatment")
    if isinstance(treatment_name, str):
        treatment_props = dict(stylesheet.treatments.get(treatment_name, {}))
        # Caller-supplied `treatment_props` field shouldn't pre-exist,
        # but if it does, the rule's overrides win.
        merged = dict(treatment_props)
        merged.update({k: v for k, v in matched.items() if k not in {"treatment", "typography"}})
        matched["treatment_props"] = treatment_props
        matched.update(merged)

    return matched
