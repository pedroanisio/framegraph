#!/usr/bin/env python3
"""Generate the FrameGraph grammar (EBNF) from the Pydantic schema.

The normative contract for a FrameGraph document is the Pydantic v2
model graph in ``framegraph._schema`` (+ the FrameSet root in
``framegraph._frameset``). This tool derives a *human-readable,
non-normative* EBNF grammar from those models, so the grammar can never
drift from the executable schema: it is produced by walking the JSON
Schema that Pydantic emits for the three document roots.

The EBNF describes the structure of a FrameGraph document over the
YAML/JSON **data model** (a YAML document is a superset of JSON). It is
a structural grammar, not a character-stream grammar: terminals such as
``string`` / ``number`` are YAML scalars, and the brace/bracket
terminals are shown in JSON flow style for clarity — the equivalent YAML
block form is always valid.

Dialect: ISO/IEC 14977-style EBNF. ``=`` defines a rule, ``;`` ends it,
``,`` is concatenation, ``|`` is alternation, ``[ ]`` is optional,
``{ }`` is zero-or-more repetition, ``( )`` groups, ``"x"`` is a
terminal, ``? x ?`` is a special-sequence (lexical token), and
``(* x *)`` is a comment. Literal structural punctuation is quoted
(``"{"``, ``","``) to distinguish it from the EBNF metasymbols.

Output is deterministic (no embedded timestamp) so it can be committed
and drift-gated in CI:

    python scripts/generate_ebnf.py                 # write docs/framegraph.ebnf
    python scripts/generate_ebnf.py -o grammar.ebnf # custom path
    python scripts/generate_ebnf.py --stdout        # print, don't write
    python scripts/generate_ebnf.py --check         # exit 1 if on-disk is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pydantic.json_schema import models_json_schema

import framegraph
from framegraph._frameset import FrameSetDocument
from framegraph._schema import DeckDocument, Document

# Document roots, in the order `validate_any` dispatches them.
ROOTS = ["Document", "DeckDocument", "FrameSetDocument"]

# EBNF terminals for structural punctuation (quoted = terminal, so they
# never collide with the `{ }` / `[ ]` metasymbols).
LB, RB = '"{"', '"}"'
LBK, RBK = '"["', '"]"'
COL, CMA = '":"', '","'

INDENT = "      "
SEP = " ,\n" + INDENT


# ─────────────────────────────────────────────────────────────────
# Schema acquisition
# ─────────────────────────────────────────────────────────────────


def build_defs() -> dict[str, Any]:
    """Return the merged ``$defs`` table for the three document roots."""
    _map, combined = models_json_schema(
        [
            (Document, "validation"),
            (DeckDocument, "validation"),
            (FrameSetDocument, "validation"),
        ],
        ref_template="#/$defs/{model}",
    )
    defs: dict[str, Any] = dict(combined.get("$defs", {}))
    # The roots themselves may live in $defs or only in the top-level
    # map; normalize so every root is addressable as a def.
    for model in (Document, DeckDocument, FrameSetDocument):
        name = model.__name__
        if name not in defs:
            defs[name] = model.model_json_schema(ref_template="#/$defs/{model}")
    return defs


# ─────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────


def ref_name(ref: str) -> str:
    """`#/$defs/RectObject` -> `RectObject`."""
    return ref.rsplit("/", 1)[-1]


def quote(value: Any) -> str:
    """Render a literal scalar value as an EBNF terminal."""
    if value is True:
        return '"true"'
    if value is False:
        return '"false"'
    if value is None:
        return "null"
    return '"' + str(value) + '"'


def is_null(schema: Any) -> bool:
    return isinstance(schema, dict) and schema.get("type") == "null"


def nullable(node: dict[str, Any]) -> bool:
    """True if the field's schema admits an explicit ``null``."""
    if node.get("type") == "null":
        return True
    for key in ("anyOf", "oneOf"):
        if key in node:
            return any(is_null(m) for m in node[key])
    t = node.get("type")
    return isinstance(t, list) and "null" in t


def dedupe(seq: list[str]) -> list[str]:
    out: list[str] = []
    for item in seq:
        if item not in out:
            out.append(item)
    return out


# ─────────────────────────────────────────────────────────────────
# Type expressions
# ─────────────────────────────────────────────────────────────────


def array_expr(node: dict[str, Any]) -> str:
    items = node.get("items")
    item = type_expr(items) if items else "any"
    lo, hi = node.get("minItems"), node.get("maxItems")
    if lo is not None and lo == hi:  # fixed-length tuple
        if lo == 0:
            return f"{LBK} , {RBK}"
        inner = f" , {CMA} , ".join([item] * lo)
        return f"{LBK} , {inner} , {RBK}"
    if lo and lo >= 1:  # one-or-more
        return f"{LBK} , {item} , {{ {CMA} , {item} }} , {RBK}"
    return f"{LBK} , [ {item} , {{ {CMA} , {item} }} ] , {RBK}"  # zero-or-more


def object_expr(node: dict[str, Any]) -> str:
    """Inline expression for a dict-typed / free-form object schema."""
    if node.get("properties"):
        return "object-any"  # anonymous keyed object (not used by the schema today)
    ap = node.get("additionalProperties")
    if isinstance(ap, dict) and ap:
        return f"{LB} , {{ string , {COL} , {type_expr(ap)} }} , {RB}"
    return "object-any"


def type_expr(node: Any) -> str:
    """Map one JSON-Schema node to an EBNF type expression."""
    if not isinstance(node, dict) or node == {}:
        return "any"
    if "discriminator" in node:
        return "VisualObject"
    if "$ref" in node:
        return ref_name(node["$ref"])
    if "const" in node:
        return quote(node["const"])
    if "enum" in node:
        return "( " + " | ".join(quote(v) for v in node["enum"]) + " )"
    if "anyOf" in node or "oneOf" in node:
        members = node.get("anyOf") or node.get("oneOf")
        if any(isinstance(m, dict) and "discriminator" in m for m in members):
            return "VisualObject"
        parts = dedupe([type_expr(m) for m in members if not is_null(m)])
        if not parts:
            return "null"
        return parts[0] if len(parts) == 1 else "( " + " | ".join(parts) + " )"
    t = node.get("type")
    if t == "array":
        return array_expr(node)
    if t == "object":
        return object_expr(node)
    if t in ("string", "integer", "number", "boolean", "null"):
        return t
    if isinstance(t, list):
        parts = dedupe([x for x in t if x != "null"])
        return parts[0] if len(parts) == 1 else "( " + " | ".join(parts) + " )"
    return "any"


def member_expr(name: str, node: dict[str, Any], required: set[str]) -> str:
    """Render one mapping member `"name" : <type>`, optional-wrapped."""
    core = type_expr(node)
    if name in required and nullable(node):
        core = f"( {core} | null )"
    body = f'"{name}" , {COL} , {core}'
    return body if name in required else f"[ {body} ]"


# ─────────────────────────────────────────────────────────────────
# Visual-object union (discriminated) + shared field factoring
# ─────────────────────────────────────────────────────────────────


def object_union(defs: dict[str, Any]) -> list[str]:
    """Ordered list of visual-object def names (concrete types + fallthrough)."""
    items = defs["Layer"]["properties"]["objects"]["items"]
    mapping: dict[str, str] = {}

    def find(node: Any) -> None:
        if isinstance(node, dict):
            if "discriminator" in node:
                mapping.update(node["discriminator"]["mapping"])
            for value in node.values():
                find(value)
        elif isinstance(node, list):
            for value in node:
                find(value)

    find(items)
    names = [ref_name(mapping[k]) for k in sorted(mapping)]
    if "_UnknownObject" in defs and "_UnknownObject" not in names:
        names.append("_UnknownObject")
    return names


def common_object_fields(defs: dict[str, Any], obj_names: list[str]) -> set[str]:
    """Field names shared by every visual-object type (the `_ObjectBase` set)."""
    sets = [set(defs[n].get("properties", {})) - {"type"} for n in obj_names]
    return set.intersection(*sets) if sets else set()


# ─────────────────────────────────────────────────────────────────
# Rule rendering
# ─────────────────────────────────────────────────────────────────


def render_mapping(name: str, defs: dict[str, Any]) -> str:
    """Render a plain (non-visual-object) model as a mapping rule."""
    d = defs[name]
    if "enum" in d:
        return f"{name} = " + " | ".join(quote(v) for v in d["enum"]) + " ;"
    props = d.get("properties", {})
    required = set(d.get("required", []))
    members = [member_expr(p, node, required) for p, node in props.items()]
    if d.get("additionalProperties") is True:
        members.append("{ extra-member }")
    return _wrap(name, members)


def render_object(name: str, defs: dict[str, Any], common: set[str]) -> str:
    """Render a visual-object type, deferring shared fields to the fragment."""
    d = defs[name]
    props = d.get("properties", {})
    required = set(d.get("required", []))
    type_node = props.get("type", {})
    type_lit = quote(type_node["const"]) if "const" in type_node else "string"
    members = [f'"type" , {COL} , {type_lit}']
    for pname, node in props.items():
        if pname == "type" or pname in common:
            continue
        members.append(member_expr(pname, node, required))
    members.append("common-object-fields")
    if d.get("additionalProperties") is True:
        members.append("{ extra-member }")
    return _wrap(name, members)


def render_common_fragment(defs: dict[str, Any], obj_names: list[str], common: set[str]) -> str:
    """Emit the shared `common-object-fields` fragment (all optional)."""
    base = next(
        (n for n in obj_names if (set(defs[n].get("properties", {})) - {"type"}) == common),
        obj_names[0],
    )
    props = defs[base].get("properties", {})
    members = [f'[ "{p}" , {COL} , {type_expr(props[p])} ]' for p in props if p in common]
    body = SEP.join(members)
    return (
        "common-object-fields = (* every field optional; mapping members unordered *)\n"
        + INDENT
        + body
        + "\n    ;"
    )


def _wrap(name: str, members: list[str]) -> str:
    if not members:
        return f"{name} =\n    {LB} , {RB} ;"
    body = SEP.join(members)
    return f"{name} =\n    {LB} ,\n" + INDENT + body + f" ,\n    {RB} ;"


# ─────────────────────────────────────────────────────────────────
# Document assembly
# ─────────────────────────────────────────────────────────────────


HEADER = """\
(* ═══════════════════════════════════════════════════════════════════ *)
(* FrameGraph — grammar (EBNF)                                          *)
(*                                                                      *)
(* GENERATED, NON-NORMATIVE. Do not edit by hand.                       *)
(*   Source of truth : framegraph._schema (Pydantic v2 models) +        *)
(*                      framegraph._frameset.FrameSetDocument           *)
(*   Generator       : scripts/generate_ebnf.py                         *)
(*   framegraph      : v{version}                                         *)
(*                                                                      *)
(* The Pydantic model graph is the executable, normative contract; this *)
(* EBNF is derived from the JSON Schema those models emit, so it cannot *)
(* drift. Regenerate with: python scripts/generate_ebnf.py             *)
(*                                                                      *)
(* Scope: a structural grammar over the YAML/JSON DATA MODEL (a YAML    *)
(* document is a superset of JSON). Terminals `string`/`number`/... are *)
(* YAML scalars; the `"{"`/`"["` terminals are shown in JSON flow style *)
(* — the equivalent YAML block form is always valid. Mapping members    *)
(* are UNORDERED; the commas/braces are the JSON projection only.       *)
(* Models declared `extra="allow"` admit arbitrary extra keys, shown as *)
(* a trailing `{ extra-member }`.                                        *)
(*                                                                      *)
(* Dialect: ISO/IEC 14977.  = define  ; end  , concat  | or            *)
(*   [ ] optional   { } repeat(0+)   ( ) group   "x" terminal           *)
(*   ? x ? lexical token   ;   paren-star ... star-paren = comment       *)
(* ═══════════════════════════════════════════════════════════════════ *)
"""

LEXICAL = """\
(* ── Lexical scalar terminals (YAML scalars / JSON primitives) ── *)
string       = ? any YAML scalar interpreted as text ? ;
number       = ? any YAML number — integer or float ? ;
integer      = ? any YAML integer ? ;
boolean      = "true" | "false" ;
null         = "null" | "~" ;   (* in YAML, an absent/empty value is also null *)
any          = string | number | boolean | null | array-any | object-any ;
array-any    = "[" , [ any , { "," , any } ] , "]" ;
object-any   = "{" , [ member-any , { "," , member-any } ] , "}" ;
member-any   = string , ":" , any ;

(* A model declared `extra="allow"` accepts arbitrary additional keys. *)
extra-member = string , ":" , any ;\
"""


def generate() -> str:
    defs = build_defs()
    obj_names = object_union(defs)
    obj_set = set(obj_names)
    common = common_object_fields(defs, obj_names)

    blocks: list[str] = [HEADER.replace("{version}", framegraph.__version__)]

    blocks.append("(* ── Start symbol ── *)")
    blocks.append("framegraph-document = " + " | ".join(ROOTS) + " ;")

    blocks.append("(* ── Document roots ── *)")
    for root in ROOTS:
        blocks.append(render_mapping(root, defs))

    blocks.append("(* ── Visual object (discriminated on `type`) ── *)")
    blocks.append("VisualObject =\n      " + "\n    | ".join(obj_names) + "\n    ;")
    blocks.append(render_common_fragment(defs, obj_names, common))
    for name in obj_names:
        blocks.append(render_object(name, defs, common))

    blocks.append("(* ── Supporting models ── *)")
    rest = sorted(n for n in defs if n not in ROOTS and n not in obj_set)
    for name in rest:
        blocks.append(render_mapping(name, defs))

    blocks.append(LEXICAL)
    return "\n\n".join(blocks).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "framegraph.ebnf",
        help="output path (default: docs/framegraph.ebnf)",
    )
    parser.add_argument("--stdout", action="store_true", help="print to stdout instead of writing")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the on-disk grammar differs from freshly generated (drift gate)",
    )
    args = parser.parse_args(argv)

    grammar = generate()

    if args.stdout:
        sys.stdout.write(grammar)
        return 0

    if args.check:
        if not args.out.exists():
            print(
                f"[ebnf] MISSING: {args.out} does not exist — run scripts/generate_ebnf.py",
                file=sys.stderr,
            )
            return 1
        current = args.out.read_text(encoding="utf-8")
        if current != grammar:
            print(
                f"[ebnf] STALE: {args.out} is out of date — run scripts/generate_ebnf.py",
                file=sys.stderr,
            )
            return 1
        print(f"[ebnf] OK: {args.out} matches the schema")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(grammar, encoding="utf-8")
    print(f"[ebnf] wrote {args.out} ({len(grammar.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
