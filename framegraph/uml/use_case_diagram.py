"""Use-case-diagram composer — Phase B.2 of UML support.

Reads a `UMLUseCaseDiagramModel` and produces a fully-laid-out
FrameGraph `visual` block. Layout strategy:

  - Actors land on a left column (Sugiyama layer 0).
  - Use cases land in the middle column (Sugiyama layer 1).
  - Use cases that are extended by another use case land in a third
    column (Sugiyama layer 2), giving the conventional left-to-right
    flow.
  - System boundaries (when declared) wrap their contained use cases
    in a labelled outer rectangle, drawn behind the ellipses.

The Sugiyama layout is rotated conceptually — actors-on-the-left
becomes "first layer" with the layout rendered as a vertical Sugiyama
producing top-to-bottom lanes that we reinterpret as left-to-right
columns. To achieve this we feed Sugiyama edges that capture
"appears to the left of": actor → use_case for associations,
use_case A → use_case B for include/extend (B is the included or
extending case, sitting to the right of A).

This commit deliberately keeps the layout simple: the y-axis is the
positional order within each column. A later phase can add explicit
column-aware layout if Sugiyama's defaults aren't sufficient on
real-world examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framegraph._uml import (
    UMLActor,
    UMLUseCase,
    UMLUseCaseDiagramModel,
)
from framegraph.layout import LayoutResult, SugiyamaConfig, sugiyama_layout
from framegraph.uml._composer_base import (
    ComposedDiagram,
    connector_object,
)


@dataclass(frozen=True)
class UseCaseDiagramOptions:
    """Tunables for the use-case-diagram composer.

    Attributes:
        column_width: Horizontal stride between columns (px).
        row_height: Vertical stride between elements within a column.
        actor_width: Width of an actor stick-figure box.
        actor_height: Height of an actor stick-figure box (incl. label).
        use_case_width: Default width of a use-case ellipse.
        use_case_height: Default height of a use-case ellipse.
        boundary_padding: Padding inside a system-boundary rectangle.
        name_size: Font size for use-case ellipse labels.
        layout: Layout strategy (`sugiyama` or `manual`).
    """

    column_width: float = 240.0
    row_height: float = 110.0
    actor_width: float = 60.0
    actor_height: float = 100.0
    use_case_width: float = 180.0
    use_case_height: float = 70.0
    boundary_padding: float = 30.0
    name_size: float = 12.0
    layout: str = "sugiyama"


def _format_relation_kind_for_stereotype(kind: str) -> str | None:
    """Return the `«…»` stereotype label for a relation kind, or None."""
    if kind == "include":
        return "include"
    if kind == "extend":
        return "extend"
    return None


def compose_use_case_diagram(
    model: UMLUseCaseDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: UseCaseDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a use-case diagram from a typed UML model.

    Args:
        model: A validated `UMLUseCaseDiagramModel`.
        canvas_size: Target canvas size (w, h) in pixels.
        options: Tunables; defaults to `UseCaseDiagramOptions()`.

    Returns:
        A `ComposedDiagram` with the laid-out visual block.

    Raises:
        ValueError: If `options.layout == "manual"` and any actor/
            use-case lacks a `position` hint.
    """
    opts = options or UseCaseDiagramOptions()

    actors_by_id: dict[str, UMLActor] = {a.id: a for a in model.actors}
    use_cases_by_id: dict[str, UMLUseCase] = {u.id: u for u in model.use_cases}

    # ── Sugiyama input ──
    # Nodes = actors + use cases. Edges feed Sugiyama's
    # "above → below" convention with the visual orientation rotated:
    # we'll treat layer 0 = leftmost column, layer 1 = middle, etc.
    # Edges that should drive horizontal ordering:
    #   actor → use_case (associations)
    #   include: from-uc → to-uc (the included is "to the right")
    #   extend: from-uc → to-uc (the extended is "to the right" since
    #     extension points are at extension targets)
    nodes: list[str] = [a.id for a in model.actors] + [u.id for u in model.use_cases]
    edges: list[tuple[str, str]] = []
    for rel in model.relations:
        edges.append((rel.from_id, rel.to_id))

    layout_result: LayoutResult | None = None
    positions: dict[str, tuple[float, float]] = {}

    if opts.layout == "manual":
        for nid in nodes:
            pinned: tuple[float, float] | None
            if nid in actors_by_id and actors_by_id[nid].position is not None:
                pos = actors_by_id[nid].position
                assert pos is not None
                pinned = (pos.x, pos.y)
            elif nid in use_cases_by_id and use_cases_by_id[nid].position is not None:
                pos = use_cases_by_id[nid].position
                assert pos is not None
                pinned = (pos.x, pos.y)
            else:
                raise ValueError(
                    f"layout='manual' requires every element to have a position; {nid!r} has none"
                )
            positions[nid] = pinned
    elif opts.layout == "sugiyama":
        # We use Sugiyama with vertical layers; then we rotate by
        # swapping x and y. Sugiyama puts source above target; rotated,
        # source ends up to the left of target — exactly the convention
        # for actor → use_case and include/extend.
        cfg = SugiyamaConfig(
            layer_height=opts.column_width,  # rotated → x stride
            node_width=opts.row_height,  # rotated → y stride
            node_gap=20.0,
        )
        layout_result = sugiyama_layout(nodes, edges, config=cfg)
        # Rotate: input (sx, sy) becomes (sy, sx) in output coords.
        # Translate so the leftmost x and topmost y land at the margins.
        # y-margin must clear the system-boundary header (padding + label
        # height) so the boundary's outer rectangle and `name` label
        # don't clip off-canvas at the top.
        margin = 40.0
        y_margin = margin + opts.boundary_padding + 24
        if layout_result.positions:
            min_x = min(y for (_, y) in layout_result.positions.values())
            min_y = min(x for (x, _) in layout_result.positions.values())
            x_shift = margin - min_x
            y_shift = y_margin - min_y
        else:
            x_shift = margin
            y_shift = y_margin
        for sg_nid, (sx, sy) in layout_result.positions.items():
            positions[str(sg_nid)] = (sy + x_shift, sx + y_shift)
    else:
        raise ValueError(
            f"unknown layout strategy {opts.layout!r}; expected 'manual' or 'sugiyama'"
        )

    # ── Pin overrides ──
    for nid in nodes:
        if nid in actors_by_id and actors_by_id[nid].position is not None:
            pos = actors_by_id[nid].position
            assert pos is not None
            positions[nid] = (pos.x, pos.y)
        elif nid in use_cases_by_id and use_cases_by_id[nid].position is not None:
            pos = use_cases_by_id[nid].position
            assert pos is not None
            positions[nid] = (pos.x, pos.y)

    # ── Emit visual objects ──
    actor_objects: list[dict[str, Any]] = []
    use_case_objects: list[dict[str, Any]] = []
    boundary_objects: list[dict[str, Any]] = []
    edge_objects: list[dict[str, Any]] = []
    note_objects: list[dict[str, Any]] = []

    # Actors — uml.actor primitive. Position is the box top-left;
    # for Sugiyama-positioned actors we centre the figure horizontally
    # and place the label below.
    for a in model.actors:
        cx, cy = positions[a.id]
        # Sugiyama gives us a center-ish anchor; convert to top-left.
        if a.position is None:
            cx -= opts.actor_width / 2
        actor_objects.append(
            {
                "type": "uml.actor",
                "id": a.id,
                "box": [cx, cy, opts.actor_width, opts.actor_height],
                "name": a.name,
            }
        )

    # Use cases — ellipse + centered text. Use case ellipse is
    # horizontally stretched per UML convention.
    for u in model.use_cases:
        cx, cy = positions[u.id]
        if u.position is None:
            cx -= opts.use_case_width / 2
        use_case_objects.append(
            {
                "type": "ellipse",
                "id": u.id,
                "box": [cx, cy, opts.use_case_width, opts.use_case_height],
                "fill": "#FFFFFF",
                "stroke": {"color": "#1A1A1A", "width": 1.0},
            }
        )
        # Label text — centered inside the ellipse box.
        use_case_objects.append(
            {
                "type": "text",
                "id": f"{u.id}__label",
                "decorative": True,
                "box": [cx, cy, opts.use_case_width, opts.use_case_height],
                "text": u.name,
                "style": {
                    "size": opts.name_size,
                    "weight": 400,
                    "color": "#1A1A1A",
                    "align": "center",
                    "v_align": "middle",
                },
            }
        )

    # System boundaries — outer rectangle wrapping contained use-case
    # ellipses. Computed from the bounding box of contained use cases
    # plus padding.
    for sb in model.system_boundaries:
        if not sb.contains:
            continue
        contained_ucs = [u for u in model.use_cases if u.id in sb.contains and u.id in positions]
        if not contained_ucs:
            continue
        # Bounding box of contained use-case ellipses
        boxes = []
        for u in contained_ucs:
            cx, cy = positions[u.id]
            if u.position is None:
                cx -= opts.use_case_width / 2
            boxes.append((cx, cy, opts.use_case_width, opts.use_case_height))
        min_x = min(b[0] for b in boxes) - opts.boundary_padding
        min_y = min(b[1] for b in boxes) - opts.boundary_padding - 24
        max_x = max(b[0] + b[2] for b in boxes) + opts.boundary_padding
        max_y = max(b[1] + b[3] for b in boxes) + opts.boundary_padding
        bw = max_x - min_x
        bh = max_y - min_y
        boundary_objects.append(
            {
                "type": "rect",
                "id": f"{sb.id}__frame",
                "decorative": True,
                "box": [min_x, min_y, bw, bh],
                "fill": "none",
                "stroke": {"color": "#1A1A1A", "width": 1.0},
            }
        )
        boundary_objects.append(
            {
                "type": "text",
                "id": f"{sb.id}__name",
                "decorative": True,
                "box": [min_x, min_y, bw, 22],
                "text": sb.name,
                "style": {
                    "size": opts.name_size + 1,
                    "weight": 700,
                    "color": "#1A1A1A",
                    "align": "center",
                    "v_align": "middle",
                },
            }
        )

    # Relations — connectors with the right styling per kind.
    for rel in model.relations:
        if rel.kind == "association":
            edge_objects.append(connector_object(rel.id, rel.from_id, rel.to_id))
        elif rel.kind in ("include", "extend"):
            # `«include»` and `«extend»` — dashed + open arrow at target.
            edge_objects.append(
                connector_object(
                    rel.id,
                    rel.from_id,
                    rel.to_id,
                    arrow_end_kind="open_arrow",
                    dashed=True,
                )
            )
        else:
            edge_objects.append(connector_object(rel.id, rel.from_id, rel.to_id))

    # Notes — fallback rect+text per the class-diagram convention.
    for n in model.notes:
        if n.position is not None:
            nx, ny = n.position.x, n.position.y
        else:
            nx, ny = canvas_size[0] / 2, canvas_size[1] - 100
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

    visual: dict[str, Any] = {
        "tokens": {},
        "layers": [
            # Boundaries paint behind everything
            {"id": "uml.boundaries", "z": 5, "objects": boundary_objects},
            # Edges between
            {"id": "uml.edges", "z": 10, "objects": edge_objects},
            # Actors and use cases on top
            {
                "id": "uml.classifiers",
                "z": 20,
                "objects": actor_objects + use_case_objects,
            },
        ],
    }
    if note_objects:
        visual["layers"].append({"id": "uml.notes", "z": 30, "objects": note_objects})

    # Compute node dimensions for diagnostic output.
    dimensions: dict[str, tuple[float, float]] = {}
    for a in model.actors:
        dimensions[a.id] = (opts.actor_width, opts.actor_height)
    for u in model.use_cases:
        dimensions[u.id] = (opts.use_case_width, opts.use_case_height)

    return ComposedDiagram(
        visual=visual,
        layout_result=layout_result,
        node_dimensions=dimensions,
    )
