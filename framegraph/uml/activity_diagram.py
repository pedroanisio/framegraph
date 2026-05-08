"""Activity-diagram composer — Phase C.3 of the UML support architecture.

Reads a `UMLActivityDiagramModel` (from framegraph._uml) and produces
a fully-laid-out FrameGraph `visual` block. Uses the Sugiyama
hierarchical layout from `framegraph.layout` on the control-flow
graph (initial above final, fork above its parallel branches,
decision above its alternatives).

Conventions
-----------
- Initial node: small filled disc.
- Final node: bullseye (filled disc inside a hollow ring).
- Flow-final node: hollow disc with an X.
- Action: rounded rectangle (label inside).
- Decision / merge: diamond (label inside, e.g., guards on edges).
- Fork / join: thick horizontal bar.
- Edges: solid lines (control flows) or dashed lines (object flows),
  with an open-arrow at the target.
- Swim lanes: rendered as background columns under the nodes that
  declare a matching `partition`. When swim-lanes are declared,
  the composer constrains each node's x-coordinate to its lane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLActivityDiagramModel,
    UMLActivityNode,
    UMLSwimlane,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class ActivityDiagramOptions:
    """Tunable parameters for the activity-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        action_min_width: Minimum width of an action rounded rectangle.
        action_height: Height of an action rounded rectangle.
        decision_size: Width and height of a decision/merge diamond.
        terminal_size: Width and height of an initial/final/flow-final
            circle.
        bar_length: Length of a fork/join bar (long axis).
        body_padding: Horizontal padding around the action name.
        name_size: Font size for action names.
        guard_size: Font size for edge guard labels.
        swimlane_width: Width of each swim lane.
        swimlane_header_height: Height of the swim-lane header band.
        layout: `sugiyama` or `manual`.
    """

    layer_height: float = 100.0
    node_gap: float = 60.0
    action_min_width: float = 140.0
    action_height: float = 50.0
    decision_size: float = 56.0
    terminal_size: float = 28.0
    bar_length: float = 120.0
    body_padding: float = 12.0
    name_size: float = 12.0
    guard_size: float = 10.0
    swimlane_width: float = 240.0
    swimlane_header_height: float = 24.0
    layout: str = "sugiyama"


class _ActivityDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for activity diagrams.

    Layout-driving edges are control flows. Object flows participate
    in the same Sugiyama graph (they impose ordering too) but render
    dashed. Swim lanes constrain node x-coordinates to their lane
    column when declared.
    """

    def __init__(
        self,
        model: UMLActivityDiagramModel,
        opts: ActivityDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        super().__init__(
            canvas_size=canvas_size,
            layer_height=opts.layer_height,
            node_gap=opts.node_gap,
            node_min_width=opts.action_min_width,
            margin=40.0,
            layout=opts.layout,
        )
        self.model = model
        self.opts = opts
        self._nodes_by_id: dict[str, UMLActivityNode] = {n.id: n for n in model.nodes}
        self._lanes_by_id: dict[str, UMLSwimlane] = {sl.id: sl for sl in model.swimlanes}
        # Captured from _emit_node_object — used by extra-layers to
        # draw lanes that span the node range.
        self._last_node_boxes: dict[str, tuple[float, float, float, float]] = {}

    # ── HierarchicalComposer hooks ──────────────────────────────

    def _extract_layout_nodes(self) -> list[str]:
        return [n.id for n in self.model.nodes]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        return [(e.from_id, e.to_id) for e in self.model.edges]

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        n = self._nodes_by_id[node_id]
        if n.kind == "action":
            label = n.name or ""
            name_w = str_width(label, self.opts.name_size)
            width = max(self.opts.action_min_width, name_w + 2 * self.opts.body_padding)
            return (width, self.opts.action_height)
        if n.kind in ("decision", "merge"):
            return (self.opts.decision_size, self.opts.decision_size)
        if n.kind in ("fork", "join"):
            return (self.opts.bar_length, 12.0)
        # initial / final / flow_final
        return (self.opts.terminal_size, self.opts.terminal_size)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        n = self._nodes_by_id[node_id]
        x, y, w, h = box
        # Apply swim-lane x-constraint if applicable.
        if n.partition is not None and n.partition in self._lanes_by_id:
            lane_idx = list(self._lanes_by_id).index(n.partition)
            lane_left = self.margin + lane_idx * self.opts.swimlane_width
            lane_cx = lane_left + self.opts.swimlane_width / 2
            x = lane_cx - w / 2
            # Note: if the user later pins a position, that takes
            # precedence per HierarchicalComposer.compose().
        self._last_node_boxes[node_id] = (x, y, w, h)

        if n.kind == "action":
            return {
                "type": "uml.action",
                "id": n.id,
                "box": [x, y, w, h],
                "name": n.name or "",
            }
        result: dict[str, Any] = {
            "type": "uml.activity_node",
            "id": n.id,
            "box": [x, y, w, h],
            "kind": n.kind,
        }
        if n.name:
            result["name"] = n.name
        return result

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for e in self.model.edges:
            edges.append(
                connector_object(
                    e.id,
                    e.from_id,
                    e.to_id,
                    arrow_end_kind="open_arrow",
                    dashed=(e.kind == "object"),
                )
            )
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        n = self._nodes_by_id[node_id]
        if n.position is None:
            return None
        return (n.position.x, n.position.y)

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        layers: list[dict[str, Any]] = []
        lane_layer = self._emit_swimlane_layer()
        if lane_layer is not None:
            # Lanes go BEHIND the nodes, hence z below uml.classifiers.
            layers.append(lane_layer)
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)
        return layers

    def _emit_swimlane_layer(self) -> dict[str, Any] | None:
        if not self.model.swimlanes or not self._last_node_boxes:
            return None
        # Compute vertical extent: from the topmost node minus margin
        # to the bottommost node plus margin.
        top = min(b[1] for b in self._last_node_boxes.values())
        bottom = max(b[1] + b[3] for b in self._last_node_boxes.values())
        height = (bottom - top) + 2 * self.opts.body_padding
        y = top - self.opts.body_padding
        objs: list[dict[str, Any]] = []
        for i, sl in enumerate(self.model.swimlanes):
            x = self.margin + i * self.opts.swimlane_width
            objs.append(
                {
                    "type": "uml.swimlane",
                    "id": sl.id,
                    "box": [x, y, self.opts.swimlane_width, height],
                    "name": sl.name,
                }
            )
        return {"id": "uml.swimlanes", "z": 5, "objects": objs}

    def _emit_notes_layer(self) -> dict[str, Any] | None:
        if not self.model.notes:
            return None
        objs: list[dict[str, Any]] = []
        for n in self.model.notes:
            if n.position is not None:
                nx, ny = n.position.x, n.position.y
            else:
                nx, ny = self.canvas_size[0] / 2, self.canvas_size[1] - 100
            nw, nh = 220.0, 60.0
            objs.append(
                {
                    "type": "rect",
                    "id": f"{n.id}.bg",
                    "decorative": True,
                    "box": [nx, ny, nw, nh],
                    "fill": "#FFF8DC",
                    "stroke": {"color": "#999999", "width": 0.5},
                }
            )
            objs.append(
                {
                    "type": "text",
                    "id": f"{n.id}.text",
                    "decorative": True,
                    "box": [nx + 8, ny + 8, nw - 16, nh - 16],
                    "text": n.text,
                    "style": {"size": 10, "color": "#1A1A1A", "wrap": True},
                }
            )
        return {"id": "uml.notes", "z": 30, "objects": objs}


def compose_activity_diagram(
    model: UMLActivityDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: ActivityDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose an activity diagram from a typed UML model.

    Args:
        model: A validated `UMLActivityDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `ActivityDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.
    """
    opts = options or ActivityDiagramOptions()
    composer = _ActivityDiagramComposer(model, opts, canvas_size)
    return composer.compose()
