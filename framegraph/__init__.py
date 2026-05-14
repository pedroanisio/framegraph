"""framegraph — YAML-first hybrid semantic-visual diagram DSL.

Public API
----------
    from framegraph import FrameGraphRenderer, FrameGraphLibrary, FrameGraphDeckRenderer

    # Render a single document
    import yaml
    doc = yaml.safe_load(open("diagram.yml"))
    svg = FrameGraphRenderer(doc).render_svg()

    # Render a multi-slide deck
    from pathlib import Path
    lib  = FrameGraphLibrary(Path("framegraph/lib"))
    data = yaml.safe_load(open("deck.yml"))
    deck = FrameGraphDeckRenderer(data, library=lib)
    deck.render_all(Path("output/"))
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from ._version import resolve_version
from .library import FrameGraphDeckRenderer, FrameGraphLibrary
from .renderer import FrameGraphRenderer

try:
    __version__ = _pkg_version("framegraph")
except PackageNotFoundError:
    # Source-tree fallback for environments where the package is not installed.
    # Reads the version directly from pyproject.toml so there is still exactly
    # one source of truth — pyproject — rather than a stale literal here.
    __version__ = resolve_version()

__all__ = ["FrameGraphRenderer", "FrameGraphLibrary", "FrameGraphDeckRenderer"]
