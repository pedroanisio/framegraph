"""Anti-drift gate: the schema reference must stay COMPLETE.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW). A documentation page claiming to
be "the complete syntax" is worthless the moment a new object type or
model lands undocumented. This gate makes completeness an enforced
invariant, not a hope: it derives the authoritative model/type set
structurally from the document roots (`Document` / `DeckDocument`) and
fails the build if the generated Schema reference omits any of it —
every object ``type`` literal and every model reachable from the roots
must appear on the generated page.
"""

from __future__ import annotations

import re
import typing

import pytest
from pydantic import BaseModel

import framegraph._schema as schema_mod
from framegraph._docsite.generate import generate_pages
from framegraph.docs import build_catalog, build_schema_models

DATE = "2026-01-01"


def _authoritative_object_types() -> set[str]:
    """Every object ``type`` literal declared by a schema model."""
    out: set[str] = set()
    for obj in vars(schema_mod).values():
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            field = obj.model_fields.get("type")
            if field is not None:
                out |= {a for a in typing.get_args(field.annotation) if isinstance(a, str)}
    return out


@pytest.fixture(scope="module")
def page() -> str:
    return generate_pages(build_catalog(), DATE)["reference/schema.md"]


class TestSchemaReferenceCompleteness:
    """The generated reference covers the full document-model surface."""

    def test_every_object_type_is_documented(self, page: str) -> None:
        """Every `type:` literal names its model on the page."""
        type_map = build_schema_models()["object_types"]
        # The structural enumeration must itself cover every type literal.
        missing_from_map = _authoritative_object_types() - set(type_map)
        assert not missing_from_map, f"types absent from catalog map: {missing_from_map}"
        # …and every mapped model must have a section on the page.
        missing = [m for m in type_map.values() if f"## `{m}`" not in page]
        assert not missing, f"object-type models missing from reference: {missing}"

    def test_every_document_model_is_documented(self, page: str) -> None:
        """Every model in the `$defs` closure has a section on the page."""
        documented = set(re.findall(r"^## `([^`]+)`", page, re.M))
        enumerated = {m["name"] for m in build_schema_models()["models"]}
        missing = enumerated - documented
        assert not missing, f"models enumerated but not rendered: {sorted(missing)}"

    def test_type_index_lists_every_type(self, page: str) -> None:
        type_map = build_schema_models()["object_types"]
        missing = [t for t in type_map if f"`{t}`" not in page]
        assert not missing, f"object types missing from page: {missing}"
