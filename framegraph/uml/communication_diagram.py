"""Communication-diagram composer — Phase E.2 of the UML support architecture.

Reads a `UMLCommunicationDiagramModel` and produces a fully-laid-out
`visual` block. Lifelines render as labelled rectangles (similar
to sequence-diagram heads) at free-form positions; messages render
as connectors carrying a `sequence: name` label near the midpoint.

Layout strategy
---------------
- Lifelines with explicit `position` keep that position.
- Unpinned lifelines are arranged on a circle around the canvas
  center.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLCommLifeline,
    UMLCommunicationDiagramModel,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class CommunicationDiagramOptions:
    """Tunable parameters for the communication-diagram composer.

    Attributes:
        lifeline_min_width: Minimum width of a lifeline box.
        lifeline_height: Height of a lifeline box.
        lifeline_padding: Horizontal padding around the head label.
        circle_radius_ratio: Fraction of canvas-min-axis used as the
            circle radius for unpinned lifelines.
        name_size: Font size for the lifeline name.
    """

    lifeline_min_width: float = 130.0
    lifeline_height: float = 44.0
    lifeline_padding: float = 14.0
    circle_radius_ratio: float = 0.32
    name_size: float = 12.0


class _CommunicationDiagramComposer:
    """Free-form-layout composer for communication diagrams."""

    def __init__(
        self,
        model: UMLCommunicationDiagramModel,
        opts: CommunicationDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the communication model, options, and canvas size."""
        self.model = model
        self.opts = opts
        self.canvas_size = canvas_size

    def _lifeline_widths(self) -> dict[str, float]:
        widths: dict[str, float] = {}
        for ll in self.model.lifelines:
            label = f"{ll.name}:{ll.type_name}" if ll.type_name else ll.name
            label_w = str_width(label, self.opts.name_size, bold=True)
            widths[ll.id] = max(
                self.opts.lifeline_min_width,
                label_w + 2 * self.opts.lifeline_padding,
            )
        return widths

    def _lifeline_positions(self) -> dict[str, tuple[float, float]]:
        """Resolve a top-left position for each lifeline.

        Pinned lifelines keep their declared `position`. Unpinned
        lifelines are spread around a circle centered on the canvas.
        """
        positions: dict[str, tuple[float, float]] = {}
        unpinned: list[UMLCommLifeline] = []
        for ll in self.model.lifelines:
            if ll.position is not None:
                positions[ll.id] = (ll.position.x, ll.position.y)
            else:
                unpinned.append(ll)

        if unpinned:
            cw, ch = self.canvas_size
            cx, cy = cw / 2, ch / 2
            radius = min(cw, ch) * self.opts.circle_radius_ratio
            n = len(unpinned)
            for i, ll in enumerate(unpinned):
                angle = -math.pi / 2 + 2 * math.pi * i / n
                x = cx + radius * math.cos(angle)
                y = cy + radius * math.sin(angle)
                # Convert center-coords to top-left.
                positions[ll.id] = (x, y - self.opts.lifeline_height / 2)
        return positions

    def compose(self) -> ComposedDiagram:
        """Lay out lifelines and messages into a composed visual block.

        Emits an edges layer (z=10), a lifelines layer (z=20), and an
        optional notes layer (z=30).
        """
        widths = self._lifeline_widths()
        positions = self._lifeline_positions()
        layers: list[dict[str, Any]] = []

        # Edges first (they sit behind the lifeline heads).
        edge_objs = self._emit_messages(positions, widths)
        layers.append({"id": "uml.edges", "z": 10, "objects": edge_objs})

        # Lifelines (z=20).
        ll_objs: list[dict[str, Any]] = []
        for ll in self.model.lifelines:
            x, y = positions[ll.id]
            w = widths[ll.id]
            obj: dict[str, Any] = {
                "type": "uml.lifeline",
                "id": ll.id,
                # Lifeline primitive draws a head + dashed line; we
                # collapse the dashed-line section to zero by setting
                # head_height == box_height.
                "box": [x - w / 2, y, w, self.opts.lifeline_height],
                "name": ll.name,
                "head_height": self.opts.lifeline_height,
            }
            if ll.type_name:
                obj["type_name"] = ll.type_name
            ll_objs.append(obj)
        layers.append({"id": "uml.classifiers", "z": 20, "objects": ll_objs})

        # Notes layer.
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)

        visual: dict[str, Any] = {"tokens": {}, "layers": layers}
        return ComposedDiagram(
            visual=visual,
            layout_result=None,
            node_dimensions={lid: (widths[lid], self.opts.lifeline_height) for lid in widths},
        )

    def _emit_messages(
        self,
        positions: dict[str, tuple[float, float]],
        widths: dict[str, float],
    ) -> list[dict[str, Any]]:
        objs: list[dict[str, Any]] = []
        for m in self.model.messages:
            arrow_kind = "filled_triangle" if m.kind == "sync" else "open_arrow"
            objs.append(
                connector_object(
                    m.id,
                    m.from_id,
                    m.to_id,
                    arrow_end_kind=arrow_kind,
                )
            )
            # Label: "1.1: name" (or just "1.1" when name is absent).
            x_from, y_from = positions[m.from_id]
            x_to, y_to = positions[m.to_id]
            mx = (x_from + x_to) / 2
            my = (y_from + y_to) / 2
            label = f"{m.sequence}: {m.name}" if m.name else m.sequence
            objs.append(
                {
                    "type": "text",
                    "id": f"{m.id}__label",
                    "decorative": True,
                    "box": [mx - 80, my - 16, 160, 20],
                    "text": label,
                    "style": {
                        "size": 10,
                        "color": "#1A1A1A",
                        "align": "center",
                    },
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


def compose_communication_diagram(
    model: UMLCommunicationDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: CommunicationDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a communication diagram from a typed UML model."""
    opts = options or CommunicationDiagramOptions()
    composer = _CommunicationDiagramComposer(model, opts, canvas_size)
    return composer.compose()
