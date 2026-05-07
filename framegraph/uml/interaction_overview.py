"""Interaction-overview-diagram composer — Phase E.3.

Per UML 2.5.1 §17.6.7, an interaction-overview diagram is an
activity-flow whose action nodes are *interaction uses* (`ref`) or
*inline sequence diagrams* (`sd`). The composer reuses the
HierarchicalComposer from Phase A so the standard activity-style
nodes (initial, decision, fork, …) align with the activity-diagram
implementation, and emits `ref` / `sd` nodes as
`uml.fragment_frame` primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLInteractionOverviewModel,
    UMLInteractionOverviewNode,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class InteractionOverviewOptions:
    """Tunable parameters for the interaction-overview composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        action_min_width: Minimum width of an interaction-use frame.
        action_height: Height of an interaction-use frame.
        decision_size: Width and height of decision/merge diamond.
        terminal_size: Width and height of initial/final disc.
        bar_length: Length of fork/join bar (long axis).
        body_padding: Horizontal padding around interaction-use names.
        name_size: Font size for interaction-use names.
        layout: `sugiyama` or `manual`.
    """

    layer_height: float = 110.0
    node_gap: float = 60.0
    action_min_width: float = 200.0
    action_height: float = 70.0
    decision_size: float = 56.0
    terminal_size: float = 28.0
    bar_length: float = 110.0
    body_padding: float = 14.0
    name_size: float = 12.0
    layout: str = "sugiyama"


class _InteractionOverviewComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for interaction-overview diagrams."""

    def __init__(
        self,
        model: UMLInteractionOverviewModel,
        opts: InteractionOverviewOptions,
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
        self._nodes_by_id: dict[str, UMLInteractionOverviewNode] = {n.id: n for n in model.nodes}

    def _extract_layout_nodes(self) -> list[str]:
        return [n.id for n in self.model.nodes]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        return [(e.from_id, e.to_id) for e in self.model.edges]

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        n = self._nodes_by_id[node_id]
        if n.kind in ("interaction_use", "sd_inline"):
            label = n.name or ""
            w = max(
                self.opts.action_min_width,
                str_width(label, self.opts.name_size, bold=True) + 2 * self.opts.body_padding + 36,
            )
            return (w, self.opts.action_height)
        if n.kind in ("decision", "merge"):
            return (self.opts.decision_size, self.opts.decision_size)
        if n.kind in ("fork", "join"):
            return (self.opts.bar_length, 12.0)
        return (self.opts.terminal_size, self.opts.terminal_size)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        n = self._nodes_by_id[node_id]
        x, y, w, h = box

        if n.kind == "interaction_use":
            return {
                "type": "uml.fragment_frame",
                "id": n.id,
                "box": [x, y, w, h],
                "kind": "ref",
                "operands": [n.name or ""],
            }
        if n.kind == "sd_inline":
            return {
                "type": "uml.fragment_frame",
                "id": n.id,
                "box": [x, y, w, h],
                "kind": "sd",
                "operands": [n.name or ""],
            }
        if n.kind in ("decision", "merge", "fork", "join"):
            return {
                "type": "uml.activity_node",
                "id": n.id,
                "box": [x, y, w, h],
                "kind": n.kind,
                **({"name": n.name} if n.name else {}),
            }
        # initial / final
        return {
            "type": "uml.activity_node",
            "id": n.id,
            "box": [x, y, w, h],
            "kind": n.kind,
            **({"name": n.name} if n.name else {}),
        }

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for e in self.model.edges:
            edges.append(
                connector_object(
                    e.id,
                    e.from_id,
                    e.to_id,
                    arrow_end_kind="open_arrow",
                )
            )
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        n = self._nodes_by_id[node_id]
        if n.position is None:
            return None
        return (n.position.x, n.position.y)

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        if not self.model.notes:
            return []
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
        return [{"id": "uml.notes", "z": 30, "objects": objs}]


def compose_interaction_overview(
    model: UMLInteractionOverviewModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: InteractionOverviewOptions | None = None,
) -> ComposedDiagram:
    """Compose an interaction-overview diagram from a typed UML model."""
    opts = options or InteractionOverviewOptions()
    composer = _InteractionOverviewComposer(model, opts, canvas_size)
    return composer.compose()
