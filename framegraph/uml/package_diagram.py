"""Package-diagram composer — Phase B of the UML support architecture.

Reads a `UMLPackageDiagramModel` (from framegraph._uml) and produces
a fully-laid-out FrameGraph `visual` block. Uses the Sugiyama
hierarchical layout from `framegraph.layout` on the package-
containment graph (parent contains child → parent above child),
with package-dependency edges routed between resolved positions.

Conventions
-----------
- A package renders as a tabbed-rectangle ("folder") — a small tab
  on top with the package name, plus a body rectangle below.
- Containment is rendered structurally: a contained package is
  positioned BELOW its parent in the Sugiyama layout. This commit
  does NOT physically nest contained packages inside their parent's
  body (true nesting requires a recursive composer pass; that's a
  Phase B follow-up). Containment is conveyed by the layered layout
  alone.
- Package dependencies render as dashed connectors with an open
  arrow at the supplier end. The `kind` (import/access/merge)
  selects an inline stereotype label (composer drops the label for
  now per the same constraint as class-diagram associations; see
  `_composer_base.connector_object`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import UMLPackage, UMLPackageDiagramModel
from framegraph.uml._composer_base import (
    ComposedDiagram,
    HierarchicalComposer,
    connector_object,
    str_width,
)


def _safe_id(raw_id: str) -> str:
    """Sanitize a UML id for use as a connector endpoint reference.

    The renderer's `connector` endpoint resolver interprets `.` in
    string endpoints as dot-notation (`object_id.port_name`), per the
    v1.4 SP-4b shorthand. UML package ids commonly contain dots
    (`app.core.db`) so we rewrite them to underscores at the
    visual-emission boundary. The mapping is reversible (the original
    id is preserved on the model side) and only affects what the
    renderer sees.
    """
    return raw_id.replace(".", "_")


@dataclass(frozen=True)
class PackageDiagramOptions:
    """Tunable parameters for the package-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between packages on the
            same layer.
        node_min_width: Minimum width of a package box.
        body_min_height: Minimum body height (below the tab).
        tab_width_ratio: Fraction of the body width consumed by the
            tab (default 0.4 → tab is 40% of the body).
        tab_height: Height of the package tab in px.
        body_padding: Horizontal padding around the package name in
            the body.
        name_size: Font size for the package name.
        layout: Layout strategy. `sugiyama` runs auto-layout on the
            containment graph. `manual` requires every package to
            have a `position`.
    """

    layer_height: float = 140.0
    node_gap: float = 60.0
    node_min_width: float = 180.0
    body_min_height: float = 80.0
    tab_width_ratio: float = 0.4
    tab_height: float = 18.0
    body_padding: float = 12.0
    name_size: float = 14.0
    layout: str = "sugiyama"


class _PackageDiagramComposer(HierarchicalComposer):
    """HierarchicalComposer specialization for package diagrams.

    Layout-driving edges are containment relationships (parent
    contains child → parent above child). Dependency edges route
    between resolved positions but do not influence layout.
    """

    def __init__(
        self,
        model: UMLPackageDiagramModel,
        opts: PackageDiagramOptions,
        canvas_size: tuple[float, float],
    ) -> None:
        """Store the package model and options, indexing packages by id."""
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
        self._packages_by_id: dict[str, UMLPackage] = {p.id: p for p in model.packages}

    # ── HierarchicalComposer hooks ──────────────────────────────

    def _extract_layout_nodes(self) -> list[str]:
        return [p.id for p in self.model.packages]

    def _extract_layout_edges(self) -> list[tuple[str, str]]:
        """Containment is the y-axis driver: parent → contained child."""
        edges: list[tuple[str, str]] = []
        for p in self.model.packages:
            for child_id in p.contains:
                edges.append((p.id, child_id))
        return edges

    def _measure_node(self, node_id: str) -> tuple[float, float]:
        p = self._packages_by_id[node_id]
        name_w = str_width(p.name, self.opts.name_size, bold=True)
        width = max(self.opts.node_min_width, name_w + 2 * self.opts.body_padding)
        height = self.opts.tab_height + self.opts.body_min_height
        return (width, height)

    def _emit_node_object(
        self, node_id: str, box: tuple[float, float, float, float]
    ) -> dict[str, Any]:
        """Build the package-box visual: tab + body, both as rect+text."""
        p = self._packages_by_id[node_id]
        x, y, w, h = box
        tab_w = w * self.opts.tab_width_ratio
        tab_h = self.opts.tab_height
        sid = _safe_id(node_id)

        # Use a `group` containing tab rect + body rect + name text.
        # The renderer's group dispatch wraps this in a single <g>
        # carrying the package id, so connectors target it cleanly.
        # The group id is sanitized (dot → underscore) because the
        # connector endpoint resolver interprets `.` as dot-notation.
        return {
            "type": "group",
            "id": sid,
            # Group's box is the union (tab + body) — used for
            # connector endpoint resolution via object_index.
            "box": [x, y, w, h],
            "objects": [
                # Tab
                {
                    "type": "rect",
                    "id": f"{sid}__tab",
                    "decorative": True,
                    "box": [x, y, tab_w, tab_h],
                    "fill": "#F0EDE6",
                    "stroke": {"color": "#1A1A1A", "width": 1.0},
                },
                # Body
                {
                    "type": "rect",
                    "id": f"{sid}__body",
                    "decorative": True,
                    "box": [x, y + tab_h, w, h - tab_h],
                    "fill": "#FFFFFF",
                    "stroke": {"color": "#1A1A1A", "width": 1.0},
                },
                # Name centered in the body
                {
                    "type": "text",
                    "id": f"{sid}__name",
                    "decorative": True,
                    "box": [
                        x + self.opts.body_padding,
                        y + tab_h + (h - tab_h) / 2 - self.opts.name_size / 2,
                        w - 2 * self.opts.body_padding,
                        self.opts.name_size + 4,
                    ],
                    "text": p.name,
                    "style": {
                        "size": self.opts.name_size,
                        "weight": 700,
                        "color": "#1A1A1A",
                        "align": "center",
                    },
                },
            ],
        }

    def _emit_edge_objects(self) -> list[dict[str, Any]]:
        """Containment edges + dependency edges, both as connectors.

        All endpoint references go through `_safe_id` to avoid
        triggering the renderer's dot-notation endpoint shorthand.
        """
        edges: list[dict[str, Any]] = []

        # Containment renders as a plain connector — the layered
        # layout already conveys the parent → child relationship
        # visually. The line provides a visible link.
        for p in self.model.packages:
            for child_id in p.contains:
                # Edge id can keep dots (it's not parsed as
                # endpoint-syntax); only `from`/`to` need sanitization.
                edges.append(
                    connector_object(
                        f"contains__{_safe_id(p.id)}__{_safe_id(child_id)}",
                        _safe_id(p.id),
                        _safe_id(child_id),
                    )
                )

        # Package dependencies — dashed + open arrow at supplier.
        for d in self.model.dependencies:
            edges.append(
                connector_object(
                    _safe_id(d.id),
                    _safe_id(d.from_id),
                    _safe_id(d.to_id),
                    arrow_end_kind="open_arrow",
                    dashed=True,
                )
            )
        return edges

    def _node_position(self, node_id: str) -> tuple[float, float] | None:
        p = self._packages_by_id[node_id]
        if p.position is None:
            return None
        return (p.position.x, p.position.y)

    def _emit_extra_layers(self) -> list[dict[str, Any]]:
        """Notes layer with fallback rect+text rendering."""
        if not self.model.notes:
            return []

        note_objects: list[dict[str, Any]] = []
        for n in self.model.notes:
            if n.position is not None:
                nx, ny = n.position.x, n.position.y
            else:
                nx, ny = self.canvas_size[0] / 2, self.canvas_size[1] - 100
            nw, nh = 220.0, 60.0
            note_objects.append(
                {
                    "type": "rect",
                    "id": f"{n.id}.bg",
                    "decorative": True,
                    "box": [nx, ny, nw, nh],
                    "fill": "#FFF8DC",
                    "stroke": {"color": "#999999", "width": 0.5},
                }
            )
            note_objects.append(
                {
                    "type": "text",
                    "id": f"{n.id}.text",
                    "decorative": True,
                    "box": [nx + 8, ny + 8, nw - 16, nh - 16],
                    "text": n.text,
                    "style": {"size": 10, "color": "#1A1A1A", "wrap": True},
                }
            )
        return [{"id": "uml.notes", "z": 30, "objects": note_objects}]


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────


def compose_package_diagram(
    model: UMLPackageDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: PackageDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a package diagram from a typed UML model.

    Args:
        model: A validated `UMLPackageDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `PackageDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.

    Raises:
        ValueError: If `options.layout == "manual"` and any package
            lacks a `position` hint.
    """
    opts = options or PackageDiagramOptions()
    composer = _PackageDiagramComposer(model, opts, canvas_size)
    return composer.compose()
