"""Drift gate: every object field a renderer reads must be declared on its model.

The renderers (`framegraph.renderers.*`) are the source of truth for which
top-level keys each visual-object `type` actually consumes. The Pydantic
models in `framegraph._schema` declare those keys so that:

  - the schema / EBNF / docs portal carry real per-type field specificity, and
  - `framegraph validate --strict` can flag unknown keys (typos, hallucinated
    field names) without false-rejecting legitimate documents.

This test statically extracts, per object `type`, the literal keys each render
function reads off its object argument — following module-local helpers,
cross-module helpers, and `RendererContext` (`r.*`) methods — and asserts that
set is a subset of the keys declared on the type's model. If a renderer starts
reading a new field, this test fails until the schema declares it (which keeps
`--strict` from rejecting documents that use the new, real field).

Open types (`use`, `component`) read arbitrary slot keys dynamically and are
exempt — see `framegraph._schema._OPEN_OBJECT_TYPES`.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import framegraph._helpers as helpers_mod
import framegraph.renderer as renderer_mod
from framegraph import renderers
from framegraph._schema import (
    _ALLOWED_OBJECT_KEYS,
    _OPEN_OBJECT_TYPES,
    _UNIVERSAL_OBJECT_KEYS,
)

# Parameters that are the RendererContext / helper handle, never the object.
_NON_OBJECT_PARAMS = {"self", "r", "ctx"}
_GETTERS = {"get", "pop"}


def _build_symbol_tables() -> tuple[dict[str, ast.FunctionDef], dict[str, ast.FunctionDef], dict]:
    """Index module-level functions and RendererContext methods by name."""
    module_funcs: dict[str, ast.FunctionDef] = {}
    method_funcs: dict[str, ast.FunctionDef] = {}
    trees: dict = {}
    for module in [renderer_mod, helpers_mod, *renderers.ALL_MODULES]:
        tree = ast.parse(inspect.getsource(module))
        trees[module.__name__] = tree
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                module_funcs.setdefault(node.name, node)
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        method_funcs.setdefault(sub.name, sub)
    return module_funcs, method_funcs, trees


_MODULE_FUNCS, _METHOD_FUNCS, _TREES = _build_symbol_tables()


def _object_param(fn: ast.FunctionDef) -> str | None:
    for arg in fn.args.args:
        if arg.arg not in _NON_OBJECT_PARAMS:
            return arg.arg
    return fn.args.args[-1].arg if fn.args.args else None


def _read_keys(fn: ast.FunctionDef, obj_name: str | None, visited: set) -> set[str]:
    """Literal keys read off `obj_name` in `fn`, following helper calls."""
    keys: set[str] = set()
    if obj_name is None or (fn.name, obj_name) in visited:
        return keys
    visited.add((fn.name, obj_name))

    # Names aliased directly to the object (`x = obj`).
    names = {obj_name}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Name)
                and node.value.id in names
                and node.targets[0].id not in names
            ):
                names.add(node.targets[0].id)
                changed = True

    for node in ast.walk(fn):
        # obj["k"]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in names
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
        # obj.get("k") / obj.pop("k")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _GETTERS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in names
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
        # "k" in obj
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
            and any(isinstance(c, ast.Name) and c.id in names for c in node.comparators)
        ):
            keys.add(node.left.value)
        # follow helper / method calls that receive the object
        if isinstance(node, ast.Call):
            callee: ast.FunctionDef | None = None
            is_method = False
            if isinstance(node.func, ast.Name):
                callee = _MODULE_FUNCS.get(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {"r", "self"}:
                    callee = _METHOD_FUNCS.get(node.func.attr)
                    is_method = True
                else:
                    callee = _MODULE_FUNCS.get(node.func.attr)
            if callee is not None:
                cparams = [a.arg for a in callee.args.args]
                for arg_i, arg in enumerate(node.args):
                    if isinstance(arg, ast.Name) and arg.id in names:
                        param_i = arg_i + 1 if is_method else arg_i
                        if 0 <= param_i < len(cparams):
                            keys |= _read_keys(callee, cparams[param_i], visited)
    return keys


def _renderer_reads() -> dict[str, set[str]]:
    """Map each object `type` to the literal top-level keys its renderer reads."""
    reads: dict[str, set[str]] = {}
    for module in renderers.ALL_MODULES:
        fns = {n.name: n for n in _TREES[module.__name__].body if isinstance(n, ast.FunctionDef)}
        for type_name, fn in module.RENDERERS.items():
            node = fns.get(fn.__name__)
            reads[type_name] = _read_keys(node, _object_param(node), set()) if node else set()
    return reads


_READS = _renderer_reads()
_CLOSED_TYPES = sorted(t for t in _READS if t not in _OPEN_OBJECT_TYPES)


def test_every_renderer_type_has_a_model() -> None:
    """Each closed renderer type maps to a schema model with an allowed-key set."""
    missing = [t for t in _CLOSED_TYPES if t not in _ALLOWED_OBJECT_KEYS]
    assert not missing, f"renderer types with no schema model: {missing}"


@pytest.mark.parametrize("type_name", _CLOSED_TYPES)
def test_renderer_reads_are_declared(type_name: str) -> None:
    """Every field a renderer reads is declared on the object's model.

    Guards against schema↔renderer drift: if this fails, a renderer reads a
    key the model does not declare, so `--strict` would reject documents that
    legitimately use it. Fix by declaring the field in `framegraph._schema`.
    """
    allowed = _ALLOWED_OBJECT_KEYS.get(type_name, set()) | set(_UNIVERSAL_OBJECT_KEYS)
    undeclared = _READS[type_name] - allowed - {"type"}
    assert not undeclared, (
        f"renderer for '{type_name}' reads undeclared field(s) {sorted(undeclared)}; "
        f"declare them on the model in framegraph/_schema.py"
    )
