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


RENDERERS = {
    "uml.classifier_box": render_classifier_box,
    "uml.actor": render_actor,
}
