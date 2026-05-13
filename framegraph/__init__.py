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

from .library import FrameGraphDeckRenderer, FrameGraphLibrary
from .renderer import FrameGraphRenderer

__version__ = "0.1.0"
__all__ = ["FrameGraphRenderer", "FrameGraphLibrary", "FrameGraphDeckRenderer"]
