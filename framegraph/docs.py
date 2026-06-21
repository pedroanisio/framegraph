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
  generate valid input documents without reading source, plus a flat
  `schema_fields` table (name / type / required / default / description /
  constraints) that the documentation portal renders directly,
- a `cli` section introspected from the live argparse parser
  (`framegraph.cli.build_parser`): every command, sub-command, option,
  and positional with its help text — so the CLI reference never drifts
  from the implemented flags.

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
    "build_schema_models",
    "render_catalog_json",
]


CATALOG_SCHEMA_VERSION = "1.2.0"
"""Semver of the catalog JSON shape. Bump major when consumers must adapt.

History:
    1.0.0 — modules / symbols / docstrings / json_schema.
    1.1.0 — additive: per-symbol ``schema_fields`` flat table and a
        top-level ``cli`` section introspected from ``build_parser()``.
    1.2.0 — additive: top-level ``schema_models`` section enumerating
        every model reachable from the document roots (``Document`` /
        ``DeckDocument``) plus the complete object ``type`` map — the
        anti-drift basis for a *complete* schema reference.
"""


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


# ─────────────────────────────────────────────────────────────────
# JSON-Schema → flat field table
# ─────────────────────────────────────────────────────────────────

# Constraint keywords surfaced verbatim in the field table (in this
# order, so the rendered string is deterministic).
_CONSTRAINT_KEYS: tuple[str, ...] = (
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
)


def _ref_name(ref: str) -> str:
    """Return the bare model name from a ``#/$defs/Name`` JSON pointer."""
    return ref.rsplit("/", 1)[-1]


def _describe_type(node: dict[str, Any]) -> str:
    """Render a JSON-Schema node as a compact human-readable type string.

    Resolves the constructs Pydantic v2 emits: ``$ref`` (named model),
    ``anyOf`` / ``oneOf`` (unions, rendered ``A | B``), ``allOf``,
    ``enum``, ``const``, and typed arrays (rendered ``array<item>``).
    Falls back to ``"any"`` for an empty / open node so the column is
    never blank.
    """
    if "$ref" in node:
        return _ref_name(node["$ref"])
    if "const" in node:
        return repr(node["const"])
    if "enum" in node:
        return "enum(" + ", ".join(repr(v) for v in node["enum"]) + ")"
    for combinator in ("anyOf", "oneOf"):
        if combinator in node:
            parts = [_describe_type(s) for s in node[combinator]]
            # Collapse the Pydantic ``Optional`` idiom (X | null) to ``X?``.
            non_null = [p for p in parts if p != "null"]
            if len(parts) - len(non_null) == 1 and non_null:
                return " | ".join(non_null) + "?"
            return " | ".join(parts)
    if "allOf" in node:
        return " & ".join(_describe_type(s) for s in node["allOf"])
    typ = node.get("type")
    if typ == "array":
        items = node.get("items")
        if isinstance(items, dict) and items:
            return f"array<{_describe_type(items)}>"
        return "array"
    if isinstance(typ, list):
        return " | ".join(typ)
    if isinstance(typ, str):
        return typ
    return "any"


def _constraints(node: dict[str, Any]) -> str:
    """Render the constraint keywords of a field node as ``k=v, …``."""
    parts = [f"{k}={node[k]!r}" for k in _CONSTRAINT_KEYS if k in node]
    return ", ".join(parts)


def _schema_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a model JSON Schema into an ordered list of field rows.

    Each row carries ``name``, ``type`` (via `_describe_type`),
    ``required`` (bool), ``default`` (omitted when the schema declares
    none), ``description`` (the Pydantic ``Field(description=…)`` or the
    property ``title``), and ``constraints``. The order follows the
    schema's ``properties`` declaration order, which Pydantic emits in
    field-definition order — keeping the rendered table stable.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = set(schema.get("required", []))
    rows: list[dict[str, Any]] = []
    for name, node in properties.items():
        if not isinstance(node, dict):
            node = {}
        row: dict[str, Any] = {
            "name": name,
            "type": _describe_type(node),
            "required": name in required,
            "description": node.get("description") or node.get("title") or "",
            "constraints": _constraints(node),
        }
        if "default" in node:
            row["default"] = node["default"]
        rows.append(row)
    return rows


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
        entry["schema_fields"] = _schema_fields(schema)
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
# CLI introspection (argparse → catalog)
# ─────────────────────────────────────────────────────────────────


def _jsonable(value: Any) -> Any:
    """Coerce an argparse default to a JSON-serializable scalar."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return repr(value)


def _argument_entry(action: Any) -> dict[str, Any] | None:
    """Describe one argparse action (option or positional), or None to skip.

    Help-suppressed actions (``help=argparse.SUPPRESS``) are omitted so
    internal flags do not leak into the public CLI reference.
    """
    import argparse

    if action.help is argparse.SUPPRESS:
        return None
    if isinstance(action, argparse._HelpAction):
        return None

    is_flag = isinstance(
        action,
        (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._StoreConstAction),
    )
    entry: dict[str, Any] = {
        "names": list(action.option_strings),
        "dest": action.dest,
        "help": action.help or "",
        "kind": "positional" if not action.option_strings else ("flag" if is_flag else "option"),
        "required": bool(getattr(action, "required", False)),
    }
    if action.metavar:
        entry["metavar"] = action.metavar
    if action.choices:
        entry["choices"] = [str(c) for c in action.choices]
    if not is_flag and action.default not in (None, argparse.SUPPRESS):
        entry["default"] = _jsonable(action.default)
    return entry


def _describe_parser(parser: Any) -> dict[str, Any]:
    """Recursively describe an argparse parser as catalog data.

    Returns a mapping with ``description``, ``options`` and
    ``positionals`` (lists of `_argument_entry` rows), and
    ``subcommands`` (a list of ``{name, help, …}`` describing each
    nested sub-parser, recursively). Ordering follows argparse's own
    insertion order, so the output is deterministic.
    """
    import argparse

    options: list[dict[str, Any]] = []
    positionals: list[dict[str, Any]] = []
    subcommands: list[dict[str, Any]] = []

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            # Map sub-parser name → its help string (held separately).
            help_by_name = {ca.dest: (ca.help or "") for ca in action._choices_actions}
            for name, sub in action.choices.items():
                child = _describe_parser(sub)
                child["name"] = name
                child["help"] = help_by_name.get(name, "")
                subcommands.append(child)
            continue
        entry = _argument_entry(action)
        if entry is None:
            continue
        (positionals if entry["kind"] == "positional" else options).append(entry)

    return {
        "description": (parser.description or "").strip(),
        "options": options,
        "positionals": positionals,
        "subcommands": subcommands,
    }


def _cli_catalog() -> dict[str, Any]:
    """Introspect the live ``framegraph`` CLI into catalog data.

    Imports `framegraph.cli.build_parser` and walks the resulting
    parser tree. Kept import-local so a missing optional CLI dependency
    cannot break ``import framegraph.docs``.
    """
    from framegraph.cli import build_parser

    root = _describe_parser(build_parser())
    root["prog"] = "framegraph"
    return root


# ─────────────────────────────────────────────────────────────────
# Complete schema-model enumeration (document-root reachable)
# ─────────────────────────────────────────────────────────────────
#
# The `modules` section above is scoped to each module's `__all__` — the
# curated *public API* surface. That is deliberately NOT the same as the
# set of models an author needs to write valid YAML: the discriminated
# object-type union members (`RectObject`, …) and many structural models
# are not exported. To produce a *complete* schema reference that cannot
# silently drop a type, enumerate every model reachable from the document
# roots via JSON-Schema `$defs`, which Pydantic derives from the models
# themselves — so the set is authoritative by construction.

# Document-root models whose `$defs` closure defines the full surface.
_DOCUMENT_ROOTS: tuple[str, ...] = ("Document", "DeckDocument")


def _object_type_map() -> dict[str, str]:
    """Map every object ``type`` literal to its model name.

    Walks the discriminated-union members in ``framegraph._schema`` and
    reads each model's ``type: Literal[...]`` field. The result is the
    authoritative, complete list of first-class object types — the basis
    for the schema-reference completeness gate.
    """
    import typing

    import framegraph._schema as schema_mod

    out: dict[str, str] = {}
    for name, obj in vars(schema_mod).items():
        if not (inspect.isclass(obj) and issubclass(obj, BaseModel)):
            continue
        field = obj.model_fields.get("type")
        if field is None:
            continue
        for arg in typing.get_args(field.annotation):
            if isinstance(arg, str):
                out[arg] = name
    return dict(sorted(out.items()))


def _collect_document_defs() -> dict[str, dict[str, Any]]:
    """Return every model schema reachable from the document roots.

    Keyed by model name; includes the root models themselves and every
    ``$defs`` entry Pydantic emits for their nested models. This is the
    complete document-model surface, derived from the models — it cannot
    omit a type that the schema actually accepts.
    """
    import framegraph._schema as schema_mod

    defs: dict[str, dict[str, Any]] = {}
    for root_name in _DOCUMENT_ROOTS:
        model = getattr(schema_mod, root_name, None)
        if model is None or not issubclass(model, BaseModel):
            continue
        root_schema = model.model_json_schema(ref_template="#/$defs/{model}")
        for name, node in (root_schema.get("$defs") or {}).items():
            defs.setdefault(name, node)
        # The root carries no $def for itself; register it explicitly.
        root_only = {k: v for k, v in root_schema.items() if k != "$defs"}
        defs.setdefault(root_name, root_only)
    return defs


def build_schema_models() -> dict[str, Any]:
    """Enumerate the complete document-model surface for the schema reference.

    Returns a mapping with:
        ``models`` — a sorted list of ``{name, title, description,
        schema_fields, json_schema}`` for every model reachable from the
        document roots,
        ``object_types`` — the complete ``type`` → model-name map,
        ``roots`` — the document-root model names.

    Completeness is structural: the set is the ``$defs`` closure of the
    document roots, so a model the schema accepts cannot be missing here.
    """
    defs = _collect_document_defs()
    models = [
        {
            "name": name,
            "title": node.get("title", name),
            "description": node.get("description", ""),
            "schema_fields": _schema_fields(node),
            "json_schema": node,
        }
        for name in sorted(defs)
        for node in (defs[name],)
    ]
    return {
        "models": models,
        "object_types": _object_type_map(),
        "roots": list(_DOCUMENT_ROOTS),
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
        "cli": _cli_catalog(),
        "schema_models": build_schema_models(),
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
