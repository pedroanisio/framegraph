"""Unit tests for `framegraph.docs` — the machine-readable API tutorial.

The catalog is consumed by LLM agents that need to learn the
framegraph public API in one read. Every public name in
`__all__` of every public module must appear, with its docstring,
signature, and (for Pydantic models) its JSON Schema.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from framegraph.docs import build_catalog, render_catalog_json


# ─────────────────────────────────────────────────────────────────
# Catalog shape
# ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return build_catalog()


class TestCatalogShape:
    """Structural invariants the JSON output must satisfy."""

    def test_top_level_keys(self, catalog: dict[str, Any]) -> None:
        assert set(catalog) >= {"schema_version", "package", "modules"}

    def test_schema_version_is_semver(self, catalog: dict[str, Any]) -> None:
        v = catalog["schema_version"]
        assert isinstance(v, str)
        parts = v.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_package_metadata(self, catalog: dict[str, Any]) -> None:
        pkg = catalog["package"]
        assert pkg["name"] == "framegraph"
        assert isinstance(pkg["version"], str)

    def test_modules_is_keyed_by_import_path(self, catalog: dict[str, Any]) -> None:
        mods = catalog["modules"]
        assert isinstance(mods, dict)
        # Every key must look like an import path
        for k in mods:
            assert k.startswith("framegraph"), k

    def test_each_module_has_overview_and_symbols(
        self, catalog: dict[str, Any]
    ) -> None:
        for path, mod in catalog["modules"].items():
            assert isinstance(mod.get("docstring"), str), path
            assert isinstance(mod.get("symbols"), list), path


# ─────────────────────────────────────────────────────────────────
# Public-surface coverage
# ─────────────────────────────────────────────────────────────────


class TestPublicSurfaceCoverage:
    """Every name exported via `__all__` must appear in the catalog."""

    EXPECTED_MODULES = [
        "framegraph",
        "framegraph._schema",
        "framegraph._uml",
        "framegraph.uml",
        "framegraph.layout",
    ]

    def test_all_public_modules_present(self, catalog: dict[str, Any]) -> None:
        for m in self.EXPECTED_MODULES:
            assert m in catalog["modules"], f"missing module: {m}"

    @pytest.mark.parametrize(
        "module,expected_names",
        [
            ("framegraph", {"FrameGraphRenderer", "FrameGraphLibrary", "FrameGraphDeckRenderer"}),
            ("framegraph.uml", {"ClassDiagramOptions", "ComposedDiagram", "compose_class_diagram"}),
            ("framegraph.layout", {"LayoutResult", "SugiyamaConfig", "sugiyama_layout"}),
        ],
    )
    def test_module_exports_are_listed(
        self,
        catalog: dict[str, Any],
        module: str,
        expected_names: set[str],
    ) -> None:
        symbol_names = {s["name"] for s in catalog["modules"][module]["symbols"]}
        missing = expected_names - symbol_names
        assert not missing, f"{module} missing exports: {missing}"

    def test_uml_ontology_exports_complete(self, catalog: dict[str, Any]) -> None:
        """All `_uml.py` exports must surface — this is the UML contract."""
        names = {s["name"] for s in catalog["modules"]["framegraph._uml"]["symbols"]}
        # Spot-check the model classes and the top-level entry point
        assert {
            "UMLClass",
            "UMLClassDiagramModel",
            "UMLAssociation",
            "validate_class_diagram",
        }.issubset(names)


# ─────────────────────────────────────────────────────────────────
# Per-symbol fields
# ─────────────────────────────────────────────────────────────────


class TestSymbolEntries:
    """Each entry must carry the fields an LLM agent needs."""

    def _find(self, catalog: dict[str, Any], module: str, name: str) -> dict[str, Any]:
        for s in catalog["modules"][module]["symbols"]:
            if s["name"] == name:
                return s
        raise AssertionError(f"{module}.{name} not found")

    def test_class_entry_carries_signature_and_docstring(
        self, catalog: dict[str, Any]
    ) -> None:
        s = self._find(catalog, "framegraph._uml", "UMLClass")
        assert s["kind"] == "class"
        assert isinstance(s["docstring"], str) and s["docstring"].strip()
        assert "(" in s["signature"] and ")" in s["signature"]

    def test_pydantic_model_carries_json_schema(self, catalog: dict[str, Any]) -> None:
        """Pydantic v2 models expose `model_json_schema()` — surface it."""
        s = self._find(catalog, "framegraph._uml", "UMLClass")
        schema = s.get("json_schema")
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert "id" in schema["properties"]
        assert "name" in schema["properties"]

    def test_function_entry_carries_signature(self, catalog: dict[str, Any]) -> None:
        s = self._find(catalog, "framegraph._uml", "validate_class_diagram")
        assert s["kind"] == "function"
        assert "data" in s["signature"]
        assert "UMLClassDiagramModel" in s["signature"]

    def test_docstring_sections_parsed(self, catalog: dict[str, Any]) -> None:
        """Args/Returns/Raises sections of Google-style docstrings are extracted."""
        s = self._find(catalog, "framegraph._uml", "validate_class_diagram")
        sections = s.get("docstring_sections", {})
        assert "Args" in sections
        assert "Returns" in sections
        assert "Raises" in sections


# ─────────────────────────────────────────────────────────────────
# JSON serialization
# ─────────────────────────────────────────────────────────────────


class TestJsonRendering:
    """`render_catalog_json` produces RFC 8259 JSON ingestible by any LLM."""

    def test_render_returns_valid_json(self, catalog: dict[str, Any]) -> None:
        text = render_catalog_json(catalog)
        round_trip = json.loads(text)
        assert round_trip["package"]["name"] == "framegraph"

    def test_render_is_deterministic(self, catalog: dict[str, Any]) -> None:
        """Two renders of the same catalog produce byte-identical output.

        Determinism is required for diff-based drift detection in CI.
        """
        a = render_catalog_json(catalog)
        b = render_catalog_json(catalog)
        assert a == b

    def test_render_keys_are_sorted(self, catalog: dict[str, Any]) -> None:
        """Sort keys so two builds with different dict-ordering still match."""
        text = render_catalog_json(catalog)
        # Top-level keys should be alphabetically ordered
        loaded = json.loads(text)
        # And the JSON serializer must have used sort_keys=True
        # (verify by re-serializing with sort_keys and comparing)
        canonical = json.dumps(loaded, sort_keys=True, indent=2, ensure_ascii=False)
        assert text.strip() == canonical.strip()
