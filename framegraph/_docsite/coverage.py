"""Docstring-coverage gate over the framegraph source tree.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW) — DOCS ARE UNVERIFIED BY DEFAULT.
A documentation portal generated from docstrings is only as complete as
the docstrings themselves. An undocumented public symbol produces a
blank, misleading, or hallucinated portal entry. This module makes the
absence of a docstring a *build failure*, not a silent gap.

Policy
------
Walking the AST (no import side effects), a symbol is **required** to
carry a docstring when:

- it is a module (every ``.py`` file), or
- it is a class (`ClassDef`) — the schema models *are* the API, or
- it is a **module-level** function or a **method** (a function whose
  direct parent is a module or a class) whose name is public (does not
  start with a single underscore). Dunder methods such as ``__init__``
  count as public for this gate; single-underscore helpers (``_foo``)
  are exempt.

**Nested local functions are exempt.** A closure defined inside another
function body (e.g. a per-call ``vy(val)`` scale helper, a decorator's
inner ``wrapper``) is an implementation detail: it never appears in the
generated portal — which only renders the ``__all__`` surface — and
conventional Python style (pydocstyle, interrogate) does not require a
docstring on it. Requiring one would add noise, not coverage.

The gate is deterministic: gaps are returned sorted by ``(path, line)``.

CLI
---
``python -m framegraph._docsite.coverage`` prints every gap and exits
non-zero when any exist (suitable for CI and pre-commit).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Gap", "undocumented_symbols", "coverage_summary"]

# Package root resolved relative to this file: framegraph/_docsite/coverage.py
# → the `framegraph/` directory is the parent of `_docsite/`.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, order=True)
class Gap:
    """One public symbol that is missing a docstring.

    Attributes:
        path: Source file path, relative to the repository root.
        line: 1-based line number of the ``def`` / ``class`` statement
            (``0`` for a module-level gap).
        kind: One of ``"module"``, ``"class"``, or ``"function"``.
        name: The symbol name (``"<module>"`` for a module-level gap).
    """

    path: str
    line: int
    kind: str
    name: str


def _requires_function_doc(name: str) -> bool:
    """Return True when a function/method name is in scope for the gate.

    Public names and dunders are in scope; single-underscore helpers are
    exempt (they are internal and not rendered in the portal).
    """
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


_FuncDef = (ast.FunctionDef, ast.AsyncFunctionDef)


def _visit_body(
    body: list[ast.stmt],
    *,
    inside_function: bool,
    on_class: Any,
    on_function: Any,
) -> None:
    """Recurse one statement list, tracking whether we are in a function.

    ``inside_function`` is True once we descend into any function body, so
    nested closures can be skipped while class methods (whose parent is a
    class, not a function) are still visited. Class bodies reset the flag
    to False so their methods are required to carry docstrings.
    """
    for node in body:
        if isinstance(node, ast.ClassDef):
            on_class(node)
            _visit_body(
                node.body,
                inside_function=False,
                on_class=on_class,
                on_function=on_function,
            )
        elif isinstance(node, _FuncDef):
            if not inside_function:
                on_function(node)
            _visit_body(
                node.body,
                inside_function=True,
                on_class=on_class,
                on_function=on_function,
            )
        elif hasattr(node, "body") and isinstance(node.body, list):
            # if/for/while/with/try blocks: descend, preserving context so a
            # method guarded by `if TYPE_CHECKING:` still counts as a method.
            _visit_body(
                node.body,
                inside_function=inside_function,
                on_class=on_class,
                on_function=on_function,
            )
            for attr in ("orelse", "finalbody"):
                extra = getattr(node, attr, None)
                if isinstance(extra, list):
                    _visit_body(
                        extra,
                        inside_function=inside_function,
                        on_class=on_class,
                        on_function=on_function,
                    )


def _scan_file(path: Path, root: Path) -> list[Gap]:
    """Collect docstring gaps in one Python source file."""
    rel = str(path.relative_to(root))
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    gaps: list[Gap] = []

    if ast.get_docstring(tree) is None:
        gaps.append(Gap(rel, 0, "module", "<module>"))

    def on_class(node: ast.ClassDef) -> None:
        if ast.get_docstring(node) is None:
            gaps.append(Gap(rel, node.lineno, "class", node.name))

    def on_function(node: ast.AST) -> None:
        name = node.name  # type: ignore[attr-defined]
        if not _requires_function_doc(name):
            return
        if ast.get_docstring(node) is None:  # type: ignore[arg-type]
            gaps.append(Gap(rel, node.lineno, "function", name))  # type: ignore[attr-defined]

    _visit_body(tree.body, inside_function=False, on_class=on_class, on_function=on_function)
    return gaps


def undocumented_symbols(
    package_root: Path | str | None = None,
    *,
    repo_root: Path | str | None = None,
) -> list[Gap]:
    """Return every undocumented public symbol under ``package_root``.

    Args:
        package_root: Directory to scan. Defaults to the installed
            ``framegraph`` package directory.
        repo_root: Base for the relative paths in returned `Gap`s.
            Defaults to the parent of ``package_root``.

    Returns:
        Gaps sorted by ``(path, line)`` — deterministic across runs.
    """
    pkg = Path(package_root) if package_root else _PACKAGE_ROOT
    base = Path(repo_root) if repo_root else pkg.parent
    gaps: list[Gap] = []
    for py in sorted(pkg.rglob("*.py")):
        gaps.extend(_scan_file(py, base))
    return sorted(gaps)


def coverage_summary(package_root: Path | str | None = None) -> dict[str, int]:
    """Return counts of documented vs. total symbols, by kind.

    Keys: ``modules``, ``classes``, ``functions`` (each a ``"doc/total"``
    is *not* used — instead two integer keys ``*_documented`` and
    ``*_total`` are emitted so callers can compute ratios).
    """
    pkg = Path(package_root) if package_root else _PACKAGE_ROOT
    totals = {"modules": 0, "classes": 0, "functions": 0}
    documented = {"modules": 0, "classes": 0, "functions": 0}
    for py in sorted(pkg.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        totals["modules"] += 1
        if ast.get_docstring(tree) is not None:
            documented["modules"] += 1

        def on_class(node: ast.ClassDef) -> None:
            totals["classes"] += 1
            if ast.get_docstring(node) is not None:
                documented["classes"] += 1

        def on_function(node: ast.AST) -> None:
            if not _requires_function_doc(node.name):  # type: ignore[attr-defined]
                return
            totals["functions"] += 1
            if ast.get_docstring(node) is not None:  # type: ignore[arg-type]
                documented["functions"] += 1

        _visit_body(
            tree.body,
            inside_function=False,
            on_class=on_class,
            on_function=on_function,
        )
    return {
        "modules_documented": documented["modules"],
        "modules_total": totals["modules"],
        "classes_documented": documented["classes"],
        "classes_total": totals["classes"],
        "functions_documented": documented["functions"],
        "functions_total": totals["functions"],
    }


def _main(argv: list[str] | None = None) -> int:
    """CLI entry point: print gaps, exit non-zero when any remain."""
    gaps = undocumented_symbols()
    summary = coverage_summary()
    if gaps:
        print(f"Docstring coverage gate: {len(gaps)} undocumented symbol(s)\n")
        for g in gaps:
            print(f"  {g.path}:{g.line}  {g.kind} {g.name}")
        print()
    print(
        "Coverage — "
        f"modules {summary['modules_documented']}/{summary['modules_total']}, "
        f"classes {summary['classes_documented']}/{summary['classes_total']}, "
        f"functions {summary['functions_documented']}/{summary['functions_total']}"
    )
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
