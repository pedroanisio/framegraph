"""FrameSet — unifying abstraction over single documents and decks.

This module is the home of ADR 0001 ("Collapse `Document` and `Deck`
into a `FrameSet` graph"). It declares four Pydantic models —
`FrameTarget`, `FrameLink`, `Frame`, `FrameSetDocument` — and the
total coercion `coerce_to_frameset(doc)` that lifts the older
`hybrid-semantic-visual-diagram` and `presentation-deck` shapes
into a `FrameSetDocument` without changing rendered output.

The renderer dispatcher consumes only `FrameSetDocument` after Phase
1 lands; older entry points coerce on the way in.

Design notes
------------

- Every model is `extra="forbid"` so that authoring errors on the
  new surface fail loudly. The lift from older shapes is explicit
  about which keys it copies and which it discards.
- `FrameSetDocument` has its own validation gate
  (`validate_frameset`) registered alongside `validate_document` and
  `validate_deck` in `framegraph/_schema.py`.
- `coerce_to_frameset` is **total**: every old-shape document, every
  new-shape document, and every empty/partial-test fixture in the
  corpus survives the round-trip. The `tests/` corpus pins
  byte-identical render parity for old shapes (see
  `tests/integration/test_frameset_render_parity.py`).
- Backwards compatibility is the load contract: any YAML that
  used to load with `validate_document` / `validate_deck` still
  loads. The reverse — old code reading new-shape YAML — is not a
  goal; new YAML requires the renderer's FrameSet path.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────
# Common type aliases — match `_schema.py` so the surfaces are
# trivially compatible.
# ─────────────────────────────────────────────────────────────────


CanvasDims = Annotated[list[float], Field(min_length=2, max_length=2)]
"""Canvas dimensions `[width, height]` — exactly two numbers."""


# ─────────────────────────────────────────────────────────────────
# FrameTarget — one render target (canvas + adjustments) per Frame
# ─────────────────────────────────────────────────────────────────


class FrameTargetAdjustments(BaseModel):
    """Per-target tuning applied at projection time.

    Phase 5 of ADR 0001 ships three orthogonal knobs that adapt the
    same Frame to different viewport contexts (landscape, portrait,
    mobile, print) without duplicating the source. They run in a
    fixed, documented order inside `apply_target_adjustments`:

    1. ``font_scale`` — multiply every ``visual.tokens.text_styles[*].size``
       by the factor. Strictly positive. ``1.0`` is a no-op.
    2. ``hide`` — drop matching layer ids from
       ``visual.layers``; within remaining layers, drop matching
       top-level object ids from ``layer.objects``. Ids that match
       neither are silently ignored (forward-compatible with future
       targets that hide things only present on other Frames).
    3. ``padding_delta`` — signed pixel value added as an inset on
       each axis of ``scene.canvas.size`` (i.e. each axis shrinks by
       ``2 * padding_delta``). Pattern-system margins, which derive
       from canvas size, scale proportionally. A negative value
       expands the renderable canvas.

    Attributes:
        font_scale: Strictly positive multiplier. ``None`` is a no-op.
        hide: Layer / top-level-object ids to drop from the projected
            doc. Defaults to the empty list (no-op).
        padding_delta: Signed integer pixels per axis. ``None`` and
            ``0`` are no-ops. Negative values expand the canvas.
    """

    model_config = ConfigDict(extra="forbid")
    font_scale: float | None = Field(default=None, gt=0)
    hide: list[str] = Field(default_factory=list)
    padding_delta: float | None = None


class FrameTarget(BaseModel):
    """One render target for a `Frame`.

    A target is a named (canvas, adjustments) pair. The same Frame
    may declare multiple targets (e.g. landscape + portrait + mobile);
    the renderer picks one per render call, defaulting to the first.

    Attributes:
        name: Target identifier. Free-form; convention is one of
            ``landscape``, ``portrait``, ``mobile``, or a project-
            specific tag like ``a4-print``.
        canvas: ``[width, height]`` in pixels. Phase 1 keeps `units`
            implicit at "px" to match `Scene.canvas`.
        adjustments: Per-target tuning. ``None`` is a no-op (Phases
            1-4 behavior preserved). Phase 5 wires font-scale, hide,
            and padding-delta overrides via
            `apply_target_adjustments`.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    canvas: CanvasDims
    adjustments: FrameTargetAdjustments | None = None


# ─────────────────────────────────────────────────────────────────
# FrameLink — typed navigation edge between Frames or to URLs
# ─────────────────────────────────────────────────────────────────


_LinkRelation = Literal[
    "next",
    "prev",
    "see_also",
    "appendix",
    "source",
    "child",
    "parent",
    "external",
]
"""Controlled vocabulary for link relations.

`next`/`prev` model linear deck navigation; `see_also` /
`appendix` / `source` model cross-references inside a FrameSet;
`child` / `parent` model hierarchical sitemaps; `external` is
reserved for outbound URLs.
"""


class FrameLink(BaseModel):
    """A typed navigation edge from a Frame to another Frame or URL.

    Attributes:
        to: The link target. Either a Frame `id` (resolved against
            the same FrameSet) or a fully-qualified URL when
            `external=True`.
        relation: The link kind. Defaults to ``see_also``.
        label: Optional display text. Renderers that emit clickable
            output (HTML, PDF) use this as the anchor text; renderers
            that don't (SVG today) ignore it.
        external: When True, `to` is treated as an absolute URL.
            When False (default), `to` is resolved against the
            FrameSet's frame id table.
    """

    model_config = ConfigDict(extra="forbid")
    to: str = Field(..., min_length=1)
    relation: _LinkRelation = "see_also"
    label: str | None = None
    external: bool = False


# ─────────────────────────────────────────────────────────────────
# Frame — the renderable atom
# ─────────────────────────────────────────────────────────────────


class Frame(BaseModel):
    """A renderable frame inside a `FrameSetDocument`.

    A Frame carries one renderable scene (the existing visual
    layers / semantic graph), plus first-class navigation metadata:
    one or more render targets (canvas dimensions), zero or more
    typed links to other Frames or URLs, and `next` / `prev` shortcuts
    for the common deck-chain shape.

    `extra="allow"` is intentional. The historical `Document` shape
    carries `dsl`, `version`, `kind`, `scene`, `semantic`, `visual`
    keys; the deck slide entry shape carries `slide`, `id`, `title`,
    `notes`, `use`, `fill`, etc. Both shapes participate in the
    coercion shim, and authors of the new shape may want to attach
    arbitrary metadata that downstream consumers (a sitemap
    generator, a deck navigator, an HTML emitter) will read. The
    structural keys below are the validated minimum; everything else
    passes through.

    Attributes:
        id: Frame identifier; unique within its FrameSet.
        title: Optional human-readable title (used by deck chrome
            and sitemaps).
        targets: Render targets. When empty, falls back to the
            `FrameSetDocument.frameset.defaults.targets`. When that
            is also empty, a `[1280, 720]` default applies.
        next: Optional Frame id; sugar for the chain link
            ``{to: <id>, relation: next}``.
        prev: Optional Frame id; sugar for ``{to: <id>, relation: prev}``.
        links: Additional typed edges to other Frames or URLs.
        extends: Optional Frame id this Frame inherits from. Same
            semantics as the legacy slide-level `$extends`: tokens,
            symbols, component_defs, and layers merge with the base
            in order base-then-this; same-id layers replace.
        visual: The visual block — same structure as legacy `Document.visual`.
        semantic: Optional semantic block — same structure as legacy.
        scene: Optional scene block — for compatibility with
            single-document content that embeds rendering_contract
            and the legacy `canvas`. When `targets` is non-empty,
            `scene.canvas` is informational only.
        use: Optional pattern reference (id or slug); coerced from
            the deck slide shape.
        fill: Optional pattern fill payload; coerced from the deck
            slide shape.
    """

    model_config = ConfigDict(extra="allow")
    id: str = Field(..., min_length=1)
    title: str | None = None
    targets: list[FrameTarget] = Field(default_factory=list)
    next: str | None = None
    prev: str | None = None
    links: list[FrameLink] = Field(default_factory=list)
    extends: str | None = None
    visual: dict[str, Any] | None = None
    semantic: dict[str, Any] | None = None
    scene: dict[str, Any] | None = None
    use: int | str | None = None
    fill: dict[str, Any] | None = None
    notes: str | None = None


# ─────────────────────────────────────────────────────────────────
# FrameSetDefaults — defaults shared across every Frame
# ─────────────────────────────────────────────────────────────────


class FrameSetDefaults(BaseModel):
    """Defaults applied to every Frame that doesn't override them.

    Attributes:
        targets: Default render targets. A Frame inherits these when
            its own `targets` list is empty.
    """

    model_config = ConfigDict(extra="forbid")
    targets: list[FrameTarget] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# FrameSetMeta — top-level FrameSet configuration
# ─────────────────────────────────────────────────────────────────


class FrameSetMeta(BaseModel):
    """The `frameset:` block — defaults + theme + deck-equivalent globals.

    This is the bag of "applies to every Frame" configuration that
    used to live half in `Document`'s top level (`$theme`,
    `stylesheet`) and half in `DeckDocument.deck` (`canvas`, `tokens`,
    `symbols`, `component_defs`, `chrome`).

    `extra="allow"` mirrors `_schema.DeckConfig` so the same global-
    token / symbol / component-def shape passes through unchanged.
    """

    model_config = ConfigDict(extra="allow")
    defaults: FrameSetDefaults = Field(default_factory=FrameSetDefaults)
    canvas: CanvasDims | None = None
    tokens: dict[str, Any] | None = None
    symbols: dict[str, Any] | None = None
    component_defs: dict[str, Any] | None = None
    chrome: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────
# FrameSetDocument — the new top-level shape
# ─────────────────────────────────────────────────────────────────


class FrameSetDocument(BaseModel):
    """Root document for `kind: frameset`.

    Validates `dsl: FrameGraph`, a numeric `version`,
    `kind: frameset`, an optional `frameset:` block (theme, defaults,
    deck-equivalent globals), and a non-empty list of `frames`.

    Phase 1 contract: every Frame must have a unique `id`; every
    `next` / `prev` / link `to` reference must resolve to a Frame
    id in the same FrameSetDocument or be marked `external=True`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    dsl: Literal["FrameGraph"]
    version: float
    kind: Literal["frameset"]
    frameset: FrameSetMeta = Field(default_factory=FrameSetMeta)
    theme: str | None = Field(default=None, alias="$theme")
    stylesheet: str | None = None
    frames: list[Frame] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_id_uniqueness_and_link_targets(self) -> FrameSetDocument:
        """Enforce two structural invariants on the frame graph.

        1. Every `Frame.id` is unique within the FrameSet — link
           resolution (`next`/`prev`/`links[*].to`) requires it.
        2. Every internal `to` reference (i.e. not `external=True`)
           resolves to a known Frame id.
        """
        ids: list[str] = [f.id for f in self.frames]
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        for fid in ids:
            seen[fid] = seen.get(fid, 0) + 1
            if seen[fid] == 2:
                duplicates.append(fid)
        if duplicates:
            raise ValueError(
                f"FrameSet has duplicate frame ids: {duplicates}. Every Frame.id must be unique."
            )

        id_set = set(ids)
        broken: list[str] = []
        for f in self.frames:
            if f.next is not None and f.next not in id_set:
                broken.append(f"{f.id}.next → {f.next!r}")
            if f.prev is not None and f.prev not in id_set:
                broken.append(f"{f.id}.prev → {f.prev!r}")
            if f.extends is not None and f.extends not in id_set:
                broken.append(f"{f.id}.extends → {f.extends!r}")
            for link in f.links:
                if not link.external and link.to not in id_set:
                    broken.append(f"{f.id}.links.to → {link.to!r}")
        if broken:
            raise ValueError(
                "FrameSet has unresolved link references: "
                + ", ".join(broken)
                + ". Every internal `to` / `next` / `prev` / `extends` "
                "must resolve to a known Frame id, or links must be "
                "marked `external: true`."
            )
        return self


# ─────────────────────────────────────────────────────────────────
# Validation gate
# ─────────────────────────────────────────────────────────────────


def validate_frameset(data: dict[str, Any]) -> FrameSetDocument:
    """Validate a parsed YAML mapping as a `FrameSetDocument`.

    Args:
        data: The result of `yaml.safe_load(...)` on a frameset YAML
            file. Must declare `kind: frameset`.

    Returns:
        A validated `FrameSetDocument`.

    Raises:
        pydantic.ValidationError: If the input violates the schema.
    """
    return FrameSetDocument.model_validate(data)


# ─────────────────────────────────────────────────────────────────
# Coercion — old shapes lift to FrameSetDocument
# ─────────────────────────────────────────────────────────────────


_DEFAULT_CANVAS: CanvasDims = [1280.0, 720.0]
"""Fallback canvas size when no source signal is available.

Matches the bundled `framegraph-overview-deck.yml`'s canvas — the
project's de-facto standard for 16:9 1280p decks.
"""


def _canvas_from_scene(scene: dict[str, Any] | None) -> CanvasDims | None:
    """Extract `[w, h]` from a `scene` block, if present and well-formed."""
    if not scene:
        return None
    canvas = scene.get("canvas")
    if not isinstance(canvas, dict):
        return None
    size = canvas.get("size")
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        return None
    try:
        return [float(size[0]), float(size[1])]
    except (TypeError, ValueError):
        return None


def _canvas_from_deck(deck: dict[str, Any] | None) -> CanvasDims | None:
    """Extract `[w, h]` from a deck-level `deck.canvas` block."""
    if not deck:
        return None
    canvas = deck.get("canvas")
    if not isinstance(canvas, dict):
        return None
    size = canvas.get("size")
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        return None
    try:
        return [float(size[0]), float(size[1])]
    except (TypeError, ValueError):
        return None


def _slide_to_frame(slide: dict[str, Any], default_id: str) -> Frame:
    """Lift one deck-slide entry into a Frame.

    The legacy slide entry shape carries `id`, `title`, `notes`,
    optional `use` + `fill` for pattern composition, and optional
    `tokens` / `symbols` / `component_defs` / `visual` /
    `semantic` for bespoke content. Every key flows through —
    `Frame` is `extra="allow"` and the renderer reads from the
    raw mapping for tokens / symbols / component_defs.
    """
    # Pop the keys we structurally care about; the rest flows through
    # via extra="allow".
    payload = dict(slide)  # shallow copy to avoid mutating caller
    fid = str(payload.pop("id", default_id))
    title = payload.pop("title", None)
    notes = payload.pop("notes", None)
    use = payload.pop("use", None)
    fill = payload.pop("fill", None)
    visual = payload.pop("visual", None)
    semantic = payload.pop("semantic", None)
    scene = payload.pop("scene", None)
    extends = payload.pop("$extends", None) or payload.pop("extends", None)
    return Frame(
        id=fid,
        title=title,
        notes=notes,
        use=use,
        fill=fill,
        visual=visual,
        semantic=semantic,
        scene=scene,
        extends=extends,
        # `payload` carries the residual keys (slide number, tokens,
        # symbols, etc.). Pydantic's extra="allow" preserves them.
        **payload,
    )


def coerce_to_frameset(data: dict[str, Any]) -> FrameSetDocument:
    """Lift any FrameGraph YAML payload into a `FrameSetDocument`.

    Total over the three documented kinds:

    - ``kind: frameset`` — passed straight to `validate_frameset`.
    - ``kind: presentation-deck`` — wrapped: each `slide` becomes
      a `Frame`, the deck's `canvas` becomes the FrameSet's default
      target, and the linear slide order materializes as `next` /
      `prev` links.
    - ``kind: hybrid-semantic-visual-diagram`` — wrapped: the whole
      document becomes a single Frame, `scene.canvas` becomes that
      Frame's sole target, the document's own `dsl` / `version`
      become the FrameSet's `dsl` / `version`.

    Documents without `kind:` (or with one of the rare `kind: hsv-…`
    or `kind: hybrid-…-diagram` legacy aliases) follow the
    "single-document" path — anything that has a `slides:` list is
    treated as a deck.

    Args:
        data: Parsed YAML mapping. Must carry `dsl: FrameGraph`.

    Returns:
        A validated `FrameSetDocument` representing the same content.

    Raises:
        ValueError: If the input is not a mapping, lacks
            `dsl: FrameGraph`, or specifies a kind that cannot be
            coerced (none currently — the function is total over
            FrameGraph YAML).
        pydantic.ValidationError: If the resulting FrameSet fails
            validation (duplicate ids, dangling references).
    """
    if not isinstance(data, dict):
        raise ValueError(f"FrameGraph document root must be a mapping; got {type(data).__name__}")
    if data.get("dsl") != "FrameGraph":
        raise ValueError(
            f"FrameGraph document must declare `dsl: FrameGraph`; got {data.get('dsl')!r}"
        )

    kind = data.get("kind")
    if kind == "frameset":
        return validate_frameset(data)

    version = float(data.get("version", 1.0))

    # Deck path: any document with a `slides:` list, even without a
    # `kind:` marker (the corpus has both shapes).
    slides = data.get("slides")
    if kind == "presentation-deck" or isinstance(slides, list):
        deck_block = data.get("deck") if isinstance(data.get("deck"), dict) else {}
        canvas = _canvas_from_deck(deck_block) or list(_DEFAULT_CANVAS)
        defaults = FrameSetDefaults(targets=[FrameTarget(name="default", canvas=canvas)])
        # Carry through deck-level globals as the FrameSet meta.
        meta = FrameSetMeta(
            defaults=defaults,
            canvas=canvas,
            tokens=deck_block.get("tokens") if isinstance(deck_block, dict) else None,
            symbols=deck_block.get("symbols") if isinstance(deck_block, dict) else None,
            component_defs=deck_block.get("component_defs")
            if isinstance(deck_block, dict)
            else None,
            chrome=deck_block.get("chrome") if isinstance(deck_block, dict) else None,
        )
        # Materialize Frames in slide order, with implicit next/prev.
        frames: list[Frame] = []
        slide_list = slides if isinstance(slides, list) else []
        for idx, slide in enumerate(slide_list):
            if not isinstance(slide, dict):
                continue
            default_id = f"slide_{slide.get('slide', idx + 1):02d}"
            frame = _slide_to_frame(slide, default_id)
            # Per-slide canvas overrides the deck default — preserve
            # via a Frame-level target.
            slide_scene = slide.get("scene") if isinstance(slide.get("scene"), dict) else None
            slide_canvas = _canvas_from_scene(slide_scene)
            if slide_canvas is not None and slide_canvas != canvas:
                frame.targets = [FrameTarget(name="default", canvas=slide_canvas)]
            frames.append(frame)
        # Wire next / prev chain.
        for i, f in enumerate(frames):
            if f.next is None and i + 1 < len(frames):
                f.next = frames[i + 1].id
            if f.prev is None and i > 0:
                f.prev = frames[i - 1].id

        if not frames:
            # An empty deck still produces a valid FrameSet with one
            # placeholder Frame so downstream consumers always have
            # something to render or skip.
            frames = [
                Frame(
                    id="empty",
                    title="Empty deck",
                    targets=[FrameTarget(name="default", canvas=canvas)],
                )
            ]

        return FrameSetDocument(
            dsl="FrameGraph",
            version=version,
            kind="frameset",
            frameset=meta,
            theme=data.get("$theme"),
            stylesheet=data.get("stylesheet"),
            frames=frames,
        )

    # Single-document path (everything else, including
    # `hybrid-semantic-visual-diagram` and unrecognized kinds).
    scene = data.get("scene") if isinstance(data.get("scene"), dict) else None
    canvas = _canvas_from_scene(scene) or list(_DEFAULT_CANVAS)
    defaults = FrameSetDefaults(targets=[FrameTarget(name="default", canvas=canvas)])
    meta = FrameSetMeta(defaults=defaults, canvas=canvas)
    frame_id = (
        str(data.get("scene", {}).get("id") if isinstance(data.get("scene"), dict) else "doc")
        or "doc"
    )
    frame = Frame(
        id=frame_id,
        title=str(scene.get("name")) if scene and scene.get("name") else None,
        targets=[FrameTarget(name="default", canvas=canvas)],
        scene=scene,
        semantic=data.get("semantic") if isinstance(data.get("semantic"), dict) else None,
        visual=data.get("visual") if isinstance(data.get("visual"), dict) else None,
    )
    return FrameSetDocument(
        dsl="FrameGraph",
        version=version,
        kind="frameset",
        frameset=meta,
        theme=data.get("$theme"),
        stylesheet=data.get("stylesheet"),
        frames=[frame],
    )


# ─────────────────────────────────────────────────────────────────
# Reverse projection — FrameSetDocument → legacy single-doc dict
# ─────────────────────────────────────────────────────────────────


def project_frame_to_document(
    frameset: FrameSetDocument, frame: Frame, target: FrameTarget
) -> dict[str, Any]:
    """Project one Frame at one target back to a legacy single-document dict.

    Used by the renderer dispatcher: rather than rewriting the whole
    `FrameGraphRenderer` pipeline to consume FrameSets directly, the
    Phase 1 implementation projects each Frame back to the
    `kind: hybrid-semantic-visual-diagram` shape that the existing
    renderer already understands. This keeps the per-type render
    modules and the pattern bridge untouched.

    The resulting dict carries the FrameSet's globals (theme,
    stylesheet, tokens, symbols, component_defs) merged into the
    single-frame visual block so the renderer sees the same
    inheritance chain it always has.

    Args:
        frameset: The full `FrameSetDocument` (provides defaults).
        frame: The Frame to project.
        target: The render target whose canvas is used.

    Returns:
        A `dict` shaped like a legacy
        ``kind: hybrid-semantic-visual-diagram`` document, suitable
        for `FrameGraphRenderer(doc).render_svg()`.
    """
    # Start with the Frame's existing scene block so rendering_contract
    # / source_image / etc. survive unchanged.
    scene: dict[str, Any] = dict(frame.scene or {})
    scene.setdefault("id", frame.id)
    if frame.title is not None:
        scene.setdefault("name", frame.title)
    scene["canvas"] = {"size": list(target.canvas), "units": "px"}

    visual: dict[str, Any] = dict(frame.visual or {})

    # Merge FrameSet meta tokens / symbols / component_defs into the
    # visual block, with Frame-level keys winning (matches the legacy
    # `library < deck < $extends < slide` order at slide level).
    if frameset.frameset.tokens:
        visual.setdefault("tokens", {})
        existing_tokens = dict(visual.get("tokens") or {})
        merged_tokens = dict(frameset.frameset.tokens)
        merged_tokens.update(existing_tokens)
        visual["tokens"] = merged_tokens
    if frameset.frameset.symbols:
        existing_symbols = dict(visual.get("symbols") or {})
        merged_symbols = dict(frameset.frameset.symbols)
        merged_symbols.update(existing_symbols)
        visual["symbols"] = merged_symbols
    if frameset.frameset.component_defs:
        existing_cdefs = dict(visual.get("component_defs") or {})
        merged_cdefs = dict(frameset.frameset.component_defs)
        merged_cdefs.update(existing_cdefs)
        visual["component_defs"] = merged_cdefs

    return {
        "dsl": "FrameGraph",
        "version": frameset.version,
        "kind": "hybrid-semantic-visual-diagram",
        "scene": scene,
        "semantic": frame.semantic
        or {"ontology": {"node_types": {}, "edge_types": {}}, "nodes": [], "edges": []},
        "visual": visual,
    }


# ─────────────────────────────────────────────────────────────────
# Phase 2 — native-FrameSet enrichment (deck-merge lift)
# ─────────────────────────────────────────────────────────────────


_CANONICAL_RENDERING_CONTRACT: dict[str, Any] = {
    "coordinate_mode": "absolute",
    "preserve_manual_line_breaks": True,
    "text": {"min_font_size": 7, "overflow": "shrink_to_fit"},
    "semantics": {"decorative_objects_may_omit_bind": True},
}
"""The four canonical rendering contracts that `library.build_slide_doc`
auto-injects on every deck slide. The native-FrameSet enrichment path
applies them when the source Frame doesn't already declare its own
``scene.rendering_contract``.
"""


_CANONICAL_EMPTY_SEMANTIC: dict[str, Any] = {
    "ontology": {"node_types": {}, "edge_types": {}},
    "nodes": [],
    "edges": [],
}
"""Empty semantic block matching `library.build_slide_doc`'s fallback."""


def _deep_merge(base: Any, override: Any) -> Any:
    """Recursive dict merge — `override` wins on scalar conflicts.

    Inlined here rather than imported from `framegraph.library` so
    `_frameset.py` stays free of circular-import worries; keeps the
    module a self-contained Phase-1+2 surface. Behaviour mirrors
    `library.deep_merge` exactly: lists are *replaced*, not
    concatenated.
    """
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    result: dict[str, Any] = dict(base)
    for k, v in override.items():
        result[k] = _deep_merge(result.get(k), v) if k in result else v
    return result


def _resolve_extends_chain(
    frame: Frame, frameset: FrameSetDocument, _seen: frozenset[str] = frozenset()
) -> Frame:
    """Resolve a Frame's `extends` chain into a single merged Frame.

    Walks `frame.extends` recursively and merges the chain
    *base-first* — so the most-derived Frame's keys win. Cycles raise
    `ValueError`. Phase 1's `FrameSetDocument` validator already
    rejects dangling `extends` references; this helper assumes
    they're resolved.

    Token / symbol / component_def / layer merge semantics mirror
    `library.build_slide_doc`'s `$extends` handling:

    - **tokens** — recursive `_deep_merge`, derived wins on scalar conflicts.
    - **symbols** — shallow union, derived wins on key conflicts.
    - **component_defs** — shallow union, derived wins.
    - **layers** — base layers first, derived layers second; same-id
      derived layer replaces the base layer of that id.
    """
    if frame.extends is None:
        return frame
    if frame.id in _seen:
        raise ValueError(
            f"Cycle detected resolving Frame.extends for {frame.id!r}: {sorted(_seen | {frame.id})}"
        )
    base_frame = next((f for f in frameset.frames if f.id == frame.extends), None)
    if base_frame is None:
        # Phase 1's validator should have caught this; fail cleanly
        # here in case a user constructed FrameSetDocument by hand.
        raise ValueError(f"Frame {frame.id!r} extends unknown frame {frame.extends!r}")
    base_resolved = _resolve_extends_chain(base_frame, frameset, _seen | {frame.id})

    # Token / symbol / component_def merge inside `visual`.
    base_visual: dict[str, Any] = dict(base_resolved.visual or {})
    derived_visual: dict[str, Any] = dict(frame.visual or {})

    merged_visual: dict[str, Any] = {}
    base_tokens = base_visual.get("tokens") or {}
    derived_tokens = derived_visual.get("tokens") or {}
    if base_tokens or derived_tokens:
        merged_visual["tokens"] = _deep_merge(base_tokens, derived_tokens)

    base_symbols = base_visual.get("symbols") or {}
    derived_symbols = derived_visual.get("symbols") or {}
    if base_symbols or derived_symbols:
        merged_visual["symbols"] = {**base_symbols, **derived_symbols}

    base_cdefs = base_visual.get("component_defs") or {}
    derived_cdefs = derived_visual.get("component_defs") or {}
    if base_cdefs or derived_cdefs:
        merged_visual["component_defs"] = {**base_cdefs, **derived_cdefs}

    # Layer merge: base layers first, derived second; same-id derived
    # layer replaces base layer of that id.
    base_layers = list(base_visual.get("layers") or [])
    derived_layers = list(derived_visual.get("layers") or [])
    if base_layers or derived_layers:
        merged_layer_map: dict[str, dict[str, Any]] = {}
        for lyr in base_layers + derived_layers:
            if isinstance(lyr, dict):
                merged_layer_map[str(lyr.get("id", ""))] = lyr
        merged_visual["layers"] = list(merged_layer_map.values())

    # Carry through any other visual-block keys the derived frame
    # declared (e.g. style overrides we haven't formalized yet).
    for k, v in derived_visual.items():
        if k not in merged_visual:
            merged_visual[k] = v
    for k, v in base_visual.items():
        if k not in merged_visual:
            merged_visual[k] = v

    # Same merge order for the scene block: derived keys win.
    merged_scene = _deep_merge(base_resolved.scene or {}, frame.scene or {})

    # Build a synthetic merged Frame. Use the derived frame's id, links,
    # next/prev, targets — those are not inheritable. `extends` clears
    # because the chain is now resolved.
    return Frame(
        id=frame.id,
        title=frame.title or base_resolved.title,
        targets=frame.targets,
        next=frame.next,
        prev=frame.prev,
        links=frame.links,
        extends=None,
        visual=merged_visual or None,
        semantic=frame.semantic or base_resolved.semantic,
        scene=merged_scene or None,
        use=frame.use if frame.use is not None else base_resolved.use,
        fill=frame.fill if frame.fill is not None else base_resolved.fill,
        notes=frame.notes or base_resolved.notes,
    )


def build_frame_doc(
    frameset: FrameSetDocument, frame: Frame, target: FrameTarget
) -> dict[str, Any]:
    """Assemble an enriched single-doc dict for one Frame at one target.

    The native-FrameSet equivalent of `library.build_slide_doc`.
    Applies the same enrichment chain so the rendered output is
    consistent across the deck and FrameSet code paths:

    1. Resolve `Frame.extends` recursively (cycles raise).
    2. Token deep-merge: `frameset.tokens` < `frame.visual.tokens`.
       Frame-local tokens win on scalar conflicts.
    3. Symbol shallow-merge: `frameset.symbols` ∪ `frame.visual.symbols`.
       Frame-local wins on key conflicts.
    4. Component_defs shallow-merge: same rule.
    5. Canvas: from the chosen `FrameTarget`.
    6. Rendering contract: take the Frame's `scene.rendering_contract`
       when set; otherwise apply the four canonical contracts that
       `library.build_slide_doc` injects on every deck slide.
    7. Semantic block: take the Frame's, otherwise canonical-empty.

    Pattern composition (`Frame.use` set) is **out of scope** for
    Phase 2 — that requires `FrameGraphLibrary` access (theme +
    stylesheet lookup). When `frame.use` is set, `build_frame_doc`
    raises `NotImplementedError` with a pointer to use
    `FrameGraphDeckRenderer.build_slide_doc` via the legacy deck
    path until Phase 7 lands the FrameSet-native composer.

    Args:
        frameset: The validated `FrameSetDocument`.
        frame: The Frame to project.
        target: The render target whose canvas is used.

    Returns:
        A `dict` shaped like a legacy
        ``kind: hybrid-semantic-visual-diagram`` document.

    Raises:
        ValueError: If `frame.extends` introduces a cycle or refers
            to an unknown Frame id.
        NotImplementedError: If `frame.use` is set (pattern
            composition — Phase 7 scope).
    """
    if frame.use is not None:
        raise NotImplementedError(
            f"Frame {frame.id!r} carries `use:` (pattern composition) — "
            f"Phase 2 doesn't yet support patterns through the FrameSet path. "
            f"Use `FrameGraphDeckRenderer.build_slide_doc` for now (legacy deck path)."
        )

    resolved = _resolve_extends_chain(frame, frameset)

    # Token deep-merge: frameset-level < frame-level.
    fs_tokens = frameset.frameset.tokens or {}
    frame_visual = dict(resolved.visual or {})
    frame_tokens = frame_visual.get("tokens") or {}
    merged_tokens = _deep_merge(fs_tokens, frame_tokens)

    # Symbol / component_def shallow merge: frameset-level ∪ frame-level.
    fs_symbols = frameset.frameset.symbols or {}
    frame_symbols = frame_visual.get("symbols") or {}
    merged_symbols = {**fs_symbols, **frame_symbols}

    fs_cdefs = frameset.frameset.component_defs or {}
    frame_cdefs = frame_visual.get("component_defs") or {}
    merged_cdefs = {**fs_cdefs, **frame_cdefs}

    visual: dict[str, Any] = dict(frame_visual)
    if merged_tokens:
        visual["tokens"] = merged_tokens
    if merged_symbols:
        visual["symbols"] = merged_symbols
    if merged_cdefs:
        visual["component_defs"] = merged_cdefs

    # Scene: start from the Frame's existing scene (so per-Frame
    # rendering_contract / source_image / etc. survive); inject the
    # canvas from the resolved target; default rendering_contract
    # when the Frame doesn't already declare one.
    scene: dict[str, Any] = dict(resolved.scene or {})
    scene.setdefault("id", resolved.id)
    if resolved.title is not None:
        scene.setdefault("name", resolved.title)
    scene["canvas"] = {"size": list(target.canvas), "units": "px"}
    scene.setdefault("rendering_contract", dict(_CANONICAL_RENDERING_CONTRACT))

    semantic = resolved.semantic or dict(_CANONICAL_EMPTY_SEMANTIC)

    doc: dict[str, Any] = {
        "dsl": "FrameGraph",
        "version": frameset.version,
        "kind": "hybrid-semantic-visual-diagram",
        "scene": scene,
        "semantic": semantic,
        "visual": visual,
    }
    # Phase 5 — apply per-target adjustments (font scale, hide,
    # padding delta) after the projection is otherwise complete.
    if target.adjustments is not None:
        doc = apply_target_adjustments(doc, target.adjustments)
    return doc


# ─────────────────────────────────────────────────────────────────
# Per-target adjustments — Phase 5 of ADR 0001
# ─────────────────────────────────────────────────────────────────


def _scale_text_size(value: Any, factor: float) -> Any:
    """Multiply a single text-style ``size`` value by `factor`.

    Sizes in `visual.tokens.text_styles` are typically numbers (px),
    but the schema uses ``extra="allow"`` so they may also arrive as
    strings (e.g. ``"14"``) or be missing. This helper preserves
    every non-numeric shape unchanged — strings, None, and complex
    types pass through untouched. Only `int`/`float` values scale.
    """
    if isinstance(value, bool):
        # `bool` is a subclass of `int` in Python; never scale flags.
        return value
    if isinstance(value, (int, float)):
        return value * factor
    return value


def _apply_font_scale(visual: dict[str, Any], factor: float) -> None:
    """Walk `visual.tokens.text_styles[*]` and scale numeric ``size`` fields."""
    tokens = visual.get("tokens")
    if not isinstance(tokens, dict):
        return
    text_styles = tokens.get("text_styles")
    if not isinstance(text_styles, dict):
        return
    for style_def in text_styles.values():
        if not isinstance(style_def, dict):
            continue
        if "size" in style_def:
            style_def["size"] = _scale_text_size(style_def["size"], factor)


def _apply_hide(visual: dict[str, Any], hide_ids: list[str]) -> None:
    """Drop matching layers and matching top-level objects in remaining layers.

    Matches by `id` exactly. Order-preserving for retained items.
    Non-matching ids are silently ignored — by design, the same
    `hide` list may be reused across Frames where only some ids are
    present.
    """
    if not hide_ids:
        return
    drop = set(hide_ids)
    layers = visual.get("layers")
    if not isinstance(layers, list):
        return
    kept_layers: list[Any] = []
    for layer in layers:
        if not isinstance(layer, dict):
            kept_layers.append(layer)
            continue
        if layer.get("id") in drop:
            continue
        objects = layer.get("objects")
        if isinstance(objects, list):
            layer["objects"] = [
                obj
                for obj in objects
                if not (isinstance(obj, dict) and obj.get("id") in drop)
            ]
        kept_layers.append(layer)
    visual["layers"] = kept_layers


def _apply_padding_delta(scene: dict[str, Any], delta: float) -> None:
    """Inset `scene.canvas.size` by `2 * delta` per axis.

    A positive `delta` shrinks the renderable canvas (think: page
    margins around the content). A negative `delta` expands it.
    Pattern-system margins, which derive from canvas size, scale
    proportionally because a smaller canvas yields a smaller 8 %
    safety inset and proportionally tighter gutters.

    The result is clamped to a minimum of 1 px per axis to keep the
    renderer's ``viewBox="0 0 W H"`` valid even when an aggressive
    delta would otherwise zero out the canvas.
    """
    if delta == 0:
        return
    canvas = scene.get("canvas")
    if not isinstance(canvas, dict):
        return
    size = canvas.get("size")
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        return
    try:
        w = float(size[0])
        h = float(size[1])
    except (TypeError, ValueError):
        return
    new_w = max(1.0, w - 2.0 * delta)
    new_h = max(1.0, h - 2.0 * delta)
    canvas["size"] = [new_w, new_h]


def apply_target_adjustments(
    doc: dict[str, Any], adjustments: FrameTargetAdjustments
) -> dict[str, Any]:
    """Mutate-and-return a projected single-doc dict per `adjustments`.

    Phase 5 of ADR 0001. Applies the three adjustment knobs in a
    fixed, documented order:

    1. ``font_scale`` — scales `visual.tokens.text_styles[*].size`.
    2. ``hide`` — drops matching layers and matching top-level
       objects within remaining layers.
    3. ``padding_delta`` — shrinks `scene.canvas.size` by
       ``2 * padding_delta`` on each axis.

    The function mutates `doc` in place AND returns it (the
    mutate-and-return idiom matches `build_frame_doc`'s usage). Pass
    a deep-copied dict if you need the original preserved.

    Args:
        doc: A projected single-doc dict (output of
            `build_frame_doc` or `project_frame_to_document`).
        adjustments: The adjustments to apply.

    Returns:
        The mutated `doc`.
    """
    visual = doc.get("visual")
    if isinstance(visual, dict):
        if adjustments.font_scale is not None and adjustments.font_scale != 1.0:
            _apply_font_scale(visual, adjustments.font_scale)
        if adjustments.hide:
            _apply_hide(visual, adjustments.hide)

    if adjustments.padding_delta is not None and adjustments.padding_delta != 0:
        scene = doc.get("scene")
        if isinstance(scene, dict):
            _apply_padding_delta(scene, adjustments.padding_delta)

    return doc


# ─────────────────────────────────────────────────────────────────
# Renderer adapter — emit one SVG per (Frame, target)
# ─────────────────────────────────────────────────────────────────


class RenderedFrame:
    """One Frame's rendered SVG output at one target.

    A small structural record returned by `render_frameset`. Holds the
    Frame id, target name + canvas, the generated SVG string, and any
    per-frame rendering warnings collected by
    `FrameGraphRenderer.warnings`.
    """

    __slots__ = ("frame_id", "target_name", "canvas", "svg", "warnings")

    def __init__(
        self,
        frame_id: str,
        target_name: str,
        canvas: CanvasDims,
        svg: str,
        warnings: list[str],
    ) -> None:
        self.frame_id = frame_id
        self.target_name = target_name
        self.canvas = canvas
        self.svg = svg
        self.warnings = warnings


def _resolve_target(
    frame: Frame, frameset: FrameSetDocument, target_name: str | None
) -> FrameTarget:
    """Pick a render target for a Frame.

    Resolution order:
      1. If `target_name` is given, look for it on the Frame.
      2. If `target_name` is given and the Frame has no per-frame
         targets, try the FrameSet defaults.
      3. If `target_name` is None, return the Frame's first target,
         or the FrameSet's first default, or the canvas-fallback
         `[1280, 720]`.

    Raises:
        KeyError: When `target_name` is given and no target with
            that name exists on either the Frame or in the
            FrameSet defaults.
    """
    candidates = list(frame.targets)
    if not candidates:
        candidates = list(frameset.frameset.defaults.targets)
    if not candidates:
        # Last-resort fallback so a Frame without explicit targets
        # always renders at the project's de-facto 1280x720.
        return FrameTarget(name="default", canvas=list(_DEFAULT_CANVAS))

    if target_name is None:
        return candidates[0]

    for t in candidates:
        if t.name == target_name:
            return t
    raise KeyError(
        f"Frame {frame.id!r} has no target named {target_name!r}; "
        f"available: {[t.name for t in candidates]}"
    )


def render_frameset(
    frameset: FrameSetDocument,
    *,
    target_name: str | None = None,
    frame_ids: list[str] | None = None,
) -> list[RenderedFrame]:
    """Render every Frame in the FrameSet to SVG at the given target.

    Each Frame is projected to a legacy single-document dict via
    `build_frame_doc` (Phase 2 — applies deck-merge enrichments:
    deep-merged tokens / symbols / component_defs from
    ``frameset.frameset.*`` plus canonical rendering-contract
    defaults) and fed through `FrameGraphRenderer(doc).render_svg()`.
    The per-type renderer modules and the pattern bridge stay
    untouched — this function is purely an envelope.

    Byte-identical-parity contract: for FrameSets coerced from
    legacy single-document YAML (where every Frame already carries
    a complete `scene` block), `build_frame_doc` is a no-op
    enrichment (the canonical defaults `setdefault` past the
    existing values). Phase 1's render-parity tests pin this.

    Args:
        frameset: A validated `FrameSetDocument`.
        target_name: Optional target identifier (e.g. "landscape",
            "mobile"). When None, each Frame uses its first target
            (or the FrameSet defaults' first target).
        frame_ids: Optional allow-list of Frame ids to render. When
            None, every Frame in the FrameSet is rendered.

    Returns:
        A list of `RenderedFrame`s, one per requested Frame, in the
        Frames' declared order.

    Raises:
        KeyError: When `target_name` is given and not found on a
            Frame.
        Exception: Anything `FrameGraphRenderer.render_svg` raises is
            propagated.
    """
    # Lazy import — `framegraph.renderer` imports plenty of modules at
    # construction time; the deferred import here keeps a bare
    # `coerce_to_frameset(...)` call cheap.
    from framegraph.renderer import FrameGraphRenderer

    selected: list[Frame]
    if frame_ids is None:
        selected = list(frameset.frames)
    else:
        wanted = set(frame_ids)
        selected = [f for f in frameset.frames if f.id in wanted]
        missing = wanted - {f.id for f in selected}
        if missing:
            raise KeyError(
                f"FrameSet does not contain frame ids: {sorted(missing)}; "
                f"available: {[f.id for f in frameset.frames]}"
            )

    rendered: list[RenderedFrame] = []
    for frame in selected:
        target = _resolve_target(frame, frameset, target_name)
        # Phase 2 dispatcher: pattern-composed Frames (`use:` set)
        # cannot yet take the FrameSet path because the FrameSet
        # doesn't carry library theme + stylesheet — Phase 7 scope.
        # Until then, emit a clear NotImplementedError via
        # `build_frame_doc` rather than silently falling back to
        # `project_frame_to_document` (which would skip pattern
        # composition entirely).
        doc = build_frame_doc(frameset, frame, target)
        renderer = FrameGraphRenderer(doc)
        svg = renderer.render_svg()
        rendered.append(
            RenderedFrame(
                frame_id=frame.id,
                target_name=target.name,
                canvas=list(target.canvas),
                svg=svg,
                warnings=list(renderer.warnings),
            )
        )
    return rendered


# ─────────────────────────────────────────────────────────────────
# Link injection — Phase 6 of ADR 0001
# ─────────────────────────────────────────────────────────────────


def _compute_frame_url(
    frame_id: str,
    target_name: str,
    *,
    base_url: str | None = None,
    file_template: str | None = None,
) -> str:
    """Compute a navigation URL for a (Frame, target) pair.

    Phase 6 of ADR 0001. Two URL strategies:

    1. ``file_template`` — Python ``str.format`` template using
       ``{frame_id}`` and ``{target_name}``. Useful for static-export
       workflows where every Frame is a sibling SVG file
       (``"slide_{frame_id}.svg"``). Other unknown placeholders are
       left untouched.
    2. ``base_url`` — sitemap-style absolute URL of the form
       ``<base_url>/<target_name>/<frame_id>``, matching the URL
       pattern emitted by `emit_sitemap` (Phase 4). Frame ids and
       target names are URL-escaped.

    Exactly one of the two must be supplied. Both ``None`` raises
    ``ValueError``; both set raises ``ValueError``.

    Args:
        frame_id: The destination Frame id.
        target_name: The active target name.
        base_url: Sitemap-style URL prefix.
        file_template: Python ``str.format`` template.

    Returns:
        The computed URL.

    Raises:
        ValueError: If neither or both of the URL inputs are supplied.
    """
    if base_url is None and file_template is None:
        raise ValueError(
            "_compute_frame_url requires exactly one of `base_url` or `file_template`"
        )
    if base_url is not None and file_template is not None:
        raise ValueError(
            "_compute_frame_url accepts at most one of `base_url` or `file_template`; "
            "both were given"
        )

    if file_template is not None:
        return file_template.format(frame_id=frame_id, target_name=target_name)

    # `base_url` path — sitemap-compatible URL pattern.
    from urllib.parse import quote, urlparse

    assert base_url is not None  # narrowing for type-checker
    if not base_url.strip():
        raise ValueError("base_url must be a non-empty URL prefix")
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"base_url {base_url!r} is not a valid URL prefix; "
            "expected something like 'https://example.com' or "
            "'https://example.com/docs'"
        )
    prefix = base_url.rstrip("/")
    return f"{prefix}/{quote(target_name, safe='')}/{quote(frame_id, safe='')}"


_SVG_BODY_SPLIT_RE = re.compile(r"(?P<head>.*?</desc>\s*(?:<defs>.*?</defs>\s*)?)(?P<body>.*)</svg>", re.DOTALL)


def inject_svg_navigation_links(
    svg: str,
    frame: Frame,
    frameset: FrameSetDocument,
    *,
    target_name: str,
    base_url: str | None = None,
    file_template: str | None = None,
) -> str:
    """Wrap a rendered SVG's body in ``<a href="...">`` for click-to-advance.

    Phase 6 of ADR 0001. The simplest deck-navigation contract:
    when a Frame has a `next` link, the entire rendered scene
    becomes a single clickable region pointing at the next Frame.
    Click anywhere → advance. Survives SVG → PDF (vector) and
    SVG → HTML embed equally because the SVG2 ``<a>`` element is
    natively supported by browsers, weasyprint, and modern PDF
    viewers.

    The wrapper goes around all *visible* content — between the
    document's ``<defs>`` block (or ``<desc>`` if no defs) and
    ``</svg>``. The ``<title>`` and ``<desc>`` accessibility tags
    stay outside the link so screen readers still pick up the
    Frame's name first.

    URL resolution mirrors `_compute_frame_url`:

    - When ``file_template`` is given, the URL is
      ``file_template.format(frame_id=…, target_name=…)``.
    - When ``base_url`` is given, the URL follows the Phase 4
      sitemap pattern: ``<base_url>/<target_name>/<frame_id>``.

    Returns the SVG unchanged when:

    - both ``base_url`` and ``file_template`` are ``None``,
    - ``frame.next`` is ``None`` (no navigation target), OR
    - the SVG body cannot be located (defensive — the renderer's
      output schema is stable but we never crash a render on a
      cosmetic feature).

    Args:
        svg: The rendered SVG document, with ``<?xml ?>`` prolog.
        frame: The Frame whose ``next`` link to render as ``<a>``.
        frameset: The parent FrameSet — used to validate that
            ``frame.next`` resolves to a known Frame id (it should
            already, by `validate_frameset`'s contract).
        target_name: The active target — used in the URL.
        base_url: Optional sitemap-style URL prefix.
        file_template: Optional ``str.format`` template.

    Returns:
        The SVG, possibly with the body wrapped in ``<a href="...">``.

    Raises:
        ValueError: If both ``base_url`` and ``file_template`` are
            supplied.
    """
    if base_url is not None and file_template is not None:
        raise ValueError(
            "inject_svg_navigation_links accepts at most one of "
            "`base_url` or `file_template`; both were given"
        )
    if base_url is None and file_template is None:
        return svg
    if frame.next is None:
        return svg
    if frame.next not in {f.id for f in frameset.frames}:
        # Defensive: validate_frameset already enforces this, but
        # be tolerant when called on a hand-built frame object.
        return svg

    url = _compute_frame_url(
        frame.next,
        target_name,
        base_url=base_url,
        file_template=file_template,
    )

    match = _SVG_BODY_SPLIT_RE.search(svg)
    if match is None:
        return svg
    body = match.group("body")
    # Build aria-label from the target Frame's title when present;
    # falls back to the frame id.
    target_frame = next((f for f in frameset.frames if f.id == frame.next), None)
    label = target_frame.title if target_frame and target_frame.title else frame.next
    # Escape `&`, `<`, `>`, `"` in the URL and aria-label so the
    # injected attribute values are well-formed XML.
    from xml.sax.saxutils import quoteattr

    href_attr = quoteattr(url)
    label_attr = quoteattr(f"Next: {label}")
    head_end = match.start("body")
    body_end = match.end("body")
    return (
        svg[:head_end]
        + f"<a href={href_attr} aria-label={label_attr}>"
        + body
        + "</a>"
        + svg[body_end:]
    )


# ─────────────────────────────────────────────────────────────────
# Sitemap emission — Phase 4 of ADR 0001
# ─────────────────────────────────────────────────────────────────


def _frame_target_names(frame: Frame, frameset: FrameSetDocument) -> list[str]:
    """Names of every target a Frame can render at, in resolution order.

    Mirrors `_resolve_target` precedence: per-Frame `targets:` first,
    falling back to `frameset.defaults.targets`, falling back to a
    synthetic ``"default"`` target. The list is order-preserving and
    deduplicated by name.
    """
    seen: set[str] = set()
    names: list[str] = []
    candidates = list(frame.targets) or list(frameset.frameset.defaults.targets)
    if not candidates:
        return ["default"]
    for t in candidates:
        if t.name not in seen:
            seen.add(t.name)
            names.append(t.name)
    return names


def list_frameset_target_union(frameset: FrameSetDocument) -> list[str]:
    """Union of every target name declared anywhere in the FrameSet.

    Order: FrameSet defaults first (in declaration order), then any
    additional per-Frame targets discovered while walking
    `frameset.frames` in order. Duplicates are dropped on first sight.

    Args:
        frameset: A validated `FrameSetDocument`.

    Returns:
        Ordered list of unique target names. When neither defaults nor
        any Frame declares a target, returns ``["default"]`` to match
        the synthetic fallback in `_resolve_target`.
    """
    seen: set[str] = set()
    names: list[str] = []
    for t in frameset.frameset.defaults.targets:
        if t.name not in seen:
            seen.add(t.name)
            names.append(t.name)
    for frame in frameset.frames:
        for t in frame.targets:
            if t.name not in seen:
                seen.add(t.name)
                names.append(t.name)
    if not names:
        return ["default"]
    return names


def emit_sitemap(
    frameset: FrameSetDocument,
    base_url: str,
    *,
    target_filter: list[str] | None = None,
) -> str:
    """Emit a `sitemap.xml` for a FrameSet's link graph.

    Phase 4 of ADR 0001. The link graph **is** the sitemap: every
    Frame contributes one URL per render target it declares. URLs
    follow the path-style pattern::

        <base_url>/<target>/<frame_id>

    The output is a `<urlset>` document conforming to the sitemap.org
    0.9 schema (``http://www.sitemaps.org/schemas/sitemap/0.9``). It
    is deterministic: Frames walk in declaration order, targets walk
    in their per-Frame resolution order (per-Frame `targets:` first,
    then FrameSet defaults). Frame ids and base-URL path components
    are URL-escaped via `urllib.parse.quote` so reserved characters
    (`?`, `#`, spaces) don't corrupt the URL.

    Args:
        frameset: A validated `FrameSetDocument`.
        base_url: Site root, with or without a trailing slash. May
            include a path prefix (e.g. ``https://example.com/docs``).
            The scheme is preserved verbatim; only the path tail is
            normalised.
        target_filter: Optional allow-list of target names. When
            given, only URLs whose target name matches an entry in
            this list are emitted. When None (default), every
            (Frame × declared target) pair contributes one URL.

    Returns:
        The sitemap as an XML string, including the
        `<?xml version="1.0" encoding="UTF-8"?>` prolog. Suitable for
        writing to ``sitemap.xml`` and serving from a static host.

    Raises:
        ValueError: If `base_url` is empty or has no scheme/host
            component (i.e. is not parseable as a URL prefix).
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote, urlparse

    if not base_url or not base_url.strip():
        raise ValueError("base_url must be a non-empty URL prefix")
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"base_url {base_url!r} is not a valid URL prefix; "
            "expected something like 'https://example.com' or "
            "'https://example.com/docs'"
        )

    prefix = base_url.rstrip("/")
    allow: set[str] | None = set(target_filter) if target_filter is not None else None

    SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", SITEMAP_NS)
    urlset = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    for frame in frameset.frames:
        for target_name in _frame_target_names(frame, frameset):
            if allow is not None and target_name not in allow:
                continue
            # `quote` with default safe="/" preserves path
            # separators inside frame ids (rare but legal) while
            # escaping spaces, '#', '?', etc. We pass empty `safe`
            # because frame ids and target names are single path
            # segments — any '/' inside them is data, not a separator.
            url_path = (
                f"{prefix}/"
                f"{quote(target_name, safe='')}/"
                f"{quote(frame.id, safe='')}"
            )
            url_el = ET.SubElement(urlset, f"{{{SITEMAP_NS}}}url")
            loc_el = ET.SubElement(url_el, f"{{{SITEMAP_NS}}}loc")
            loc_el.text = url_path

    ET.indent(urlset, space="  ")
    body = ET.tostring(urlset, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


__all__ = [
    "Frame",
    "FrameLink",
    "FrameSetDefaults",
    "FrameSetDocument",
    "FrameSetMeta",
    "FrameTarget",
    "FrameTargetAdjustments",
    "RenderedFrame",
    "apply_target_adjustments",
    "build_frame_doc",
    "coerce_to_frameset",
    "emit_sitemap",
    "inject_svg_navigation_links",
    "list_frameset_target_union",
    "project_frame_to_document",
    "render_frameset",
    "validate_frameset",
]
