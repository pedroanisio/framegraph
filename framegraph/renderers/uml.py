"""UML notation primitives — Phase A.2 of the UML support architecture.

Visual-block object types that draw UML notation. These are
*primitives* — they accept the structured fields that UML notation
requires (visibility, multiplicity, abstract, static, etc.) and
emit SVG with the conventional formatting (visibility prefixes,
italic abstract, underlined static, stereotype guillemets).

Authors who want to hand-place a UML element instantiate these
directly in `visual.layers`. The Phase A.3 class-diagram composer
generates them programmatically from a typed UML model
(`framegraph._uml.UMLClassDiagramModel`) via Sugiyama layout from
`framegraph.layout`.

Currently provides:
    uml.classifier_box — three-compartment box (name, attributes,
                          operations) with full UML notation
                          (stereotypes, visibility prefixes,
                          italic abstract, underlined static).

Future primitives in this module:
    uml.lifeline / uml.activation_bar  (Phase D — sequence diagrams)
    uml.actor / uml.use_case            (Phase B — use-case)
    uml.state / uml.transition          (Phase C — state machines)
    uml.note                            (Phase A.x — once Phase A
                                         lands cleanly)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from framegraph._helpers import attrs, box, esc, fmt, fnum
from framegraph._types import RendererContext

# UML visibility → glyph prefix per UML 2.5 §7.5.4.4.
_VISIBILITY_PREFIX: dict[str, str] = {
    "public": "+",
    "private": "-",
    "protected": "#",
    "package": "~",
}


def _format_attribute(attr: Mapping[str, Any]) -> str:
    """Format one attribute into its UML signature string.

    Order per UML 2.5 §9.5.4: `visibility / name : type [multiplicity]
    = default {constraints}`.

    Args:
        attr: Attribute mapping with the same fields as `UMLAttribute`
            in `framegraph._uml`. Unknown fields are ignored;
            structural fields below are recognized.

    Returns:
        A single-line signature string. Static and abstract are
        applied via `text-decoration` / `font-style` at render time;
        this function returns the textual content only.
    """
    parts: list[str] = []
    vis = _VISIBILITY_PREFIX.get(str(attr.get("visibility", "public")), "+")
    parts.append(vis)

    name = str(attr.get("name", ""))
    if attr.get("derived"):
        name = "/" + name
    parts.append(name)

    type_str = attr.get("type")
    mult = attr.get("multiplicity")
    if type_str:
        suffix = f": {type_str}"
        if mult:
            suffix += f"[{mult}]"
        parts[-1] += suffix
    elif mult:
        parts[-1] += f"[{mult}]"

    default = attr.get("default")
    if default is not None:
        parts[-1] += f" = {default}"

    if attr.get("readonly"):
        parts[-1] += " {readOnly}"

    return " ".join(parts)


def _format_operation(op: Mapping[str, Any]) -> str:
    """Format one operation into its UML signature string.

    Per UML 2.5 §9.6.4: `visibility name(parameters): return-type
    {constraints}`. Parameters with `direction: return` are
    consumed into the return-type slot.

    Args:
        op: Operation mapping with the same fields as `UMLOperation`.

    Returns:
        A single-line signature string.
    """
    vis = _VISIBILITY_PREFIX.get(str(op.get("visibility", "public")), "+")
    name = str(op.get("name", ""))

    params = op.get("parameters") or []
    return_param = next((p for p in params if p.get("direction") == "return"), None)
    formal_params = [p for p in params if p.get("direction") != "return"]

    param_strs: list[str] = []
    for p in formal_params:
        direction = str(p.get("direction", "in"))
        prefix = "" if direction == "in" else f"{direction} "
        pname = str(p.get("name", ""))
        ptype = p.get("type")
        pmult = p.get("multiplicity")
        s = f"{prefix}{pname}"
        if ptype:
            s += f": {ptype}"
        if pmult:
            s += f"[{pmult}]"
        if p.get("default") is not None:
            s += f" = {p['default']}"
        param_strs.append(s)

    sig = f"{vis} {name}({', '.join(param_strs)})"

    # Return type: explicit `return_type` field wins; else use the
    # `direction: return` parameter's type if present.
    return_type = op.get("return_type")
    if not return_type and return_param:
        return_type = return_param.get("type")
    if return_type:
        sig += f": {return_type}"

    if op.get("query"):
        sig += " {query}"

    return sig


def _line_decoration(member: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return `(italic, underline)` for a class member.

    Italic = abstract; underline = static. Per UML 2.5 §11.4.4 and
    §9.4.5 these are the orthogonal text decorations members carry.
    """
    italic = bool(member.get("abstract", False))
    underline = bool(member.get("static", False))
    return italic, underline


def render_classifier_box(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML classifier (class/interface/enumeration) box.

    Three compartments stacked vertically:
      1. Header: optional `«stereotype»` line, then class name (italic
         when `abstract: true`).
      2. Attributes: one line per attribute, formatted per UML §9.5.4.
      3. Operations: one line per operation, formatted per UML §9.6.4.

    Compartments separate themselves with horizontal rules. Empty
    compartments are still drawn (this is the conventional "no
    members" rendering — a thin empty band, not a missing box).

    YAML surface
    ------------
    Required:
        type:    uml.classifier_box
        box:     [x, y, w, h]
        name:    <class name>

    Optional:
        stereotype:  string rendered as `«…»` above the name
        abstract:    bool — name renders italic
        attributes:  list of {name, type, visibility, multiplicity,
                              default, static, derived, readonly,
                              abstract}
        operations:  list of {name, parameters, return_type,
                              visibility, abstract, static, query}
        style:
            border_color:    default chrome_line equivalent
            border_width:    default 0.5
            header_fill:     default panel
            header_text_style:    style id or inline
            member_text_style:    style id or inline
            stereotype_text_style: style id or inline

    Layout
    ------
    Header row height: 28 + (8 if stereotype else 0).
    Attribute compartment: 22px per attribute, min 22 even when empty.
    Operation compartment: 22px per operation, min 22 even when empty.
    Total height = sum of three; if `box[3]` (height) is supplied, it
    OVERRIDES the auto-sum and rows are positioned within it (the
    composer typically supplies an explicit height, since it knows
    the surrounding layout).
    """
    bx, by, bw, _ = box(obj.get("box", [0, 0, 200, 100]))
    style = obj.get("style") or {}
    stereotype = obj.get("stereotype")
    name = str(obj.get("name", ""))
    abstract = bool(obj.get("abstract", False))
    attributes = obj.get("attributes") or []
    operations = obj.get("operations") or []

    # ── Defaults ──
    border_color = r.color(style.get("border_color", "#1A1A1A"), "#1A1A1A")
    border_width = fnum(style.get("border_width"), 1.0)
    header_fill = r.fill_value(style.get("header_fill", "#F0EDE6"), "#F0EDE6")
    body_fill = r.fill_value(style.get("body_fill", "#FFFFFF"), "#FFFFFF")

    member_size = fnum(style.get("member_size"), 11)
    name_size = fnum(style.get("name_size"), 14)
    stereotype_size = fnum(style.get("stereotype_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    line_height = member_size + 8  # 8px leading
    # Header height — depends on stereotype presence
    header_h = 36 if stereotype else 28
    attrs_h = max(line_height, len(attributes) * line_height + 8)
    ops_h = max(line_height, len(operations) * line_height + 8)
    total_h = header_h + attrs_h + ops_h

    # Override with explicit height when supplied (composer-driven sizing)
    obj_box = obj.get("box")
    if isinstance(obj_box, (list, tuple)) and len(obj_box) == 4 and fnum(obj_box[3]) > 0:
        explicit_h = fnum(obj_box[3])
        # Distribute extra space proportionally if explicit > total
        if explicit_h > total_h:
            extra = explicit_h - total_h
            # Half to attrs, half to ops (header stays fixed)
            attrs_h += extra / 2
            ops_h += extra / 2
            total_h = explicit_h
        else:
            total_h = explicit_h

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # ── Body background (full box) ──
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(total_h)}" '
        f'fill="{body_fill}"/>'
    )

    # ── Header background ──
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(header_h)}" '
        f'fill="{header_fill}"/>'
    )

    # ── Header text ──
    cx = bx + bw / 2
    if stereotype:
        # `«stereotype»` line at the top
        st_y = by + 12
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(st_y)}" '
            f'font-family="{font_family}" font-size="{fmt(stereotype_size)}" '
            f'fill="{text_color}" text-anchor="middle" font-style="italic">'
            f"«{esc(stereotype)}»</text>"
        )
        name_y = by + 26
    else:
        name_y = by + 18

    name_attrs: dict[str, Any] = {
        "x": fmt(cx),
        "y": fmt(name_y + name_size * 0.4),
        "font-family": font_family,
        "font-size": fmt(name_size),
        "font-weight": "700",
        "fill": text_color,
        "text-anchor": "middle",
    }
    if abstract:
        name_attrs["font-style"] = "italic"
    out.append(f"<text {attrs(name_attrs)}>{esc(name)}</text>")

    # ── Header rule ──
    rule_y = by + header_h
    out.append(
        f'<line x1="{fmt(bx)}" y1="{fmt(rule_y)}" x2="{fmt(bx + bw)}" y2="{fmt(rule_y)}" '
        f'stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # ── Attribute compartment ──
    attr_top = by + header_h
    text_x = bx + 8
    cursor_y = attr_top + line_height - 2  # baseline of first line
    for a in attributes:
        line_text = _format_attribute(a)
        italic, underline = _line_decoration(a)
        text_attrs: dict[str, Any] = {
            "x": fmt(text_x),
            "y": fmt(cursor_y),
            "font-family": font_family,
            "font-size": fmt(member_size),
            "fill": text_color,
        }
        if italic:
            text_attrs["font-style"] = "italic"
        if underline:
            text_attrs["text-decoration"] = "underline"
        out.append(f"<text {attrs(text_attrs)}>{esc(line_text)}</text>")
        cursor_y += line_height

    # ── Attribute/operation rule ──
    ops_top = attr_top + attrs_h
    out.append(
        f'<line x1="{fmt(bx)}" y1="{fmt(ops_top)}" x2="{fmt(bx + bw)}" y2="{fmt(ops_top)}" '
        f'stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # ── Operation compartment ──
    cursor_y = ops_top + line_height - 2
    for op in operations:
        line_text = _format_operation(op)
        italic, underline = _line_decoration(op)
        text_attrs = {
            "x": fmt(text_x),
            "y": fmt(cursor_y),
            "font-family": font_family,
            "font-size": fmt(member_size),
            "fill": text_color,
        }
        if italic:
            text_attrs["font-style"] = "italic"
        if underline:
            text_attrs["text-decoration"] = "underline"
        out.append(f"<text {attrs(text_attrs)}>{esc(line_text)}</text>")
        cursor_y += line_height

    # ── Outer frame ──
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(total_h)}" '
        f'fill="none" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    out.append("</g>")
    return "\n".join(out)


def render_actor(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML Actor — stick-figure glyph + name label below.

    The stick-figure is drawn from primitive paths so it doesn't
    require a webfont. Proportions are conventional UML notation:
    head 30%, body 40%, arms 25%, legs 30% of the total height.

    YAML surface
    ------------
    Required:
        type:    uml.actor
        box:     [x, y, w, h]
        name:    <actor name>

    Optional:
        style:
            stroke_color:  default "#1A1A1A"
            stroke_width:  default 1.5
            label_size:    default 11
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 60, 100]))
    name = str(obj.get("name", ""))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.5)
    label_size = fnum(style.get("label_size"), 11)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")

    # Reserve label space at the bottom (label_size + 4px gap).
    label_h = label_size + 4
    figure_h = bh - label_h
    cx = bx + bw / 2
    fy_top = by

    # Figure layout (relative to figure_h):
    head_r = figure_h * 0.10  # head radius
    head_cy = fy_top + head_r
    body_top = head_cy + head_r
    body_bottom = fy_top + figure_h * 0.60
    arms_y = body_top + figure_h * 0.10
    arms_w = bw * 0.50
    legs_top = body_bottom
    legs_bottom = fy_top + figure_h
    legs_w = bw * 0.40

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Head — filled none, stroked
    out.append(
        f'<circle cx="{fmt(cx)}" cy="{fmt(head_cy)}" r="{fmt(head_r)}" '
        f'fill="none" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Body
    out.append(
        f'<line x1="{fmt(cx)}" y1="{fmt(body_top)}" x2="{fmt(cx)}" y2="{fmt(body_bottom)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Arms (horizontal cross)
    out.append(
        f'<line x1="{fmt(cx - arms_w / 2)}" y1="{fmt(arms_y)}" '
        f'x2="{fmt(cx + arms_w / 2)}" y2="{fmt(arms_y)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Left leg
    out.append(
        f'<line x1="{fmt(cx)}" y1="{fmt(legs_top)}" '
        f'x2="{fmt(cx - legs_w / 2)}" y2="{fmt(legs_bottom)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Right leg
    out.append(
        f'<line x1="{fmt(cx)}" y1="{fmt(legs_top)}" '
        f'x2="{fmt(cx + legs_w / 2)}" y2="{fmt(legs_bottom)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Label below the figure
    label_y = fy_top + figure_h + label_size
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(label_y)}" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="{fmt(label_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">{esc(name)}</text>'
    )

    out.append("</g>")
    return "\n".join(out)


def render_component_box(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML Component box — rectangle with the component icon glyph.

    The UML 2.5.1 component icon is a small rectangle with two
    protruding tabs on its left side. We draw it in the upper-right
    corner of the component box per UML notation.

    YAML surface
    ------------
    Required:
        type:    uml.component_box
        box:     [x, y, w, h]
        name:    <component name>

    Optional:
        stereotype:  string rendered as `«…»` above the name
        style:
            border_color:    default "#1A1A1A"
            border_width:    default 1.0
            fill:            default "#FFFFFF"
            name_size:       default 14
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 200, 120]))
    name = str(obj.get("name", ""))
    stereotype = obj.get("stereotype")
    style = obj.get("style") or {}

    border_color = r.color(style.get("border_color", "#1A1A1A"), "#1A1A1A")
    border_width = fnum(style.get("border_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    name_size = fnum(style.get("name_size"), 14)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Outer body
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # Component icon — small rect with two tabs on the left, in the
    # upper-right corner of the body.
    icon_w = 18.0
    icon_h = 14.0
    icon_x = bx + bw - icon_w - 8
    icon_y = by + 8
    tab_w = 6.0
    tab_h = 4.0
    # Main rectangle of the icon
    out.append(
        f'<rect x="{fmt(icon_x)}" y="{fmt(icon_y)}" width="{fmt(icon_w)}" height="{fmt(icon_h)}" '
        f'fill="{fill}" stroke="{border_color}" stroke-width="0.75"/>'
    )
    # Two tabs protruding from the left edge of the icon
    for tab_offset_y in (3.0, icon_h - 3.0 - tab_h):
        out.append(
            f'<rect x="{fmt(icon_x - tab_w / 2)}" y="{fmt(icon_y + tab_offset_y)}" '
            f'width="{fmt(tab_w)}" height="{fmt(tab_h)}" '
            f'fill="{fill}" stroke="{border_color}" stroke-width="0.75"/>'
        )

    # Optional stereotype above the name
    cx = bx + bw / 2
    if stereotype:
        st_y = by + 22
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(st_y)}" '
            f'font-family="{font_family}" font-size="10" '
            f'fill="{text_color}" text-anchor="middle" font-style="italic">'
            f"«{esc(stereotype)}»</text>"
        )
        name_y = by + 42
    else:
        name_y = by + 28

    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(name_y)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )

    out.append("</g>")
    return "\n".join(out)


def render_lollipop(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML provided-interface lollipop — circle on a stem.

    YAML surface
    ------------
    Required:
        type:    uml.lollipop
        box:     [x, y, w, h]  — the stem extends across w from the
                                  attachment point at (x, y+h/2);
                                  the circle sits at the far end.
        name:    <interface name>

    Optional:
        style:
            stroke_color:  default "#1A1A1A"
            stroke_width:  default 1.0
            radius:        default 6
            label_size:    default 10
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 40, 16]))
    name = str(obj.get("name", ""))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    radius = fnum(style.get("radius"), 6)
    label_size = fnum(style.get("label_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    # Anchor at left-middle; circle at right-middle
    anchor_x = bx
    anchor_y = by + bh / 2
    circle_cx = bx + bw - radius
    circle_cy = anchor_y

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Stem
    out.append(
        f'<line x1="{fmt(anchor_x)}" y1="{fmt(anchor_y)}" '
        f'x2="{fmt(circle_cx - radius)}" y2="{fmt(circle_cy)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Circle (lollipop tip)
    out.append(
        f'<circle cx="{fmt(circle_cx)}" cy="{fmt(circle_cy)}" r="{fmt(radius)}" '
        f'fill="none" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Label below the circle
    out.append(
        f'<text x="{fmt(circle_cx)}" y="{fmt(circle_cy + radius + label_size + 2)}" '
        f'font-family="{font_family}" font-size="{fmt(label_size)}" '
        f'fill="{text_color}" text-anchor="middle">{esc(name)}</text>'
    )
    out.append("</g>")
    return "\n".join(out)


def render_socket(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML required-interface socket — half-circle on a stem.

    Same layout as the lollipop, but the tip is a leftward-facing
    arc (semicircle) rather than a full circle. Authors connect a
    socket to a lollipop visually by placing them at the same y on
    adjacent components — the arc cradles the circle.
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 40, 16]))
    name = str(obj.get("name", ""))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    radius = fnum(style.get("radius"), 7)
    label_size = fnum(style.get("label_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    anchor_x = bx
    anchor_y = by + bh / 2
    arc_cx = bx + bw - radius
    arc_cy = anchor_y

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Stem
    out.append(
        f'<line x1="{fmt(anchor_x)}" y1="{fmt(anchor_y)}" '
        f'x2="{fmt(arc_cx)}" y2="{fmt(arc_cy)}" '
        f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Arc — open semicircle facing left (the "socket")
    arc_top_x = arc_cx
    arc_top_y = arc_cy - radius
    arc_bot_x = arc_cx
    arc_bot_y = arc_cy + radius
    out.append(
        f'<path d="M {fmt(arc_top_x)} {fmt(arc_top_y)} '
        f"A {fmt(radius)} {fmt(radius)} 0 0 1 "
        f'{fmt(arc_bot_x)} {fmt(arc_bot_y)}" '
        f'fill="none" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Label
    out.append(
        f'<text x="{fmt(arc_cx)}" y="{fmt(arc_cy + radius + label_size + 2)}" '
        f'font-family="{font_family}" font-size="{fmt(label_size)}" '
        f'fill="{text_color}" text-anchor="middle">{esc(name)}</text>'
    )
    out.append("</g>")
    return "\n".join(out)


def render_node_box(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML deployment Node — 3D box (cuboid).

    The node is drawn as a face rectangle plus a top quadrilateral
    (parallelogram) and a right quadrilateral, simulating a cuboid
    in oblique projection.

    YAML surface
    ------------
    Required:
        type:    uml.node_box
        box:     [x, y, w, h]    — the front face
        name:    <node name>

    Optional:
        kind:        device | execution_environment (selects the
                     implicit stereotype)
        stereotype:  string rendered as `«…»` above the name (when
                     present, takes precedence over the implicit
                     keyword from `kind`)
        depth:       isometric depth offset in px (default 18)
        style:
            border_color:   default "#1A1A1A"
            border_width:   default 1.0
            fill:           default "#F5F2EC"
            top_fill:       default same as fill (slightly darker)
            name_size:      default 14
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 220, 130]))
    name = str(obj.get("name", ""))
    kind = str(obj.get("kind", "device"))
    stereotype = obj.get("stereotype")
    depth = fnum(obj.get("depth"), 18)
    style = obj.get("style") or {}

    border_color = r.color(style.get("border_color", "#1A1A1A"), "#1A1A1A")
    border_width = fnum(style.get("border_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#F5F2EC"), "#F5F2EC")
    top_fill = r.fill_value(style.get("top_fill", "#E8E2D2"), "#E8E2D2")
    name_size = fnum(style.get("name_size"), 14)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Top face (parallelogram): from (bx, by) shifted up-right by depth.
    top_pts = (
        f"{fmt(bx)},{fmt(by)} "
        f"{fmt(bx + depth)},{fmt(by - depth)} "
        f"{fmt(bx + bw + depth)},{fmt(by - depth)} "
        f"{fmt(bx + bw)},{fmt(by)}"
    )
    out.append(
        f'<polygon points="{top_pts}" '
        f'fill="{top_fill}" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # Right face (parallelogram).
    right_pts = (
        f"{fmt(bx + bw)},{fmt(by)} "
        f"{fmt(bx + bw + depth)},{fmt(by - depth)} "
        f"{fmt(bx + bw + depth)},{fmt(by + bh - depth)} "
        f"{fmt(bx + bw)},{fmt(by + bh)}"
    )
    out.append(
        f'<polygon points="{right_pts}" '
        f'fill="{top_fill}" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # Front face (rectangle).
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # Stereotype (explicit > implicit kind keyword)
    cx = bx + bw / 2
    if stereotype:
        keyword = stereotype
    elif kind == "execution_environment":
        keyword = "executionEnvironment"
    else:
        keyword = "device"

    st_y = by + 22
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(st_y)}" '
        f'font-family="{font_family}" font-size="10" '
        f'fill="{text_color}" text-anchor="middle" font-style="italic">'
        f"«{esc(keyword)}»</text>"
    )
    name_y = by + 42
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(name_y)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )

    out.append("</g>")
    return "\n".join(out)


def render_artifact_box(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML Artifact — rectangle with «artifact» + document icon.

    The «artifact» keyword sits above the artifact name and a
    folded-document icon is placed in the upper-right corner.

    YAML surface
    ------------
    Required:
        type:    uml.artifact_box
        box:     [x, y, w, h]
        name:    <artifact name>

    Optional:
        stereotype:  sub-stereotype rendered above the implicit «artifact»
        style:
            border_color:   default "#1A1A1A"
            border_width:   default 1.0
            fill:           default "#FFFFFF"
            name_size:      default 12
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 160, 80]))
    name = str(obj.get("name", ""))
    stereotype = obj.get("stereotype")
    style = obj.get("style") or {}

    border_color = r.color(style.get("border_color", "#1A1A1A"), "#1A1A1A")
    border_width = fnum(style.get("border_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    name_size = fnum(style.get("name_size"), 12)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Body
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{border_color}" stroke-width="{fmt(border_width)}"/>'
    )

    # Folded-document icon in the upper-right corner: a small rectangle
    # with the upper-right corner cut.
    icon_w = 16.0
    icon_h = 18.0
    fold = 5.0
    ix = bx + bw - icon_w - 6
    iy = by + 6
    icon_pts = (
        f"{fmt(ix)},{fmt(iy)} "
        f"{fmt(ix + icon_w - fold)},{fmt(iy)} "
        f"{fmt(ix + icon_w)},{fmt(iy + fold)} "
        f"{fmt(ix + icon_w)},{fmt(iy + icon_h)} "
        f"{fmt(ix)},{fmt(iy + icon_h)}"
    )
    out.append(
        f'<polygon points="{icon_pts}" fill="{fill}" stroke="{border_color}" stroke-width="0.75"/>'
    )
    # Fold line
    out.append(
        f'<polyline points="{fmt(ix + icon_w - fold)},{fmt(iy)} '
        f"{fmt(ix + icon_w - fold)},{fmt(iy + fold)} "
        f'{fmt(ix + icon_w)},{fmt(iy + fold)}" '
        f'fill="none" stroke="{border_color}" stroke-width="0.75"/>'
    )

    # «artifact» keyword + optional sub-stereotype above
    cx = bx + bw / 2
    next_y = by + 18
    if stereotype:
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(next_y)}" '
            f'font-family="{font_family}" font-size="10" '
            f'fill="{text_color}" text-anchor="middle" font-style="italic">'
            f"«{esc(stereotype)}»</text>"
        )
        next_y += 14
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(next_y)}" '
        f'font-family="{font_family}" font-size="10" '
        f'fill="{text_color}" text-anchor="middle" font-style="italic">'
        f"«artifact»</text>"
    )
    name_y = next_y + 18
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(name_y)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )

    out.append("</g>")
    return "\n".join(out)


def render_activity_node(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render an activity-diagram node (initial / final / decision / fork / join / etc.).

    YAML surface
    ------------
    Required:
        type:    uml.activity_node
        box:     [x, y, w, h]    — the bounding box.
        kind:    initial | final | flow_final | decision | merge |
                 fork | join

    Optional:
        name:    text label (rendered above or beside the node
                 depending on kind)
        orientation: horizontal | vertical (only relevant for fork/join;
                     defaults to horizontal — a thick horizontal bar)
        style:
            fill:           default "#1A1A1A" for filled circles,
                            "#FFFFFF" for diamonds
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.5
            label_size:     default 11
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 32, 32]))
    kind = str(obj.get("kind", "action"))
    name = obj.get("name")
    orientation = str(obj.get("orientation", "horizontal"))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.5)
    label_size = fnum(style.get("label_size"), 11)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    cx = bx + bw / 2
    cy = by + bh / 2
    radius = min(bw, bh) / 2

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    if kind == "initial":
        fill = r.fill_value(style.get("fill", "#1A1A1A"), "#1A1A1A")
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
    elif kind == "final":
        outer_fill = "#FFFFFF"
        inner_fill = r.fill_value(style.get("fill", "#1A1A1A"), "#1A1A1A")
        # Outer ring
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="{outer_fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Inner solid disc (~60% of outer radius)
        inner_r = radius * 0.55
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(inner_r)}" '
            f'fill="{inner_fill}" stroke="none"/>'
        )
    elif kind == "flow_final":
        # Hollow circle with an X
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        offset = radius * 0.55
        out.append(
            f'<line x1="{fmt(cx - offset)}" y1="{fmt(cy - offset)}" '
            f'x2="{fmt(cx + offset)}" y2="{fmt(cy + offset)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        out.append(
            f'<line x1="{fmt(cx + offset)}" y1="{fmt(cy - offset)}" '
            f'x2="{fmt(cx - offset)}" y2="{fmt(cy + offset)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
    elif kind in ("decision", "merge"):
        # Diamond: four corners on the box midpoints.
        fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
        pts = (
            f"{fmt(cx)},{fmt(by)} "
            f"{fmt(bx + bw)},{fmt(cy)} "
            f"{fmt(cx)},{fmt(by + bh)} "
            f"{fmt(bx)},{fmt(cy)}"
        )
        out.append(
            f'<polygon points="{pts}" '
            f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        if name:
            out.append(
                f'<text x="{fmt(cx)}" y="{fmt(cy + label_size / 3)}" '
                f'font-family="{font_family}" font-size="{fmt(label_size)}" '
                f'fill="{text_color}" text-anchor="middle">{esc(str(name))}</text>'
            )
    elif kind in ("fork", "join"):
        # Thick bar — horizontal by default, vertical when requested.
        fill = r.fill_value(style.get("fill", "#1A1A1A"), "#1A1A1A")
        if orientation == "vertical":
            bar_x = cx - 3
            out.append(
                f'<rect x="{fmt(bar_x)}" y="{fmt(by)}" width="6" height="{fmt(bh)}" '
                f'fill="{fill}" stroke="none"/>'
            )
        else:
            bar_y = cy - 3
            out.append(
                f'<rect x="{fmt(bx)}" y="{fmt(bar_y)}" width="{fmt(bw)}" height="6" '
                f'fill="{fill}" stroke="none"/>'
            )
    else:
        # Fallback: small open circle to make malformed input visible.
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )

    # External label for filled circles (initial/final/flow_final)
    # and for fork/join. Placed below the node.
    if name and kind in ("initial", "final", "flow_final", "fork", "join"):
        label_y = by + bh + label_size + 4
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(label_y)}" '
            f'font-family="{font_family}" font-size="{fmt(label_size)}" '
            f'fill="{text_color}" text-anchor="middle">{esc(str(name))}</text>'
        )

    out.append("</g>")
    return "\n".join(out)


def render_action(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render an activity Action — rounded rectangle with a name label.

    YAML surface
    ------------
    Required:
        type:    uml.action
        box:     [x, y, w, h]
        name:    <action name>

    Optional:
        style:
            fill:           default "#FFFFFF"
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            radius:         corner radius (default 12)
            name_size:      default 12
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 140, 50]))
    name = str(obj.get("name", ""))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    radius = fnum(style.get("radius"), 12)
    name_size = fnum(style.get("name_size"), 12)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    cx = bx + bw / 2
    cy = by + bh / 2

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'rx="{fmt(radius)}" ry="{fmt(radius)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    out.append(
        f'<text x="{fmt(cx)}" y="{fmt(cy + name_size / 3)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'fill="{text_color}" text-anchor="middle">{esc(name)}</text>'
    )
    out.append("</g>")
    return "\n".join(out)


def render_swimlane(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a vertical swim-lane (UML ActivityPartition).

    YAML surface
    ------------
    Required:
        type:    uml.swimlane
        box:     [x, y, w, h]    — the lane rectangle including header.
        name:    <lane name>

    Optional:
        style:
            fill:           default "#FFFFFF"
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            header_height:  default 24
            header_fill:    default "#F0EDE6"
            name_size:      default 12
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 200, 400]))
    name = str(obj.get("name", ""))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    header_h = fnum(style.get("header_height"), 24)
    header_fill = r.fill_value(style.get("header_fill", "#F0EDE6"), "#F0EDE6")
    name_size = fnum(style.get("name_size"), 12)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Body
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Header band
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(header_h)}" '
        f'fill="{header_fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Name
    out.append(
        f'<text x="{fmt(bx + bw / 2)}" y="{fmt(by + header_h / 2 + name_size / 3)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )
    out.append("</g>")
    return "\n".join(out)


def render_state_box(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML simple/composite state — rounded rectangle.

    Renders a rounded rectangle with the state name in the header,
    an optional internal-actions compartment listing entry/exit/do
    when any are supplied, and a body compartment for sub-states
    (when this is a composite state). The composer fills the body
    by placing sub-states in their own resolved boxes — the renderer
    only paints the chrome.

    YAML surface
    ------------
    Required:
        type:    uml.state_box
        box:     [x, y, w, h]
        name:    <state name>

    Optional:
        entry:   string rendered as `entry / <…>`
        exit:    string rendered as `exit / <…>`
        do:      string rendered as `do / <…>`
        composite: bool — when True, draw a divider between header
                   and the body so sub-states sit inside a clear band
        style:
            fill:           default "#FFFFFF"
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            radius:         corner radius (default 14)
            name_size:      default 13
            action_size:    default 10
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 180, 70]))
    name = str(obj.get("name", ""))
    entry = obj.get("entry")
    exit_action = obj.get("exit")
    do = obj.get("do")
    composite = bool(obj.get("composite", False))
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    radius = fnum(style.get("radius"), 14)
    name_size = fnum(style.get("name_size"), 13)
    action_size = fnum(style.get("action_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Body
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'rx="{fmt(radius)}" ry="{fmt(radius)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )

    # Header / name
    header_y = by + name_size + 6
    out.append(
        f'<text x="{fmt(bx + bw / 2)}" y="{fmt(header_y)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )

    # Internal-actions compartment (if any)
    actions: list[str] = []
    if entry:
        actions.append(f"entry / {entry}")
    if exit_action:
        actions.append(f"exit / {exit_action}")
    if do:
        actions.append(f"do / {do}")

    divider_y = header_y + 6
    if actions or composite:
        out.append(
            f'<line x1="{fmt(bx + 8)}" y1="{fmt(divider_y)}" '
            f'x2="{fmt(bx + bw - 8)}" y2="{fmt(divider_y)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width * 0.8)}"/>'
        )

    if actions:
        text_y = divider_y + action_size + 4
        for line in actions:
            out.append(
                f'<text x="{fmt(bx + 10)}" y="{fmt(text_y)}" '
                f'font-family="{font_family}" font-size="{fmt(action_size)}" '
                f'fill="{text_color}">{esc(line)}</text>'
            )
            text_y += action_size + 3

    out.append("</g>")
    return "\n".join(out)


def render_pseudostate(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML pseudostate glyph (choice, junction, history, etc.).

    Initial / final / fork / join overlap with activity-node glyphs;
    those kinds delegate to the activity_node renderer for visual
    consistency. State-machine-specific glyphs:

    - `choice`: hollow diamond.
    - `junction`: small filled disc.
    - `shallow_history`: hollow circle with `H`.
    - `deep_history`: hollow circle with `H*`.
    - `entry_point` / `exit_point`: hollow circle (exit_point adds X).
    - `terminate`: an X glyph.

    YAML surface
    ------------
    Required:
        type:    uml.pseudostate
        box:     [x, y, w, h]
        kind:    <one of the listed kinds>

    Optional:
        name:    label rendered below the glyph
        style:   stroke_color / stroke_width / label_size / fill
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 28, 28]))
    kind = str(obj.get("kind", "junction"))
    name = obj.get("name")
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.5)
    label_size = fnum(style.get("label_size"), 11)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    cx = bx + bw / 2
    cy = by + bh / 2
    radius = min(bw, bh) / 2

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    # Delegate kinds shared with activity diagrams.
    if kind in ("initial", "final", "fork", "join"):
        # Reuse render_activity_node for consistent glyph rendering.
        delegate = dict(obj)
        delegate["type"] = "uml.activity_node"
        return render_activity_node(r, delegate)

    if kind == "choice":
        fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
        pts = (
            f"{fmt(cx)},{fmt(by)} "
            f"{fmt(bx + bw)},{fmt(cy)} "
            f"{fmt(cx)},{fmt(by + bh)} "
            f"{fmt(bx)},{fmt(cy)}"
        )
        out.append(
            f'<polygon points="{pts}" '
            f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
    elif kind == "junction":
        fill = r.fill_value(style.get("fill", "#1A1A1A"), "#1A1A1A")
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
    elif kind in ("shallow_history", "deep_history"):
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        glyph = "H" if kind == "shallow_history" else "H*"
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(cy + label_size / 3)}" '
            f'font-family="{font_family}" font-size="{fmt(label_size)}" '
            f'font-weight="700" fill="{text_color}" text-anchor="middle">'
            f"{esc(glyph)}</text>"
        )
    elif kind in ("entry_point", "exit_point"):
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        if kind == "exit_point":
            offset = radius * 0.55
            out.append(
                f'<line x1="{fmt(cx - offset)}" y1="{fmt(cy - offset)}" '
                f'x2="{fmt(cx + offset)}" y2="{fmt(cy + offset)}" '
                f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
            )
            out.append(
                f'<line x1="{fmt(cx + offset)}" y1="{fmt(cy - offset)}" '
                f'x2="{fmt(cx - offset)}" y2="{fmt(cy + offset)}" '
                f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
            )
    elif kind == "terminate":
        offset = radius * 0.7
        out.append(
            f'<line x1="{fmt(cx - offset)}" y1="{fmt(cy - offset)}" '
            f'x2="{fmt(cx + offset)}" y2="{fmt(cy + offset)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width * 1.5)}"/>'
        )
        out.append(
            f'<line x1="{fmt(cx + offset)}" y1="{fmt(cy - offset)}" '
            f'x2="{fmt(cx - offset)}" y2="{fmt(cy + offset)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width * 1.5)}"/>'
        )
    else:
        # Fallback to a small circle for malformed kind values.
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(radius)}" '
            f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )

    if name:
        label_y = by + bh + label_size + 4
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(label_y)}" '
            f'font-family="{font_family}" font-size="{fmt(label_size)}" '
            f'fill="{text_color}" text-anchor="middle">{esc(str(name))}</text>'
        )

    out.append("</g>")
    return "\n".join(out)


def render_lifeline(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a sequence-diagram lifeline — head box with dashed line below.

    YAML surface
    ------------
    Required:
        type:    uml.lifeline
        box:     [x, y, w, h]    — the FULL lifeline box: head sits
                                   at (x, y, w, head_height), the
                                   dashed line spans from below the
                                   head to (y + h).
        name:    <participant name>

    Optional:
        type_name: optional class/type label rendered as `name:Type`
        actor:     when True, render the head as a stick-figure
                   actor (delegates to render_actor) and use the
                   actor's box as the head footprint.
        head_height: head box height (default 36)
        style:
            fill:           default "#FFFFFF"
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            name_size:      default 12
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 120, 400]))
    name = str(obj.get("name", ""))
    type_name = obj.get("type_name")
    actor = bool(obj.get("actor", False))
    head_h = fnum(obj.get("head_height"), 36)
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    name_size = fnum(style.get("name_size"), 12)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    cx = bx + bw / 2
    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]

    if actor:
        # Inline actor stick figure (head + body + arms + legs) sized
        # to fit inside `head_h` (the band reserved for the head). The
        # dashed timeline starts BELOW the figure + label so neither
        # overlaps the line.
        head_r = max(6.0, min(head_h * 0.16, 10.0))
        # Allocate the head_h band: head circle, body trunk (with
        # arms), legs, gap, label. Anchor everything to `by + 2`.
        head_cy = by + head_r + 2
        trunk_top_y = head_cy + head_r
        trunk_h = head_r * 1.8
        trunk_bot_y = trunk_top_y + trunk_h
        leg_h = head_r * 1.4
        leg_bot_y = trunk_bot_y + leg_h
        arm_y = trunk_top_y + trunk_h * 0.35
        arm_half = head_r * 1.6

        # Head
        out.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(head_cy)}" r="{fmt(head_r)}" '
            f'fill="none" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Trunk (body)
        out.append(
            f'<line x1="{fmt(cx)}" y1="{fmt(trunk_top_y)}" '
            f'x2="{fmt(cx)}" y2="{fmt(trunk_bot_y)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Arms (horizontal, crossing trunk)
        out.append(
            f'<line x1="{fmt(cx - arm_half)}" y1="{fmt(arm_y)}" '
            f'x2="{fmt(cx + arm_half)}" y2="{fmt(arm_y)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Legs (V from waist)
        out.append(
            f'<line x1="{fmt(cx)}" y1="{fmt(trunk_bot_y)}" '
            f'x2="{fmt(cx - arm_half * 0.8)}" y2="{fmt(leg_bot_y)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        out.append(
            f'<line x1="{fmt(cx)}" y1="{fmt(trunk_bot_y)}" '
            f'x2="{fmt(cx + arm_half * 0.8)}" y2="{fmt(leg_bot_y)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Label below the figure (with breathing room).
        label_y = leg_bot_y + name_size + 4
        label = f"{name}:{type_name}" if type_name else name
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(label_y)}" '
            f'font-family="{font_family}" font-size="{fmt(name_size)}" '
            f'fill="{text_color}" text-anchor="middle">{esc(label)}</text>'
        )
        # Dashed timeline starts BELOW the label, not at by+head_h.
        timeline_start_y = label_y + 6
        out.append(
            f'<line x1="{fmt(cx)}" y1="{fmt(timeline_start_y)}" '
            f'x2="{fmt(cx)}" y2="{fmt(by + bh)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}" '
            f'stroke-dasharray="6,5"/>'
        )
    else:
        # Head rectangle
        out.append(
            f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(head_h)}" '
            f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
        )
        # Name (or name:type) inside the head
        label = f"{name}:{type_name}" if type_name else name
        # Head names are conventionally underlined for instances.
        out.append(
            f'<text x="{fmt(cx)}" y="{fmt(by + head_h / 2 + name_size / 3)}" '
            f'font-family="{font_family}" font-size="{fmt(name_size)}" '
            f'font-weight="700" fill="{text_color}" text-anchor="middle" '
            f'text-decoration="underline">{esc(label)}</text>'
        )
        # Dashed lifeline below the head
        out.append(
            f'<line x1="{fmt(cx)}" y1="{fmt(by + head_h)}" '
            f'x2="{fmt(cx)}" y2="{fmt(by + bh)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}" '
            f'stroke-dasharray="6,5"/>'
        )

    out.append("</g>")
    return "\n".join(out)


def render_activation_bar(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a sequence-diagram activation bar — thin filled rectangle.

    YAML surface
    ------------
    Required:
        type:    uml.activation_bar
        box:     [x, y, w, h]

    Optional:
        style:
            fill:           default "#FFFFFF"
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 10, 60]))
    style = obj.get("style") or {}
    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    out.append("</g>")
    return "\n".join(out)


def render_fragment_frame(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a UML CombinedFragment frame — labelled rectangle with operator tag.

    The operator tag is a small pentagon in the upper-left corner.
    Multi-operand operators (alt, par) render dashed dividers between
    operands; the composer supplies operand y-positions via the
    `dividers` field.

    YAML surface
    ------------
    Required:
        type:        uml.fragment_frame
        box:         [x, y, w, h]
        kind:        alt | opt | loop | par | break | …

    Optional:
        operands:    list of guard strings (one per operand)
        dividers:    list of y-coordinates for inter-operand dividers
                     (composer supplies these; absolute coords)
        style:
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            fill:           default "none"
            tag_size:       default 11
            guard_size:     default 10
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 240, 80]))
    kind = str(obj.get("kind", "opt"))
    operands = obj.get("operands") or []
    dividers = obj.get("dividers") or []
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "none"), "none")
    tag_size = fnum(style.get("tag_size"), 11)
    guard_size = fnum(style.get("guard_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Outer frame
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )

    # Operator tag (pentagon) in the upper-left corner.
    tag_w = max(40.0, tag_size * len(kind) * 0.7 + 16)
    tag_h = tag_size + 8
    tag_pts = (
        f"{fmt(bx)},{fmt(by)} "
        f"{fmt(bx + tag_w)},{fmt(by)} "
        f"{fmt(bx + tag_w + 6)},{fmt(by + tag_h / 2)} "
        f"{fmt(bx + tag_w)},{fmt(by + tag_h)} "
        f"{fmt(bx)},{fmt(by + tag_h)}"
    )
    out.append(
        f'<polygon points="{tag_pts}" '
        f'fill="#FFFFFF" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    out.append(
        f'<text x="{fmt(bx + 8)}" y="{fmt(by + tag_h / 2 + tag_size / 3)}" '
        f'font-family="{font_family}" font-size="{fmt(tag_size)}" '
        f'font-weight="700" fill="{text_color}">'
        f"{esc(kind)}</text>"
    )

    # First-operand guard (if any) sits just to the right of the tag.
    if operands:
        out.append(
            f'<text x="{fmt(bx + tag_w + 14)}" y="{fmt(by + tag_h / 2 + tag_size / 3)}" '
            f'font-family="{font_family}" font-size="{fmt(guard_size)}" '
            f'fill="{text_color}">'
            f"[{esc(str(operands[0]))}]</text>"
        )

    # Dashed dividers + per-operand guards (for alt/par)
    for i, dy in enumerate(dividers):
        out.append(
            f'<line x1="{fmt(bx)}" y1="{fmt(dy)}" '
            f'x2="{fmt(bx + bw)}" y2="{fmt(dy)}" '
            f'stroke="{stroke_color}" stroke-width="{fmt(stroke_width * 0.8)}" '
            f'stroke-dasharray="5,4"/>'
        )
        # Operand guard (1-indexed because the first operand sits in
        # the tag region, the i-th divider precedes operand i+1).
        guard_idx = i + 1
        if guard_idx < len(operands):
            out.append(
                f'<text x="{fmt(bx + 8)}" y="{fmt(dy + guard_size + 4)}" '
                f'font-family="{font_family}" font-size="{fmt(guard_size)}" '
                f'fill="{text_color}">'
                f"[{esc(str(operands[guard_idx]))}]</text>"
            )

    out.append("</g>")
    return "\n".join(out)


def render_timing_lane(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a timing-diagram lane — labelled rectangle with state ticks.

    A timing lane stacks the declared states vertically with a thin
    label band on the left listing the state names. The composer
    overlays the state-change step lines on top of this lane.

    YAML surface
    ------------
    Required:
        type:    uml.timing_lane
        box:     [x, y, w, h]
        name:    <lifeline name>
        states:  list of state names (top → bottom)

    Optional:
        label_width:  width reserved for the state-name label column
                      (default 70)
        style:
            stroke_color:   default "#1A1A1A"
            stroke_width:   default 1.0
            fill:           default "#FFFFFF"
            label_fill:     default "#F0EDE6"
            name_size:      default 12
            state_size:     default 10
    """
    bx, by, bw, bh = box(obj.get("box", [0, 0, 600, 100]))
    name = str(obj.get("name", ""))
    states = list(obj.get("states") or [])
    label_w = fnum(obj.get("label_width"), 70)
    style = obj.get("style") or {}

    stroke_color = r.color(style.get("stroke_color", "#1A1A1A"), "#1A1A1A")
    stroke_width = fnum(style.get("stroke_width"), 1.0)
    fill = r.fill_value(style.get("fill", "#FFFFFF"), "#FFFFFF")
    label_fill = r.fill_value(style.get("label_fill", "#F0EDE6"), "#F0EDE6")
    name_size = fnum(style.get("name_size"), 12)
    state_size = fnum(style.get("state_size"), 10)
    text_color = r.color(style.get("text_color", "#1A1A1A"), "#1A1A1A")
    font_family = "Helvetica, Arial, sans-serif"

    out: list[str] = [f"<g {attrs(r.group_attrs(obj))}>"]
    # Lane body
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}" '
        f'fill="{fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Label column
    out.append(
        f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(label_w)}" height="{fmt(bh)}" '
        f'fill="{label_fill}" stroke="{stroke_color}" stroke-width="{fmt(stroke_width)}"/>'
    )
    # Lifeline name (rotated 90° in the label band's top portion)
    out.append(
        f'<text x="{fmt(bx + label_w / 2)}" y="{fmt(by + name_size + 4)}" '
        f'font-family="{font_family}" font-size="{fmt(name_size)}" '
        f'font-weight="700" fill="{text_color}" text-anchor="middle">'
        f"{esc(name)}</text>"
    )
    # State labels (stacked vertically)
    if states:
        n = len(states)
        # Reserve top of lane for the lifeline name; states stack
        # below.
        states_top = by + name_size + 12
        states_h = bh - (states_top - by) - 8
        slot_h = states_h / n
        for i, s in enumerate(states):
            y_center = states_top + i * slot_h + slot_h / 2
            # State label inside the column
            out.append(
                f'<text x="{fmt(bx + label_w - 6)}" y="{fmt(y_center + state_size / 3)}" '
                f'font-family="{font_family}" font-size="{fmt(state_size)}" '
                f'fill="{text_color}" text-anchor="end">{esc(s)}</text>'
            )
            # Light horizontal grid line spanning the lane body
            grid_y = states_top + (i + 1) * slot_h
            if i < n - 1:
                out.append(
                    f'<line x1="{fmt(bx + label_w)}" y1="{fmt(grid_y)}" '
                    f'x2="{fmt(bx + bw)}" y2="{fmt(grid_y)}" '
                    f'stroke="#CCCCCC" stroke-width="0.5" '
                    f'stroke-dasharray="2,3"/>'
                )

    out.append("</g>")
    return "\n".join(out)


RENDERERS = {
    "uml.classifier_box": render_classifier_box,
    "uml.actor": render_actor,
    "uml.component_box": render_component_box,
    "uml.lollipop": render_lollipop,
    "uml.socket": render_socket,
    "uml.node_box": render_node_box,
    "uml.artifact_box": render_artifact_box,
    "uml.activity_node": render_activity_node,
    "uml.action": render_action,
    "uml.swimlane": render_swimlane,
    "uml.state_box": render_state_box,
    "uml.pseudostate": render_pseudostate,
    "uml.lifeline": render_lifeline,
    "uml.activation_bar": render_activation_bar,
    "uml.fragment_frame": render_fragment_frame,
    "uml.timing_lane": render_timing_lane,
}
