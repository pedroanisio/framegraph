"""Profile-diagram composer — Phase E.4 of the UML support architecture.

Reads a `UMLProfileDiagramModel` and produces a fully-laid-out
`visual` block. Stereotypes render as `«stereotype»` boxes,
metaclasses as `«metaclass»` boxes, and Extensions as connectors
with a filled-triangle arrow at the metaclass end.

Layout strategy: Sugiyama hierarchical with metaclasses above their
extending stereotypes (so that the extension arrow points up).
Required extensions render with a `{required}` constraint annotation
appended to the connector id (the renderer surfaces the constraint
in label text on a follow-up; for now we encode it in the id
prefix so tests can verify it propagated).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLMetaclassRef,
    UMLProfileDiagramModel,
    UMLStereotype,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class ProfileDiagramOptions:
    """Tunable parameters for the profile-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        node_min_width: Minimum width of a stereotype/metaclass box.
        node_min_height: Minimum height (when no properties).
        property_line_height: Height per property line in stereotypes.
        body_padding: Horizontal padding around node names.
        name_size: Font size for node names.
        property_size: Font size for property labels.
        layout: `sugiyama` or `manual`.
    """

    layer_height: float = 130.0
    node_gap: float = 60.0
    node_min_width: float = 160.0
    node_min_height: float = 70.0
    property_line_height: float = 18.0
    body_padding: float = 14.0
    name_size: float = 13.0
    property_size: float = 11.0
    layout: str = "sugiyama"


class _ProfileDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for profile diagrams."""

    def __init__(
        self,
        model: UMLProfileDiagramModel,
        opts: ProfileDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
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
        self._stereotypes_by_id: dict[str, UMLStereotype] = {s.id: s for s in model.stereotypes}
        self._metaclasses_by_id: dict[str, UMLMetaclassRef] = {m.id: m for m in model.metaclasses}

    def _extract_layout_nodes(self) -> list[str]:
        return [s.id for s in self.model.stereotypes] + [m.id for m in self.model.metaclasses]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        # Metaclass above stereotype: edge points (metaclass → stereotype)
        # so Sugiyama puts the metaclass on a smaller y.
        return [(ext.to_id, ext.from_id) for ext in self.model.extensions]

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        if node_id in self._stereotypes_by_id:
            s = self._stereotypes_by_id[node_id]
            name_w = str_width(s.name, self.opts.name_size, bold=True)
            width = max(self.opts.node_min_width, name_w + 2 * self.opts.body_padding)
            n_props = len(s.properties)
            height = self.opts.node_min_height + n_props * self.opts.property_line_height
            return (width, height)
        m = self._metaclasses_by_id[node_id]
        name_w = str_width(m.name, self.opts.name_size, bold=True)
        width = max(self.opts.node_min_width, name_w + 2 * self.opts.body_padding)
        return (width, self.opts.node_min_height)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        x, y, w, h = box
        if node_id in self._stereotypes_by_id:
            s = self._stereotypes_by_id[node_id]
            obj: dict[str, Any] = {
                "type": "uml.classifier_box",
                "id": s.id,
                "box": [x, y, w, h],
                "name": s.name,
                "stereotype": "stereotype",
            }
            if s.properties:
                obj["attributes"] = [{"name": p, "visibility": "public"} for p in s.properties]
            return obj
        m = self._metaclasses_by_id[node_id]
        return {
            "type": "uml.classifier_box",
            "id": m.id,
            "box": [x, y, w, h],
            "name": m.name,
            "stereotype": "metaclass",
        }

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for ext in self.model.extensions:
            edge_id = f"{ext.id}__required" if ext.required else ext.id
            # Per UML, the filled-triangle arrow is at the metaclass
            # end (the supplier). The model declares
            # from_id = stereotype, to_id = metaclass, so the arrow
            # is at the *target* end.
            edges.append(
                connector_object(
                    edge_id,
                    ext.from_id,
                    ext.to_id,
                    arrow_end_kind="filled_triangle",
                )
            )
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        if node_id in self._stereotypes_by_id:
            s = self._stereotypes_by_id[node_id]
            return (s.position.x, s.position.y) if s.position else None
        m = self._metaclasses_by_id[node_id]
        return (m.position.x, m.position.y) if m.position else None

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


def compose_profile_diagram(
    model: UMLProfileDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: ProfileDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a profile diagram from a typed UML model."""
    opts = options or ProfileDiagramOptions()
    composer = _ProfileDiagramComposer(model, opts, canvas_size)
    return composer.compose()
