"""Shared composer infrastructure for UML diagram composers.

Phase B refactors the Sugiyama-driven layout pattern out of
`class_diagram.py` so other hierarchical composers
(`package_diagram`, `use_case_diagram`, `component_diagram`,
`deployment_diagram`, `activity_diagram`, `state_machine`) can
reuse it without copy-pasting.

Three layers of reuse here:

  1. **Pure helpers** — `_str_width`, `_char_em`, the visibility-
     prefix table. Shared by every composer that needs to size text
     in a layout-time pass.
  2. **Connector emission** — `connector_object()` builds a UML-
     conventional connector with the right arrow kind and dash
     pattern. Used by every composer that emits typed edges.
  3. **`HierarchicalComposer`** — abstract base that runs the
     four-stage Sugiyama-backed pipeline (measure → build layout
     graph → run Sugiyama → emit visual). Subclass hooks let each
     diagram type plug in its own classifier set, edge selection,
     and primitive emission.

The class-diagram composer in `class_diagram.py` continues to work
as before; it imports these helpers but is not yet refactored to
use `HierarchicalComposer`. That refactor is independent of Phase B
shipping new diagram types and lands when there is value in
deduplicating it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from framegraph.layout import LayoutResult, SugiyamaConfig, sugiyama_layout

# ─────────────────────────────────────────────────────────────────
# Pure helpers — width estimation
# ─────────────────────────────────────────────────────────────────
#
# Mirrors the renderer's `_str_width` / `_char_em` exactly so the
# composer can size boxes before a renderer instance exists. Kept
# in sync by inspection; the renderer is the source of truth and
# any drift here just means slightly off measurements (we bias wide,
# so off-by-a-few pixels is fine).

_CW_NORMAL = {
    "narrow": 0.34,
    "normal": 0.50,
    "wide": 0.65,
    "space": 0.25,
    "digit": 0.52,
    "punct": 0.30,
}
_CW_BOLD = {
    "narrow": 0.38,
    "normal": 0.56,
    "wide": 0.72,
    "space": 0.28,
    "digit": 0.58,
    "punct": 0.34,
}
_NARROW_CH = set("ijlfrт:;!|1()")
_WIDE_CH = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw@#%")
_DIGIT_CH = set("0123456789")
_PUNCT_CH = set(",.'\"-–—")


def _char_em(c: str, bold: bool) -> float:
    """Estimate the em-fraction width of a single character."""
    table = _CW_BOLD if bold else _CW_NORMAL
    if c in (" ", "\t"):
        return table["space"]
    if c in _NARROW_CH:
        return table["narrow"]
    if c in _WIDE_CH:
        return table["wide"]
    if c in _DIGIT_CH:
        return table["digit"]
    if c in _PUNCT_CH:
        return table["punct"]
    return table["normal"]


def str_width(text: str, fs: float, bold: bool = False) -> float:
    """Estimate the rendered width of `text` in pixels at font-size `fs`."""
    return sum(_char_em(c, bold) for c in text) * fs


# ─────────────────────────────────────────────────────────────────
# Connector emission — shared UML edge convention
# ─────────────────────────────────────────────────────────────────


def connector_object(
    edge_id: str,
    from_id: str,
    to_id: str,
    *,
    arrow_end_kind: str | None = None,
    arrow_start_kind: str | None = None,
    dashed: bool = False,
    color: str = "#1A1A1A",
    width: float = 1.0,
) -> dict[str, Any]:
    """Build a connector visual object with UML edge conventions.

    The edge endpoints are referenced by id; the renderer's
    `connector` primitive resolves them against `r.object_index`
    at paint time, so the composer doesn't need to compute
    midpoints itself.

    Args:
        edge_id: Unique id for the connector.
        from_id: Source classifier id.
        to_id: Target classifier id.
        arrow_end_kind: Marker shape at the destination end. One of
            `hollow_triangle` / `hollow_diamond` / `filled_diamond` /
            `open_arrow` / `filled_triangle`. None = no end arrow.
        arrow_start_kind: Marker shape at the source end. None = no
            start arrow.
        dashed: When True, render with a `[5, 4]` dash pattern.
        color: Stroke color. Default is the FrameGraph slate.
        width: Stroke width in px.

    Returns:
        A dict ready to drop into a `visual.layers[].objects` list.
        The composer wraps these in an "uml.edges" layer.
    """
    stroke: dict[str, Any] = {"color": color, "width": width}
    if dashed:
        stroke["dash"] = [5, 4]
    if arrow_end_kind:
        stroke["arrow_end"] = True
        stroke["arrow_end_kind"] = arrow_end_kind
    if arrow_start_kind:
        stroke["arrow_start"] = True
        stroke["arrow_start_kind"] = arrow_start_kind

    return {
        "type": "connector",
        "id": edge_id,
        "from": from_id,
        "to": to_id,
        "stroke": stroke,
    }


# ─────────────────────────────────────────────────────────────────
# Hierarchical composer base
# ─────────────────────────────────────────────────────────────────


@dataclass
class ComposedDiagram:
    """Result of any UML composer.

    Same shape as `framegraph.uml.class_diagram.ComposedDiagram`. The
    types are kept separate so subclasses can extend the result
    type without affecting class-diagram callers, but the field
    layout matches.

    Attributes:
        visual: The fully-laid-out `visual` block. Insert into a
            FrameGraph document under the `visual` key.
        layout_result: The Sugiyama `LayoutResult` (None when
            `layout: manual`). Useful for diagnostics.
        node_dimensions: Mapping `node_id → (width, height)`.
            Diagnostic.
    """

    visual: dict[str, Any]
    layout_result: LayoutResult | None = None
    node_dimensions: dict[str, tuple[float, float]] = field(default_factory=dict)

    def to_visual(self) -> dict[str, Any]:
        """Return just the visual block for insertion into a FrameGraph doc."""
        return self.visual


class HierarchicalComposer(ABC):
    """Abstract base for UML composers using Sugiyama layered layout.

    The class-diagram composer was the first instance of this
    pattern; later composers (package, use-case, component,
    deployment, activity, state-machine) follow the same shape
    with different specializations.

    Subclasses provide:
      - `_extract_layout_nodes()` → list of node ids that participate
        in the layered layout (typically all "container" or
        "classifier" elements; sometimes a subset).
      - `_extract_layout_edges()` → directed edges that drive the
        y-axis hierarchy. Subclass decides which UML edge kinds
        belong here (e.g. generalizations + realizations for class
        diagrams; package-containment for package diagrams).
      - `_measure_node(node_id)` → `(width, height)` for sizing.
      - `_emit_node_object(node_id, box)` → the visual primitive
        for one classifier-shaped object.
      - `_emit_edge_objects()` → list of UML connectors plus any
        non-layout edges (associations, dependencies) that route
        between resolved positions.

    The base class then runs the four-stage pipeline in `compose()`.
    """

    def __init__(
        self,
        *,
        canvas_size: tuple[float, float] = (1280.0, 720.0),
        layer_height: float = 160.0,
        node_gap: float = 60.0,
        node_min_width: float = 160.0,
        margin: float = 40.0,
        layout: str = "sugiyama",
    ) -> None:
        self.canvas_size = canvas_size
        self.layer_height = layer_height
        self.node_gap = node_gap
        self.node_min_width = node_min_width
        self.margin = margin
        self.layout = layout

    # ── Subclass hooks ──────────────────────────────────────────

    @abstractmethod
    def _extract_layout_nodes(self) -> list[str]:
        """Return the ids of nodes that participate in the layered layout."""
        ...

    @abstractmethod
    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        """Return directed edges driving the y-axis hierarchy.

        Sugiyama's convention is "above → below"; subclasses are
        responsible for orienting the edges accordingly. For
        example, a class diagram returns `(parent, child)` for each
        generalization so the parent ends up on a smaller y.
        """
        ...

    @abstractmethod
    def _measure_node(self, node_id: str) -> tuple[float, float]:
        """Return `(width, height)` for the named node."""
        ...

    @abstractmethod
    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        """Build the visual primitive for one node at the resolved box."""
        ...

    @abstractmethod
    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        """Build the connector objects for layout-driving + non-layout edges."""
        ...

    @abstractmethod
    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        """Return the author-supplied position hint for a node, or None."""
        ...

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        """Optional hook: return additional visual layers (notes, packages, etc.).

        Default: empty. Subclasses override to inject layers besides
        the built-in `uml.edges` and `uml.classifiers`.
        """
        return []

    # ── Pipeline ────────────────────────────────────────────────

    def compose(self) -> ComposedDiagram:
        """Run the four-stage Sugiyama-backed pipeline.

        Returns:
            A `ComposedDiagram` whose `visual` field is ready to
            drop into a FrameGraph document.
        """
        # ── Step 1: measure ──
        nodes = self._extract_layout_nodes()
        dimensions: dict[str, tuple[float, float]] = {n: self._measure_node(n) for n in nodes}

        # ── Step 2 & 3: layout ──
        layout_result: LayoutResult | None = None
        positions: dict[str, tuple[float, float]] = {}

        if self.layout == "manual":
            for n in nodes:
                pinned = self._node_position(n)
                if pinned is None:
                    raise ValueError(
                        f"layout='manual' requires every node to have a "
                        f"position hint, but {n!r} has none"
                    )
                positions[n] = pinned
        elif self.layout == "sugiyama":
            edges = self._extract_layout_edges()
            max_w = max((dimensions[n][0] for n in nodes), default=self.node_min_width)
            max_h = max((dimensions[n][1] for n in nodes), default=self.layer_height)
            cfg = SugiyamaConfig(
                layer_height=max(self.layer_height, max_h + 40),
                node_width=max_w,
                node_gap=self.node_gap,
            )
            layout_result = sugiyama_layout(nodes, edges, config=cfg)
            # Translate so the leftmost node's left edge sits at margin.
            # `sugiyama_layout` types node ids as `Hashable`; the
            # composer feeds in `str` so cast at the boundary.
            if layout_result.positions:
                min_left = min(
                    x - dimensions[str(nid)][0] / 2
                    for nid, (x, _) in layout_result.positions.items()
                )
                x_shift = self.margin - min_left
            else:
                x_shift = self.margin
            for nid, (x, y) in layout_result.positions.items():
                positions[str(nid)] = (x + x_shift, y + self.margin)
        else:
            raise ValueError(
                f"unknown layout strategy {self.layout!r}; expected 'manual' or 'sugiyama'"
            )

        # ── Step 4: pin overrides ──
        for n in nodes:
            pinned = self._node_position(n)
            if pinned is not None:
                positions[n] = pinned

        # ── Step 5: emit visual objects ──
        node_objects: list[dict[str, Any]] = []
        for n in nodes:
            x, y = positions[n]
            w, h = dimensions[n]
            # Convention: Sugiyama-positioned nodes use the position
            # as the box CENTER, then we normalize to top-left. Pinned
            # positions are already top-left.
            if self._node_position(n) is None:
                x -= w / 2
            box = (x, y, w, h)
            node_objects.append(self._emit_node_object(n, box))

        edge_objects = self._emit_edge_objects()
        extra_layers = self._emit_extra_layers()

        visual: dict[str, Any] = {
            "tokens": {},
            "layers": [
                {"id": "uml.edges", "z": 10, "objects": edge_objects},
                {"id": "uml.classifiers", "z": 20, "objects": node_objects},
                *extra_layers,
            ],
        }

        return ComposedDiagram(
            visual=visual,
            layout_result=layout_result,
            node_dimensions=dimensions,
        )
