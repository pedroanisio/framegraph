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
        adjustments: Free-form per-target tuning bag. Phase 1 ignores
            this field; Phase 4 (per ADR 0001) wires per-target
            font-scale / padding / hide-on-target overrides.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    canvas: CanvasDims
    adjustments: dict[str, Any] | None = None


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

    return {
        "dsl": "FrameGraph",
        "version": frameset.version,
        "kind": "hybrid-semantic-visual-diagram",
        "scene": scene,
        "semantic": semantic,
        "visual": visual,
    }


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


__all__ = [
    "Frame",
    "FrameLink",
    "FrameSetDefaults",
    "FrameSetDocument",
    "FrameSetMeta",
    "FrameTarget",
    "RenderedFrame",
    "build_frame_doc",
    "coerce_to_frameset",
    "project_frame_to_document",
    "render_frameset",
    "validate_frameset",
]
