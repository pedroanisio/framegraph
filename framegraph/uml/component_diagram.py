"""Component-diagram composer — Phase C.1 of the UML support architecture.

Reads a `UMLComponentDiagramModel` (from framegraph._uml) and
produces a fully-laid-out FrameGraph `visual` block. Uses the
Sugiyama hierarchical layout from `framegraph.layout` on the
assembly-connector graph (consumer above provider, conventionally),
with delegation connectors and lollipop/socket interface decorations
emitted as overlay layers.

Conventions
-----------
- A component renders as a rectangle with the UML 2.5 component
  icon (rectangle with two left-side tabs) in its upper-right
  corner. Stereotype `«component»` may be added by the caller via
  `style.show_stereotype`.
- Provided interfaces render as lollipops (filled circle on a stem)
  attached to the right edge.
- Required interfaces render as sockets (half-circle on a stem)
  attached to the right edge.
- Assembly connectors render as plain lines between component ids.
- Delegation connectors render as dashed lines with an open arrow
  at the delegate end.
- Connector endpoints may reference either a component id directly
  or a fully-qualified `component_id.interface_name` — the composer
  resolves interface names to the parent component's center on
  emission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLComponent,
    UMLComponentDiagramModel,
)
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


@dataclass(frozen=True)
class ComponentDiagramOptions:
    """Tunable parameters for the component-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between components on the
            same layer.
        node_min_width: Minimum width of a component box.
        node_min_height: Minimum height of a component box.
        body_padding: Horizontal padding around the component name.
        name_size: Font size for the component name (bold).
        stereotype_size: Font size for the optional «component»
            stereotype label.
        interface_stem: Length of the stem for lollipops/sockets.
        interface_pitch: Vertical gap between stacked interface tips.
        layout: Layout strategy. `sugiyama` runs auto-layout on the
            assembly-connector graph. `manual` requires every
            component to have a `position`.
        show_stereotype: When True, render `«component»` above the
            component name on each box.
    """

    layer_height: float = 180.0
    node_gap: float = 80.0
    node_min_width: float = 200.0
    node_min_height: float = 110.0
    body_padding: float = 14.0
    name_size: float = 14.0
    stereotype_size: float = 10.0
    interface_stem: float = 28.0
    interface_pitch: float = 22.0
    layout: str = "sugiyama"
    show_stereotype: bool = False


class _ComponentDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for component diagrams.

    Layout-driving edges are assembly connectors, oriented so that
    the consumer (the component holding the *required* interface)
    sits above the provider (the component holding the *provided*
    interface). When a connector references components directly
    (without interface qualification), orientation falls back to the
    declared `from` → `to` order.
    """

    def __init__(
        self,
        model: UMLComponentDiagramModel,
        opts: ComponentDiagramOptions,
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
        self._components_by_id: dict[str, UMLComponent] = {c.id: c for c in model.components}
        # Index every interface name -> owning component id.
        self._iface_owner: dict[str, str] = {}
        for c in model.components:
            for iface in c.provided_interfaces:
                self._iface_owner[f"{c.id}.{iface}"] = c.id
            for iface in c.required_interfaces:
                self._iface_owner[f"{c.id}.{iface}"] = c.id
        # Index ports by id -> owning component id.
        self._port_owner: dict[str, str] = {}
        for c in model.components:
            for p in c.ports:
                self._port_owner[p.id] = c.id

    # ── HierarchicalComposer hooks ──────────────────────────────

    def _extract_layout_nodes(self) -> list[str]:
        return [c.id for c in self.model.components]

    def _resolve_endpoint_to_component(self, endpoint: str) -> str:
        """Map a connector endpoint to its owning component id."""
        if endpoint in self._components_by_id:
            return endpoint
        if endpoint in self._iface_owner:
            return self._iface_owner[endpoint]
        if endpoint in self._port_owner:
            return self._port_owner[endpoint]
        # Endpoint validation already ran in the model validator;
        # if we land here the validator missed something — fail loud.
        raise ValueError(f"connector endpoint {endpoint!r} did not resolve")

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        """Assembly connectors drive the y-axis hierarchy.

        Convention: a component holding a *required* interface depends
        on (sits above) a component holding the matching *provided*
        interface. When endpoints are interface-qualified we use that
        information; otherwise we fall back to declared from→to.
        """
        edges: list[tuple[str, str]] = []
        for conn in self.model.connectors:
            if conn.kind != "assembly":
                continue
            src_comp = self._resolve_endpoint_to_component(conn.from_id)
            dst_comp = self._resolve_endpoint_to_component(conn.to_id)
            if src_comp == dst_comp:
                continue
            # Determine consumer→provider direction. If `from_id` names
            # a required interface, src is the consumer; if it names a
            # provided interface, src is the provider — flip.
            src_is_required = (
                conn.from_id in self._iface_owner
                and conn.from_id.split(".", 1)[1]
                in self._components_by_id[src_comp].required_interfaces
            )
            src_is_provided = (
                conn.from_id in self._iface_owner
                and conn.from_id.split(".", 1)[1]
                in self._components_by_id[src_comp].provided_interfaces
            )
            if src_is_required:
                edges.append((src_comp, dst_comp))
            elif src_is_provided:
                edges.append((dst_comp, src_comp))
            else:
                # Plain component-to-component assembly: declared order.
                edges.append((src_comp, dst_comp))
        return edges

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        c = self._components_by_id[node_id]
        name_w = str_width(c.name, self.opts.name_size, bold=True)
        width = max(self.opts.node_min_width, name_w + 2 * self.opts.body_padding + 40)
        # Reserve vertical space for stacked interface labels on the
        # right edge: the body must be tall enough to host both
        # provided and required tips with `interface_pitch` spacing.
        n_ifaces = len(c.provided_interfaces) + len(c.required_interfaces)
        iface_h = max(0, n_ifaces - 1) * self.opts.interface_pitch + 24
        height = max(self.opts.node_min_height, iface_h + 60)
        return (width, height)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        c = self._components_by_id[node_id]
        x, y, w, h = box
        result: dict[str, Any] = {
            "type": "uml.component_box",
            "id": c.id,
            "box": [x, y, w, h],
            "name": c.name,
        }
        if self.opts.show_stereotype:
            result["stereotype"] = "component"
        return result

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        """Connector objects between resolved component ids.

        Endpoints that name interfaces or ports are normalized to
        their owning component id so the renderer's connector
        resolver finds a registered object.
        """
        edges: list[dict[str, Any]] = []
        for conn in self.model.connectors:
            src_comp = self._resolve_endpoint_to_component(conn.from_id)
            dst_comp = self._resolve_endpoint_to_component(conn.to_id)
            if conn.kind == "delegation":
                edges.append(
                    connector_object(
                        conn.id,
                        src_comp,
                        dst_comp,
                        arrow_end_kind="open_arrow",
                        dashed=True,
                    )
                )
            else:
                # Assembly: plain line. The lollipop/socket overlay
                # supplies the visual semantics.
                edges.append(connector_object(conn.id, src_comp, dst_comp))
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        c = self._components_by_id[node_id]
        if c.position is None:
            return None
        return (c.position.x, c.position.y)

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        """Emit lollipop/socket interface decorations and notes.

        Two layers:
          - `uml.interfaces` (z=25): provided lollipops + required
            sockets, attached to each component's right edge.
          - `uml.notes` (z=30): free-text annotations.
        """
        layers: list[dict[str, Any]] = []
        iface_objects = self._emit_interface_objects()
        if iface_objects:
            layers.append({"id": "uml.interfaces", "z": 25, "objects": iface_objects})
        notes_layer = self._emit_notes_layer()
        if notes_layer is not None:
            layers.append(notes_layer)
        return layers

    def _emit_interface_objects(self) -> list[dict[str, Any]]:
        """Build lollipop + socket primitives anchored to each component.

        For each component, provided interfaces are stacked first
        (top), then required interfaces. Each tip extends to the right
        of the component's body by `interface_stem`.
        """
        objects: list[dict[str, Any]] = []
        # We need each component's resolved box. Re-derive from the
        # composer pipeline by reading the visual we just built? No —
        # cleaner: recompute positions the same way `compose()` does.
        # The base class hands us positions implicitly via
        # `_emit_node_object`; here we read them back from the same
        # source: positions stored on the composer instance.
        # The base class does NOT cache positions on `self`. We fetch
        # them from the visual by walking the node objects' boxes.
        # Since `_emit_extra_layers` runs after `_emit_node_object`
        # but the base-class compose() builds layers from results
        # *after* extra layers, we need positions another way.
        #
        # Practical solution: stash positions as we emit nodes.
        for c in self.model.components:
            box = self._last_node_boxes.get(c.id)
            if box is None:
                # Component had no layout — skip its interfaces.
                continue
            x, y, w, h = box
            tips = list(c.provided_interfaces) + list(c.required_interfaces)
            if not tips:
                continue
            # Center the stack vertically on the right face.
            n = len(tips)
            total = (n - 1) * self.opts.interface_pitch
            top_y = y + h / 2 - total / 2
            stem = self.opts.interface_stem

            for i, iface in enumerate(c.provided_interfaces):
                ay = top_y + i * self.opts.interface_pitch
                objects.append(
                    {
                        "type": "uml.lollipop",
                        "id": f"{c.id}__prov__{iface}",
                        "box": [x + w, ay - 8, stem, 16],
                        "name": iface,
                    }
                )
            offset = len(c.provided_interfaces)
            for i, iface in enumerate(c.required_interfaces):
                ay = top_y + (offset + i) * self.opts.interface_pitch
                objects.append(
                    {
                        "type": "uml.socket",
                        "id": f"{c.id}__req__{iface}",
                        "box": [x + w, ay - 8, stem, 16],
                        "name": iface,
                    }
                )
        return objects

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

    # ── Position-cache override ─────────────────────────────────
    #
    # The base class doesn't expose resolved boxes to extra-layer
    # hooks. We capture them as `_emit_node_object` is called.

    _last_node_boxes: dict[str, tuple[float, float, float, float]]

    def __init_subclass__(cls, **kwargs: Any) -> None:  # pragma: no cover
        super().__init_subclass__(**kwargs)


def _wrap_emit_node_object(composer: _ComponentDiagramComposer) -> None:
    """Wrap `_emit_node_object` so resolved boxes survive into extra-layers.

    Instead of monkey-patching, we attach `_last_node_boxes` and let
    `_emit_node_object` write into it. Done as a free function to keep
    the class definition narrow and the side-effect explicit.
    """
    composer._last_node_boxes = {}
    original = composer._emit_node_object

    def wrapper(node_id: str, box: tuple[float, float, float, float]) -> dict[str, Any]:
        composer._last_node_boxes[node_id] = box
        return original(node_id, box)

    composer._emit_node_object = wrapper  # type: ignore[method-assign]


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────


def compose_component_diagram(
    model: UMLComponentDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: ComponentDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a component diagram from a typed UML model.

    Args:
        model: A validated `UMLComponentDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `ComponentDiagramOptions()`.

    Returns:
        A `ComposedDiagram` whose `visual` field renders to a UML
        component diagram with provided/required interface
        decorations.

    Raises:
        ValueError: If `options.layout == "manual"` and any component
            lacks a `position`.
    """
    opts = options or ComponentDiagramOptions()
    composer = _ComponentDiagramComposer(model, opts, canvas_size)
    _wrap_emit_node_object(composer)
    return composer.compose()
