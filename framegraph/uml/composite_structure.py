"""Composite-structure-diagram composer — Phase E.5.

Reads a `UMLCompositeStructureModel` and produces a fully-laid-out
`visual` block with the enclosing classifier as an outer frame and
the parts/ports/connectors arranged inside.

Layout strategy
---------------
- Outer frame: a single classifier-box at the canvas center (margin
  on each side).
- Parts: laid out in a grid inside the frame body. Two columns by
  default; the composer tiles parts left-to-right, top-to-bottom.
- Boundary ports: clipped to the four faces of the outer frame
  (north, south, east, west) using the port's declared `side`.
- Connectors: plain lines between any two declared endpoints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLCompositeStructureModel,
    UMLPort,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    connector_object,
)


@dataclass(frozen=True)
class CompositeStructureOptions:
    """Tunable parameters for the composite-structure composer.

    Attributes:
        margin: Outer page margin (px).
        frame_padding: Horizontal+vertical padding inside the
            outer frame around the parts grid.
        part_width: Width of each part box.
        part_height: Height of each part box.
        part_gap: Gap between parts in the grid.
        port_size: Width and height of a port square.
        columns: Number of columns in the parts grid (default 2).
        name_size: Font size for outer frame and part names.
    """

    margin: float = 60.0
    frame_padding: float = 36.0
    part_width: float = 200.0
    part_height: float = 100.0
    part_gap: float = 30.0
    port_size: float = 12.0
    columns: int = 2
    name_size: float = 14.0


class _CompositeStructureComposer:
    """Free-form-layout composer for composite-structure diagrams."""

    def __init__(
        self,
        model: UMLCompositeStructureModel,
        opts: CompositeStructureOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the composite-structure model, options, and canvas size."""
        self.model = model
        self.opts = opts
        self.canvas_size = canvas_size

    def _frame_box(self) -> tuple[float, float, float, float]:
        cw, ch = self.canvas_size
        # Use the canvas minus margin as the frame box.
        x = self.opts.margin
        y = self.opts.margin
        w = cw - 2 * self.opts.margin
        h = ch - 2 * self.opts.margin
        return (x, y, w, h)

    def _grid_dimensions(self) -> tuple[int, int]:
        n = len(self.model.parts)
        cols = min(self.opts.columns, n) if n else 1
        rows = math.ceil(n / cols) if cols else 1
        return (cols, rows)

    def _part_position(
        self,
        i: int,
        frame_box: tuple[float, float, float, float],
    ) -> tuple[float, float]:
        """Compute top-left of part i inside the frame."""
        fx, fy, fw, fh = frame_box
        cols, rows = self._grid_dimensions()
        # Reserve space at the top of the frame for the classifier
        # name/header (~36 px).
        header_h = 40.0
        inner_x = fx + self.opts.frame_padding
        inner_y = fy + header_h
        inner_w = fw - 2 * self.opts.frame_padding
        # Distribute parts: total used width = cols*part_width +
        # (cols-1)*gap. Center horizontally.
        used_w = cols * self.opts.part_width + max(0, cols - 1) * self.opts.part_gap
        x_offset = (inner_w - used_w) / 2
        col = i % cols
        row = i // cols
        x = inner_x + x_offset + col * (self.opts.part_width + self.opts.part_gap)
        y = inner_y + row * (self.opts.part_height + self.opts.part_gap)
        return (x, y)

    def _boundary_port_position(
        self,
        port: UMLPort,
        frame_box: tuple[float, float, float, float],
        idx_on_side: int,
        total_on_side: int,
    ) -> tuple[float, float]:
        """Place a port on the outer frame's boundary."""
        fx, fy, fw, fh = frame_box
        ps = self.opts.port_size
        # Distribute ports evenly along the chosen side.
        if total_on_side <= 0:
            total_on_side = 1
        frac = (idx_on_side + 1) / (total_on_side + 1)
        if port.side == "north":
            return (fx + fw * frac - ps / 2, fy - ps / 2)
        if port.side == "south":
            return (fx + fw * frac - ps / 2, fy + fh - ps / 2)
        if port.side == "east":
            return (fx + fw - ps / 2, fy + fh * frac - ps / 2)
        # west (default)
        return (fx - ps / 2, fy + fh * frac - ps / 2)

    def _part_port_position(
        self,
        port_id: str,
        part_box: tuple[float, float, float, float],
        idx_on_part: int,
        total_on_part: int,
    ) -> tuple[float, float]:
        """Place a port on a part's east edge (default)."""
        px, py, pw, ph = part_box
        ps = self.opts.port_size
        if total_on_part <= 0:
            total_on_part = 1
        frac = (idx_on_part + 1) / (total_on_part + 1)
        return (px + pw - ps / 2, py + ph * frac - ps / 2)

    def compose(self) -> ComposedDiagram:
        """Lay out the outer frame, parts, ports, connectors, and notes.

        Emits frame (z=5), connectors (z=15), parts (z=20), ports
        (z=25), and an optional notes layer (z=30).
        """
        layers: list[dict[str, Any]] = []
        frame_box = self._frame_box()
        fx, fy, fw, fh = frame_box

        # Outer frame layer (z=5): outer classifier box.
        outer = {
            "type": "uml.classifier_box",
            "id": self.model.classifier_id,
            "box": list(frame_box),
            "name": self.model.classifier_name,
        }
        layers.append({"id": "uml.frame", "z": 5, "objects": [outer]})

        # Parts (z=20) — placed inside the frame.
        part_objs: list[dict[str, Any]] = []
        part_boxes: dict[str, tuple[float, float, float, float]] = {}
        for i, p in enumerate(self.model.parts):
            if p.position is not None:
                px, py = p.position.x, p.position.y
            else:
                px, py = self._part_position(i, frame_box)
            pb = (px, py, self.opts.part_width, self.opts.part_height)
            part_boxes[p.id] = pb
            label = f"{p.name}:{p.type_name}" if p.type_name else p.name
            part_objs.append(
                {
                    "type": "uml.classifier_box",
                    "id": p.id,
                    "box": list(pb),
                    "name": label,
                }
            )
        layers.append({"id": "uml.parts", "z": 20, "objects": part_objs})

        # Ports (z=25) — boundary + per-part.
        port_objs: list[dict[str, Any]] = []
        # Group boundary ports by side for even distribution.
        ports_by_side: dict[str, list[UMLPort]] = {}
        for port in self.model.ports:
            ports_by_side.setdefault(port.side, []).append(port)
        port_boxes: dict[str, tuple[float, float, float, float]] = {}
        for side_ports in ports_by_side.values():
            for j, port in enumerate(side_ports):
                ppx, ppy = self._boundary_port_position(port, frame_box, j, len(side_ports))
                pb = (ppx, ppy, self.opts.port_size, self.opts.port_size)
                port_boxes[port.id] = pb
                port_objs.append(
                    {
                        "type": "rect",
                        "id": port.id,
                        "box": list(pb),
                        "fill": "#FFFFFF",
                        "stroke": {"color": "#1A1A1A", "width": 1.0},
                    }
                )
        # Per-part ports (placed on the part's east edge).
        for part in self.model.parts:
            if not part.ports:
                continue
            part_box = part_boxes.get(part.id)
            if part_box is None:
                continue
            for j, port_id in enumerate(part.ports):
                ppx, ppy = self._part_port_position(port_id, part_box, j, len(part.ports))
                port_box = (ppx, ppy, self.opts.port_size, self.opts.port_size)
                port_boxes[port_id] = port_box
                port_objs.append(
                    {
                        "type": "rect",
                        "id": port_id,
                        "box": list(port_box),
                        "fill": "#FFFFFF",
                        "stroke": {"color": "#1A1A1A", "width": 1.0},
                    }
                )
        if port_objs:
            layers.append({"id": "uml.ports", "z": 25, "objects": port_objs})

        # Connectors (z=15 — behind parts so they don't overdraw).
        edge_objs: list[dict[str, Any]] = []
        for c in self.model.connectors:
            edge_objs.append(connector_object(c.id, c.from_id, c.to_id))
        if edge_objs:
            layers.append({"id": "uml.edges", "z": 15, "objects": edge_objs})

        # Notes (z=30).
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)

        visual: dict[str, Any] = {"tokens": {}, "layers": layers}
        return ComposedDiagram(
            visual=visual,
            layout_result=None,
            node_dimensions={
                p.id: (self.opts.part_width, self.opts.part_height) for p in self.model.parts
            },
        )

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


def compose_composite_structure(
    model: UMLCompositeStructureModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: CompositeStructureOptions | None = None,
) -> ComposedDiagram:
    """Compose a composite-structure diagram from a typed UML model."""
    opts = options or CompositeStructureOptions()
    composer = _CompositeStructureComposer(model, opts, canvas_size)
    return composer.compose()
