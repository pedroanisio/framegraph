"""FrameGraph YAML -> SVG renderer.

Hosts the `FrameGraphRenderer` class — the concrete `RendererContext`
implementation that drives the per-type renderer modules in
`framegraph.renderers.*`. The package's user-facing CLI lives in
`framegraph.cli`; per-type rendering helpers live in `framegraph._helpers`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from framegraph._types import RenderFn

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc

from framegraph._helpers import (
    Box,
    Point,
    attrs,
    box,
    deep_get,
    esc,
    fmt,
    fnum,
    pt,
    pts_attr,
    sid,
)

# ---------------------------------------------------------------------------
# Marker shape table — UML 2.5 §11 arrowhead variants
# ---------------------------------------------------------------------------
#
# Each entry maps a `kind` name to (svg_path_d, viewbox_metadata). The
# viewbox tuple is (viewBox_attr, markerWidth, markerHeight, refX, refY).
# Default `filled_triangle` lives in `defs_svg` directly to preserve
# v1.x byte-identity; entries here are only emitted when the kind is
# explicitly registered via `register_marker_kind`.
#
# All shapes orient along the marker's x-axis with the tip at refX,
# matching SVG's `orient="auto-start-reverse"` convention.

_MARKER_SHAPES: dict[str, tuple[str, tuple[str, int, int, int, float]]] = {
    # Hollow triangle (UML generalization, realization)
    "hollow_triangle": (
        "M0,0 L10,5 L0,10 Z",
        ("0 0 10 10", 10, 10, 10, 5),
    ),
    # Hollow diamond (UML aggregation)
    "hollow_diamond": (
        "M0,5 L6,0 L12,5 L6,10 Z",
        ("0 0 12 10", 12, 10, 12, 5),
    ),
    # Filled diamond (UML composition)
    "filled_diamond": (
        "M0,5 L6,0 L12,5 L6,10 Z",
        ("0 0 12 10", 12, 10, 12, 5),
    ),
    # Open arrow ─ V-shape, no fill (UML association navigability,
    # dependency). Distinct from filled_triangle which is solid.
    "open_arrow": (
        "M0,0 L10,5 L0,10",
        ("0 0 10 10", 10, 10, 10, 5),
    ),
}


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

        Raises:
            pydantic.ValidationError: When `doc` declares
                `dsl: FrameGraph` but its structure does not satisfy
                the Pydantic schema in `framegraph._schema`. Documents
                without the `dsl: FrameGraph` marker (empty dicts,
                partial test fixtures, deck-composed slide docs that
                omit the marker) skip validation — see the schema
                module's `validate_document` for the gate logic.

        """
        # Validation gate: real FrameGraph documents always carry the
        # `dsl: FrameGraph` marker. Internal/partial dicts without it
        # are passed through unvalidated so the renderer remains
        # usable for unit tests and the deck composer's intermediate
        # slide builds. See framegraph._schema for the rationale.
        if isinstance(doc, Mapping) and doc.get("dsl") == "FrameGraph":
            from framegraph._schema import validate_document

            validate_document(dict(doc))

        self.doc = doc
        self.scene: dict[str, Any] = dict(doc.get("scene", {}) or {})
        self.semantic: dict[str, Any] = dict(doc.get("semantic", {}) or {})
        self.visual: dict[str, Any] = dict(doc.get("visual", {}) or {})
        self.tokens: dict[str, Any] = dict(self.visual.get("tokens", {}) or {})

        self.colors: Mapping[str, Any] = self.tokens.get("colors", {}) or {}
        self.fonts: Mapping[str, Any] = self.tokens.get("fonts", {}) or {}
        self.text_styles: Mapping[str, Mapping[str, Any]] = self.tokens.get("text_styles", {}) or {}
        self.stroke_styles: Mapping[str, Mapping[str, Any]] = (
            self.tokens.get("stroke_styles", {}) or {}
        )
        self.component_defs: dict[str, dict[str, Any]] = dict(
            self.visual.get("component_defs", {}) or {}
        )
        self.layers: list[Mapping[str, Any]] = [
            lyr for lyr in (self.visual.get("layers", []) or []) if isinstance(lyr, Mapping)
        ]

        # ── v3 additions ──────────────────────────────────────────────
        # Annotated to match the `RendererContext` Protocol exactly —
        # mypy treats Protocol attributes invariantly, so the class
        # annotation must equal the Protocol's annotation.
        # Annotated as concrete `dict` (not `Mapping`) to satisfy the
        # invariant Protocol attribute match in `RendererContext`.
        self.glyph_map: dict[str, str] = dict(self.tokens.get("glyph_map", {}) or {})
        self.fill_styles: dict[str, Any] = dict(self.tokens.get("fill_styles", {}) or {})
        self.symbols: dict[str, Any] = dict(self.visual.get("symbols", {}) or {})
        self.gradient_defs: list[str] = []
        self._uses_icon_font: bool = False
        # `yaml_source_dir` is set by the CLI / deck renderer after
        # construction so that `<image>` objects can resolve relative
        # `href` values. Empty string when no source path is known.
        self.yaml_source_dir: str = ""
        # ──────────────────────────────────────────────────────────────

        self.object_index: dict[str, dict[str, Any]] = {}
        self.semantic_ids = self._collect_semantic_ids()
        self.marker_colors: list[str] = []
        # `marker_kinds` is the (color, kind) set used by `defs_svg` to
        # emit additional marker shapes (hollow triangle, diamonds, etc.)
        # beyond the default filled triangle. Populated lazily by
        # `register_marker_kind`. Empty by default → defs output is
        # byte-identical with v1.x.
        self.marker_kinds: set[tuple[str, str]] = set()
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
        # Auto-distribute connector endpoints that pile up on a single
        # side. Populated lazily; populated entries take precedence
        # over the per-endpoint default that resolves to the side
        # midpoint. See `_assign_side_ports` for the policy.
        self._side_port_assignments: dict[str, tuple[int, int]] = {}
        self._assign_side_ports()

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
        """Convert fill_styles entries into SVG gradient `<defs>` strings.

        Default coordinate space is `objectBoundingBox` so gradients scale
        with each shape; override with `gradient_units: userSpaceOnUse`
        when canvas-space gradients are required.

        Per-stop transparency is emitted via SVG `stop-opacity`; gradient
        roots may declare `opacity` (applied to every stop that does not
        override it), `spread_method` (`pad`|`reflect`|`repeat`), and
        `gradient_transform` (raw SVG transform string).
        """
        for name, fs in self.fill_styles.items():
            self._register_gradient(name, fs)

    def _register_gradient(self, name: str, fs: Mapping[str, Any]) -> str:
        """Build a single gradient `<defs>` entry and return its SVG id.

        Idempotent: re-registering the same `name` returns the existing id
        without re-appending. Inline gradients call this with a synthetic
        name to register on first use from `fill_value()`.
        """
        gid = sid("grad_" + name)
        # Idempotency: skip if a def for this id already exists.
        if any(f'id="{gid}"' in g for g in self.gradient_defs):
            return gid

        gtype = str(fs.get("type", ""))
        # Per-gradient default opacity (applies to stops that don't set their own).
        root_opacity = fs.get("opacity")
        stops_svg_parts: list[str] = []
        for s in fs.get("stops") or []:
            offset = fmt(s.get("offset", 0))
            stop_color = self.color(s.get("color"), "#000000")
            # Per-stop opacity wins; falls back to gradient root opacity; else opaque.
            stop_op = s.get("opacity")
            if stop_op is None:
                stop_op = root_opacity
            op_attr = f' stop-opacity="{fmt(stop_op)}"' if stop_op is not None else ""
            stops_svg_parts.append(f'<stop offset="{offset}" stop-color="{stop_color}"{op_attr}/>')
        stops_svg = "".join(stops_svg_parts)

        # Optional shared attributes: spread method, coordinate space, transform.
        units = str(fs.get("gradient_units", "objectBoundingBox"))
        spread = fs.get("spread_method")
        spread_attr = f' spreadMethod="{esc(spread)}"' if spread else ""
        gtrans = fs.get("gradient_transform")
        gtrans_attr = f' gradientTransform="{esc(gtrans)}"' if gtrans else ""

        if gtype == "linear_gradient":
            p1 = fs.get("from", [0, 0])
            p2 = fs.get("to", [0, 1])
            self.gradient_defs.append(
                f'<linearGradient id="{gid}"'
                f' x1="{fmt(fnum(p1[0]))}" y1="{fmt(fnum(p1[1]))}"'
                f' x2="{fmt(fnum(p2[0]))}" y2="{fmt(fnum(p2[1]))}"'
                f' gradientUnits="{esc(units)}"{spread_attr}{gtrans_attr}>{stops_svg}</linearGradient>'
            )
        elif gtype == "radial_gradient":
            c = fs.get("center", [0.5, 0.5])
            r = fnum(fs.get("radius"), 0.5)
            # Optional focal point for off-centre highlight: defaults to centre.
            focal = fs.get("focal")
            focal_attr = ""
            if (
                isinstance(focal, Sequence)
                and not isinstance(focal, (str, bytes))
                and len(focal) >= 2
            ):
                focal_attr = f' fx="{fmt(fnum(focal[0]))}" fy="{fmt(fnum(focal[1]))}"'
            self.gradient_defs.append(
                f'<radialGradient id="{gid}"'
                f' cx="{fmt(fnum(c[0]))}" cy="{fmt(fnum(c[1]))}" r="{fmt(r)}"'
                f"{focal_attr}"
                f' gradientUnits="{esc(units)}"{spread_attr}{gtrans_attr}>{stops_svg}</radialGradient>'
            )
        return gid

    # ── v3: fill resolution (color token OR gradient IdRef) ────────────
    def fill_value(self, v: Any, default: str = "none") -> str:
        """Resolve a fill value to an SVG paint string.

        - None / "none"  → default
        - fill_styles key → url(#grad_name)
        - inline gradient mapping (`{type: linear_gradient|radial_gradient, ...}`)
          → registered on demand and returned as `url(#grad_inline_N)`
        - color token / literal → hex string
        """
        if v is None:
            return default
        # Inline gradient: register a synthetic fill_style on first sight.
        if isinstance(v, Mapping):
            gtype = v.get("type")
            if gtype in ("linear_gradient", "radial_gradient"):
                inline_name = "inline_" + str(len(self.fill_styles))
                # Persist so deterministic reuse + defs_svg picks it up.
                self.fill_styles[inline_name] = dict(v)
                gid = self._register_gradient(inline_name, v)
                return f"url(#{gid})"
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
        "small": {"dx": 0, "dy": 1, "blur": 1.5, "color": "#000000", "opacity": 0.10},
        "medium": {"dx": 0, "dy": 2, "blur": 4.0, "color": "#000000", "opacity": 0.14},
        "large": {"dx": 0, "dy": 4, "blur": 8.0, "color": "#000000", "opacity": 0.18},
    }
    _GLOW_PRESETS: dict[str, dict[str, Any]] = {
        "small": {"blur": 2.0, "color": "#FFD700", "opacity": 0.45},
        "medium": {"blur": 4.0, "color": "#FFD700", "opacity": 0.55},
        "large": {"blur": 8.0, "color": "#FFD700", "opacity": 0.65},
    }

    def _resolve_effect_spec(self, kind: str, spec: Any) -> dict[str, Any] | None:
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
        """Resolve an effect spec to a stable filter id.

        Registers the `<filter>` element on first use.

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
                f"<feMerge>"
                f'<feMergeNode in="shadow"/>'
                f'<feMergeNode in="SourceGraphic"/>'
                f"</feMerge>"
                f"</filter>"
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
                f"<feMerge>"
                f'<feMergeNode in="glow"/>'
                f'<feMergeNode in="SourceGraphic"/>'
                f"</feMerge>"
                f"</filter>"
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

    def _str_width(
        self,
        text: str,
        fs: float,
        bold: bool,
        font: str | None = None,
    ) -> float:
        """Estimate rendered width of text in pixels.

        When ``font`` is a resolved CSS font-family chain and both
        ``fontTools`` and ``fc-match`` are available on the system, the
        width is computed from the actual per-glyph advances of the file
        fontconfig resolves for that chain — the same file the rasterizer
        (cairosvg via Pango) will draw with. This eliminates the wrap-vs-
        render mismatch that the per-class fallback table introduces when
        the installed font is wider than Helvetica.

        When ``font`` is ``None`` or real metrics are unavailable, falls
        back to the per-character-class estimator (legacy behavior).
        """
        if font:
            from framegraph._font_metrics import measure_text

            real = measure_text(text, font, fs, bold)
            if real is not None:
                return real
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

    def _assign_side_ports(self) -> None:
        """Assign distributed side-ports to piled-up connector endpoints.

        Pre-pass. Walks every connector in z-order. For each `from`/`to` endpoint
        of the form ``{object: X, side: Y}`` *without* an explicit
        ``offset`` or ``port_index``, the connector is registered as a
        candidate for the ``(X, Y)`` collision bucket. After the walk,
        any bucket with two or more candidates gets each endpoint
        assigned ``(port_index, port_total)`` evenly along that side.

        The assignments are keyed on the connector's ``id`` plus the
        side label (``"from"`` / ``"to"``) and consumed by
        :meth:`endpoint` when the endpoint resolves.

        This makes "many edges to one hub" produce a clean fan-out of
        attachment points instead of a marker pile-up at the side
        midpoint — without requiring the deck author to compute and
        write per-edge port indices by hand.
        """
        # bucket: (oid, side) → list of (assignment_key, sort_key)
        buckets: dict[tuple[str, str], list[tuple[str, float]]] = {}
        # When a connector explicitly specifies a port_index/port_total
        # we record the *total* the author committed to so the
        # auto-assigner respects it (no surprise reflows of decks
        # that already use the explicit form).
        committed_totals: dict[tuple[str, str], int] = {}
        for layer in self.sorted_layers():
            for obj in layer.get("objects", []) or []:
                if not isinstance(obj, Mapping) or obj.get("type") != "connector":
                    continue
                conn_id = obj.get("id")
                if conn_id is None:
                    continue
                for end_label in ("from", "to"):
                    ep = obj.get(end_label)
                    if not isinstance(ep, Mapping):
                        continue
                    oid = ep.get("object")
                    side = ep.get("side")
                    if oid is None or side is None:
                        continue
                    if "offset" in ep:
                        continue  # author chose a literal anchor → respect it
                    if "port_total" in ep:
                        committed_totals[(str(oid), str(side))] = int(ep["port_total"])
                        continue
                    bucket_key = (str(oid), str(side))
                    sort_key = self._port_sort_key(obj, end_label)
                    buckets.setdefault(bucket_key, []).append((f"{conn_id}::{end_label}", sort_key))

        for bucket_key, members in buckets.items():
            if len(members) < 2:
                continue  # single edge — midpoint anchor is fine
            committed = committed_totals.get(bucket_key)
            total = committed if committed and committed >= len(members) else len(members)
            members.sort(key=lambda m: m[1])
            for i, (assign_key, _) in enumerate(members, start=1):
                self._side_port_assignments[assign_key] = (i, total)

    def _port_sort_key(self, conn: Mapping[str, Any], end_label: str) -> float:
        """Tangent-direction coordinate of the *other* endpoint.

        Sorting auto-distributed ports by the source's projection along
        the target side keeps semantically related edges visually
        adjacent (e.g. a left-row source ends up on the left port).
        Falls back to ``0.0`` when the other endpoint can't be
        resolved (e.g. literal coordinate or unknown reference).
        """
        other_label = "from" if end_label == "to" else "to"
        other = conn.get(other_label)
        if not isinstance(other, Mapping):
            return 0.0
        oid = other.get("object")
        if oid is None or str(oid) not in self.object_index:
            return 0.0
        rec = self.object_index[str(oid)]
        b = rec.get("box")
        if not b:
            return 0.0
        x, y, w, h = b
        # The endpoint we're placing is on its own object's `side`;
        # we use the x-centre of the *other* endpoint when distributing
        # along a horizontal (north/south) side, and the y-centre for
        # vertical (east/west) sides.
        ep = conn.get(end_label)
        side = ep.get("side") if isinstance(ep, Mapping) else None
        if str(side).lower() in ("east", "right", "west", "left"):
            return float(y + h / 2)
        return float(x + w / 2)

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
        # `opacity` (alias `stroke_opacity`) lets stroke styles declare
        # transparency without forcing rgba colour literals; it is left
        # absent (rather than defaulted to 1.0) so stroke_attrs can omit
        # the SVG attribute entirely when no opacity was requested.
        if "stroke_opacity" in st and "opacity" not in st:
            st["opacity"] = st["stroke_opacity"]
        return st

    def opacity_attrs(
        self,
        obj: Mapping[str, Any],
        *,
        has_fill: bool = True,
        has_stroke: bool = True,
    ) -> dict[str, Any]:
        """Build per-shape `fill-opacity` / `stroke-opacity` SVG attrs.

        Object-level `opacity` is emitted by `group_attrs()` on the
        wrapping `<g>`. This helper handles the channel-specific values
        that compose with it: callers merge the result into the geometry
        attribute dict (rect, ellipse, path, line, polyline).

        Channels are dropped when the geometry has no paint in that
        channel (e.g., `<line>` has no fill, so `has_fill=False` skips
        any `fill-opacity` even when the object declared one).
        """
        out: dict[str, Any] = {}
        if has_fill:
            fop = obj.get("fill_opacity")
            if fop is not None:
                out["fill-opacity"] = fmt(fop)
        if has_stroke:
            sop = obj.get("stroke_opacity")
            if sop is not None:
                out["stroke-opacity"] = fmt(sop)
        return out

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

    def marker_id(self, color: str, kind: str = "filled_triangle") -> str:
        """Return the SVG `<marker>` id used by arrowheads of the given color and kind.

        The `kind` parameter selects the arrowhead shape; default
        `"filled_triangle"` matches the v1.x arrowhead and keeps
        existing fixtures byte-identical. UML 2.5 introduces
        additional shapes for inheritance/realization (hollow
        triangle), aggregation (hollow diamond), and composition
        (filled diamond).
        """
        suffix = "" if kind == "filled_triangle" else "-" + kind
        return "ah-" + color.lstrip("#").upper() + suffix

    def defs_svg(self) -> str:
        """Emit: optional Tabler Icons @import, gradient defs, per-color arrow markers, effect filters."""
        has_content = (
            self.marker_colors or self.gradient_defs or self._uses_icon_font or self.effect_filters
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
        # Extra marker shapes registered via `register_marker_kind`
        # (UML inheritance/realization/aggregation/composition arrowheads).
        # Sorted for deterministic <defs> output across runs.
        for color, kind in sorted(self.marker_kinds):
            mid = self.marker_id(color, kind)
            shape_entry = _MARKER_SHAPES.get(kind)
            if shape_entry is None:
                continue
            shape_path, vbox = shape_entry
            vb, mw, mh, refx, refy = vbox
            # Hollow shapes render with white fill + colored stroke
            # (UML hollow triangle / diamond convention).
            # Open arrow renders as a stroked V (no fill).
            # Filled shapes render with the color as fill.
            if kind in ("hollow_triangle", "hollow_diamond"):
                fill = "#FFFFFF"
                extra = f' stroke="{esc(color)}" stroke-width="1"'
            elif kind == "open_arrow":
                fill = "none"
                extra = f' stroke="{esc(color)}" stroke-width="1.5" fill="none"'
            else:
                fill = color
                extra = ""
            if kind == "open_arrow":
                # `fill="none"` already in extra; don't duplicate
                out.append(
                    f'<marker id="{esc(mid)}" viewBox="{vb}"'
                    f' markerWidth="{mw}" markerHeight="{mh}"'
                    f' refX="{refx}" refY="{refy}"'
                    f' orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                    f'<path d="{shape_path}"{extra}/></marker>'
                )
            else:
                out.append(
                    f'<marker id="{esc(mid)}" viewBox="{vb}"'
                    f' markerWidth="{mw}" markerHeight="{mh}"'
                    f' refX="{refx}" refY="{refy}"'
                    f' orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                    f'<path d="{shape_path}" fill="{esc(fill)}"{extra}/></marker>'
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
        if width > 0 and deep_get(self.scene, ["rendering_contract", "hairline_guard"], False):
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
        # Stroke opacity: emit only when explicitly requested (no implicit 1.0).
        st_op = st.get("opacity")
        if st_op is not None:
            a["stroke-opacity"] = fmt(st_op)
        dash = st.get("dash")
        if dash:
            if isinstance(dash, Sequence) and not isinstance(dash, str):
                a["stroke-dasharray"] = " ".join(fmt(x) for x in dash)
            else:
                a["stroke-dasharray"] = dash
        if arrows:
            # `arrow_kind` selects the marker shape; defaults to the
            # filled-triangle shape that v1.x emitted unconditionally.
            kind_start = str(
                st.get("arrow_start_kind") or st.get("arrow_kind") or "filled_triangle"
            )
            kind_end = str(st.get("arrow_end_kind") or st.get("arrow_kind") or "filled_triangle")
            if st.get("arrow_start"):
                if kind_start != "filled_triangle":
                    self.register_marker_kind(color, kind_start)
                elif color not in self.marker_colors:
                    # Inline-color strokes never reach `_build_markers`;
                    # ensure the filled-triangle marker for this color is
                    # emitted so `marker-start` URL resolves.
                    self.marker_colors.append(color)
                a["marker-start"] = "url(#" + self.marker_id(color, kind_start) + ")"
            if st.get("arrow_end"):
                if kind_end != "filled_triangle":
                    self.register_marker_kind(color, kind_end)
                elif color not in self.marker_colors:
                    self.marker_colors.append(color)
                a["marker-end"] = "url(#" + self.marker_id(color, kind_end) + ")"
        return a

    def register_marker_kind(self, color: str, kind: str) -> None:
        """Register an additional arrowhead shape for the given color.

        The default `filled_triangle` is auto-emitted via
        `marker_colors`; other kinds (per `_MARKER_SHAPES`) must be
        registered before `defs_svg()` runs. Callers passing
        `arrow_kind` through `stroke_attrs` register implicitly.
        """
        if kind == "filled_triangle":
            return
        if kind not in _MARKER_SHAPES:
            return
        # Make sure the base color is in marker_colors so defs_svg
        # treats this color as "used."
        if color not in self.marker_colors:
            self.marker_colors.append(color)
        self.marker_kinds.add((color, kind))

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
        quality = str(deep_get(self.scene, ["rendering_contract", "render_quality"], "hd")).lower()
        hd_attrs = (
            ' shape-rendering="geometricPrecision" text-rendering="optimizeLegibility"'
            if quality != "legacy"
            else ""
        )
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' width="{fmt(width)}" height="{fmt(height)}"'
            f' viewBox="0 0 {fmt(width)} {fmt(height)}"'
            f"{hd_attrs}"
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

    def register(self, type_name: str, fn: RenderFn) -> None:
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
        fn = self._dispatch.get(str(t)) if t is not None else None
        if fn:
            return cast(str, fn(self, obj))
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

    def endpoint(
        self, ep: Any, *, _connector_id: str | None = None, _end_label: str | None = None
    ) -> Point:
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
                return cast(Point, rec["ports"][port])
            return cast(Point, rec["ports"].get("center", (0.0, 0.0)))
        # ── map form ──────────────────────────────────────────────────────
        if isinstance(ep, Mapping):
            if "point" in ep:
                return pt(ep["point"])
            oid_raw: Any = ep.get("object")
            if oid_raw is None or str(oid_raw) not in self.object_index:
                raise ValueError(f"unknown endpoint object {oid_raw!r}")
            oid = str(oid_raw)
            rec = self.object_index[oid]
            if ep.get("port") is not None:
                port = str(ep["port"])
                if port not in rec["ports"]:
                    raise ValueError(f"object {oid!r} has no port {port!r}")
                return cast(Point, rec["ports"][port])
            if ep.get("side") is not None:
                # Distributed-port form: {side, port_index, port_total}
                # spaces port `i` evenly along the chosen side. Lets a
                # single-target hub (e.g. a UML aggregate-root receiving
                # five aggregation arrows) declare attachment points
                # that don't cluster at the centre. `port_inset`
                # controls the margin from each box corner; defaults
                # to 24 px so glyphs don't touch the corner.
                if ep.get("port_total") is not None:
                    return self.side_anchor(
                        rec,
                        str(ep["side"]),
                        port_index=int(ep.get("port_index", 1)),
                        port_total=int(ep["port_total"]),
                        port_inset=fnum(ep.get("port_inset"), 24.0),
                    )
                # Auto-distribution: the pre-pass found ≥2 connectors
                # converging on this side without explicit offsets,
                # so each gets a port assignment that fans out the
                # attachment points. An explicit offset on the
                # endpoint short-circuits this — the author wins.
                if "offset" not in ep and _connector_id is not None and _end_label is not None:
                    auto_key = f"{_connector_id}::{_end_label}"
                    auto = self._side_port_assignments.get(auto_key)
                    if auto is not None:
                        idx, total = auto
                        return self.side_anchor(
                            rec,
                            str(ep["side"]),
                            port_index=idx,
                            port_total=total,
                        )
                return self.side_anchor(rec, str(ep["side"]), fnum(ep.get("offset"), 0))
            return cast(Point, rec["ports"].get("center", (0.0, 0.0)))
        # ── coordinate pair ───────────────────────────────────────────────
        return pt(ep)

    def side_anchor(
        self,
        rec: Mapping[str, Any],
        side: str,
        offset: float = 0.0,
        *,
        port_index: int | None = None,
        port_total: int | None = None,
        port_inset: float = 24.0,
    ) -> Point:
        """Return a point on a named side of an indexed object.

        Two anchoring modes:

          - **Offset** (default) — anchor at the side's midpoint shifted
            by `offset` along the side's tangent. Backwards-compatible
            with all existing decks.
          - **Distributed port** — when `port_total` is set, the anchor
            is the `port_index`-th evenly spaced port along the side
            (1-indexed). The first and last ports sit `port_inset` px
            from the box corners. Resolves the "many edges to one
            hub" cluster that produces overlapping arrowhead markers
            on aggregate-root nodes (UML class diagrams), routing
            sources (sequence diagrams), and bus-style adapters.

        Args:
            rec: An entry from `self.object_index` (must have a
                non-empty `box`).
            side: One of `north`/`top`, `south`/`bottom`,
                `east`/`right`, `west`/`left`. Anything else returns
                the box center.
            offset: Tangential offset along the chosen side (positive
                in the canvas-x direction for top/bottom, in the
                canvas-y direction for left/right). Ignored when
                `port_total` is set.
            port_index: 1-indexed position of this port among
                `port_total`. Out-of-range values clamp to the
                nearest endpoint port.
            port_total: Number of evenly spaced ports the side hosts.
            port_inset: Margin from each box corner reserved before
                the first / after the last port.

        Raises:
            ValueError: If `rec["box"]` is missing or falsy.

        """
        b = rec.get("box")
        if not b:
            raise ValueError("side_anchor requires object box")
        x, y, w, h = b

        if port_total is not None and port_total > 0:
            idx = max(1, min(int(port_index or 1), port_total))
            # Available span along the side's tangent direction.
            tangent_len = w if side in ("north", "top", "south", "bottom") else h
            inset = min(port_inset, max(0.0, (tangent_len - 1) / 2))
            usable = max(0.0, tangent_len - 2 * inset)
            if port_total == 1:
                # Single port → centred on the side.
                tangent_offset = tangent_len / 2.0
            else:
                tangent_offset = inset + usable * (idx - 1) / (port_total - 1)
            if side in ("north", "top"):
                return x + tangent_offset, y
            if side in ("south", "bottom"):
                return x + tangent_offset, y + h
            if side in ("east", "right"):
                return x + w, y + tangent_offset
            if side in ("west", "left"):
                return x, y + tangent_offset
            return x + w / 2, y + h / 2

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
        # Lines/polylines carry stroke only (`fill="none"`), so fill_opacity
        # is intentionally suppressed here even when present on the object.
        op_extra = self.opacity_attrs(obj, has_fill=False)
        # Shadow / glow available on lines for "highlighted edge" effects.
        fx_extra = self.effect_filter_attrs(obj)
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
            geom.update(op_extra)
            geom.update(fx_extra)
            svg = f"<line {attrs(geom)}/>"
        else:
            geom = {"points": pts_attr(points), "fill": "none"}
            geom.update(self.stroke_attrs(st, arrows=True))
            geom.update(op_extra)
            geom.update(fx_extra)
            svg = f"<polyline {attrs(geom)}/>"
        return f"<g {attrs(self.group_attrs(obj))}>{svg}</g>"
