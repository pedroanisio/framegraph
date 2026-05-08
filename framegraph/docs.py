"""Machine-readable API tutorial catalog.

Walks every name in the `__all__` of every public module of the
`framegraph` package and emits a JSON catalog designed for LLM
agents to learn the public API in one read. Each entry carries:

- the symbol's qualified name and kind (class / function / type alias),
- a `signature` rendered from `inspect.signature` (or a synthesized
  one for Pydantic models),
- the full docstring plus a section-parsed view (Args/Returns/Raises/
  Examples) for Google-style docstrings,
- for Pydantic models, the full `model_json_schema()` so an agent can
  generate valid input documents without reading source.

The output is deterministic (sorted keys) so CI drift checks reduce
to a byte-level diff.

Public surface
--------------
- `build_catalog()` — returns the catalog as a Python dict.
- `render_catalog_json(catalog)` — returns the catalog as JSON text.
- `CATALOG_SCHEMA_VERSION` — semver of the catalog format itself,
  bumped when the shape changes.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
from typing import Any

from pydantic import BaseModel

__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "build_catalog",
    "render_catalog_json",
]


CATALOG_SCHEMA_VERSION = "1.0.0"
"""Semver of the catalog JSON shape. Bump major when consumers must adapt."""


# Modules whose `__all__` defines the public API surface. Order is
# the order they appear in the catalog (deterministic).
_PUBLIC_MODULES: tuple[str, ...] = (
    "framegraph",
    "framegraph._schema",
    "framegraph._uml",
    "framegraph._patterns",
    "framegraph.uml",
    "framegraph.layout",
)


# ─────────────────────────────────────────────────────────────────
# Docstring section parser (Google style)
# ─────────────────────────────────────────────────────────────────


_SECTION_RE = re.compile(
    r"^(Args|Arguments|Returns|Yields|Raises|Notes|Note|Examples|Example|"
    r"Attributes|See Also|Warnings|Warning):\s*$"
)


def _parse_docstring_sections(doc: str) -> dict[str, str]:
    """Split a Google-style docstring into named sections.

    Returns a mapping from section title (e.g. ``"Args"``) to the
    section body as a single string. The leading summary paragraph
    (before any section heading) is **not** included — callers can
    use the original docstring for that.
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in inspect.cleandoc(doc).splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            current = m.group(1)
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).rstrip() for k, v in sections.items()}


# ─────────────────────────────────────────────────────────────────
# Symbol introspection
# ─────────────────────────────────────────────────────────────────


def _signature(obj: Any) -> str:
    """Render a one-line signature for a class or function.

    Type aliases (`X = A | B`, `typing.Literal`, `typing.Annotated`,
    etc.) have no callable signature; we fall back to their string
    representation so the catalog still surfaces the alias body.
    """
    name: str | None = getattr(obj, "__name__", None)
    if name is None:
        # Type aliases — render the body, e.g. ``"UMLClass | UMLInterface"``.
        return str(obj)
    try:
        return f"{name}{inspect.signature(obj)}"
    except (TypeError, ValueError):
        return name


def _kind(obj: Any) -> str:
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj) or inspect.isbuiltin(obj):
        return "function"
    return "type_alias"


def _pydantic_schema(obj: Any) -> dict[str, Any] | None:
    """Return the JSON Schema for a Pydantic v2 model, or None."""
    if not inspect.isclass(obj):
        return None
    if not issubclass(obj, BaseModel):
        return None
    try:
        return obj.model_json_schema()
    except Exception:  # pragma: no cover — Pydantic raises on bad models
        return None


def _symbol_entry(module_name: str, name: str, obj: Any) -> dict[str, Any]:
    doc = inspect.getdoc(obj) or ""
    entry: dict[str, Any] = {
        "name": name,
        "qualname": f"{module_name}.{name}",
        "kind": _kind(obj),
        "signature": _signature(obj),
        "docstring": doc,
        "docstring_sections": _parse_docstring_sections(doc) if doc else {},
    }
    schema = _pydantic_schema(obj)
    if schema is not None:
        entry["json_schema"] = schema
    return entry


def _module_entry(module_name: str) -> dict[str, Any]:
    mod = importlib.import_module(module_name)
    exports = getattr(mod, "__all__", None)
    if not exports:
        # Fall back to public names (those not starting with `_`).
        exports = [n for n in dir(mod) if not n.startswith("_")]
    symbols = []
    for name in exports:
        obj = getattr(mod, name, None)
        if obj is None:
            continue
        symbols.append(_symbol_entry(module_name, name, obj))
    # Stable order: alphabetical by symbol name.
    symbols.sort(key=lambda s: s["name"])
    return {
        "name": module_name,
        "docstring": inspect.getdoc(mod) or "",
        "symbols": symbols,
    }


# ─────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────


def build_catalog() -> dict[str, Any]:
    """Build the catalog as a Python dict.

    The returned mapping is plain JSON-serializable types (``dict``,
    ``list``, ``str``, ``int``, ``bool``, ``None``). No Pydantic
    models or other live objects appear.

    Returns:
        Catalog with keys ``schema_version``, ``package``, ``modules``.
        ``modules`` is a dict keyed by import path.
    """
    from framegraph import __version__

    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "package": {"name": "framegraph", "version": __version__},
        "modules": {m: _module_entry(m) for m in _PUBLIC_MODULES},
    }


def render_catalog_json(catalog: dict[str, Any]) -> str:
    """Render the catalog to deterministic JSON text.

    Keys are sorted alphabetically so two builds against the same
    source produce byte-identical output — required for CI drift
    checks that diff a checked-in copy.

    Args:
        catalog: A catalog dict (typically the return value of
            `build_catalog()`).

    Returns:
        JSON text encoded as UTF-8 with two-space indentation.
    """
    return json.dumps(catalog, sort_keys=True, indent=2, ensure_ascii=False)
