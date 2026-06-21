"""State-machine-diagram composer — Phase C.4 of the UML support architecture.

Reads a `UMLStateMachineModel` (from framegraph._uml) and produces
a fully-laid-out FrameGraph `visual` block. Uses the Sugiyama
hierarchical layout from `framegraph.layout` on the transition
graph (transition source above target).

Conventions
-----------
- Simple state: rounded rectangle with the state name.
- Composite state: rounded rectangle with a header band — sub-states
  sit below in the same Sugiyama graph (the renderer does not
  physically nest them in this commit; nesting is a follow-up).
- Pseudostate glyphs: initial disc, final bullseye, choice diamond,
  junction disc, fork/join bar, shallow/deep history `H` / `H*`,
  entry/exit point circles, terminate cross.
- Transitions render as solid lines with an open-arrow marker. The
  composer carries the `trigger [guard] / effect` label on the
  connector when supported (currently the connector primitive does
  not surface mid-line labels — the composer drops them with a
  TODO; rendering of transition labels is a Phase C.4.1 follow-up).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLPseudostate,
    UMLState,
    UMLStateMachineModel,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class StateMachineOptions:
    """Tunable parameters for the state-machine composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        state_min_width: Minimum width of a state rounded rectangle.
        state_min_height: Minimum height of a state rounded rectangle.
        composite_min_height: Minimum height when the state is
            composite (carries sub-states).
        pseudostate_size: Width and height of pseudostate glyphs
            (circles, diamonds, etc.).
        bar_length: Length of a fork/join bar (long axis).
        body_padding: Horizontal padding around the state name.
        name_size: Font size for the state name.
        action_size: Font size for entry/exit/do action labels.
        layout: `sugiyama` or `manual`.
    """

    layer_height: float = 130.0
    node_gap: float = 70.0
    state_min_width: float = 160.0
    state_min_height: float = 70.0
    composite_min_height: float = 110.0
    pseudostate_size: float = 28.0
    bar_length: float = 110.0
    body_padding: float = 14.0
    name_size: float = 13.0
    action_size: float = 10.0
    layout: str = "sugiyama"


class _StateMachineComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for state machines.

    Layout-driving edges are transitions — the source sits above the
    target. Pseudostates participate in the same graph; they are
    distinguished from states only at primitive emission time.
    """

    def __init__(
        self,
        model: UMLStateMachineModel,
        opts: StateMachineOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the state-machine model and options, indexing states and pseudostates."""
        super().__init__(
            canvas_size=canvas_size,
            layer_height=opts.layer_height,
            node_gap=opts.node_gap,
            node_min_width=opts.state_min_width,
            margin=40.0,
            layout=opts.layout,
        )
        self.model = model
        self.opts = opts
        self._states_by_id: dict[str, UMLState] = {s.id: s for s in model.states}
        self._pseudo_by_id: dict[str, UMLPseudostate] = {p.id: p for p in model.pseudostates}

    # ── HierarchicalComposer hooks ──────────────────────────────

    def _extract_layout_nodes(self) -> list[str]:
        # Both states and pseudostates participate in the layout.
        return [s.id for s in self.model.states] + [p.id for p in self.model.pseudostates]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        return [(t.from_id, t.to_id) for t in self.model.transitions]

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        if node_id in self._states_by_id:
            s = self._states_by_id[node_id]
            name_w = str_width(s.name, self.opts.name_size, bold=True)
            width = max(self.opts.state_min_width, name_w + 2 * self.opts.body_padding)
            # Reserve room for action lines if any.
            action_count = sum(1 for v in (s.entry, s.exit_action, s.do) if v)
            base_h = self.opts.state_min_height
            if s.regions:
                base_h = max(base_h, self.opts.composite_min_height)
            extra = max(0, action_count) * (self.opts.action_size + 4)
            return (width, base_h + extra)
        # Pseudostate
        p = self._pseudo_by_id[node_id]
        if p.kind in ("fork", "join"):
            return (self.opts.bar_length, 12.0)
        return (self.opts.pseudostate_size, self.opts.pseudostate_size)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        x, y, w, h = box
        if node_id in self._states_by_id:
            s = self._states_by_id[node_id]
            result: dict[str, Any] = {
                "type": "uml.state_box",
                "id": s.id,
                "box": [x, y, w, h],
                "name": s.name,
            }
            if s.entry:
                result["entry"] = s.entry
            if s.exit_action:
                result["exit"] = s.exit_action
            if s.do:
                result["do"] = s.do
            if s.regions:
                result["composite"] = True
            return result
        # Pseudostate
        p = self._pseudo_by_id[node_id]
        result = {
            "type": "uml.pseudostate",
            "id": p.id,
            "box": [x, y, w, h],
            "kind": p.kind,
        }
        if p.name:
            result["name"] = p.name
        return result

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for t in self.model.transitions:
            edges.append(
                connector_object(
                    t.id,
                    t.from_id,
                    t.to_id,
                    arrow_end_kind="open_arrow",
                    dashed=(t.kind == "internal"),
                )
            )
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        if node_id in self._states_by_id:
            s = self._states_by_id[node_id]
            if s.position is None:
                return None
            return (s.position.x, s.position.y)
        p = self._pseudo_by_id[node_id]
        if p.position is None:
            return None
        return (p.position.x, p.position.y)

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


def compose_state_machine(
    model: UMLStateMachineModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: StateMachineOptions | None = None,
) -> ComposedDiagram:
    """Compose a state-machine diagram from a typed UML model.

    Args:
        model: A validated `UMLStateMachineModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `StateMachineOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.
    """
    opts = options or StateMachineOptions()
    composer = _StateMachineComposer(model, opts, canvas_size)
    return composer.compose()
