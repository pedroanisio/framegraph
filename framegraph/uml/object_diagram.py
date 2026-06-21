"""Object-diagram composer — Phase E.6 of the UML support architecture.

Reads a `UMLObjectDiagramModel` and produces a fully-laid-out
`visual` block. Instance specifications render as classifier-box
primitives with `name:Type` underlined headers and slot lines in
the body compartment. Links render as plain lines (no arrowhead by
default — instance-level associations don't carry navigation
arrows in standard UML).

Layout strategy: Sugiyama hierarchical on the link graph (any
declared `from` → `to` orientation drives the y-axis). Instances
without links land in their own component.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLInstance,
    UMLObjectDiagramModel,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class ObjectDiagramOptions:
    """Tunable parameters for the object-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        node_min_width: Minimum width of an instance box.
        header_height: Header height (instance name).
        slot_line_height: Height per slot line in the body.
        body_padding: Horizontal padding around slot lines.
        name_size: Font size for the instance header.
        slot_size: Font size for slot lines.
        layout: `sugiyama` or `manual`.
    """

    layer_height: float = 130.0
    node_gap: float = 60.0
    node_min_width: float = 180.0
    header_height: float = 36.0
    slot_line_height: float = 18.0
    body_padding: float = 12.0
    name_size: float = 13.0
    slot_size: float = 11.0
    layout: str = "sugiyama"


class _ObjectDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for object diagrams."""

    def __init__(
        self,
        model: UMLObjectDiagramModel,
        opts: ObjectDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the object model and options for layout."""
        super().__init__(
            canvas_size=canvas_size,
            layer_height=opts.layer_height,
            node_gap=opts.node_gap,
            node_min_width=opts.node_min_width,
            margin=40.0,
            layout=opts.layout,
        )
        self.model = model
        self.opts = opts
        self._instances_by_id: dict[str, UMLInstance] = {i.id: i for i in model.instances}

    def _instance_label(self, inst: UMLInstance) -> str:
        if inst.name:
            return f"{inst.name}:{inst.type_name}"
        return f":{inst.type_name}"

    def _extract_layout_nodes(self) -> list[str]:
        return [i.id for i in self.model.instances]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        return [(ln.from_id, ln.to_id) for ln in self.model.links]

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        inst = self._instances_by_id[node_id]
        label = self._instance_label(inst)
        # Body width must accommodate header label and the widest slot
        # line.
        widths = [str_width(label, self.opts.name_size, bold=True)]
        for slot in inst.slots:
            line = f"{slot.name} = {slot.value}" if slot.value else slot.name
            widths.append(str_width(line, self.opts.slot_size))
        body_w = max(widths) + 2 * self.opts.body_padding
        width = max(self.opts.node_min_width, body_w)
        height = self.opts.header_height + len(inst.slots) * self.opts.slot_line_height
        if not inst.slots:
            height += self.opts.slot_line_height  # min one body row
        return (width, height)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        inst = self._instances_by_id[node_id]
        x, y, w, h = box
        # Use uml.classifier_box with the instance label. Slots emit
        # as attributes for the body compartment.
        attrs = [
            {
                "name": s.name,
                "default": s.value,
                "visibility": "public",
            }
            for s in inst.slots
        ]
        return {
            "type": "uml.classifier_box",
            "id": inst.id,
            "box": [x, y, w, h],
            "name": self._instance_label(inst),
            "attributes": attrs,
        }

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for ln in self.model.links:
            edges.append(connector_object(ln.id, ln.from_id, ln.to_id))
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        inst = self._instances_by_id[node_id]
        if inst.position is None:
            return None
        return (inst.position.x, inst.position.y)

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


def compose_object_diagram(
    model: UMLObjectDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: ObjectDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose an object diagram from a typed UML model."""
    opts = options or ObjectDiagramOptions()
    composer = _ObjectDiagramComposer(model, opts, canvas_size)
    return composer.compose()
