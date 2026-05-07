"""framegraph.layout — Pure-Python graph-layout algorithms.

Standalone layout library. No FrameGraph schema or renderer
dependencies; the output is `(node_id → (x, y))` plus
`(edge → list[Point])` and consumers are free to map that into
visual objects.

Currently provides:
    sugiyama — Hierarchical (Sugiyama framework) layered graph
               layout. 4-stage pipeline: cycle removal → layer
               assignment → crossing minimization → x-coordinate
               assignment.
"""

from framegraph.layout.sugiyama import LayoutResult, SugiyamaConfig, sugiyama_layout

__all__ = ["LayoutResult", "SugiyamaConfig", "sugiyama_layout"]
