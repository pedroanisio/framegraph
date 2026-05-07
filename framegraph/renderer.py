#!/usr/bin/env python3
"""FrameGraph YAML -> SVG renderer  (v3.0)

New in v3 vs v2:
  - visual.symbols  +  type: use   — reusable multi-shape templates (SVG <symbol>/<use>)
  - type: icon  +  tokens.glyph_map — icon-font or Unicode glyph objects
  - tokens.fill_styles gradients   — LinearGradient / RadialGradient resolved as url(#id)
  - layer.opacity                  — fade an entire layer with one field
  - EllipseObject outer_ring       — second concentric stroke (halo / ring effect)
  All v2 features preserved; no existing YAML breaks.

Usage:
    python framegraph_to_svg_v3.py input.yml -o output.svg [--strict] [--no-validate] [--quiet]
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError as exc:
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc

Point = tuple[float, float]
Box = tuple[float, float, float, float]


# ── Lorem ipsum word bank (deterministic, no randomness) ─────────────────────
_LOREM_WORDS = [
    "Lorem",
    "ipsum",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipiscing",
    "elit",
    "sed",
    "do",
    "eiusmod",
    "tempor",
    "incididunt",
    "ut",
    "labore",
    "et",
    "dolore",
    "magna",
    "aliqua",
    "Ut",
    "enim",
    "ad",
    "minim",
    "veniam",
    "quis",
    "nostrud",
    "exercitation",
    "ullamco",
    "laboris",
    "nisi",
    "ut",
    "aliquip",
    "ex",
    "ea",
    "commodo",
    "consequat",
    "Duis",
    "aute",
    "irure",
    "dolor",
    "in",
    "reprehenderit",
    "in",
    "voluptate",
    "velit",
    "esse",
    "cillum",
    "dolore",
    "eu",
    "fugiat",
    "nulla",
    "pariatur",
    "Excepteur",
    "sint",
    "occaecat",
    "cupidatat",
    "non",
    "proident",
    "sunt",
    "in",
    "culpa",
    "qui",
    "officia",
    "deserunt",
    "mollit",
    "anim",
    "id",
    "est",
    "laborum",
    "Sed",
    "ut",
    "perspiciatis",
    "unde",
    "omnis",
    "iste",
    "natus",
    "error",
    "sit",
    "voluptatem",
    "accusantium",
    "doloremque",
    "laudantium",
    "totam",
    "rem",
    "aperiam",
    "eaque",
    "ipsa",
    "quae",
    "ab",
    "illo",
    "inventore",
    "veritatis",
    "et",
    "quasi",
    "architecto",
    "beatae",
    "vitae",
    "dicta",
    "sunt",
    "explicabo",
    "Nemo",
    "enim",
    "ipsam",
    "voluptatem",
    "quia",
    "voluptas",
    "sit",
    "aspernatur",
    "aut",
    "odit",
    "aut",
    "fugit",
    "sed",
    "quia",
    "consequuntur",
    "magni",
    "dolores",
    "eos",
    "qui",
    "ratione",
    "voluptatem",
    "sequi",
    "nesciunt",
    "neque",
    "porro",
    "quisquam",
    "est",
    "qui",
    "dolorem",
    "ipsum",
    "quia",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipisci",
    "velit",
]


def _lorem(n_words: int = 30) -> str:
    """Return N words of lorem ipsum, cycling through the word bank."""
    if n_words <= 0:
        n_words = 30
    words = []
    for i in range(n_words):
        w = _LOREM_WORDS[i % len(_LOREM_WORDS)]
        words.append(w)
    # Capitalise first word, add a period at the end
    if words:
        words[0] = words[0].capitalize()
        words[-1] = words[-1].rstrip(".") + "."
    return " ".join(words)


def _expand_lorem(text: str) -> str:
    """Expand lorem placeholder strings:
      "lorem"      → 30 words
      "lorem:N"    → N words
    Non-lorem strings are returned unchanged.
    """
    t = str(text).strip()
    tl = t.lower()
    if tl == "lorem":
        return _lorem(30)
    if tl.startswith("lorem:"):
        try:
            n = int(tl[6:].strip())
            return _lorem(n)
        except ValueError:
            return _lorem(30)
    return text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def fnum(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if math.isfinite(n) and abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.3f}".rstrip("0").rstrip(".")


def sid(v: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(v))
    if not s or not re.match(r"^[A-Za-z_]", s):
        s = "id_" + s
    return s


def attrs(a: Mapping[str, Any]) -> str:
    out: list[str] = []
    for k, v in a.items():
        if v is None or v is False:
            continue
        if v is True:
            v = "true"
        out.append(f'{k}="{esc(v)}"')
    return " ".join(out)


def box(v: Any) -> Box:
    if not isinstance(v, Sequence) or isinstance(v, (str, bytes)) or len(v) != 4:
        raise ValueError(f"expected box [x,y,w,h], got {v!r}")
    return fnum(v[0]), fnum(v[1]), fnum(v[2]), fnum(v[3])


def pt(v: Any) -> Point:
    if not isinstance(v, Sequence) or isinstance(v, (str, bytes)) or len(v) != 2:
        raise ValueError(f"expected point [x,y], got {v!r}")
    return fnum(v[0]), fnum(v[1])


def deep_get(m: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = m
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def pts_attr(points: Sequence[Point]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class FrameGraphRenderer:
    """Render a FrameGraph YAML document to a single SVG string.

    Construct with a parsed YAML mapping (use `from_yaml_file` for the
    common path that loads from disk), then call `render_svg()` for the
    serialized output or `write_svg(path)` to persist it.

    The class also implements the `RendererContext` Protocol — it is
    passed as the `r` argument to every plug-in registered through
    `register(type_name, fn)` or auto-discovered from
    `framegraph.renderers.*`.

    Attributes:
        scene: `scene` block from the document (canvas, rendering
            contract).
        semantic: `semantic` block (typed nodes/edges, ontology).
        visual: `visual` block (tokens, layers, objects).
        tokens: `visual.tokens` shorthand.
        colors / fonts / text_styles / stroke_styles / fill_styles:
            individual token tables, each defaulting to an empty dict
            when absent in the document.
        glyph_map: token-resolved glyph alias map for icon objects.
        symbols: `visual.symbols` — reusable SVG `<symbol>`/`<use>`
            templates.
        component_defs: `visual.component_defs` — reusable component
            templates.
        layers: ordered list of layer mappings.
        object_index: built during `index_objects()`. Keyed by object
            id; value is `{"box": Box, "ports": dict[str, Point],
            "raw": Mapping}`.
        warnings: per-object render failures appended by `render_svg`.
            Always inspect after rendering — exceptions raised by
            individual object renderers are demoted to comments and
            recorded here, not propagated.

    """

    def __init__(self, doc: Mapping[str, Any]) -> None:
        """Initialize the renderer from a parsed FrameGraph document.

        Args:
            doc: The full FrameGraph YAML document as a mapping. Must
                contain a `visual` block; `scene` and `semantic` are
                optional (default to empty mappings).

        """
        self.doc = doc
        self.scene = doc.get("scene", {}) or {}
        self.semantic = doc.get("semantic", {}) or {}
        self.visual = doc.get("visual", {}) or {}
        self.tokens = self.visual.get("tokens", {}) or {}

        self.colors: Mapping[str, Any] = self.tokens.get("colors", {}) or {}
        self.fonts: Mapping[str, Any] = self.tokens.get("fonts", {}) or {}
        self.text_styles: Mapping[str, Mapping[str, Any]] = self.tokens.get("text_styles", {}) or {}
        self.stroke_styles: Mapping[str, Mapping[str, Any]] = (
            self.tokens.get("stroke_styles", {}) or {}
        )
        self.component_defs: Mapping[str, Mapping[str, Any]] = (
            self.visual.get("component_defs", {}) or {}
        )
        self.layers: list[Mapping[str, Any]] = [
            lyr for lyr in (self.visual.get("layers", []) or []) if isinstance(lyr, Mapping)
        ]

        # ── v3 additions ──────────────────────────────────────────────
        self.glyph_map: dict[str, str] = dict(self.tokens.get("glyph_map", {}) or {})
        self.fill_styles: dict[str, Any] = dict(self.tokens.get("fill_styles", {}) or {})
        self.symbols: dict[str, Any] = dict(self.visual.get("symbols", {}) or {})
        self.gradient_defs: list[str] = []
        self._uses_icon_font: bool = False
        # ──────────────────────────────────────────────────────────────

        self.object_index: dict[str, dict[str, Any]] = {}
        self.semantic_ids = self._collect_semantic_ids()
        self.marker_colors: list[str] = []
        self.warnings: list[str] = []

        # ── HD effect filter registry (lazy) ──────────────────────────
        # Keyed by deterministic SVG id; value is the resolved <filter>
        # element string. `effect_filter_id(kind, spec)` populates this
        # on first use; defs_svg() emits the collected filters.
        self.effect_filters: dict[str, str] = {}

        self._dispatch: dict[str, Any] = {}
        self._register_all()
        self._build_gradients()  # must come before _build_markers (may add colors)
        self._build_markers()
        self.index_objects()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> FrameGraphRenderer:
        """Load and validate a FrameGraph YAML file from disk.

        Args:
            path: Path to a `.yml` / `.yaml` file.

        Returns:
            A configured `FrameGraphRenderer` ready to call
            `render_svg()`.

        Raises:
            ValueError: If the YAML root is not a mapping, or if the
                document does not declare `dsl: FrameGraph`.

        """
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, Mapping):
            raise ValueError("FrameGraph YAML root must be a mapping/object")
        if data.get("dsl") != "FrameGraph":
            raise ValueError(f"expected dsl: FrameGraph, got {data.get('dsl')!r}")
        return cls(data)

    def _collect_semantic_ids(self) -> set[str]:
        ids: set[str] = set()
        for node in self.semantic.get("nodes", []) or []:
            if isinstance(node, Mapping) and node.get("id") is not None:
                ids.add(str(node["id"]))
        for edge in self.semantic.get("edges", []) or []:
            if isinstance(edge, Mapping) and edge.get("id") is not None:
                ids.add(str(edge["id"]))
        ontology = self.semantic.get("ontology", {}) or {}
        for key in ("node_types", "edge_types"):
            entries = ontology.get(key, {}) or {}
            if isinstance(entries, Mapping):
                ids.update(str(k) for k in entries)
        return ids

    # ── v3: gradient defs ─────────────────────────────────────────────
    def _build_gradients(self) -> None:
        """Convert fill_styles entries into SVG gradient <defs> strings.
        Gradient coordinates use objectBoundingBox so they scale with each shape.
        """
        for name, fs in self.fill_styles.items():
            gtype = str(fs.get("type", ""))
            gid = sid("grad_" + name)
            stops_svg = "".join(
                f'<stop offset="{fmt(s.get("offset", 0))}"'
                f' stop-color="{self.color(s.get("color"), "#000000")}"/>'
                for s in (fs.get("stops") or [])
            )
            if gtype == "linear_gradient":
                p1 = fs.get("from", [0, 0])
                p2 = fs.get("to", [0, 1])
                self.gradient_defs.append(
                    f'<linearGradient id="{gid}"'
                    f' x1="{fmt(fnum(p1[0]))}" y1="{fmt(fnum(p1[1]))}"'
                    f' x2="{fmt(fnum(p2[0]))}" y2="{fmt(fnum(p2[1]))}"'
                    f' gradientUnits="objectBoundingBox">{stops_svg}</linearGradient>'
                )
            elif gtype == "radial_gradient":
                c = fs.get("center", [0.5, 0.5])
                r = fnum(fs.get("radius"), 0.5)
                self.gradient_defs.append(
                    f'<radialGradient id="{gid}"'
                    f' cx="{fmt(fnum(c[0]))}" cy="{fmt(fnum(c[1]))}" r="{fmt(r)}"'
                    f' gradientUnits="objectBoundingBox">{stops_svg}</radialGradient>'
                )

    # ── v3: fill resolution (color token OR gradient IdRef) ────────────
    def fill_value(self, v: Any, default: str = "none") -> str:
        """Resolve a fill value:
        - None / "none"  → default
        - fill_styles key → url(#grad_name)
        - color token / literal → hex string
        """
        if v is None:
            return default
        s = str(v)
        if s == "none":
            return "none"
        if s in self.fill_styles:
            return f"url(#{sid('grad_' + s)})"
        return self.color(v, default)

    def _build_markers(self) -> None:
        seen: set[str] = set()
        for ss in self.stroke_styles.values() or []:
            c = self.color(ss.get("color"), "#000000")
            if c not in seen:
                seen.add(c)
                self.marker_colors.append(c)
        if "#000000" not in seen:
            self.marker_colors.append("#000000")

    # ── HD effect filters: shadow + glow ──────────────────────────────
    # Presets are tuned for slide-grade output at 960×660+ canvases.
    # Inline mappings override presets per-object.
    _SHADOW_PRESETS: dict[str, dict[str, Any]] = {
        "small":  {"dx": 0, "dy": 1, "blur": 1.5, "color": "#000000", "opacity": 0.10},
        "medium": {"dx": 0, "dy": 2, "blur": 4.0, "color": "#000000", "opacity": 0.14},
        "large":  {"dx": 0, "dy": 4, "blur": 8.0, "color": "#000000", "opacity": 0.18},
    }
    _GLOW_PRESETS: dict[str, dict[str, Any]] = {
        "small":  {"blur": 2.0, "color": "#FFD700", "opacity": 0.45},
        "medium": {"blur": 4.0, "color": "#FFD700", "opacity": 0.55},
        "large":  {"blur": 8.0, "color": "#FFD700", "opacity": 0.65},
    }

    def _resolve_effect_spec(
        self, kind: str, spec: Any
    ) -> dict[str, Any] | None:
        """Normalize a `shadow:` / `glow:` field to a parameter mapping.

        Accepted forms:
          - None / falsy / "none" → no effect
          - "small" / "medium" / "large" → preset lookup
          - mapping → preset lookup for `preset` key (default "medium"),
            then merged with caller-supplied overrides
        """
        if spec is None or spec is False:
            return None
        presets = self._SHADOW_PRESETS if kind == "shadow" else self._GLOW_PRESETS
        if isinstance(spec, str):
            if spec.lower() in ("none", ""):
                return None
            base = presets.get(spec.lower())
            if base is None:
                # Unknown preset name → treat as no-op rather than error,
                # mirroring the renderer's "tolerant" stance on token misses.
                return None
            return dict(base)
        if isinstance(spec, Mapping):
            preset_name = str(spec.get("preset", "medium")).lower()
            base = dict(presets.get(preset_name, presets["medium"]))
            for k, v in spec.items():
                if k == "preset":
                    continue
                base[k] = v
            return base
        return None

    def effect_filter_id(self, kind: str, spec: Any) -> str | None:
        """Resolve an effect spec to a stable filter id, registering the
        `<filter>` element on first use.

        Args:
            kind: "shadow" or "glow".
            spec: A preset name, mapping, or None. See
                `_resolve_effect_spec` for accepted forms.

        Returns:
            The SVG element id (without `#`) suitable for use in
            `filter="url(#…)"`, or None when `spec` resolves to no effect.
        """
        params = self._resolve_effect_spec(kind, spec)
        if params is None:
            return None
        # Deterministic id from params so identical effects share one <filter>.
        if kind == "shadow":
            key = (
                f"sh_{fmt(fnum(params.get('dx'), 0))}_"
                f"{fmt(fnum(params.get('dy'), 2))}_"
                f"{fmt(fnum(params.get('blur'), 4))}_"
                f"{self.color(params.get('color'), '#000000').lstrip('#').upper()}_"
                f"{fmt(fnum(params.get('opacity'), 0.14))}"
            )
        else:  # glow
            key = (
                f"gl_{fmt(fnum(params.get('blur'), 4))}_"
                f"{self.color(params.get('color'), '#FFD700').lstrip('#').upper()}_"
                f"{fmt(fnum(params.get('opacity'), 0.55))}"
            )
        fid = sid("fg-fx-" + key)
        if fid in self.effect_filters:
            return fid
        if kind == "shadow":
            dx = fnum(params.get("dx"), 0)
            dy = fnum(params.get("dy"), 2)
            blur = fnum(params.get("blur"), 4)
            color = self.color(params.get("color"), "#000000")
            opacity = fnum(params.get("opacity"), 0.14)
            # Filter region must be larger than the source to avoid
            # clipping the shadow at the edges.
            filt = (
                f'<filter id="{fid}"'
                f' x="-20%" y="-20%" width="140%" height="140%">'
                f'<feGaussianBlur in="SourceAlpha" stdDeviation="{fmt(blur)}"/>'
                f'<feOffset dx="{fmt(dx)}" dy="{fmt(dy)}" result="off"/>'
                f'<feFlood flood-color="{esc(color)}"'
                f' flood-opacity="{fmt(opacity)}"/>'
                f'<feComposite in2="off" operator="in" result="shadow"/>'
                f'<feMerge>'
                f'<feMergeNode in="shadow"/>'
                f'<feMergeNode in="SourceGraphic"/>'
                f'</feMerge>'
                f'</filter>'
            )
        else:  # glow
            blur = fnum(params.get("blur"), 4)
            color = self.color(params.get("color"), "#FFD700")
            opacity = fnum(params.get("opacity"), 0.55)
            filt = (
                f'<filter id="{fid}"'
                f' x="-50%" y="-50%" width="200%" height="200%">'
                f'<feGaussianBlur in="SourceAlpha" stdDeviation="{fmt(blur)}"/>'
                f'<feFlood flood-color="{esc(color)}"'
                f' flood-opacity="{fmt(opacity)}"/>'
                f'<feComposite in2="SourceAlpha" operator="in" result="glow"/>'
                f'<feMerge>'
                f'<feMergeNode in="glow"/>'
                f'<feMergeNode in="SourceGraphic"/>'
                f'</feMerge>'
                f'</filter>'
            )
        self.effect_filters[fid] = filt
        return fid

    def effect_filter_attrs(self, obj: Mapping[str, Any]) -> dict[str, Any]:
        """Return SVG attributes wiring `shadow` / `glow` fields on an object.

        Resolves both fields; if both are present, glow wins (it's the
        more visually-dominant effect). Returns an empty dict when no
        effect is declared, so call sites can `.update()` unconditionally.
        """
        for kind in ("glow", "shadow"):
            fid = self.effect_filter_id(kind, obj.get(kind))
            if fid is not None:
                return {"filter": f"url(#{fid})"}
        return {}

    # ------------------------------------------------------------------
    # Object index  (pass 1)
    # ------------------------------------------------------------------

    # ── Per-character-class width tables (Arial, em-units at 1px) ────────
    _CW_BOLD = {
        "narrow": 0.38,
        "normal": 0.56,
        "wide": 0.72,
        "space": 0.28,
        "digit": 0.58,
        "punct": 0.34,
    }
    _CW_NORMAL = {
        "narrow": 0.34,
        "normal": 0.50,
        "wide": 0.65,
        "space": 0.25,
        "digit": 0.52,
        "punct": 0.30,
    }
    _NARROW_CH = set("ijlfrт:;!|1()")
    _WIDE_CH = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw@#%")
    _DIGIT_CH = set("0123456789")
    _PUNCT_CH = set(",.'\"-\u2013\u2014")

    def _char_em(self, c: str, bold: bool) -> float:
        d = self._CW_BOLD if bold else self._CW_NORMAL
        if c in (" ", "\t"):
            return d["space"]
        if c in self._NARROW_CH:
            return d["narrow"]
        if c in self._WIDE_CH:
            return d["wide"]
        if c in self._DIGIT_CH:
            return d["digit"]
        if c in self._PUNCT_CH:
            return d["punct"]
        return d["normal"]

    def _str_width(self, text: str, fs: float, bold: bool) -> float:
        """Estimate rendered width of text in pixels."""
        return sum(self._char_em(c, bold) for c in text) * fs

    def sorted_layers(self) -> list[Mapping[str, Any]]:
        """Return layers ordered by ascending `z` (layers without `z` sort as 0)."""
        return sorted(self.layers, key=lambda lyr: fnum(lyr.get("z"), 0))

    def index_objects(self) -> None:
        """Walk every layer and populate `self.object_index`.

        Called once during `__init__`. Each indexed object contributes
        its bounding box and named ports so that `endpoint(...)` can
        resolve cross-layer connector references.
        """
        for layer in self.sorted_layers():
            for obj in layer.get("objects", []) or []:
                self._index_one(obj)

    def _index_one(self, obj: Mapping[str, Any]) -> None:
        if not isinstance(obj, Mapping) or obj.get("id") is None:
            return
        oid = str(obj["id"])
        b = self.object_box(obj)
        ports = self.object_ports(obj, b)
        self.object_index[oid] = {"box": b, "ports": ports, "raw": obj}
        # Recurse into group/container children (indexed with declared boxes;
        # container will update them with resolved boxes at render time)
        for child in obj.get("children") or obj.get("objects") or []:
            self._index_one(child)

    def object_box(self, obj: Mapping[str, Any]) -> Box | None:
        """Return the canvas-space bounding box `(x, y, w, h)` for an object.

        Falls back through type-specific shorthands when `box` is
        absent: `chip_row.origin` + item widths, `line.from`/`line.to`
        endpoints, etc.

        Args:
            obj: An object mapping with at least a `type` key.

        Returns:
            A 4-tuple `(x, y, w, h)`, or None when no box can be
            inferred from the object's keys.

        """
        if "box" in obj:
            return box(obj["box"])
        if obj.get("type") == "chip_row" and "origin" in obj:
            x, y = pt(obj["origin"])
            gap = fnum(obj.get("gap"), 0)
            h = fnum(obj.get("height"), 0)
            widths: list[float] = [
                fnum(item.get("width"), 0)
                if isinstance(item, Mapping)
                else max(20.0, len(str(item)) * 6.0 + 12.0)
                for item in (obj.get("items", []) or [])
            ]
            return x, y, sum(widths) + max(0, len(widths) - 1) * gap, h
        if obj.get("type") == "line" and "from" in obj and "to" in obj:
            x1, y1 = pt(obj["from"])
            x2, y2 = pt(obj["to"])
            return min(x1, x2), min(y1, y2), abs(x2 - x1) or 1.0, abs(y2 - y1) or 1.0
        # ── v3: use object has the same box as declared ────────────────
        # (already handled by the "box" in obj check above)
        return None

    def object_ports(self, obj: Mapping[str, Any], b: Box | None) -> dict[str, Point]:
        """Return the named anchor points exposed by an object.

        Standard cardinal ports (`center`, `north`, `south`, `east`,
        `west` plus `top`/`bottom`/`left`/`right` aliases) are derived
        from the bounding box. Type-specific extras: `start`/`end`
        for `line` objects, custom port names from `use` symbols.

        Args:
            obj: The object mapping.
            b: The pre-computed bounding box, or None when the object
                has no inferrable box (in which case only type-specific
                ports — if any — are returned).

        Returns:
            Dict mapping port name → `(x, y)` canvas-space coordinate.

        """
        ports: dict[str, Point] = {}
        if b:
            x, y, w, h = b
            ports.update(
                {
                    "center": (x + w / 2, y + h / 2),
                    "north": (x + w / 2, y),
                    "south": (x + w / 2, y + h),
                    "east": (x + w, y + h / 2),
                    "west": (x, y + h / 2),
                    "top": (x + w / 2, y),
                    "bottom": (x + w / 2, y + h),
                    "right": (x + w, y + h / 2),
                    "left": (x, y + h / 2),
                }
            )
        if obj.get("type") == "line":
            if "from" in obj:
                ports["start"] = pt(obj["from"])
            if "to" in obj:
                ports["end"] = pt(obj["to"])
        # ── v3: transform symbol ports to canvas space for use objects ─
        if obj.get("type") == "use":
            sym_name = str(obj.get("symbol", ""))
            sym = self.symbols.get(sym_name, {})
            if sym and "box" in obj:
                ux, uy, uw, uh = box(obj["box"])
                _, _, sw, sh = box(sym.get("box", [0, 0, 1, 1]))
                sx = uw / sw if sw else 1.0
                sy = uh / sh if sh else 1.0
                for pname, pcoord in (sym.get("ports") or {}).items():
                    px, py = pt(pcoord)
                    ports[str(pname)] = (ux + px * sx, uy + py * sy)
        explicit = obj.get("ports", {}) or {}
        if isinstance(explicit, Mapping):
            for name, p in explicit.items():
                ports[str(name)] = pt(p)
        return ports

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Run static checks on the document and return a list of warnings.

        Checks: duplicate object ids, missing ids, `bind` references
        not present in the semantic-ids set, unknown `connector`
        endpoints, and `use` references to undefined symbols.

        Returns:
            One human-readable string per finding. An empty list means
            the document passes validation.

        """
        warnings: list[str] = []
        seen: set[str] = set()
        for layer in self.sorted_layers():
            for obj in layer.get("objects", []) or []:
                if not isinstance(obj, Mapping):
                    warnings.append(f"layer {layer.get('id')}: non-object entry")
                    continue
                oid = obj.get("id")
                if oid is None:
                    warnings.append(f"layer {layer.get('id')}: object missing id")
                    continue
                oid = str(oid)
                if oid in seen:
                    warnings.append(f"duplicate object id: {oid}")
                seen.add(oid)
                bind = obj.get("bind")
                if bind is not None and str(bind) not in self.semantic_ids:
                    warnings.append(f"{oid}: bind '{bind}' not in semantic ids")
                if obj.get("type") == "connector":
                    for side in ("from", "to"):
                        try:
                            self.endpoint(obj.get(side))
                        except Exception as exc:
                            warnings.append(f"connector {oid} invalid {side}: {exc}")
                if obj.get("type") == "use":
                    sym = obj.get("symbol")
                    if sym and sym not in self.symbols:
                        warnings.append(f"{oid}: unknown symbol '{sym}'")
        return warnings

    # ------------------------------------------------------------------
    # Token resolution
    # ------------------------------------------------------------------

    def color(self, v: Any, default: str = "none") -> str:
        """Resolve a color reference to a hex/CSS string.

        Args:
            v: A color token name (resolved through `self.colors`) or a
                literal CSS color (passed through unchanged). None →
                `default`.
            default: Fallback returned when `v` is None.

        """
        if v is None:
            return default
        s = str(v)
        return str(self.colors.get(s, s))

    def font(self, v: Any) -> str:
        """Resolve a font reference to a CSS `font-family` string.

        Args:
            v: A font token name or a literal family string. None →
                `tokens.fonts.primary` (defaulting to
                `"Arial, Helvetica, sans-serif"`).

        """
        if v is None:
            return str(self.fonts.get("primary", "Arial, Helvetica, sans-serif"))
        s = str(v)
        return str(self.fonts.get(s, s))

    def text_style(self, ref: Any) -> dict[str, Any]:
        """Resolve a text-style reference to a fully-defaulted style mapping.

        Args:
            ref: Either a token name (looked up in
                `tokens.text_styles`) or an inline mapping. Missing
                keys are populated with defaults: `font="primary"`,
                `size=12`, `weight=400`, `color="black"`,
                `align="left"`, `line_height=size*1.2`.

        Returns:
            A new dict with `font` and `color` already token-resolved.

        """
        st = (
            dict(ref)
            if isinstance(ref, Mapping)
            else dict(self.text_styles.get(str(ref), {}) or {})
        )
        st.setdefault("font", "primary")
        st.setdefault("size", 12)
        st.setdefault("weight", 400)
        st.setdefault("color", "black")
        st.setdefault("align", "left")
        st.setdefault("line_height", fnum(st.get("size"), 12) * 1.2)
        st["font"] = self.font(st.get("font"))
        st["color"] = self.color(st.get("color"), "#000000")
        return st

    def stroke_style(self, ref: Any = None, inline: Any = None) -> dict[str, Any] | None:
        """Resolve a stroke-style reference, optionally overlaid with inline overrides.

        Args:
            ref: Token name (looked up in `tokens.stroke_styles`) or
                an inline mapping. None to skip the token layer.
            inline: A literal color string (becomes
                `{"color": …, "width": 1}`) or a mapping that overrides
                token fields.

        Returns:
            A normalized style dict with keys `color`, `width`,
            `dash`, `arrow_start`, `arrow_end`. Returns None when
            neither `ref` nor `inline` resolves to anything — callers
            interpret this as "no stroke".

        """
        st: dict[str, Any] = {}
        if isinstance(ref, Mapping):
            st.update(ref)
        elif ref is not None:
            st.update(self.stroke_styles.get(str(ref), {}) or {})
        if isinstance(inline, str):
            st.update({"color": inline, "width": st.get("width", 1)})
        elif isinstance(inline, Mapping):
            st.update(inline)
        if not st:
            return None
        st["color"] = self.color(st.get("color"), "#000000")
        st.setdefault("width", 1)
        st.setdefault("dash", None)
        st.setdefault("arrow_start", False)
        st.setdefault("arrow_end", False)
        return st

    def rect_stroke(self, obj: Mapping[str, Any]) -> dict[str, Any] | None:
        """Resolve the stroke for a `rect`/`ellipse`-style object.

        Layered: `stroke_style` (token) takes precedence, with `stroke`
        as inline override; if only `stroke` is present, it acts as a
        literal inline style. Returns None when the object declares no
        stroke at all.
        """
        if obj.get("stroke_style") is not None:
            return self.stroke_style(obj.get("stroke_style"), obj.get("stroke"))
        if obj.get("stroke") is not None:
            return self.stroke_style(inline=obj.get("stroke"))
        return None

    # ------------------------------------------------------------------
    # Markers + defs
    # ------------------------------------------------------------------

    def marker_id(self, color: str) -> str:
        """Return the SVG `<marker>` id used by arrowheads of the given color."""
        return "ah-" + color.lstrip("#").upper()

    def defs_svg(self) -> str:
        """Emit: optional Tabler Icons @import, gradient defs, per-color arrow markers, effect filters."""
        has_content = (
            self.marker_colors
            or self.gradient_defs
            or self._uses_icon_font
            or self.effect_filters
        )
        if not has_content:
            return ""
        out = ["<defs>"]
        if self._uses_icon_font:
            # Import Tabler Icons webfont so icon codepoints render as glyphs
            out.append(
                "<style>"
                '@import url("https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.29.0'
                '/dist/tabler-icons.min.css");'
                "</style>"
            )
        out.extend(self.gradient_defs)
        # HD effect filters (shadow, glow) — emitted in registration order
        # for deterministic <defs> output across runs.
        out.extend(self.effect_filters.values())
        for c in self.marker_colors:
            mid = self.marker_id(c)
            out.append(
                f'<marker id="{esc(mid)}" viewBox="0 0 8 5"'
                f' markerWidth="8" markerHeight="5" refX="8" refY="2.5"'
                f' orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                f'<path d="M0,0 L8,2.5 L0,5 Z" fill="{esc(c)}"/></marker>'
            )
        out.append("</defs>")
        return "\n".join(out)

    def stroke_attrs(self, st: Mapping[str, Any] | None, *, arrows: bool = False) -> dict[str, Any]:
        """Convert a resolved stroke style into SVG attribute key/value pairs.

        Args:
            st: The output of `stroke_style(...)`, or None for "no
                stroke" (returns `{"stroke": "none"}`).
            arrows: When True, attach `marker-start` / `marker-end`
                URLs based on `arrow_start` / `arrow_end` flags in the
                style. Used for connectors and lines that should
                render arrowheads.

        Returns:
            A dict with SVG-ready keys (`stroke`, `stroke-width`,
            `stroke-linecap`, `stroke-linejoin`, `stroke-dasharray`,
            `marker-start`, `marker-end`).

        """
        if not st:
            return {"stroke": "none"}
        color = self.color(st.get("color"), "#000000")
        width = fnum(st.get("width"), 1)
        # ── Hairline guard ──────────────────────────────────────────────
        # Sub-px strokes shimmer / disappear under non-integer raster
        # scaling. When `rendering_contract.hairline_guard` is true,
        # promote any stroke under the threshold (default 0.75px) to
        # the threshold. Opt-in: existing v1.x fixtures keep their
        # exact stroke widths and pinned goldens stay valid.
        if width > 0 and deep_get(
            self.scene, ["rendering_contract", "hairline_guard"], False
        ):
            min_w = fnum(
                deep_get(self.scene, ["rendering_contract", "hairline_min"], 0.75),
                0.75,
            )
            if width < min_w:
                width = min_w
        a: dict[str, Any] = {
            "stroke": color,
            "stroke-width": fmt(width),
            "stroke-linecap": st.get("linecap", "butt"),
            "stroke-linejoin": st.get("linejoin", "round"),
        }
        dash = st.get("dash")
        if dash:
            if isinstance(dash, Sequence) and not isinstance(dash, str):
                a["stroke-dasharray"] = " ".join(fmt(x) for x in dash)
            else:
                a["stroke-dasharray"] = dash
        if arrows:
            mid = "url(#" + self.marker_id(color) + ")"
            if st.get("arrow_start"):
                a["marker-start"] = mid
            if st.get("arrow_end"):
                a["marker-end"] = mid
        return a

    # ------------------------------------------------------------------
    # SVG document  (pass 2)
    # ------------------------------------------------------------------

    def canvas_size(self) -> tuple[float, float]:
        """Return the canvas `(width, height)` in user units.

        Reads `scene.canvas.size`; falls back to
        `scene.source_image.{width,height}`, then `(1000, 600)`.
        """
        size = deep_get(self.scene, ["canvas", "size"])
        if isinstance(size, Sequence) and not isinstance(size, (str, bytes)) and len(size) == 2:
            return fnum(size[0], 1000), fnum(size[1], 600)
        return (
            fnum(deep_get(self.scene, ["source_image", "width"], 1000)),
            fnum(deep_get(self.scene, ["source_image", "height"], 600)),
        )

    def group_attrs(
        self, obj: Mapping[str, Any], extra: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build the SVG `<g>` attribute dict for a wrapped object.

        Args:
            obj: The object being rendered (provides `id`, `type`,
                `bind`, `decorative`, `opacity`).
            extra: Additional attributes to merge in last (override
                anything derived from `obj`).

        """
        a: dict[str, Any] = {
            "id": sid(obj.get("id", "object")),
            "data-type": obj.get("type", "object"),
        }
        if obj.get("bind") is not None:
            a["data-bind"] = obj["bind"]
        if obj.get("decorative") is not None:
            a["data-decorative"] = "true" if obj["decorative"] else "false"
        if obj.get("opacity") is not None:
            a["opacity"] = fmt(obj["opacity"])
        if extra:
            a.update(extra)
        return a

    def render_svg(self) -> str:
        """Render the document and return the SVG as a string.

        Walks every layer in z-order and dispatches each object to its
        registered renderer. Per-object render failures are demoted to
        an HTML comment in the output and an entry in
        `self.warnings`; the SVG itself is always well-formed.

        Returns:
            A complete `<?xml…?>`-prefixed SVG document ending with
            a newline.

        """
        width, height = self.canvas_size()
        title = esc(self.scene.get("name") or self.scene.get("id") or "FrameGraph")
        desc = esc(self.scene.get("description") or "Generated from FrameGraph YAML")
        body: list[str] = []
        for layer in self.sorted_layers():
            layer_id = str(layer.get("id", "layer"))
            # ── v3: layer-level opacity ────────────────────────────────
            layer_opacity = layer.get("opacity")
            op_attr = f' opacity="{fmt(layer_opacity)}"' if layer_opacity is not None else ""
            body.append(
                f'<g id="{esc(sid("layer_" + layer_id))}"'
                f' data-layer="{esc(layer_id)}"'
                f' data-z="{esc(layer.get("z", ""))}"'
                f"{op_attr}>"
            )
            for obj in layer.get("objects", []) or []:
                if not isinstance(obj, Mapping):
                    continue
                try:
                    rendered = self.render_object(obj)
                except Exception as exc:
                    self.warnings.append(f"skipped {obj.get('id', '<unknown>')}: {exc}")
                    rendered = f"<!-- skipped {esc(obj.get('id', '<unknown>'))}: {esc(exc)} -->"
                body.append("  " + rendered.replace("\n", "\n  "))
            body.append("</g>")
        defs = self.defs_svg()
        # ── HD render hints ──────────────────────────────────────────────
        # `render_quality: legacy` reverts to v1.x behaviour (no hints).
        # Default is `hd`: enables sharper geometry + glyph rasterisation
        # without changing layout, attribute names, or the DOM shape.
        quality = str(
            deep_get(self.scene, ["rendering_contract", "render_quality"], "hd")
        ).lower()
        hd_attrs = (
            ' shape-rendering="geometricPrecision"'
            ' text-rendering="optimizeLegibility"'
            if quality != "legacy"
            else ""
        )
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' width="{fmt(width)}" height="{fmt(height)}"'
            f' viewBox="0 0 {fmt(width)} {fmt(height)}"'
            f'{hd_attrs}'
            f' role="img" aria-labelledby="svg-title svg-desc">',
            f'<title id="svg-title">{title}</title>',
            f'<desc  id="svg-desc">{desc}</desc>',
        ]
        if defs:
            out.append(defs)
        # ── debug_boxes overlay ──────────────────────────────────────────
        debug = deep_get(self.scene, ["rendering_contract", "debug_boxes"], False)
        if debug:
            type_colors = {
                "text": "#E35205",
                "bullet_list": "#E35205",
                "image": "#009A44",
                "container": "#002060",
                "use": "#8B00FF",
                "bar_chart": "#1A6FA8",
                "line_chart": "#1A6FA8",
            }
            box_svgs: list[str] = []
            for oid, rec in self.object_index.items():
                b = rec.get("box")
                if not b:
                    continue
                bx, by, bw, bh = b
                if bw < 1 or bh < 1:
                    continue
                t_ = rec.get("raw", {}).get("type", "")
                sc = type_colors.get(t_, "#B4B2A9")
                r_svg = (
                    f'<rect x="{fmt(bx)}" y="{fmt(by)}" width="{fmt(bw)}" height="{fmt(bh)}"'
                    f' fill="none" stroke="{sc}" stroke-width="0.75"'
                    f' stroke-dasharray="3,2" opacity="0.7">'
                    f"<title>{esc(oid)} [{t_}]</title></rect>"
                )
                box_svgs.append(r_svg)
                for pname, pcoord in rec.get("ports", {}).items():
                    if pname not in ("center", "east", "west", "north", "south"):
                        continue
                    px_, py_ = pcoord
                    box_svgs.append(
                        f'<circle cx="{fmt(px_)}" cy="{fmt(py_)}" r="2" fill="{sc}" opacity="0.5"/>'
                    )
            if box_svgs:
                body.append(
                    '<g id="_debug_boxes" data-debug="true" pointer-events="none">\n  '
                    + "\n  ".join(box_svgs)
                    + "\n</g>"
                )

        out.extend(body)
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def write_svg(self, path: str | Path) -> None:
        """Render the document and write the SVG to disk (UTF-8)."""
        Path(path).write_text(self.render_svg(), encoding="utf-8")

    # ------------------------------------------------------------------
    # Object dispatch
    # ------------------------------------------------------------------

    def _register_all(self) -> None:
        """Auto-discover and register all built-in renderer modules."""
        from framegraph.renderers import ALL_MODULES

        for mod in ALL_MODULES:
            for type_name, fn in mod.RENDERERS.items():
                self._dispatch[type_name] = fn

    def register(self, type_name: str, fn) -> None:
        """Register a custom object-type renderer.

        fn signature: fn(renderer: FrameGraphRenderer, obj: Mapping) -> str

        Example::

            def render_callout(r, obj):
                x, y, w, h = box(obj.get("box", [0,0,0,0]))
                return f'<g id="{obj.get("id")}"><rect x="{x}"…/></g>'

            my_renderer.register("callout", render_callout)
        """
        self._dispatch[str(type_name)] = fn

    def render_object(self, obj: Mapping[str, Any]) -> str:
        """Dispatch a single object to its registered renderer.

        Args:
            obj: Object mapping with a `type` key.

        Returns:
            The renderer's SVG fragment, or an HTML comment when the
            type has no registered handler.

        """
        t = obj.get("type")
        fn = self._dispatch.get(t)
        if fn:
            return fn(self, obj)
        return f"<!-- unsupported object type {esc(t)} -->"

    # ------------------------------------------------------------------
    # Plug-in contract delegates (v2.0 modular-split repair)
    #
    # The renderer modules in framegraph.renderers.* are written against
    # the RendererContext Protocol declared in framegraph._types. That
    # Protocol exposes three callable members — text_svg, render_rect,
    # eval_length — whose implementations live as free functions in the
    # renderer modules themselves (text_objects.text_svg,
    # shapes.render_rect, layout.eval_length). The methods below thread
    # those free functions through the Protocol so plug-ins can call
    # them as r.text_svg(...), r.render_rect(...), r.eval_length(...)
    # without having to import the modules directly.
    #
    # Imports are deferred to avoid a circular import: renderers.* import
    # framegraph._types (the Protocol), and renderer.py imports
    # renderers.ALL_MODULES inside _register_all — pulling these symbols
    # at module level would close the loop.
    # ------------------------------------------------------------------

    def text_svg(
        self,
        content: Any,
        b: Box,
        style: Mapping[str, Any],
        *,
        rotation: Any = None,
        extra: Mapping[str, Any] | None = None,
    ) -> str:
        """Render `content` as text inside box `b` using the resolved `style`.

        Delegates to `framegraph.renderers.text_objects.text_svg`.
        """
        from framegraph.renderers.text_objects import text_svg as _text_svg

        return _text_svg(self, content, b, style, rotation=rotation, extra=extra)

    def render_rect(self, obj: Mapping[str, Any]) -> str:
        """Render a single `rect` object.

        Delegates to `framegraph.renderers.shapes.render_rect`. Distinct from
        `render_object({type: rect, ...})` in that it skips the dispatch
        layer — useful for plug-ins that need to draw a rectangle without
        registering or constructing a full object record.
        """
        from framegraph.renderers.shapes import render_rect as _render_rect

        return _render_rect(self, obj)

    def eval_length(self, value: Any, total: float) -> float:
        """Resolve a length expression against `total`.

        Accepts numbers, percent strings (`"40%"`), and `calc(P% +/- N)`
        expressions; anything else is coerced via `fnum`. Delegates to
        `framegraph.renderers.layout.eval_length`.
        """
        from framegraph.renderers.layout import eval_length as _eval_length

        return _eval_length(self, value, total)

    # ------------------------------------------------------------------
    # Shape renderers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # SP-3: Data-viz primitives  (v1.5)
    # ------------------------------------------------------------------
    # Shared chart YAML surface:
    #
    #   `type`: bar_chart | line_chart
    #   id:   my_chart
    #   box:  [x, y, w, h]
    #
    #   # bar_chart specific:
    #   data:
    #     labels:       ["Q1","Q2","Q3","Q4"]
    #     values:       [100, 127, 158, 196]     # single series
    #     # OR multi-series:
    #     series:
    #       - {label: "Mobile", values: [100,127,158,196], color: primary}
    #       - {label: "Desktop", values: [80,75,70,68],    color: accent}
    #     note: "Source: ABComm 2024 — illustrative"
    #
    #   style:
    #     bar_fill:       primary      # single-series bar colour (token or hex)
    #     bar_width:      0.72         # fraction of slot (0.1–0.95)
    #     axis_color:     text_muted
    #     label_style:    axis_label   # text style ref for axis labels
    #     value_labels:   true         # show value above each bar
    #     value_style:    bar_value    # text style for value labels
    #     baseline:       0            # y value for x axis
    #     grid_lines:     true
    #     grid_color:     "#EEEEEE"
    #     note_style:     caption      # text style for data note
    #     padding: [40, 20, 32, 16]   # [left, top, right, bottom] inside box
    #
    #   # line_chart specific:
    #   data:
    #     series:
    #       - {label: "No action",    values: [100,134,180,242], color: "#CC0000"}
    #       - {label: "Engage now",   values: [100,108,116,125], color: "#009A44"}
    #     x_labels:  ["Q1","Q2","Q3","Q4"]
    #     note: "Illustrative — directional only"
    #
    #   style:
    #     stroke_width:   1.5
    #     show_legend:    true
    #     legend_pos:     bottom_right  # bottom_right | bottom_left | top_right | top_left
    #     point_radius:   0             # 0 = no dots; >0 = filled circle at each data point
    #     grid_lines:     true
    #     grid_color:     "#EEEEEE"
    #     axis_color:     text_muted
    #     label_style:    axis_label
    #     padding:  [40, 16, 16, 28]   # [left, top, right, bottom]
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # SP-1a: Auto-layout container  (v1.4 — kind: stack only)
    # ------------------------------------------------------------------
    # Schema (designed for backward-compat v2.0 extension to grid/row):
    #
    #   `type`: container
    #   id:   my_container
    #   box:  [x, y, w, h]       # container bounds; required
    #   layout:
    #     kind:      stack        # stack | grid | row  (grid/row deferred to v2.0)
    #     direction: vertical     # vertical (default) | horizontal
    #     gap:       12           # px between children (default: 0)
    #     align:     stretch      # cross-axis: stretch (default) | start | center | end
    #     padding:   [16, 12]     # [h, v] or single value (default: 0)
    #     justify:   start        # main-axis: start (default) | center | end | space_between
    #   children:
    #     - type: rect            # any renderable object
    #       id:   child_1
    #       # box is OPTIONAL for children inside a container.
    #       # The container assigns the main-axis position and cross-axis size
    #       # (when align: stretch).  Children may declare their preferred
    #       # size in the main-axis dimension via box; the container uses it
    #       # if present, otherwise distributes space equally.
    #       # A "flex" key overrides equal distribution with a weight ratio.
    #
    # After layout, each child's resolved box is written back into a copy
    # before rendering, so all nested resolvers (stroke, text, ports) see
    # the correct absolute coordinates.
    # ------------------------------------------------------------------

    def endpoint(self, ep):
        """Resolve a connector endpoint to a canvas-space (x, y) point.

        Accepted forms:
          [x, y]                       — literal coordinate pair
          {point: [x, y]}              — explicit point map
          {object: "id"}               — object center
          {object: "id", port: "east"} — named port (lifted to canvas space for use objects)
          {object: "id", side: "north", offset: 10}  — cardinal side anchor
          "object_id.port_name"        — dot-notation shorthand (SP-4b)
          "object_id"                  — object center shorthand
        """
        # ── dot-notation string: "obj_id.port_name" or "obj_id" ──────────
        if isinstance(ep, str):
            if "." in ep:
                oid, port = ep.split(".", 1)
            else:
                oid, port = ep, None
            oid = oid.strip()
            if oid not in self.object_index:
                raise ValueError(f"unknown endpoint object {oid!r} (from {ep!r})")
            rec = self.object_index[oid]
            if port:
                port = port.strip()
                if port not in rec["ports"]:
                    raise ValueError(
                        f"object {oid!r} has no port {port!r} "
                        f"(available: {list(rec['ports'].keys())})"
                    )
                return rec["ports"][port]
            return rec["ports"].get("center", (0.0, 0.0))
        # ── map form ──────────────────────────────────────────────────────
        if isinstance(ep, Mapping):
            if "point" in ep:
                return pt(ep["point"])
            oid = ep.get("object")
            if oid is None or str(oid) not in self.object_index:
                raise ValueError(f"unknown endpoint object {oid!r}")
            rec = self.object_index[str(oid)]
            if ep.get("port") is not None:
                port = str(ep["port"])
                if port not in rec["ports"]:
                    raise ValueError(f"object {oid!r} has no port {port!r}")
                return rec["ports"][port]
            if ep.get("side") is not None:
                return self.side_anchor(rec, str(ep["side"]), fnum(ep.get("offset"), 0))
            return rec["ports"].get("center", (0.0, 0.0))
        # ── coordinate pair ───────────────────────────────────────────────
        return pt(ep)

    def side_anchor(self, rec: Mapping[str, Any], side: str, offset: float = 0.0) -> Point:
        """Return a point on a named side of an indexed object.

        Args:
            rec: An entry from `self.object_index` (must have a
                non-empty `box`).
            side: One of `north`/`top`, `south`/`bottom`,
                `east`/`right`, `west`/`left`. Anything else returns
                the box center.
            offset: Tangential offset along the chosen side (positive
                in the canvas-x direction for top/bottom, in the
                canvas-y direction for left/right).

        Raises:
            ValueError: If `rec["box"]` is missing or falsy.

        """
        b = rec.get("box")
        if not b:
            raise ValueError("side_anchor requires object box")
        x, y, w, h = b
        if side in ("north", "top"):
            return x + w / 2 + offset, y
        if side in ("south", "bottom"):
            return x + w / 2 + offset, y + h
        if side in ("east", "right"):
            return x + w, y + h / 2 + offset
        if side in ("west", "left"):
            return x, y + h / 2 + offset
        return x + w / 2, y + h / 2

    def path_d(self, points: Sequence[Point]) -> str:
        """Build an SVG `path` `d` attribute from a polyline point list.

        Returns an empty string when `points` is empty. The first
        point becomes a `M` (moveto); subsequent points become `L`
        (lineto) segments.
        """
        if not points:
            return ""
        d = [f"M {fmt(points[0][0])} {fmt(points[0][1])}"]
        for px, py in points[1:]:
            d.append(f"L {fmt(px)} {fmt(py)}")
        return " ".join(d)

    def line_svg(
        self,
        obj: Mapping[str, Any],
        points: Sequence[Point],
        style_name: Any = None,
        force_poly: bool = False,
    ) -> str:
        """Render a line or polyline object to an SVG fragment.

        Args:
            obj: The owning object (provides `id`, `type`, optional
                `stroke`/`stroke_style`).
            points: Two-or-more canvas-space coordinates.
            style_name: Stroke-style override, used when the caller
                wants to force a specific token regardless of the
                object's own `stroke_style`.
            force_poly: When True, always emit `<polyline>` even when
                exactly two points are supplied. Used by `polyline`
                renderers; line renderers leave it False so two-point
                inputs collapse to `<line>`.

        """
        st = self.stroke_style(
            style_name or obj.get("stroke_style"),
            obj.get("stroke") if isinstance(obj.get("stroke"), Mapping) else None,
        ) or self.stroke_style("direct_flow")
        if len(points) == 2 and not force_poly:
            p1, p2 = points
            geom: dict[str, Any] = {
                "x1": fmt(p1[0]),
                "y1": fmt(p1[1]),
                "x2": fmt(p2[0]),
                "y2": fmt(p2[1]),
                "fill": "none",
            }
            geom.update(self.stroke_attrs(st, arrows=True))
            svg = f"<line {attrs(geom)}/>"
        else:
            geom = {"points": pts_attr(points), "fill": "none"}
            geom.update(self.stroke_attrs(st, arrows=True))
            svg = f"<polyline {attrs(geom)}/>"
        return f"<g {attrs(self.group_attrs(obj))}>{svg}</g>"

    def render_connector(self, obj):
        start = self.endpoint(obj.get("from"))
        end = self.endpoint(obj.get("to"))
        route = obj.get("route", {}) or {"type": "straight"}
        rtype = str(route.get("type", "straight"))
        if rtype == "straight":
            points = [start, end]
        elif rtype in ("orthogonal", "polyline"):
            if route.get("points"):
                points = [pt(p) for p in route["points"]]
                if points and points[0] != start:
                    points.insert(0, start)
                if points and points[-1] != end:
                    points.append(end)
            else:
                mid_x = (start[0] + end[0]) / 2
                points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
        elif rtype == "bezier":
            c1 = pt(route.get("control1", route.get("c1", start)))
            c2 = pt(route.get("control2", route.get("c2", end)))
            d = f"M {fmt(start[0])} {fmt(start[1])} C {fmt(c1[0])} {fmt(c1[1])} {fmt(c2[0])} {fmt(c2[1])} {fmt(end[0])} {fmt(end[1])}"
            points = []
        else:
            raise ValueError(f"unsupported route type '{rtype}'")
        if rtype != "bezier":
            d = self.path_d(points)
        st = self.stroke_style(
            obj.get("stroke_style"),
            obj.get("stroke") if isinstance(obj.get("stroke"), Mapping) else None,
        )
        a: dict[str, Any] = {"d": d, "fill": "none"}
        a.update(self.stroke_attrs(st, arrows=True))
        out = [f"<g {attrs(self.group_attrs(obj))}>", f"<path {attrs(a)}/>"]
        label = obj.get("label")
        if isinstance(label, Mapping):
            out.append(
                self.text_svg(
                    label.get("text", ""),
                    box(label.get("box", [0, 0, 0, 0])),
                    self.text_style(label.get("style", "tiny")),
                )
            )
        out.append("</g>")
        return "\n".join(out)

    def render_legend(self, obj):
        out = [f"<g {attrs(self.group_attrs(obj))}>"]
        for item in obj.get("items", []) or []:
            if not isinstance(item, Mapping):
                continue
            sample = item.get("sample", {}) or {}
            item_id = item.get("id", "legend_item")
            if sample.get("type") == "line":
                pseudo = {
                    "id": str(item_id) + ".sample",
                    "type": "legend_sample",
                    "bind": item.get("bind"),
                    "stroke_style": sample.get("stroke_style"),
                }
                out.append(
                    self.line_svg(
                        pseudo,
                        [pt(sample.get("from", [0, 0])), pt(sample.get("to", [0, 0]))],
                        sample.get("stroke_style"),
                    )
                )
            elif sample.get("type") in ("rounded_rect", "rect"):
                pseudo = {
                    "id": str(item_id) + ".sample",
                    "type": "legend_sample",
                    "bind": item.get("bind"),
                    "box": sample.get("box", [0, 0, 0, 0]),
                    "radius": sample.get("radius", 0),
                    "fill": sample.get("fill", "none"),
                    "stroke": sample.get("stroke"),
                }
                out.append(self.render_rect(pseudo))
            label = item.get("label")
            if isinstance(label, Mapping):
                out.append(
                    self.text_svg(
                        label.get("text", ""),
                        box(label.get("box", [0, 0, 0, 0])),
                        self.text_style(label.get("style", "legend")),
                    )
                )
        out.append("</g>")
        return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="FrameGraph YAML → SVG renderer v3")
    p.add_argument("input", type=Path)
    p.add_argument("output_positional", type=Path, nargs="?")
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = args.output or args.output_positional
    try:
        renderer = FrameGraphRenderer.from_yaml_file(args.input)
        if not args.no_validate:
            for w in renderer.validate():
                print(f"warning: {w}", file=sys.stderr)
        svg = renderer.render_svg()
        if output:
            output.write_text(svg, encoding="utf-8")
            if not args.quiet:
                print(f"wrote {output}  ({output.stat().st_size / 1024:.1f} KB)", file=sys.stderr)
        else:
            print(svg, end="")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
