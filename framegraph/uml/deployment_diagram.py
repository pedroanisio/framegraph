"""Deployment-diagram composer — Phase C.2 of the UML support architecture.

Reads a `UMLDeploymentDiagramModel` (from framegraph._uml) and
produces a fully-laid-out FrameGraph `visual` block. Uses the
Sugiyama hierarchical layout from `framegraph.layout` on the
node-containment graph (parent above contained child), with
artifacts placed near their owning node and relations routed
between resolved positions.

Conventions
-----------
- A node renders as a 3D box (cuboid) with `«device»` or
  `«executionEnvironment»` keyword.
- An artifact renders as a rectangle with the `«artifact»` keyword
  and a folded-document icon in the upper-right corner.
- The composer auto-emits `«deploy»` connectors for any artifact
  ids listed under `node.artifacts`. Authors who want fine-grained
  control may instead list explicit relations and leave
  `node.artifacts` empty.
- Containment is conveyed structurally — contained nodes sit
  below their parent. Physical nesting (a contained node drawn
  inside the parent's box) is a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLArtifact,
    UMLDeploymentDiagramModel,
    UMLDeploymentNode,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class DeploymentDiagramOptions:
    """Tunable parameters for the deployment-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between siblings.
        node_min_width: Minimum width of a node 3D-box.
        node_min_height: Minimum height of a node 3D-box.
        artifact_width: Default width of an artifact box.
        artifact_height: Default height of an artifact box.
        artifact_pitch: Vertical gap between stacked artifacts on
            the same node's right side.
        artifact_offset: Horizontal offset from the node's right
            edge to the artifact's left edge.
        body_padding: Horizontal padding around the node name.
        name_size: Font size for the node/artifact name.
        layout: `sugiyama` (auto-layout) or `manual` (every node
            and artifact must declare a position).
    """

    layer_height: float = 200.0
    node_gap: float = 80.0
    node_min_width: float = 220.0
    node_min_height: float = 130.0
    artifact_width: float = 160.0
    artifact_height: float = 90.0
    artifact_pitch: float = 110.0
    artifact_offset: float = 80.0
    body_padding: float = 14.0
    name_size: float = 14.0
    layout: str = "sugiyama"


class _DeploymentDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for deployment diagrams.

    Layout-driving edges are containment relations (parent above
    contained child). Artifacts are positioned in a separate pass
    after node layout completes.
    """

    def __init__(
        self,
        model: UMLDeploymentDiagramModel,
        opts: DeploymentDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the deployment model and options, indexing nodes and artifacts."""
        super().__init__(
            canvas_size=canvas_size,
            layer_height=opts.layer_height,
            node_gap=opts.node_gap,
            node_min_width=opts.node_min_width,
            margin=50.0,
            layout=opts.layout,
        )
        self.model = model
        self.opts = opts
        self._nodes_by_id: dict[str, UMLDeploymentNode] = {n.id: n for n in model.nodes}
        self._artifacts_by_id: dict[str, UMLArtifact] = {a.id: a for a in model.artifacts}
        # Reverse index: artifact_id → owning node id (when listed
        # under a node's `artifacts` field).
        self._artifact_owner: dict[str, str] = {}
        for n in model.nodes:
            for art_id in n.artifacts:
                self._artifact_owner[art_id] = n.id
        # Captured during _emit_node_object — used by extra-layers.
        self._last_node_boxes: dict[str, tuple[float, float, float, float]] = {}

    # ── HierarchicalComposer hooks ──────────────────────────────

    def _extract_layout_nodes(self) -> list[str]:
        return [n.id for n in self.model.nodes]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        for n in self.model.nodes:
            for child in n.contains:
                edges.append((n.id, child))
        return edges

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        n = self._nodes_by_id[node_id]
        name_w = str_width(n.name, self.opts.name_size, bold=True)
        # Reserve room for the «device»/«executionEnvironment» keyword
        # plus the 3D depth offset (~22 px).
        keyword_w = str_width("«executionEnvironment»", 10)
        width = max(
            self.opts.node_min_width,
            max(name_w, keyword_w) + 2 * self.opts.body_padding + 22,
        )
        height = self.opts.node_min_height
        return (width, height)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        n = self._nodes_by_id[node_id]
        x, y, w, h = box
        self._last_node_boxes[node_id] = box
        result: dict[str, Any] = {
            "type": "uml.node_box",
            "id": n.id,
            "box": [x, y, w, h],
            "name": n.name,
            "kind": n.kind,
        }
        if n.stereotype:
            result["stereotype"] = n.stereotype
        return result

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []

        # Explicit user-declared relations.
        for r in self.model.relations:
            if r.kind == "deploy" or r.kind == "manifest":
                edges.append(
                    connector_object(
                        r.id,
                        r.from_id,
                        r.to_id,
                        arrow_end_kind="open_arrow",
                        dashed=True,
                    )
                )
            else:  # communication
                edges.append(connector_object(r.id, r.from_id, r.to_id))

        # Implicit deploy connectors from `node.artifacts`.
        for n in self.model.nodes:
            for art_id in n.artifacts:
                edges.append(
                    connector_object(
                        f"deploy__{n.id}__{art_id}",
                        art_id,
                        n.id,
                        arrow_end_kind="open_arrow",
                        dashed=True,
                    )
                )

        # Containment edges (visible link complementing the layered
        # layout).
        for n in self.model.nodes:
            for child in n.contains:
                edges.append(connector_object(f"contains__{n.id}__{child}", n.id, child))
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        n = self._nodes_by_id[node_id]
        if n.position is None:
            return None
        return (n.position.x, n.position.y)

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        layers: list[dict[str, Any]] = []
        artifact_objs = self._emit_artifact_objects()
        if artifact_objs:
            layers.append({"id": "uml.artifacts", "z": 22, "objects": artifact_objs})
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)
        return layers

    def _emit_artifact_objects(self) -> list[dict[str, Any]]:
        """Place each artifact: pinned position, owning-node offset, or fallback.

        - If the artifact has an explicit `position`, use it.
        - Else, if it's listed under a node's `artifacts` and that
          node has a resolved layout box, stack it to the right of
          the node.
        - Else, lay it out in a strip at the bottom of the canvas.
        """
        if not self.model.artifacts:
            return []

        objs: list[dict[str, Any]] = []
        # Group node-owned artifacts by owner.
        owned: dict[str, list[str]] = {}
        unowned: list[str] = []
        for a in self.model.artifacts:
            owner = self._artifact_owner.get(a.id)
            if owner is not None and owner in self._last_node_boxes:
                owned.setdefault(owner, []).append(a.id)
            else:
                unowned.append(a.id)

        for owner_id, art_ids in owned.items():
            ox, oy, ow, oh = self._last_node_boxes[owner_id]
            for i, art_id in enumerate(art_ids):
                a = self._artifacts_by_id[art_id]
                if a.position is not None:
                    ax, ay = a.position.x, a.position.y
                else:
                    ax = ox + ow + self.opts.artifact_offset
                    ay = oy + i * self.opts.artifact_pitch
                obj: dict[str, Any] = {
                    "type": "uml.artifact_box",
                    "id": a.id,
                    "box": [ax, ay, self.opts.artifact_width, self.opts.artifact_height],
                    "name": a.name,
                }
                if a.stereotype:
                    obj["stereotype"] = a.stereotype
                objs.append(obj)

        # Unowned artifacts: pinned positions if any, else a strip
        # along the bottom of the canvas.
        x_cursor = 50.0
        bottom_y = self.canvas_size[1] - self.opts.artifact_height - 30
        for art_id in unowned:
            a = self._artifacts_by_id[art_id]
            if a.position is not None:
                ax, ay = a.position.x, a.position.y
            else:
                ax, ay = x_cursor, bottom_y
                x_cursor += self.opts.artifact_width + 20
            obj = {
                "type": "uml.artifact_box",
                "id": a.id,
                "box": [ax, ay, self.opts.artifact_width, self.opts.artifact_height],
                "name": a.name,
            }
            if a.stereotype:
                obj["stereotype"] = a.stereotype
            objs.append(obj)
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


def compose_deployment_diagram(
    model: UMLDeploymentDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: DeploymentDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a deployment diagram from a typed UML model.

    Args:
        model: A validated `UMLDeploymentDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `DeploymentDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.
    """
    opts = options or DeploymentDiagramOptions()
    composer = _DeploymentDiagramComposer(model, opts, canvas_size)
    return composer.compose()
