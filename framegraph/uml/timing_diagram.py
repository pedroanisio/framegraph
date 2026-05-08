"""Timing-diagram composer — Phase E.1 of the UML support architecture.

Reads a `UMLTimingDiagramModel` and produces a fully-laid-out
`visual` block with horizontal swim-lanes (one per lifeline) carrying
state-change step lines along a left-to-right time axis.

Like the sequence-diagram composer (Phase D) and unlike the Phase
A–C composers, this composer does NOT use Sugiyama. The layout is
deterministic from `lifelines` order and `changes[].at` values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLTimingChange,
    UMLTimingDiagramModel,
    UMLTimingLifeline,
)
from framegraph.uml._composer_base import ComposedDiagram


@dataclass(frozen=True)
class TimingDiagramOptions:
    """Tunable parameters for the timing-diagram composer.

    Attributes:
        margin: Outer page margin (px).
        lane_height: Height of each lifeline lane.
        lane_gap: Vertical gap between adjacent lanes.
        lane_width: Total horizontal width of the time axis (label
            column + plot area).
        label_width: Width reserved for the state-name label column
            on the left of each lane.
        change_stroke_width: Line width for state-change step lines.
    """

    margin: float = 50.0
    lane_height: float = 130.0
    lane_gap: float = 24.0
    lane_width: float = 900.0
    label_width: float = 90.0
    change_stroke_width: float = 1.5


class _TimingDiagramComposer:
    """Custom composer for timing diagrams.

    Renders one lane per lifeline; the lane stacks the declared
    states vertically. Time progresses left-to-right inside each
    lane. State-change events draw a step-function: a horizontal
    line at the current state's y, then a vertical jump at the
    change's x to the new state's y.
    """

    def __init__(
        self,
        model: UMLTimingDiagramModel,
        opts: TimingDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        self.model = model
        self.opts = opts
        self.canvas_size = canvas_size

    # ── Layout helpers ──────────────────────────────────────────

    def _time_range(self) -> tuple[float, float]:
        if not self.model.changes:
            return (0.0, 1.0)
        ats = [c.at for c in self.model.changes]
        return (min(ats), max(ats))

    def _x_for(self, t: float, lane_x: float, plot_x_width: float) -> float:
        t_min, t_max = self._time_range()
        if t_max == t_min:
            return lane_x + plot_x_width / 2
        return lane_x + (t - t_min) / (t_max - t_min) * plot_x_width

    def _lane_box(self, idx: int) -> tuple[float, float, float, float]:
        x = self.opts.margin
        y = self.opts.margin + idx * (self.opts.lane_height + self.opts.lane_gap)
        return (x, y, self.opts.lane_width, self.opts.lane_height)

    def _state_y_in_lane(
        self,
        ll: UMLTimingLifeline,
        state_name: str,
        lane_box: tuple[float, float, float, float],
    ) -> float:
        """Return the y-coordinate of the given state's row inside the lane."""
        _, ly, _, lh = lane_box
        # Top portion of the lane is reserved for the lifeline name
        # in the renderer (12pt font + 12 px pad). Distribute states
        # in the remaining vertical band.
        name_band = 24.0
        states_top = ly + name_band
        states_h = lh - name_band - 8
        n = len(ll.states)
        slot_h = states_h / n
        idx = ll.states.index(state_name)
        # Place the row at the slot's vertical center.
        return states_top + idx * slot_h + slot_h / 2

    # ── Visual emission ─────────────────────────────────────────

    def compose(self) -> ComposedDiagram:
        layers: list[dict[str, Any]] = []

        # Lane backgrounds + state grids (z=10).
        lane_objs: list[dict[str, Any]] = []
        lane_boxes: dict[str, tuple[float, float, float, float]] = {}
        for i, ll in enumerate(self.model.lifelines):
            lb = self._lane_box(i)
            lane_boxes[ll.id] = lb
            lane_objs.append(
                {
                    "type": "uml.timing_lane",
                    "id": ll.id,
                    "box": list(lb),
                    "name": ll.name,
                    "states": list(ll.states),
                    "label_width": self.opts.label_width,
                }
            )
        layers.append({"id": "uml.lanes", "z": 10, "objects": lane_objs})

        # State-change step lines (z=20).
        change_objs = self._emit_changes(lane_boxes)
        layers.append({"id": "uml.changes", "z": 20, "objects": change_objs})

        # Notes layer (z=30).
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)

        visual: dict[str, Any] = {"tokens": {}, "layers": layers}
        return ComposedDiagram(
            visual=visual,
            layout_result=None,
            node_dimensions={
                ll.id: (self.opts.lane_width, self.opts.lane_height) for ll in self.model.lifelines
            },
        )

    def _emit_changes(
        self,
        lane_boxes: dict[str, tuple[float, float, float, float]],
    ) -> list[dict[str, Any]]:
        """Emit step-function lines for each lifeline's state changes.

        For lifeline `ll` with sorted-by-time changes
        `[(t1, s1), (t2, s2), …]`, emit a horizontal segment at y=s1
        from x(t1) to x(t2), then a vertical segment at x(t2) from
        y=s1 to y=s2, and so on. The trailing segment extends from
        the last change to the lane's right edge.
        """
        objs: list[dict[str, Any]] = []
        # Group changes by lifeline.
        by_lifeline: dict[str, list[UMLTimingChange]] = {}
        for c in self.model.changes:
            by_lifeline.setdefault(c.lifeline, []).append(c)

        for ll in self.model.lifelines:
            lb = lane_boxes[ll.id]
            lx, _, lw, _ = lb
            plot_x = lx + self.opts.label_width
            plot_w = lw - self.opts.label_width
            sorted_changes = sorted(by_lifeline.get(ll.id, []), key=lambda c: c.at)
            if not sorted_changes:
                continue

            stroke = {"color": "#1A1A1A", "width": self.opts.change_stroke_width}

            # Initial segment: from plot_x to first change's x at first state's y.
            prev_x = plot_x
            prev_y = self._state_y_in_lane(ll, sorted_changes[0].state, lb)
            for i, c in enumerate(sorted_changes):
                cx = self._x_for(c.at, plot_x, plot_w)
                cy = self._state_y_in_lane(ll, c.state, lb)
                # Horizontal segment at prev state's y (from prev_x to cx).
                if cx > prev_x + 0.01:
                    objs.append(
                        {
                            "type": "line",
                            "id": f"{ll.id}__h{i}",
                            "from": [prev_x, prev_y],
                            "to": [cx, prev_y],
                            "stroke": stroke,
                        }
                    )
                # Vertical step from prev_y to cy at cx (only when the
                # state actually changes).
                if abs(cy - prev_y) > 0.01:
                    objs.append(
                        {
                            "type": "line",
                            "id": f"{ll.id}__v{i}",
                            "from": [cx, prev_y],
                            "to": [cx, cy],
                            "stroke": stroke,
                        }
                    )
                prev_x = cx
                prev_y = cy

            # Trailing segment from last change to lane's right edge.
            right_edge = plot_x + plot_w
            if right_edge > prev_x + 0.01:
                objs.append(
                    {
                        "type": "line",
                        "id": f"{ll.id}__tail",
                        "from": [prev_x, prev_y],
                        "to": [right_edge, prev_y],
                        "stroke": stroke,
                    }
                )
        return objs

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


def compose_timing_diagram(
    model: UMLTimingDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: TimingDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a timing diagram from a typed UML model.

    Args:
        model: A validated `UMLTimingDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `TimingDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.
    """
    opts = options or TimingDiagramOptions()
    composer = _TimingDiagramComposer(model, opts, canvas_size)
    return composer.compose()
