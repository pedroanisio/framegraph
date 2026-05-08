"""Pattern fill — typed payload contract for slide patterns.

A *fill* is the content an agent supplies to instantiate one slide
from a catalog pattern. Each pattern declares zones (named regions
with `content_type`), and the fill must supply one entry per role.

Phase 1 scope (per `docs/ROADMAP-FILL-RENDER.md`):

- `PatternFill` — wraps a pattern_id + per-role content dict;
  validates against the pattern's derived fill schema.
- `derive_default_fill_schema(pattern)` — returns a dynamically-
  built Pydantic model whose fields are the pattern's roles, each
  typed to the default Pydantic shape for its `content_type`.
- `load_fill(pattern_id, payload)` — convenience resolver that
  looks up the pattern in the bundled catalog and validates the
  payload against it.
- `MissingContentTypeError` — raised when a pattern has any zone
  without a `content_type`. Phase 1 does not auto-fall-back; the
  34% un-annotated tail must be curated (Phase 6) or have a
  sidecar override (Phase 2+).

Default content shapes per `ContentType`:

| content_type | Default Pydantic shape                        |
|--------------|-----------------------------------------------|
| `title_body` | ``{title: str, body: str | None}``           |
| `metric`     | ``{label: str, value: str, trend: str | None}`` |
| `list_items` | ``list[str]``                                 |
| `key_value`  | ``dict[str, str]``                            |
| `comparison` | ``{left: str, right: str}``                  |
| `chart_data` | ``{type: str, series: list[dict]}``           |
| `table_data` | ``{headers: list[str], rows: list[list[str]]}`` |
| `image`      | ``{src: str, alt: str | None}``              |
| `axis_label` | ``{title: str, units: str | None}``          |
| `decorative` | ``None`` (no fill required; kept for symmetry)  |

Sidecars (Phase 2+, in `static/refs/fills/<id>.yml`) override these
defaults per pattern when a richer shape is needed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from framegraph._patterns import (
    ContentType,
    PatternCatalog,
    SlidePattern,
    load_pattern_catalog,
)

__all__ = [
    "MissingContentTypeError",
    "PatternFill",
    "derive_default_fill_schema",
    "load_fill",
]


# ─────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────


class MissingContentTypeError(ValueError):
    """Raised when a pattern has zones without `content_type`.

    Phase 1 hard-requires every zone to declare a content_type.
    Patterns with un-annotated zones cannot have a default fill
    schema derived; they must be curated (Phase 6) or have a
    per-pattern sidecar (Phase 2+).
    """


# ─────────────────────────────────────────────────────────────────
# Default content shapes — one Pydantic model per ContentType
# ─────────────────────────────────────────────────────────────────


class TitleBodyContent(BaseModel):
    """Default shape for `content_type == "title_body"` zones."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1)
    body: str | None = None


class MetricContent(BaseModel):
    """Default shape for `content_type == "metric"` zones.

    `value` is a string so callers can pass formatted numbers
    ("$2.4M", "+12%") without coercion. Numeric typing belongs in
    a richer sidecar, not the default.
    """

    model_config = ConfigDict(extra="forbid")
    label: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    trend: str | None = None


class ComparisonContent(BaseModel):
    """Default shape for `content_type == "comparison"` zones."""

    model_config = ConfigDict(extra="forbid")
    left: str = Field(..., min_length=1)
    right: str = Field(..., min_length=1)


class ChartDataContent(BaseModel):
    """Default shape for `content_type == "chart_data"` zones.

    Loose by design: chart subtypes vary too much for one rigid
    shape. ``type`` names the chart (``"bar"``, ``"line"``,
    ``"pie"``), ``series`` carries arbitrary per-series dicts.
    Sidecars tighten this per-pattern when needed.
    """

    model_config = ConfigDict(extra="forbid")
    type: str = Field(..., min_length=1)
    series: list[dict[str, Any]] = Field(default_factory=list)


class TableDataContent(BaseModel):
    """Default shape for `content_type == "table_data"` zones."""

    model_config = ConfigDict(extra="forbid")
    headers: list[str] = Field(..., min_length=1)
    rows: list[list[str]] = Field(default_factory=list)


class ImageContent(BaseModel):
    """Default shape for `content_type == "image"` zones."""

    model_config = ConfigDict(extra="forbid")
    src: str = Field(..., min_length=1)
    alt: str | None = None


class AxisLabelContent(BaseModel):
    """Default shape for `content_type == "axis_label"` zones."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1)
    units: str | None = None


# Map each ContentType literal to its default content type.
# `key_value` and `list_items` use generic typing rather than a
# wrapper model. `decorative` accepts None.
_DEFAULT_TYPES: dict[ContentType, Any] = {
    "title_body": TitleBodyContent,
    "metric": MetricContent,
    "list_items": list[str],
    "key_value": dict[str, str],
    "comparison": ComparisonContent,
    "chart_data": ChartDataContent,
    "table_data": TableDataContent,
    "image": ImageContent,
    "axis_label": AxisLabelContent,
    "decorative": type(None),
}


# ─────────────────────────────────────────────────────────────────
# Default fill-schema derivation
# ─────────────────────────────────────────────────────────────────


def derive_default_fill_schema(pattern: SlidePattern) -> type[BaseModel]:
    """Build a Pydantic model whose fields are this pattern's roles.

    Each field is typed to the default Pydantic shape for its zone's
    ``content_type``. The returned model has ``extra="forbid"`` so
    payloads with unknown roles fail loudly.

    Args:
        pattern: A `SlidePattern` whose zones all carry a
            ``content_type`` annotation.

    Returns:
        A dynamically-created Pydantic ``BaseModel`` subclass. The
        class name is ``"DefaultFill_p{id}"``; instantiate it via
        ``Model.model_validate(payload)``.

    Raises:
        MissingContentTypeError: If any zone in the pattern lacks a
            ``content_type``. The error message names every offender.
    """
    missing = [z.role for z in pattern.zones if z.content_type is None]
    if missing:
        raise MissingContentTypeError(
            f"pattern {pattern.id} ({pattern.name!r}) has {len(missing)} zone(s) "
            f"without content_type: {missing}. Annotate via "
            f"scripts/annotate_content_types.py or add a sidecar in "
            f"static/refs/fills/{pattern.id:03d}-*.yml"
        )

    fields: dict[str, Any] = {}
    for z in pattern.zones:
        ct = z.content_type
        # ct is non-None here (checked above); type checker can't see
        # the guard through the comprehension, so assert for clarity.
        assert ct is not None
        py_type = _DEFAULT_TYPES[ct]
        # Required field — Field(...) triggers Pydantic's "required"
        # behavior; for `decorative` we still require the key but
        # only `None` is a valid value (per type(None)).
        fields[z.role] = (py_type, Field(...))

    Model = create_model(
        f"DefaultFill_p{pattern.id}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return Model


# ─────────────────────────────────────────────────────────────────
# PatternFill — the public payload wrapper
# ─────────────────────────────────────────────────────────────────


class PatternFill(BaseModel):
    """A validated content payload for one pattern.

    Attributes:
        pattern_id: The catalog id of the pattern being filled.
            Must match the pattern resolved from `_pattern`.
        content: A Pydantic model instance (the dynamically-derived
            fill schema for the pattern), with one attribute per
            zone role. Created at validation time; callers receive
            it as a typed object (not a dict).

    Construction:
        Validate via ``PatternFill.model_validate({"pattern_id": N,
        "content": {...}, "_pattern": <SlidePattern>})``. The
        ``_pattern`` field is the resolved pattern (passed in by
        `load_fill` or by callers who already have one); it's
        consumed during validation and not stored.

        The convenience function `load_fill(pattern_id, payload)`
        looks up the pattern in the bundled catalog and skips the
        ``_pattern`` plumbing.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    pattern_id: int = Field(..., gt=0)
    content: Any  # typed by validator below

    @model_validator(mode="before")
    @classmethod
    def _validate_against_pattern(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        pattern: SlidePattern | None = data.pop("_pattern", None)
        if pattern is None:
            # No pattern handed in — defer; caller must supply one
            # via load_fill or pass _pattern explicitly. Returning
            # data here makes the model unusable but doesn't crash;
            # the missing `content` typing surfaces at field-level.
            return data
        if data.get("pattern_id") != pattern.id:
            raise ValueError(
                f"pattern_id {data.get('pattern_id')} in payload does not "
                f"match resolved pattern id {pattern.id}"
            )
        Model = derive_default_fill_schema(pattern)
        # Validate the content against the derived model and replace
        # the dict with the typed instance.
        data["content"] = Model.model_validate(data.get("content") or {})
        return data


# ─────────────────────────────────────────────────────────────────
# Catalog-resolving convenience
# ─────────────────────────────────────────────────────────────────


_CATALOG: PatternCatalog | None = None


def _catalog() -> PatternCatalog:
    """Lazy-load the bundled catalog (cached for repeat calls)."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_pattern_catalog()
    return _CATALOG


def load_fill(pattern_id: int, payload: dict[str, Any]) -> PatternFill:
    """Resolve a pattern by id and validate a payload against it.

    Args:
        pattern_id: The catalog id of the pattern to fill.
        payload: A mapping from zone role → content. The content
            shape per role is dictated by the zone's
            ``content_type`` (or by a sidecar override, Phase 2+).

    Returns:
        A validated `PatternFill`.

    Raises:
        KeyError: If no pattern with that id exists in the catalog.
        pydantic.ValidationError: If the payload doesn't satisfy
            the derived schema (missing roles, unknown roles, wrong
            content shape).
        MissingContentTypeError: If the pattern has any zones
            without ``content_type``. Sidecar override required
            (Phase 2+).
    """
    pattern = _catalog().get(pattern_id)
    return PatternFill.model_validate(
        {"pattern_id": pattern_id, "content": payload, "_pattern": pattern}
    )
