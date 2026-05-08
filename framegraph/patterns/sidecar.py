"""Sidecar fill schemas — per-pattern overrides of default content shapes.

A sidecar YAML file declares richer per-zone fill shapes than the
content_type defaults provide. For example, BMC's `revenue_streams`
(content_type=`list_items`, default `list[str]`) is more useful as
`list[{label, metric}]` — the sidecar declares that override.

Phase 2 sidecar mini-DSL (v1):

  pattern_id: <int>
  zones:
    <role>:
      item_kind: object | string  # for list_items zones
      item_fields:                # required when item_kind == object
        <field_name>:
          type: string            # only `string` supported in v1
          required: true | false
  example_fill:                   # optional but recommended
    <role>: <fill content matching the override or default shape>

Anything richer (numeric types, nested objects, cross-zone
constraints) waits for later phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from framegraph._patterns import SlidePattern
from framegraph.patterns.fill import (
    _DEFAULT_TYPES,
    MissingContentTypeError,
)

__all__ = [
    "BMC_SIDECAR_PATH",
    "PatternFillSidecar",
    "SidecarFieldSpec",
    "SidecarZoneOverride",
    "derive_fill_schema_with_sidecar",
    "load_sidecar",
]


# Path to the BMC sidecar — the Phase 2 proof.
BMC_SIDECAR_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "static"
    / "refs"
    / "fills"
    / "044-business-model-canvas.yml"
)


# ─────────────────────────────────────────────────────────────────
# Sidecar schema (Pydantic)
# ─────────────────────────────────────────────────────────────────


class SidecarFieldSpec(BaseModel):
    """A single field declaration inside a sidecar object item.

    Phase 2 supports only ``type: string`` and a ``required`` flag.
    Numeric / nested / unioned types are deferred to later phases.
    """

    model_config = ConfigDict(extra="forbid")
    type: Literal["string"] = "string"
    required: bool = True


class SidecarZoneOverride(BaseModel):
    """Per-zone override spec.

    ``item_kind`` selects between a flat list of strings (the
    default for `list_items` content_type — leave the sidecar
    silent for that zone) and a list of structured objects whose
    fields are declared in ``item_fields``.
    """

    model_config = ConfigDict(extra="forbid")
    item_kind: Literal["object", "string"]
    item_fields: dict[str, SidecarFieldSpec] | None = None

    @model_validator(mode="after")
    def _validate_object_requires_fields(self) -> SidecarZoneOverride:
        if self.item_kind == "object" and not self.item_fields:
            raise ValueError("item_kind=object requires `item_fields` to be set")
        if self.item_kind == "string" and self.item_fields:
            raise ValueError("item_kind=string does not accept `item_fields`")
        return self


class PatternFillSidecar(BaseModel):
    """One pattern's sidecar fill spec.

    Attributes:
        pattern_id: The catalog id this sidecar overrides.
        zones: Per-zone overrides, keyed by role. Zones not listed
            here keep their content_type-derived default shape.
        example_fill: Optional example payload that should validate
            against the effective (default + overrides) schema for
            the pattern. Used by `scripts/validate_fills.py` and by
            tests as a round-trip contract.
    """

    model_config = ConfigDict(extra="forbid")
    pattern_id: int = Field(..., gt=0)
    zones: dict[str, SidecarZoneOverride] = Field(default_factory=dict)
    example_fill: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────


def load_sidecar(path: Path | str) -> PatternFillSidecar:
    """Load and validate a sidecar YAML file.

    Args:
        path: Path to a sidecar YAML.

    Returns:
        A validated `PatternFillSidecar`.

    Raises:
        FileNotFoundError: If the path does not exist.
        pydantic.ValidationError: If the YAML doesn't satisfy the
            sidecar schema.
    """
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return PatternFillSidecar.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Effective fill-schema builder (default + sidecar overrides)
# ─────────────────────────────────────────────────────────────────


def _build_object_item_model(role: str, override: SidecarZoneOverride) -> type[BaseModel]:
    """Construct a Pydantic model for one object-shaped list item."""
    assert override.item_kind == "object"
    assert override.item_fields is not None
    fields: dict[str, Any] = {}
    for name, spec in override.item_fields.items():
        # v1 only supports type=string; required from the spec.
        py_type = str
        if spec.required:
            fields[name] = (py_type, Field(...))
        else:
            fields[name] = (py_type | None, None)
    return create_model(
        f"Item_{role}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def derive_fill_schema_with_sidecar(
    pattern: SlidePattern,
    sidecar: PatternFillSidecar,
) -> type[BaseModel]:
    """Build a fill-schema Pydantic model honoring sidecar overrides.

    For each zone:

    - If the sidecar declares an override for that role, use the
      override's shape (currently only `list_items` zones with
      object-typed items are supported).
    - Otherwise, use the default shape derived from the zone's
      `content_type`.

    Args:
        pattern: The catalog pattern being filled.
        sidecar: The pattern's sidecar (must declare the same
            ``pattern_id``).

    Returns:
        A dynamically-created Pydantic model with one field per
        zone role and ``extra="forbid"``.

    Raises:
        ValueError: If the sidecar's pattern_id does not match the
            pattern's id.
        MissingContentTypeError: If a zone has no content_type and
            no sidecar override either.
        KeyError: If the sidecar references a role not present in
            the pattern.
    """
    if sidecar.pattern_id != pattern.id:
        raise ValueError(
            f"sidecar pattern_id {sidecar.pattern_id} does not match pattern id {pattern.id}"
        )

    pattern_roles = {z.role for z in pattern.zones}
    unknown = set(sidecar.zones) - pattern_roles
    if unknown:
        raise KeyError(
            f"sidecar references unknown roles for pattern {pattern.id}: {sorted(unknown)}"
        )

    fields: dict[str, Any] = {}
    for z in pattern.zones:
        override = sidecar.zones.get(z.role)
        if override is not None:
            # Sidecar wins.
            if override.item_kind == "string":
                py_type: Any = list[str]
            else:  # object
                # `_build_object_item_model` returns a Pydantic model
                # built at runtime; mypy can't see it as a type, so
                # we subscribe `list[]` via `__class_getitem__` to
                # avoid the static valid-type check on `list[Item]`.
                Item = _build_object_item_model(z.role, override)
                py_type = list.__class_getitem__(Item)
            fields[z.role] = (py_type, Field(...))
            continue

        # No override — fall back to default shape from content_type.
        ct = z.content_type
        if ct is None:
            raise MissingContentTypeError(
                f"pattern {pattern.id} ({pattern.name!r}): zone "
                f"{z.role!r} has no content_type and no sidecar "
                f"override; cannot derive fill shape"
            )
        fields[z.role] = (_DEFAULT_TYPES[ct], Field(...))

    return create_model(
        f"FillWithSidecar_p{pattern.id}",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
