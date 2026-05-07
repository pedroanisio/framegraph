"""Class-diagram composer — Phase A.3 of the UML support architecture.

Reads a `UMLClassDiagramModel` (Phase A.1) and produces a fully-
laid-out FrameGraph `visual` block ready for the renderer. Uses the
pure-Python Sugiyama layout from `framegraph.layout` for hierarchical
auto-placement of classifiers based on the generalization/realization
graph; associations and dependencies route as straight lines between
already-placed nodes.

Pipeline
--------
1. **Measure classifiers.** Compute `(width, height)` for each
   class / interface / enumeration based on its longest member
   signature and member count.
2. **Build layout graph.** Nodes = all classifiers. Edges =
   generalizations + realizations (these define the y-axis
   hierarchy; child classifier appears below parent in the layered
   layout). Associations and dependencies are NOT layout-driving —
   they route as straight lines between resolved positions.
3. **Run Sugiyama.** Stage 1 cycle removal handles inheritance
   loops (rare but valid input). Stage 4 Brandes-Köpf produces
   compact, balanced x-coordinates.
4. **Apply position pins.** Classifiers with author-supplied
   `position: {x, y}` override Sugiyama's resolved coordinates.
   This is the layout escape hatch from Phase A.1.
5. **Emit visual objects.**
   - Each classifier → `uml.classifier_box` at the resolved box.
   - Each generalization → `connector` with `hollow_triangle`
     arrow at the parent end.
   - Each realization → `connector` with `hollow_triangle` arrow
     at the interface end + dashed line.
   - Each aggregation → `connector` with `hollow_diamond` at the
     whole end.
   - Each composition → `connector` with `filled_diamond` at the
     whole end.
   - Each plain association → `connector` with optional
     `open_arrow` (when navigability is set).
   - Each dependency → `connector` with `open_arrow` at supplier
     + dashed line, optional stereotype label.
   - Each note → `uml.note` (Phase A.x — not implemented yet;
     notes render as a fallback `rect`+`text` here).
   - Each package → `group` containing tabbed-rectangle frame
     plus contained classifier boxes.

Output
------
A `ComposedDiagram` dataclass containing the final `Visual` block
plus diagnostics (Sugiyama crossings, reversed edges, layout-graph
sizes). Authors who want the bare visual block call `.to_visual()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from framegraph._uml import (
    UMLAssociation,
    UMLClass,
    UMLClassDiagramModel,
    UMLEnumeration,
    UMLInterface,
)
from framegraph.layout import LayoutResult, SugiyamaConfig, sugiyama_layout

# ─────────────────────────────────────────────────────────────────
# Width / height estimation
# ─────────────────────────────────────────────────────────────────
#
# Used to size classifier boxes before layout. The estimator mirrors
# the renderer's `_str_width` (which sits on a renderer instance we
# don't have at compose time). It is deliberately conservative —
# bias slightly wide is better than truncation.

_CW_NORMAL = {
    "narrow": 0.34,
    "normal": 0.50,
    "wide": 0.65,
    "space": 0.25,
    "digit": 0.52,
    "punct": 0.30,
}
_CW_BOLD = {
    "narrow": 0.38,
    "normal": 0.56,
    "wide": 0.72,
    "space": 0.28,
    "digit": 0.58,
    "punct": 0.34,
}
_NARROW_CH = set("ijlfrт:;!|1()")
_WIDE_CH = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw@#%")
_DIGIT_CH = set("0123456789")
_PUNCT_CH = set(",.'\"-–—")


def _char_em(c: str, bold: bool) -> float:
    table = _CW_BOLD if bold else _CW_NORMAL
    if c in (" ", "\t"):
        return table["space"]
    if c in _NARROW_CH:
        return table["narrow"]
    if c in _WIDE_CH:
        return table["wide"]
    if c in _DIGIT_CH:
        return table["digit"]
    if c in _PUNCT_CH:
        return table["punct"]
    return table["normal"]


def _str_width(text: str, fs: float, bold: bool = False) -> float:
    """Estimate the rendered width of `text` in pixels at font-size `fs`."""
    return sum(_char_em(c, bold) for c in text) * fs


# ─────────────────────────────────────────────────────────────────
# Compose-time data structures
# ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassDiagramOptions:
    """Tunable parameters for the class-diagram composer.

    Attributes:
        layer_height: Vertical distance between Sugiyama layers (px).
        node_gap: Minimum horizontal gap between classifiers in the
            same layer.
        node_min_width: Minimum width of a classifier box.
        node_padding: Horizontal padding inside the classifier box
            on each side.
        member_size: Font size used for attribute and operation
            lines (px).
        name_size: Font size used for the classifier name.
        line_height: Vertical pixels per attribute / operation line.
        layout: Layout strategy. `sugiyama` runs auto-layout on the
            generalization graph. `manual` skips layout entirely —
            requires every classifier to have a `position`.
    """

    layer_height: float = 160.0
    node_gap: float = 60.0
    node_min_width: float = 160.0
    node_padding: float = 16.0
    member_size: float = 11.0
    name_size: float = 14.0
    line_height: float = 19.0
    layout: str = "sugiyama"


@dataclass
class ComposedDiagram:
    """Result of `compose_class_diagram`.

    Attributes:
        visual: The fully-laid-out `visual` block. Insert into a
            FrameGraph document under the `visual` key.
        layout_result: The Sugiyama `LayoutResult` (None when
            `layout: manual`). Useful for diagnostics — crossings
            count, reversed edges, layer ordering.
        node_dimensions: Mapping `classifier_id → (width, height)`
            after the measurement step. Diagnostic.
    """

    visual: dict[str, Any]
    layout_result: LayoutResult | None = None
    node_dimensions: dict[str, tuple[float, float]] = field(default_factory=dict)

    def to_visual(self) -> dict[str, Any]:
        """Return just the visual block — for insertion into a FrameGraph doc."""
        return self.visual


# ─────────────────────────────────────────────────────────────────
# Classifier sizing
# ─────────────────────────────────────────────────────────────────


def _format_attribute_for_width(attr: dict[str, Any]) -> str:
    """Re-implement the visibility/name/type formatting for width estimation.

    Mirrors `framegraph.renderers.uml._format_attribute` exactly. Kept
    inline here to avoid importing from the renderer module — the
    composer should be usable independently of the renderer.
    """
    visibility_prefix = {"public": "+", "private": "-", "protected": "#", "package": "~"}
    vis = visibility_prefix.get(str(attr.get("visibility", "public")), "+")
    name = str(attr.get("name", ""))
    if attr.get("derived"):
        name = "/" + name
    s = f"{vis} {name}"
    type_str = attr.get("type")
    mult = attr.get("multiplicity")
    if type_str:
        s += f": {type_str}"
        if mult:
            s += f"[{mult}]"
    elif mult:
        s += f"[{mult}]"
    if attr.get("default") is not None:
        s += f" = {attr['default']}"
    if attr.get("readonly"):
        s += " {readOnly}"
    return s


def _format_operation_for_width(op: dict[str, Any]) -> str:
    """Mirror of `framegraph.renderers.uml._format_operation` for width estimation."""
    visibility_prefix = {"public": "+", "private": "-", "protected": "#", "package": "~"}
    vis = visibility_prefix.get(str(op.get("visibility", "public")), "+")
    name = str(op.get("name", ""))
    params = op.get("parameters") or []
    return_param = next((p for p in params if p.get("direction") == "return"), None)
    formal = [p for p in params if p.get("direction") != "return"]
    parts = []
    for p in formal:
        d = str(p.get("direction", "in"))
        prefix = "" if d == "in" else f"{d} "
        s = f"{prefix}{p.get('name', '')}"
        if p.get("type"):
            s += f": {p['type']}"
        if p.get("multiplicity"):
            s += f"[{p['multiplicity']}]"
        if p.get("default") is not None:
            s += f" = {p['default']}"
        parts.append(s)
    sig = f"{vis} {name}({', '.join(parts)})"
    rt = op.get("return_type") or (return_param.get("type") if return_param else None)
    if rt:
        sig += f": {rt}"
    if op.get("query"):
        sig += " {query}"
    return sig


def _measure_classifier(
    classifier: UMLClass | UMLInterface | UMLEnumeration,
    opts: ClassDiagramOptions,
) -> tuple[float, float]:
    """Compute `(width, height)` for a classifier box based on its members.

    Width is driven by the longest single line. Height is the sum of
    header + per-compartment heights with conventional minimums.
    """
    # Header lines: optional stereotype + name
    name_width = _str_width(classifier.name, opts.name_size, bold=True)
    stereotype = (
        f"«{classifier.stereotype}»"
        if hasattr(classifier, "stereotype") and getattr(classifier, "stereotype", None)
        else ""
    )
    stereotype_width = _str_width(stereotype, opts.member_size) if stereotype else 0.0

    # Attribute / operation widths
    attr_widths: list[float] = []
    op_widths: list[float] = []

    if isinstance(classifier, UMLClass):
        for a in classifier.attributes:
            attr_widths.append(
                _str_width(_format_attribute_for_width(a.model_dump()), opts.member_size)
            )
        for op in classifier.operations:
            op_widths.append(
                _str_width(_format_operation_for_width(op.model_dump()), opts.member_size)
            )
    elif isinstance(classifier, UMLInterface):
        for a in classifier.constants:
            attr_widths.append(
                _str_width(_format_attribute_for_width(a.model_dump()), opts.member_size)
            )
        for op in classifier.operations:
            op_widths.append(
                _str_width(_format_operation_for_width(op.model_dump()), opts.member_size)
            )
    elif isinstance(classifier, UMLEnumeration):
        for lit in classifier.literals:
            attr_widths.append(_str_width(lit, opts.member_size))
        for op in classifier.operations:
            op_widths.append(
                _str_width(_format_operation_for_width(op.model_dump()), opts.member_size)
            )

    longest = max([name_width, stereotype_width, *attr_widths, *op_widths], default=0.0)
    width = max(opts.node_min_width, longest + 2 * opts.node_padding)

    # Height: header (28 or 36) + attrs compartment + ops compartment
    n_attrs = len(attr_widths)
    n_ops = len(op_widths)
    header_h = 36.0 if stereotype else 28.0
    attrs_h = max(opts.line_height, n_attrs * opts.line_height + 8)
    ops_h = max(opts.line_height, n_ops * opts.line_height + 8)
    height = header_h + attrs_h + ops_h

    return (width, height)


# ─────────────────────────────────────────────────────────────────
# Visual-object emission
# ─────────────────────────────────────────────────────────────────


def _classifier_to_visual(
    classifier: UMLClass | UMLInterface | UMLEnumeration,
    box: tuple[float, float, float, float],
) -> dict[str, Any]:
    """Convert a typed classifier into a `uml.classifier_box` visual object."""
    obj: dict[str, Any] = {
        "type": "uml.classifier_box",
        "id": classifier.id,
        "box": list(box),
        "name": classifier.name,
    }
    if isinstance(classifier, UMLClass):
        if classifier.stereotype:
            obj["stereotype"] = classifier.stereotype
        if classifier.abstract:
            obj["abstract"] = True
        if classifier.attributes:
            obj["attributes"] = [a.model_dump(exclude_none=True) for a in classifier.attributes]
        if classifier.operations:
            obj["operations"] = [op.model_dump(exclude_none=True) for op in classifier.operations]
    elif isinstance(classifier, UMLInterface):
        # Interface stereotype is conventional; emit it.
        obj["stereotype"] = "interface"
        if classifier.constants:
            obj["attributes"] = [a.model_dump(exclude_none=True) for a in classifier.constants]
        if classifier.operations:
            obj["operations"] = [op.model_dump(exclude_none=True) for op in classifier.operations]
    elif isinstance(classifier, UMLEnumeration):
        obj["stereotype"] = "enumeration"
        # Render literals as attribute lines (UML convention — enum
        # literals appear in the attribute compartment).
        obj["attributes"] = [
            {"name": lit, "visibility": "public", "static": True, "readonly": True}
            for lit in classifier.literals
        ]
        if classifier.operations:
            obj["operations"] = [op.model_dump(exclude_none=True) for op in classifier.operations]
    return obj


def _connector_object(
    edge_id: str,
    from_id: str,
    to_id: str,
    *,
    arrow_end_kind: str | None = None,
    arrow_start_kind: str | None = None,
    dashed: bool = False,
    label: str | None = None,
    stereotype: str | None = None,
) -> dict[str, Any]:
    """Build a connector object with the right UML arrow conventions."""
    stroke: dict[str, Any] = {"color": "#1A1A1A", "width": 1.0}
    if dashed:
        stroke["dash"] = [5, 4]
    if arrow_end_kind:
        stroke["arrow_end"] = True
        stroke["arrow_end_kind"] = arrow_end_kind
    if arrow_start_kind:
        stroke["arrow_start"] = True
        stroke["arrow_start_kind"] = arrow_start_kind

    obj: dict[str, Any] = {
        "type": "connector",
        "id": edge_id,
        "from": from_id,
        "to": to_id,
        "stroke": stroke,
    }
    # NOTE: connector labels (association names, dependency
    # stereotypes) are not emitted inline here — the connector
    # renderer's `label.box` is required to position labels but we
    # don't have access to the resolved endpoint coordinates at
    # compose time without a separate pass. Phase A.x can add a
    # label-placement pass that puts text at the connector midpoint.
    # For now the labels are dropped silently; that's documented in
    # the test suite.
    _ = (label, stereotype)  # acknowledged-unused
    return obj


def _emit_association_label(
    end: UMLAssociation, side: str, position: tuple[float, float]
) -> dict[str, Any] | None:
    """Build a small `text` object for an association end's role/multiplicity.

    Args:
        end: The association (the function reads `end1`/`end2` based on side).
        side: `"end1"` or `"end2"`.
        position: Absolute `(x, y)` near the association end.

    Returns:
        A `text` visual object, or None when the end has no label content.
    """
    end_data = end.end1 if side == "end1" else end.end2
    parts = []
    if end_data.role:
        parts.append(end_data.role)
    if end_data.multiplicity:
        parts.append(end_data.multiplicity)
    if not parts:
        return None
    label = " ".join(parts)
    x, y = position
    return {
        "type": "text",
        "id": f"{end.id}.{side}.label",
        "decorative": True,
        "box": [x - 40, y - 8, 80, 16],
        "text": label,
        "style": {"size": 9, "color": "#5A5A56", "align": "center"},
    }


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────


def compose_class_diagram(
    model: UMLClassDiagramModel,
    *,
    canvas_size: tuple[float, float] = (1280.0, 720.0),
    options: ClassDiagramOptions | None = None,
) -> ComposedDiagram:
    """Compose a class diagram from a typed UML model into a visual block.

    Args:
        model: A validated `UMLClassDiagramModel`.
        canvas_size: Target canvas `(width, height)` in pixels. Used
            only when `layout: sugiyama` to anchor the layout in
            the upper-left of the canvas with a small margin.
        options: Tunable composer parameters. Defaults to
            `ClassDiagramOptions()`.

    Returns:
        A `ComposedDiagram` whose `.visual` field is a FrameGraph
        `visual` block dict (tokens, layers, objects), ready to drop
        into a FrameGraph document.

    Raises:
        ValueError: If `options.layout == "manual"` and any
            classifier lacks a `position` hint.
    """
    opts = options or ClassDiagramOptions()

    # Combine all classifier types into one ordered list for stable iteration.
    classifiers: list[UMLClass | UMLInterface | UMLEnumeration] = [
        *model.classes,
        *model.interfaces,
        *model.enumerations,
    ]
    # ── Step 1: measure ──
    dimensions: dict[str, tuple[float, float]] = {
        c.id: _measure_classifier(c, opts) for c in classifiers
    }

    # ── Step 2 & 3: layout graph + Sugiyama ──
    layout_result: LayoutResult | None = None
    positions: dict[str, tuple[float, float]] = {}

    if opts.layout == "manual":
        for c in classifiers:
            if c.position is None:
                raise ValueError(
                    f"layout='manual' requires every classifier to have a "
                    f"position hint, but {c.id!r} has none"
                )
            positions[c.id] = (c.position.x, c.position.y)
    elif opts.layout == "sugiyama":
        node_ids = [c.id for c in classifiers]
        # Layout-graph edges: generalizations + realizations only.
        # Associations and dependencies route as straight lines later
        # without driving the y-axis hierarchy.
        layout_edges: list[tuple[str, str]] = []
        for g in model.generalizations:
            # Sugiyama: child layer < parent layer (parent at top).
            # In our convention: `from` is child, `to` is parent. We
            # want the parent at a lower y (visually higher up), so
            # the edge in Sugiyama's "above → below" sense is
            # parent → child, i.e. (to_id, from_id).
            layout_edges.append((g.to_id, g.from_id))
        for r in model.realizations:
            layout_edges.append((r.to_id, r.from_id))

        # Use the WIDEST classifier's measured width as Sugiyama's
        # `node_width` so its horizontal compaction respects real box
        # sizes rather than `opts.node_min_width`. Same with height
        # via `layer_height`.
        max_width = max((dimensions[c.id][0] for c in classifiers), default=opts.node_min_width)
        max_height = max((dimensions[c.id][1] for c in classifiers), default=opts.layer_height)
        sugi_cfg = SugiyamaConfig(
            layer_height=max(opts.layer_height, max_height + 40),
            node_width=max_width,
            node_gap=opts.node_gap,
        )
        layout_result = sugiyama_layout(node_ids, layout_edges, config=sugi_cfg)

        # Translate the layout origin to the canvas top-left + a margin.
        # We compute the margin so the LEFTMOST box's LEFT edge lands at
        # `left_margin`, accounting for box widths (Sugiyama gives node
        # centers; we need the leftmost EDGE).
        margin = 40.0
        if layout_result.positions:
            min_left_edge = min(
                x - dimensions[nid][0] / 2 for nid, (x, _) in layout_result.positions.items()
            )
            x_shift = margin - min_left_edge
        else:
            x_shift = margin
        for nid, (x, y) in layout_result.positions.items():
            positions[nid] = (x + x_shift, y + margin)
    else:
        raise ValueError(
            f"unknown layout strategy {opts.layout!r}; expected 'manual' or 'sugiyama'"
        )

    # ── Step 4: pin overrides ──
    for c in classifiers:
        if c.position is not None:
            positions[c.id] = (c.position.x, c.position.y)

    # ── Step 5: emit visual objects ──
    classifier_objects: list[dict[str, Any]] = []
    edge_objects: list[dict[str, Any]] = []
    label_objects: list[dict[str, Any]] = []

    # Compute resolved boxes (the position is conventionally a corner;
    # we use it as the top-left of the box).
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for c in classifiers:
        x, y = positions[c.id]
        w, h = dimensions[c.id]
        # Center the box on the position so connectors land mid-edge.
        # Convention: position is the box center for Sugiyama-positioned
        # nodes, top-left for manually-pinned ones. Normalise to top-left.
        if c.position is None:
            x -= w / 2
        boxes[c.id] = (x, y, w, h)
        classifier_objects.append(_classifier_to_visual(c, boxes[c.id]))

    # Generalizations — child → parent, hollow triangle at parent end
    for g in model.generalizations:
        edge_objects.append(
            _connector_object(g.id, g.from_id, g.to_id, arrow_end_kind="hollow_triangle")
        )

    # Realizations — class → interface, hollow triangle + dashed
    for r in model.realizations:
        edge_objects.append(
            _connector_object(
                r.id,
                r.from_id,
                r.to_id,
                arrow_end_kind="hollow_triangle",
                dashed=True,
            )
        )

    # Associations / aggregations / compositions
    for a in model.associations:
        if a.kind == "aggregation":
            arrow_start = "hollow_diamond"
            arrow_end = None
        elif a.kind == "composition":
            arrow_start = "filled_diamond"
            arrow_end = None
        else:
            # Plain association — open arrow only when navigability is set
            arrow_start = None
            arrow_end = "open_arrow" if a.end2.navigable else None
            if a.end1.navigable:
                arrow_start = "open_arrow"
        edge_objects.append(
            _connector_object(
                a.id,
                a.end1.id_ref,
                a.end2.id_ref,
                arrow_start_kind=arrow_start,
                arrow_end_kind=arrow_end,
                label=a.name,
            )
        )

    # Dependencies — open arrow + dashed
    for d in model.dependencies:
        edge_objects.append(
            _connector_object(
                d.id,
                d.from_id,
                d.to_id,
                arrow_end_kind="open_arrow",
                dashed=True,
                stereotype=d.stereotype,
            )
        )

    # Notes — fallback to rect+text until uml.note primitive lands
    for n in model.notes:
        if n.position is not None:
            nx, ny = n.position.x, n.position.y
        else:
            # Place near the first anchor or at the canvas center
            if n.anchor_ids and n.anchor_ids[0] in boxes:
                ax, ay, _, _ = boxes[n.anchor_ids[0]]
                nx, ny = ax + 200, ay
            else:
                nx, ny = canvas_size[0] / 2, canvas_size[1] / 2
        nw, nh = 220.0, 60.0
        # Note rectangle (dog-ear approximation: just a rect for now)
        label_objects.append(
            {
                "type": "rect",
                "id": f"{n.id}.bg",
                "box": [nx, ny, nw, nh],
                "fill": "#FFF8DC",
                "stroke": {"color": "#999999", "width": 0.5},
                "decorative": True,
            }
        )
        label_objects.append(
            {
                "type": "text",
                "id": f"{n.id}.text",
                "box": [nx + 8, ny + 8, nw - 16, nh - 16],
                "text": n.text,
                "style": {"size": 10, "color": "#1A1A1A", "wrap": True},
                "decorative": True,
            }
        )
        # Dashed anchor connector to each anchor
        for anchor in n.anchor_ids:
            if anchor in boxes:
                edge_objects.append(
                    _connector_object(
                        f"{n.id}.anchor.{anchor}",
                        f"{n.id}.bg",
                        anchor,
                        dashed=True,
                    )
                )

    # ── Step 6: assemble visual block ──
    visual: dict[str, Any] = {
        "tokens": {},
        "layers": [
            {
                "id": "uml.edges",
                "z": 10,
                "objects": edge_objects,
            },
            {
                "id": "uml.classifiers",
                "z": 20,
                "objects": classifier_objects,
            },
            {
                "id": "uml.notes",
                "z": 30,
                "objects": label_objects,
            },
        ],
    }

    return ComposedDiagram(
        visual=visual,
        layout_result=layout_result,
        node_dimensions=dimensions,
    )
