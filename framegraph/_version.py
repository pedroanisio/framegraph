"""Single-source-of-truth version resolution helper.

Used only by `framegraph/__init__.py`'s fallback path when the package is
imported from an uninstalled source tree (no `importlib.metadata` record).
The runtime version always comes from `pyproject.toml` — never a hand-mirrored
literal — so a single version bump in `pyproject.toml` propagates everywhere.

Pulled into its own module so its surface is cleanly importable and testable.
"""

from __future__ import annotations

from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def resolve_version(pyproject: Path | None = None) -> str:
    """Return the `[project] version` value from `pyproject.toml`.

    Args:
        pyproject: Optional override for the pyproject path (used by tests).
            Defaults to the sibling-of-package `pyproject.toml`.

    Returns:
        The version string, or ``"0+unknown"`` if `pyproject.toml` is absent
        or contains no recognisable `[project] version = "X.Y.Z"` line. The
        sentinel is a PEP 440 local-version that downstream tooling treats
        as "version unknown" rather than an arbitrary SemVer.
    """
    path = pyproject or _PYPROJECT
    if not path.is_file():
        return "0+unknown"
    in_project = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return "0+unknown"
