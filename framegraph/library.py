#!/usr/bin/env python3
"""fg_library.py  —  FrameGraph Component Library Composer

Resolves $theme and $symbols directives in a diagram YAML, merges the
referenced library files into a complete, self-contained FrameGraph YAML,
then optionally pipes directly to the renderer.

Directives (stripped before output):
  $theme:   "mckinsey"           # loads lib/tokens/<id>.yml
  $symbols: ["shared/s_node"]   # loads lib/symbols/<path>.sym.yml

Merge rules:
  tokens:  library base  < diagram overrides  (diagram always wins on conflict)
  symbols: library pool  + diagram-local       (diagram-local wins on same key)

Usage:
  python fg_library.py compose diagram.fg.yml -t mckinsey -o built.yml
  python fg_library.py compose diagram.fg.yml --render -o output.svg
  python fg_library.py list-themes
  python fg_library.py show-theme mckinsey
  python fg_library.py list-symbols
"""

from __future__ import annotations

import argparse
import copy
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from framegraph._helpers import fnum
from framegraph.canvas import DEFAULT_DECK_CANVAS, CanvasSize, canvas_from_mapping

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML required: pip install pyyaml") from exc


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge two dicts.  override wins on scalar conflicts.
    Lists are NOT merged — override replaces the entire list.
    """
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    result = dict(base)
    for k, v in override.items():
        result[k] = deep_merge(result.get(k), v) if k in result else v
    return result


def _scale_text_styles(text_styles: dict[str, Any], scale: float) -> dict[str, Any]:
    """Apply a uniform scale factor to every text-style's size + line_height.

    Used by the deck loader to expose the layout planner's chosen
    typography scale to the renderer. Render itself stays faithful;
    the planner is the only thing that decides how big text gets.

    Args:
        text_styles: Stylesheet's named text-style mapping.
        scale: Scale factor in (0, 1]. 1.0 returns input unchanged.

    Returns:
        A new dict with the same keys; each style's ``size`` and
        ``line_height`` (when present) multiplied by ``scale``.
    """
    if scale >= 0.999 or not text_styles:
        return dict(text_styles)
    out: dict[str, Any] = {}
    for name, raw in text_styles.items():
        if not isinstance(raw, dict):
            out[name] = raw
            continue
        scaled = dict(raw)
        if "size" in scaled:
            with suppress(TypeError, ValueError):
                scaled["size"] = float(scaled["size"]) * scale
        if "line_height" in scaled:
            with suppress(TypeError, ValueError):
                scaled["line_height"] = float(scaled["line_height"]) * scale
        out[name] = scaled
    return out


def strip_meta(d: dict[str, Any]) -> dict[str, Any]:
    """Remove _meta keys — they are library metadata, not FrameGraph fields."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file into a dict, returning ``{}`` for empty documents."""
    with open(path, encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
        return cast(dict[str, Any], loaded or {})


def dump_yaml(data: dict[str, Any], path: Path | None = None) -> str:
    """Serialize ``data`` to YAML, writing to ``path`` if given, and return it.

    Preserves key order and uses block style with unicode allowed.
    """
    text = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    if path:
        path.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Library loader
# ---------------------------------------------------------------------------


class FrameGraphLibrary:
    """Manages the library directory.  Discovers token packs and symbol packs
    and exposes them by their _meta.id (e.g. "mckinsey", "shared/s_node").
    """

    def __init__(self, lib_path: Path) -> None:
        """Scan a `lib/` directory of token packs and symbol packs.

        Args:
            lib_path: Filesystem path to a directory containing
                `tokens/*.yml` and `symbols/**/*.sym.yml`. Either
                subdirectory may be missing — packs already discovered
                remain accessible.

        """
        self.lib_path = lib_path
        self._token_packs: dict[str, Path] = {}
        self._symbol_packs: dict[str, Path] = {}
        self._scan()

    def _scan(self) -> None:
        tokens_dir = self.lib_path / "tokens"
        symbols_dir = self.lib_path / "symbols"
        if tokens_dir.exists():
            for f in tokens_dir.glob("*.yml"):
                data = load_yaml(f)
                meta = data.get("_meta", {})
                fid = meta.get("id") or f.stem
                self._token_packs[fid] = f
        if symbols_dir.exists():
            for f in symbols_dir.rglob("*.sym.yml"):
                data = load_yaml(f)
                meta = data.get("_meta", {})
                fid = meta.get("id") or str(f.relative_to(symbols_dir)).replace(".sym.yml", "")
                self._symbol_packs[fid] = f
                # also register by short key (filename stem)
                short = f.stem.replace(".sym", "")
                if short not in self._symbol_packs:
                    self._symbol_packs[short] = f

    def token_ids(self) -> list[str]:
        """Return the sorted ids of every discovered token pack."""
        return sorted(self._token_packs)

    def list_themes(self) -> list[str]:
        """Return the sorted ids of every discovered theme (token pack).

        Themes and token packs are the same thing — a theme *is* a bundled
        token pack such as `mckinsey`, `bain`, or `deloitte`. This is the
        documented public method referenced from README.md, AGENTS.md, and
        docs/MANUAL.md; it forwards to `token_ids()` for the canonical
        implementation.
        """
        return self.token_ids()

    def symbol_ids(self) -> list[str]:
        """Return the sorted ids of every discovered symbol pack."""
        return sorted(self._symbol_packs)

    def load_tokens(self, theme_id: str) -> dict[str, Any]:
        """Return the tokens section of a token pack (stripped of _meta)."""
        path = self._token_packs.get(theme_id)
        if not path:
            raise ValueError(
                f"unknown theme '{theme_id}'.  Available: {', '.join(self.token_ids())}"
            )
        raw = load_yaml(path)
        return strip_meta(raw)  # {colors, fonts, text_styles, stroke_styles, …}

    def load_symbols(self, sym_ref: str) -> dict[str, Any]:
        """Return the symbols dict from a symbol pack."""
        path = self._symbol_packs.get(sym_ref)
        if not path:
            # try as a relative path
            candidate = self.lib_path / "symbols" / (sym_ref + ".sym.yml")
            if candidate.exists():
                path = candidate
            else:
                raise ValueError(
                    f"unknown symbol pack '{sym_ref}'.  Available: {', '.join(self.symbol_ids())}"
                )
        raw = load_yaml(path)
        return cast(dict[str, Any], raw.get("symbols", {}))

    def show_theme(self, theme_id: str) -> None:
        """Pretty-print a token pack's metadata and color table to stdout.

        Args:
            theme_id: Pack id from `token_ids()`. Unknown ids print a
                "not found" line and return without raising.

        """
        path = self._token_packs.get(theme_id)
        if not path:
            print(f"theme not found: {theme_id}")
            return
        raw = load_yaml(path)
        meta = raw.get("_meta", {})
        print(f"\n{'=' * 60}")
        print(f"  {meta.get('name', theme_id)}  (id: {meta.get('id')})")
        if meta.get("brand_notes"):
            note = str(meta["brand_notes"]).strip().replace("\n", " ")
            print(f"  {note[:100]}{'…' if len(note) > 100 else ''}")
        print(f"{'=' * 60}")
        colors = raw.get("colors", {})
        print("\n  Colors:")
        for k, v in colors.items():
            print(f"    {k:20s}  {v}")
        print()


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


class FrameGraphComposer:
    """Assembles a complete FrameGraph YAML by merging library pieces into a
    diagram spec.  Processes and strips $theme and $symbols directives.
    """

    def __init__(self, library: FrameGraphLibrary) -> None:
        """Bind the composer to a `FrameGraphLibrary` for piece lookups."""
        self.library = library

    def compose(
        self,
        diagram: dict[str, Any],
        theme_override: str | None = None,
        extra_symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Merge library tokens and symbols into a diagram, stripping directives.

        Deep-copies ``diagram``, then pops ``$theme`` and ``$symbols`` (or the
        explicit overrides) and folds the referenced token pack and symbol
        packs into ``visual``. Library tokens are defaults; diagram values win.

        Args:
            diagram: The source FrameGraph spec.
            theme_override: Theme id replacing any ``$theme`` directive.
            extra_symbols: Symbol refs prepended ahead of ``$symbols``.

        Returns:
            The merged spec with directives removed.
        """
        doc = copy.deepcopy(diagram)

        # ── Extract directives ────────────────────────────────────────
        theme_id = theme_override or doc.pop("$theme", None)
        sym_refs: list[str] = list(doc.pop("$symbols", []) or [])
        if extra_symbols:
            sym_refs = list(extra_symbols) + sym_refs  # CLI overrides prepended

        visual = doc.setdefault("visual", {})

        # ── 1. Merge token pack ───────────────────────────────────────
        if theme_id:
            lib_tokens = self.library.load_tokens(theme_id)
            diag_tokens = visual.get("tokens") or {}
            # deep-merge: library provides defaults, diagram overrides
            visual["tokens"] = deep_merge(lib_tokens, diag_tokens)

        # ── 2. Merge symbol packs ─────────────────────────────────────
        if sym_refs:
            lib_symbols: dict[str, Any] = {}
            for ref in sym_refs:
                lib_symbols.update(self.library.load_symbols(ref))
            diag_symbols = visual.get("symbols") or {}
            # diagram-local symbols win on key conflicts
            visual["symbols"] = {**lib_symbols, **diag_symbols}

        return doc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_compose(args: argparse.Namespace, lib: FrameGraphLibrary) -> int:
    """Compose a diagram against the library and write/print the merged YAML.

    The composer's only job is YAML expansion. Use the package CLI
    (`framegraph render <input>`) to convert the composed YAML to SVG.
    """
    composer = FrameGraphComposer(lib)
    diagram = load_yaml(args.input)

    extra_syms = args.symbols.split(",") if args.symbols else None
    built = composer.compose(diagram, theme_override=args.theme, extra_symbols=extra_syms)

    output = args.output
    if output:
        dump_yaml(built, output)
        print(f"wrote {output}", file=sys.stderr)
    else:
        print(dump_yaml(built), end="")

    return 0


def cmd_list_themes(lib: FrameGraphLibrary) -> int:
    """Print each token pack id with its display name; return exit code 0."""
    print("\nAvailable themes:")
    for tid in lib.token_ids():
        path = lib._token_packs[tid]
        raw = load_yaml(path)
        name = raw.get("_meta", {}).get("name", tid)
        print(f"  {tid:20s}  {name}")
    print()
    return 0


def cmd_show_theme(args: argparse.Namespace, lib: FrameGraphLibrary) -> int:
    """Print the theme named by ``args.theme_id``; return exit code 0."""
    lib.show_theme(args.theme_id)
    return 0


def cmd_list_symbols(lib: FrameGraphLibrary) -> int:
    """Print each symbol pack id with its symbol names; return exit code 0."""
    print("\nAvailable symbol packs:")
    for sid in lib.symbol_ids():
        path = lib._symbol_packs[sid]
        raw = load_yaml(path)
        syms = raw.get("symbols", {})
        print(f"  {sid:40s}  symbols: {', '.join(syms.keys())}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the composer CLI argument parser with all subcommands.

    Subcommands: ``compose``, ``list-themes``, ``show-theme``,
    ``list-symbols``, and ``render-deck``.
    """
    p = argparse.ArgumentParser(
        description="FrameGraph Component Library Composer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--lib-path",
        type=Path,
        default=Path(__file__).parent / "lib",
        help="Library root (default: ./lib)",
    )

    sub = p.add_subparsers(dest="command")

    # compose
    cp = sub.add_parser("compose", help="Merge library into a diagram YAML")
    cp.add_argument("input", type=Path, help="Diagram .fg.yml source")
    cp.add_argument("-o", "--output", type=Path, help="Output YAML path")
    cp.add_argument("-t", "--theme", help="Theme id (overrides $theme in file)")
    cp.add_argument("-s", "--symbols", help="Comma-separated extra symbol refs")

    # list-themes
    sub.add_parser("list-themes", help="List available token packs")

    # show-theme
    sp = sub.add_parser("show-theme", help="Print theme color palette")
    sp.add_argument("theme_id")

    # list-symbols
    sub.add_parser("list-symbols", help="List available symbol packs")

    # render-deck
    rp = sub.add_parser("render-deck", help="Render a multi-page deck YAML into per-slide SVGs")
    rp.add_argument("input", type=Path, help="Deck YAML (.deck.yml)")
    rp.add_argument("-o", "--output", type=Path, help="Output directory (default: ./output)")

    return p


# ---------------------------------------------------------------------------
# Deck renderer  (v1.2 extension — multi-page)
# ---------------------------------------------------------------------------


def _resolve_frame_target_canvas(frame: Any, frameset: Any, target_name: str) -> list[float]:
    """Look up a `FrameTarget`'s canvas by name on a Frame inside a FrameSet.

    Phase 3 helper. Resolution order matches `_frameset._resolve_target`:
    per-Frame `targets` first, then the FrameSet's
    `defaults.targets`. Raises `KeyError` when the name is not
    declared on either side — same contract as the renderer
    adapter so `framegraph deck --target <name>` and
    `render_frameset(..., target_name=<name>)` fail in the same way.

    Args:
        frame: A `framegraph._frameset.Frame` instance.
        frameset: A `framegraph._frameset.FrameSetDocument` instance.
        target_name: The target identifier to resolve.

    Returns:
        The matching target's `canvas` list `[width, height]`.

    Raises:
        KeyError: When neither the Frame nor the FrameSet defaults
            declare a target with that name.
    """
    candidates = list(frame.targets) or list(frameset.frameset.defaults.targets)
    for t in candidates:
        if t.name == target_name:
            return list(t.canvas)
    raise KeyError(
        f"Frame {frame.id!r} has no target named {target_name!r}; "
        f"available: {[t.name for t in candidates]}"
    )


def list_frameset_targets(deck_data: dict[str, Any]) -> list[str]:
    """Return every target name declared on a FrameSet view of `deck_data`.

    Phase 3 helper for `framegraph deck --all-targets`. Coerces the
    input to a `FrameSetDocument` and walks the FrameSet defaults
    plus every per-Frame target, returning the unique target names
    in declaration order.

    Args:
        deck_data: A FrameGraph YAML payload. Anything
            `coerce_to_frameset` accepts is accepted here.

    Returns:
        Ordered, deduplicated list of target names. Empty when the
        FrameSet declares no targets (callers can fall back to
        single-target rendering).
    """
    from framegraph._frameset import coerce_to_frameset

    raw_for_coerce = (
        deck_data
        if isinstance(deck_data, dict) and deck_data.get("dsl") == "FrameGraph"
        else {**(deck_data if isinstance(deck_data, dict) else {}), "dsl": "FrameGraph"}
    )
    fs = coerce_to_frameset(raw_for_coerce)
    seen: list[str] = []
    seen_set: set[str] = set()
    for t in fs.frameset.defaults.targets:
        if t.name not in seen_set:
            seen.append(t.name)
            seen_set.add(t.name)
    for f in fs.frames:
        for t in f.targets:
            if t.name not in seen_set:
                seen.append(t.name)
                seen_set.add(t.name)
    return seen


class FrameGraphDeckRenderer:
    """Renders a multi-page deck YAML (kind: presentation-deck) into one SVG
    per slide.

    Deck YAML structure:
        dsl: FrameGraph
        version: 1.2
        kind: presentation-deck
        $theme: <id>          # optional library theme
        deck:
            canvas: {size: [960, 540], units: px}
            tokens: {...}     # deck-level token overrides (merged on top of $theme)
            symbols: {...}    # deck-level shared symbols
            component_defs: {...}
        slides:
            - slide: 1
              id: s1_opening
              title: "..."
              tokens: {...}   # slide-local overrides (merged on top of deck tokens)
              symbols: {...}  # slide-local additions
              semantic: {...} # optional semantic block
              visual:
                  layers: [...]
    """

    def __init__(
        self,
        deck_yaml: dict[str, Any],
        library: FrameGraphLibrary | None = None,
    ) -> None:
        """Build a deck renderer from a parsed deck YAML and an optional library.

        Args:
            deck_yaml: Parsed deck document. Must contain a `slides`
                list; the top-level `deck` mapping carries
                deck-global tokens, symbols, and component defs.
            library: A `FrameGraphLibrary` used to resolve theme
                references (`tokens: theme:bcg_built` etc.). When
                None, theme references in the deck are unresolved.

        Raises:
            pydantic.ValidationError: When `deck_yaml` declares
                `dsl: FrameGraph` but its structure does not satisfy
                the Pydantic schema. Inputs without the marker pass
                through unvalidated — see framegraph._schema.

        """
        # Validation gate — symmetric with FrameGraphRenderer.__init__.
        if isinstance(deck_yaml, dict) and deck_yaml.get("dsl") == "FrameGraph":
            from framegraph._schema import validate_deck

            validate_deck(deck_yaml)

        self.raw = deck_yaml
        self.library = library
        self.deck_config = deck_yaml.get("deck", {}) or {}
        self.slides_raw = deck_yaml.get("slides", []) or []

        # Auto-assign slide numbers when omitted (1-based, declaration
        # order). Decks frequently omit the per-slide `slide:` field —
        # without this default every reader (filename builder, chrome
        # page-number, notes export) falls back to 0 and produces
        # `slide_00_<id>.svg` filenames plus missing page numbers.
        # Mutating once here keeps the eight downstream readers
        # consistent. Explicit `slide:` values are preserved as-is so
        # operators can use sparse / out-of-order numbering when they
        # want it.
        for _i, _slide in enumerate(self.slides_raw):
            if isinstance(_slide, dict) and "slide" not in _slide:
                _slide["slide"] = _i + 1

        self.global_tokens, self.global_symbols, self.global_cdefs = self._build_globals()
        # Index slides by id for $extends resolution
        self._slide_index: dict[str, Any] = {
            str(s["id"]): s for s in self.slides_raw if s.get("id")
        }
        # Stylesheet — resolved once at construction. Slides using
        # `use: <pattern>` consult this to style every zone uniformly.
        # Top-level `stylesheet:` accepts a bundled name (e.g.
        # "default") or a path. Defaults to the bundled "default".
        self._stylesheet = self._load_stylesheet()
        # Pattern catalog — lazy-loaded on first `use:` encounter.
        self._catalog: Any = None
        # Per-slide layout reports — populated by `build_slide_doc`
        # for templated slides. Keyed by slide id; carries the
        # planner's scale and overflow facts.
        self._layout_reports: dict[str, Any] = {}

    def _build_globals(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        theme_id = self.raw.get("$theme")
        library = self.library
        base_tokens: dict[str, Any] = {}
        if theme_id and library is not None:
            base_tokens = library.load_tokens(theme_id)
        deck_tokens = deep_merge(base_tokens, self.deck_config.get("tokens") or {})
        deck_symbols: dict[str, Any] = {}
        for ref in self.raw.get("$symbols", []) or []:
            if library is None:
                raise ValueError("$symbols requires a FrameGraphLibrary")
            deck_symbols.update(library.load_symbols(str(ref)))
        deck_symbols.update(self.deck_config.get("symbols") or {})
        deck_cdefs = {**(self.deck_config.get("component_defs") or {})}
        return deck_tokens, deck_symbols, deck_cdefs

    def _load_stylesheet(self) -> Any:
        """Resolve the deck's stylesheet declaration.

        Reads the top-level ``stylesheet:`` field. Accepts a bundled
        name (string, looked up under ``framegraph/lib/styles/``), a
        filesystem path, or an inline mapping.

        When the field is omitted, the stylesheet is auto-selected
        based on the deck canvas:

        * Canvas width ≥ 1600 px (screen-slide territory: 1600×900,
          1920×1080, 2560×1440, etc.) → ``default-screen`` (16pt body,
          13pt label, 18pt title, readable at presentation distance).
        * Canvas width < 1600 px (letter-size print, 1280×720
          screencast, web embed) → ``default`` (10pt body, 8pt label,
          12pt title — Big-4 print density).

        Explicit ``stylesheet:`` declarations always win; the
        auto-selection only applies when the field is absent. The
        breakpoint and bundled stylesheet names are stable contract —
        regression-guarded by ``tests/integration/test_deck_default_stylesheet.py``.
        """
        from framegraph.patterns.style import (
            Stylesheet,
            load_bundled_stylesheet,
            load_stylesheet,
        )

        ref = self.raw.get("stylesheet")
        if ref is None:
            # Canvas-aware default selection. Read width from the
            # deck-level canvas; fall back to a print-grade default
            # when the canvas is absent or malformed.
            canvas = canvas_from_mapping(
                self.deck_config.get("canvas"),
                fallback=CanvasSize(0.0, 0.0),
            )
            canvas_w = canvas.width
            return load_bundled_stylesheet("default-screen" if canvas_w >= 1600 else "default")
        if isinstance(ref, dict):
            return Stylesheet.model_validate(ref)
        if isinstance(ref, str):
            ref_path = Path(ref)
            if ref_path.exists():
                return load_stylesheet(ref_path)
            return load_bundled_stylesheet(ref)
        raise ValueError(
            f"deck.stylesheet must be a name, path, or mapping; got {type(ref).__name__}"
        )

    def _get_catalog(self) -> Any:
        """Lazy-load the bundled pattern catalog."""
        if self._catalog is None:
            from framegraph._patterns import load_pattern_catalog

            self._catalog = load_pattern_catalog()
        return self._catalog

    def _resolve_pattern(self, ref: Any) -> Any:
        """Resolve a `use:` reference to a SlidePattern.

        Accepts an integer id, a numeric string, or a slug
        (lowercased pattern name with spaces → hyphens).
        """
        catalog = self._get_catalog()
        # Integer id (or numeric string).
        if isinstance(ref, int):
            return catalog.get(ref)
        if isinstance(ref, str):
            s = ref.strip()
            if s.isdigit():
                return catalog.get(int(s))
            # Slug: match against pattern.name lowercased+slugified.
            target = s.lower().replace("_", "-")
            for p in catalog.slide_template_patterns:
                slug = "".join(
                    ch if ch.isalnum() or ch == "-" else "-" if ch == " " else ""
                    for ch in p.name.lower()
                )
                # Collapse runs of '-'.
                while "--" in slug:
                    slug = slug.replace("--", "-")
                slug = slug.strip("-")
                if slug == target:
                    return p
            raise KeyError(f"no pattern matching slug {ref!r}")
        raise TypeError(f"`use:` expects an int id or string slug; got {type(ref).__name__}")

    def _build_pattern_slide_doc(
        self,
        slide: dict[str, Any],
        *,
        canvas: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a Document for a slide using `use: <pattern>` + `fill:`.

        Composition pipeline:

          structure  ← bundled catalog pattern
          data       ← slide.fill
          visual     ← deck.stylesheet (treatments, typography, chrome)
          tokens     ← deck.$theme + deck.tokens + slide.tokens
          chrome     ← stylesheet.slide_chrome (top stripe, title bar,
                       page number, brand mark, footer rule)
          synthesis  ← stylesheet.synthesis_band (when slide has
                       `synthesis: "..."`)

        The slide author writes only `use` + `fill` + optional
        `synthesis`. Every slide gets the same chrome + footer +
        card discipline regardless of which pattern it uses.
        """
        from framegraph.patterns import (
            compose_document,
            compute_layout_plan,
            derive_default_fill_schema,
            derive_fill_schema_with_sidecar,
            load_sidecar,
        )

        pattern = self._resolve_pattern(slide["use"])

        # Sidecar auto-discovery — same convention as the CLI's
        # `_find_sidecar`. Sidecars ship inside the package under
        # `framegraph/data/fills/` (moved from the legacy
        # `static/refs/fills/` path in the publish-prep commit so the
        # wheel carries them).
        fills_dir = Path(__file__).resolve().parent / "data" / "fills"
        sidecar_matches = (
            sorted(fills_dir.glob(f"{pattern.id:03d}-*.yml")) if fills_dir.exists() else []
        )

        if sidecar_matches:
            sidecar = load_sidecar(sidecar_matches[0])
            Model = derive_fill_schema_with_sidecar(pattern, sidecar)
        else:
            Model = derive_default_fill_schema(pattern)

        fill = Model.model_validate(slide.get("fill") or {})

        # Phase 3 — `canvas` override (used by multi-target rendering).
        # When None, fall back to the deck-level canvas.
        if canvas is None:
            canvas = self.deck_config.get("canvas")
        canvas_size = canvas_from_mapping(canvas, fallback=DEFAULT_DECK_CANVAS)
        canvas_w, canvas_h = canvas_size.size

        # Compute the content rect (canvas minus chrome / footer /
        # synthesis reservations).
        ss = self._stylesheet.model_dump() if self._stylesheet is not None else {}
        chrome_cfg = ss.get("slide_chrome") or {}
        synthesis_cfg = ss.get("synthesis_band") or {}

        top_reserve = 0.0
        if chrome_cfg.get("enabled"):
            top_reserve = float((chrome_cfg.get("title_separator") or {}).get("y_offset", 56))
        bottom_reserve = 0.0
        footer_cfg = chrome_cfg.get("footer") or {}
        if footer_cfg:
            bottom_reserve += float(footer_cfg.get("height", 24))

        synthesis_text = slide.get("synthesis")
        if synthesis_text and synthesis_cfg.get("enabled"):
            bottom_reserve += float(synthesis_cfg.get("height", 72)) + float(
                synthesis_cfg.get("margin_bottom", 24)
            )

        # Pad between chrome and the first card.
        content_top_pad = 16.0
        content_bottom_pad = 8.0

        content_y = top_reserve + content_top_pad
        content_h = max(
            1.0,
            canvas_h - content_y - bottom_reserve - content_bottom_pad,
        )

        # Layout planner — single decision-maker for geometry +
        # uniform typography scale. Returns boxes, the scale factor
        # to apply to every text style on this slide, and the
        # LayoutReport (overflow facts for the operator).
        plan = compute_layout_plan(pattern, canvas_w, content_h, fill=fill)
        layout = {role: (x, y + content_y, w, h) for role, (x, y, w, h) in plan.boxes.items()}
        plan_scale = plan.scale
        plan_report = plan.report

        label_overrides = slide.get("labels") if isinstance(slide.get("labels"), dict) else None
        numbers = slide.get("numbers") if isinstance(slide.get("numbers"), dict) else None
        titles = slide.get("titles") if isinstance(slide.get("titles"), dict) else None

        doc = compose_document(
            pattern,
            fill,
            layout,
            canvas_w,
            canvas_h,
            stylesheet=self._stylesheet,
            label_overrides=label_overrides,
            numbers=numbers,
            titles=titles,
        )

        # Merge tokens — theme + deck + slide. The stylesheet's
        # named text_styles are exposed as tokens so referenced
        # styles (`style: card_label`, etc.) resolve at render time.
        slide_num = slide.get("slide", 0)
        slide_id = slide.get("id", f"slide_{slide_num:02d}")
        slide_tokens = deep_merge(self.global_tokens, slide.get("tokens") or {})

        if self._stylesheet is not None and self._stylesheet.text_styles:
            existing_text_styles = slide_tokens.get("text_styles") or {}
            # Apply the planner's uniform scale to every text style so
            # the slide reads as a single consistent typographic scale.
            # Card chrome (label band, padding) does not scale, by
            # design — only the text-size axis bends.
            scaled_text_styles = (
                _scale_text_styles(self._stylesheet.text_styles, plan_scale)
                if plan_scale < 0.999
                else self._stylesheet.text_styles
            )
            slide_tokens = dict(slide_tokens)
            slide_tokens["text_styles"] = {
                **scaled_text_styles,
                **existing_text_styles,
            }

        doc["visual"]["tokens"] = slide_tokens
        doc["scene"]["id"] = slide_id
        doc["scene"]["name"] = slide.get("title", pattern.name)
        if slide.get("description"):
            doc["scene"]["description"] = slide["description"]

        # Build chrome + synthesis layers and prepend so they paint
        # behind the content. The pattern's `enterprise_layout` may
        # carry chrome-level overrides (e.g. cover slides suppress the
        # chrome title + separator + page number to give the body
        # display type full vertical space). Slide-level `chrome:`
        # still wins on conflict — the catalog ships defaults, the
        # author can override per-slide.
        layers = list(doc["visual"].get("layers") or [])
        slide_for_chrome = slide
        ent_canvas = (
            pattern.enterprise_layout.canvas_overrides
            if pattern.enterprise_layout is not None
            else None
        )
        if ent_canvas:
            existing = slide.get("chrome", {})
            if isinstance(existing, dict):
                merged_chrome = {**ent_canvas, **existing}
                slide_for_chrome = {**slide, "chrome": merged_chrome}
            elif existing is False or existing == 0:
                # author explicitly disabled chrome — honor that
                pass
            else:
                slide_for_chrome = {**slide, "chrome": dict(ent_canvas)}
        chrome_layer = self._build_chrome_layer_v2(
            slide=slide_for_chrome,
            chrome_cfg=chrome_cfg,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            brand_text=self.deck_config.get("brand_text") or self.raw.get("brand_text"),
        )
        if chrome_layer is not None:
            layers.insert(0, chrome_layer)

        if synthesis_text and synthesis_cfg.get("enabled"):
            synthesis_layer = self._build_synthesis_layer(
                synthesis_text=synthesis_text,
                synthesis_cfg=synthesis_cfg,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                footer_h=float(footer_cfg.get("height", 24)) if footer_cfg else 0.0,
            )
            if synthesis_layer is not None:
                layers.append(synthesis_layer)

        doc["visual"]["layers"] = layers

        # Stash the planner's report for downstream collection by the
        # deck loader. One report per slide; keyed by slide id.
        self._layout_reports[slide_id] = plan_report

        return doc

    def _build_chrome_layer_v2(
        self,
        slide: dict[str, Any],
        chrome_cfg: dict[str, Any],
        canvas_w: float,
        canvas_h: float,
        brand_text: str | None,
    ) -> dict[str, Any] | None:
        """Universal chrome: top stripe, title band, separator, page number,
        brand mark, footer rule. Driven entirely by `slide_chrome` config.

        Author can opt out with `chrome: false` on the slide. Author
        can override individual fields with `chrome: { ... }` map.
        """
        if not chrome_cfg or not chrome_cfg.get("enabled"):
            return None
        slide_chrome = slide.get("chrome", {})
        if slide_chrome is False or slide_chrome == 0:
            return None
        overrides = dict(slide_chrome) if isinstance(slide_chrome, dict) else {}

        objects: list[dict[str, Any]] = []

        # 0. Page background — full-canvas opaque rect so slides render
        # with a defined background in every viewer. Without this the
        # SVG falls back to the viewer's default (often transparent or
        # checkerboard), which makes pattern slides look unfinished
        # next to bespoke slides that paint their own background.
        # Config key: `slide_chrome.page_background.color` (token name
        # or hex). Defaults to `surface`; pass `null` or omit `color`
        # to disable. Author can override per slide via
        # `chrome.page_background_color`.
        page_bg_cfg = chrome_cfg.get("page_background", {"color": "surface"})
        if isinstance(page_bg_cfg, dict):
            page_bg_color = overrides.get("page_background_color") or page_bg_cfg.get("color")
            if page_bg_color:
                objects.append(
                    {
                        "id": "_chrome.page_bg",
                        "type": "rect",
                        "box": [0, 0, canvas_w, canvas_h],
                        "fill": page_bg_color,
                        "decorative": True,
                    }
                )

        # 1. Top stripe (full-bleed band of accent color)
        top_stripe = chrome_cfg.get("top_stripe") or {}
        if top_stripe:
            stripe_h = float(top_stripe.get("height", 4))
            stripe_color = overrides.get("top_stripe_color") or top_stripe.get("color", "accent")
            objects.append(
                {
                    "id": "_chrome.top_stripe",
                    "type": "rect",
                    "box": [0, 0, canvas_w, stripe_h],
                    "fill": stripe_color,
                    "decorative": True,
                }
            )

        # 2. Title band — slide title in the top strip
        title_band = chrome_cfg.get("title_band") or {}
        if title_band:
            band_h = float(title_band.get("height", 52))
            band_y = float(title_band.get("y_offset", 0))
            margin_l = float(title_band.get("margin_left", 32))
            margin_r = float(title_band.get("margin_right", 80))
            # An explicit `chrome.title: ""` suppresses the chrome title
            # (used by cover/divider patterns whose body draws the
            # display title instead). Falls back to slide.title only
            # when the override key is absent.
            if "title" in overrides:
                title_text = overrides["title"] or ""
            else:
                title_text = slide.get("title", "") or ""
            if title_text:
                objects.append(
                    {
                        "id": "_chrome.title",
                        "type": "text",
                        "decorative": True,
                        "box": [
                            margin_l,
                            band_y,
                            max(0.0, canvas_w - margin_l - margin_r),
                            band_h,
                        ],
                        "text": title_text,
                        "style": title_band.get("typography", "slide_title_band"),
                    }
                )

        # 3. Title separator rule (suppress with `chrome.title_rule: false`)
        sep = chrome_cfg.get("title_separator") or {}
        if sep and overrides.get("title_rule", True):
            sep_y = float(sep.get("y_offset", 56))
            margin_l = float((title_band or {}).get("margin_left", 32))
            margin_r = float((title_band or {}).get("margin_right", 80))
            objects.append(
                {
                    "id": "_chrome.title_rule",
                    "type": "line",
                    "decorative": True,
                    "from": [margin_l, sep_y],
                    "to": [canvas_w - margin_r, sep_y],
                    "stroke": {
                        "color": sep.get("color", "border"),
                        "width": float(sep.get("width", 0.5)),
                    },
                }
            )

        # 4. Page number — top-right (suppress with `chrome.page_number: false`)
        page_num_cfg = chrome_cfg.get("page_number") or {}
        slide_num = slide.get("slide")
        if page_num_cfg and slide_num is not None and overrides.get("page_number", True):
            x_from_right = float(page_num_cfg.get("x_from_right", 32))
            y = float(page_num_cfg.get("y", 18))
            fmt = page_num_cfg.get("format", "{n:02d}")
            try:
                num_text = fmt.format(n=int(slide_num))
            except (ValueError, KeyError):
                num_text = str(slide_num)
            objects.append(
                {
                    "id": "_chrome.page_num",
                    "type": "text",
                    "decorative": True,
                    "box": [
                        canvas_w - x_from_right - 40,
                        y - 8,
                        40,
                        18,
                    ],
                    "text": num_text,
                    "style": page_num_cfg.get("typography", "page_num"),
                }
            )

        # 5. Footer band (rule + brand mark)
        footer_cfg = chrome_cfg.get("footer") or {}
        if footer_cfg:
            footer_h = float(footer_cfg.get("height", 24))
            footer_y = canvas_h - footer_h
            margin_l = float(footer_cfg.get("margin_left", 32))
            margin_r = float(footer_cfg.get("margin_right", 32))
            rule_color = footer_cfg.get("rule_color", "border")
            rule_width = float(footer_cfg.get("rule_width", 0.5))
            rule_y = footer_y + float(footer_cfg.get("rule_y_offset", 0))
            if rule_color and rule_width > 0:
                objects.append(
                    {
                        "id": "_chrome.footer_rule",
                        "type": "line",
                        "decorative": True,
                        "from": [margin_l, rule_y],
                        "to": [canvas_w - margin_r, rule_y],
                        "stroke": {"color": rule_color, "width": rule_width},
                    }
                )
            # Brand mark
            brand_cfg = chrome_cfg.get("brand_mark") or {}
            if brand_cfg and brand_text:
                bx = float(brand_cfg.get("x", margin_l))
                by_offset = float(brand_cfg.get("y_offset", 8))
                objects.append(
                    {
                        "id": "_chrome.brand",
                        "type": "text",
                        "decorative": True,
                        "box": [
                            bx,
                            footer_y + by_offset,
                            canvas_w - margin_l - margin_r,
                            footer_h - by_offset,
                        ],
                        "text": brand_text,
                        "style": brand_cfg.get("typography", "brand_mark"),
                    }
                )

        if not objects:
            return None
        return {"id": "_slide_chrome", "z": 0, "objects": objects}

    def _build_synthesis_layer(
        self,
        synthesis_text: Any,
        synthesis_cfg: dict[str, Any],
        canvas_w: float,
        canvas_h: float,
        footer_h: float,
    ) -> dict[str, Any] | None:
        """Build the optional synthesis band rendered above the footer.

        `synthesis_text` may be a string (single emphasis line) or a
        mapping `{title: "...", body: "..."}` for two-line treatment.
        """
        if not synthesis_cfg.get("enabled"):
            return None
        height = float(synthesis_cfg.get("height", 72))
        margin_bottom = float(synthesis_cfg.get("margin_bottom", 24))
        margin_l = float(synthesis_cfg.get("margin_left", 32))
        margin_r = float(synthesis_cfg.get("margin_right", 32))

        band_y = canvas_h - footer_h - margin_bottom - height
        band_x = margin_l
        band_w = canvas_w - margin_l - margin_r
        objects: list[dict[str, Any]] = []

        # Background rect
        objects.append(
            {
                "id": "_synth.bg",
                "type": "rect",
                "decorative": True,
                "box": [band_x, band_y, band_w, height],
                "fill": synthesis_cfg.get("fill_color", "text"),
                "corner_radius": float(synthesis_cfg.get("corner_radius", 4)),
            }
        )
        # Accent bar
        accent_bar = synthesis_cfg.get("accent_bar") or {}
        if accent_bar:
            bw = float(accent_bar.get("width", 4))
            objects.append(
                {
                    "id": "_synth.accent",
                    "type": "rect",
                    "decorative": True,
                    "box": [band_x, band_y, bw, height],
                    "fill": accent_bar.get("color", "accent"),
                }
            )
        # Text
        pad = synthesis_cfg.get("padding") or [14, 24, 14, 24]
        if isinstance(pad, (int, float)):
            pad = [pad, pad, pad, pad]
        pt, pr, pb, pl = (float(p) for p in pad)
        text_x = band_x + pl
        text_y = band_y + pt
        text_w = max(0.0, band_w - pl - pr)
        text_h = max(0.0, height - pt - pb)

        if isinstance(synthesis_text, str):
            objects.append(
                {
                    "id": "_synth.body",
                    "type": "text",
                    "decorative": True,
                    "box": [text_x, text_y, text_w, text_h],
                    "text": synthesis_text,
                    "style": synthesis_cfg.get("emphasis_typography", "synthesis_em"),
                }
            )
        elif isinstance(synthesis_text, dict):
            title_t = synthesis_text.get("title") or ""
            body_t = synthesis_text.get("body") or ""
            if title_t:
                objects.append(
                    {
                        "id": "_synth.title",
                        "type": "text",
                        "decorative": True,
                        "box": [text_x, text_y, text_w, 22],
                        "text": title_t,
                        "style": synthesis_cfg.get("emphasis_typography", "synthesis_em"),
                    }
                )
            if body_t:
                objects.append(
                    {
                        "id": "_synth.body",
                        "type": "text",
                        "decorative": True,
                        "box": [text_x, text_y + 26, text_w, max(0.0, text_h - 26)],
                        "text": body_t,
                        "style": synthesis_cfg.get("body_typography", "synthesis_body"),
                    }
                )

        return {"id": "_synthesis_band", "z": 5, "objects": objects}

    def build_slide_doc(
        self,
        slide: dict[str, Any],
        *,
        canvas: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assemble a complete FrameGraph document for a single slide.

        Two slide modes:

        - **Pattern-composition mode** (`use: <pattern>` + `fill: {…}`)
          — the framework's reusable-template path. Structure is
          drawn from the bundled catalog, style from the deck's
          stylesheet, tokens from the deck's theme, content from the
          slide's `fill:`. The author writes ~5–15 lines per slide
          and gets a coherent, themed result.

        - **Hand-authored mode** (`visual: …`, `semantic: …`,
          `symbols: …`) — the original surface for bespoke slides.

        Merge order (each layer wins over the one above):
          library $theme tokens
            ↓ deck.tokens
              ↓ $extends base slide tokens   ← SP-5a
                ↓ this slide tokens

        Args:
            slide: The slide entry from `self.slides_raw`.
            canvas: Phase 3 of ADR 0001 — optional canvas override.
                When None (default), the deck-level
                `self.deck_config.get("canvas", ...)` applies.
                When given, the override wins; used by multi-target
                rendering (`--target` flag) to render the same slide
                at the FrameSet's target dimensions.
        """
        # Pattern-composition path: short-circuit when `use:` is set.
        if slide.get("use") is not None:
            return self._build_pattern_slide_doc(slide, canvas=canvas)

        if canvas is None:
            canvas = self.deck_config.get("canvas", {"size": [960, 540]})
        slide_num = slide.get("slide", 0)
        slide_id = slide.get("id", f"slide_{slide_num:02d}")

        # ── SP-5a: $extends — inherit from a named base slide ────────────
        extends_id = slide.get("$extends")
        base_slide: dict[str, Any] = {}
        if extends_id:
            base_slide = self._slide_index.get(str(extends_id), {})
            if not base_slide:
                import warnings as _w

                _w.warn(
                    f"slide {slide_id}: $extends references unknown id '{extends_id}'",
                    stacklevel=2,
                )

        # Merge token layers: global < base tokens < slide-local
        base_tokens = deep_merge(self.global_tokens, base_slide.get("tokens") or {})
        slide_tokens = deep_merge(base_tokens, slide.get("tokens") or {})

        # Merge symbol layers: global < base < slide (slide wins on name conflict)
        slide_symbols = {
            **self.global_symbols,
            **(base_slide.get("symbols") or {}),
            **(slide.get("symbols") or {}),
        }

        # Component defs: same merge order
        slide_cdefs = {
            **self.global_cdefs,
            **(base_slide.get("component_defs") or {}),
            **(slide.get("component_defs") or {}),
        }

        # Visual layers: base layers first, then slide layers appended
        # (slide layers render on top; allows base to provide chrome, child provides content)
        base_visual = dict(base_slide.get("visual") or {})
        slide_visual = dict(slide.get("visual") or {})
        if base_slide and base_visual.get("layers") and slide_visual.get("layers"):
            # Merge layer lists: base layers first, then slide layers
            # A slide layer with the same id as a base layer replaces it
            base_layers = {str(lyr.get("id", "")): lyr for lyr in base_visual.get("layers") or []}
            child_layers = {str(lyr.get("id", "")): lyr for lyr in slide_visual.get("layers") or []}
            merged = dict(base_layers)
            merged.update(child_layers)
            slide_visual["layers"] = list(merged.values())
        elif base_visual.get("layers") and not slide_visual.get("layers"):
            slide_visual["layers"] = base_visual.get("layers")

        # visual block: tokens + symbols + component_defs + merged slide layers
        slide_visual["tokens"] = slide_tokens
        slide_visual["symbols"] = slide_symbols
        if slide_cdefs:
            slide_visual["component_defs"] = slide_cdefs

        # ── Master-slide chrome ──────────────────────────────────────────
        # `deck.chrome:` declares a symbol auto-stamped on every slide as
        # a chrome layer (z=0). The slide may opt out via `chrome: false`,
        # or override params/slot values via `chrome: {params: …, …}`.
        chrome_layer = self._build_chrome_layer(slide, canvas)
        if chrome_layer is not None:
            existing_layers = list(slide_visual.get("layers") or [])
            # Prepend so the chrome paints first; same-id slide layer
            # would override via the existing dict-keyed merge above.
            chrome_id = str(chrome_layer.get("id", "_chrome"))
            if not any(str(lyr.get("id", "")) == chrome_id for lyr in existing_layers):
                slide_visual["layers"] = [chrome_layer] + existing_layers

        # Canonical semantic fallback if the slide omits it
        slide_semantic = slide.get("semantic") or {
            "ontology": {"node_types": {}, "edge_types": {}},
            "nodes": [],
            "edges": [],
        }

        return {
            "dsl": "FrameGraph",
            "version": "1.2",
            "kind": "hybrid-semantic-visual-diagram",
            "scene": {
                "id": slide_id,
                "name": slide.get("title", f"Slide {slide_num}"),
                "description": slide.get("description", ""),
                "canvas": canvas,
                "rendering_contract": {
                    "coordinate_mode": "absolute",
                    "preserve_manual_line_breaks": True,
                    "text": {"min_font_size": 7, "overflow": "shrink_to_fit"},
                    "semantics": {"decorative_objects_may_omit_bind": True},
                },
            },
            "semantic": slide_semantic,
            "visual": slide_visual,
        }

    def _build_chrome_layer(
        self, slide: dict[str, Any], canvas: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Build the auto-prepended chrome layer for a slide.

        Reads `deck.chrome` (the master-slide chrome declaration) and the
        slide's own `chrome:` field. The slide may opt out
        (`chrome: false`) or override the deck's params / slot values
        (`chrome: {params: …, slot1: …}`).

        Args:
            slide: The slide entry from `self.slides_raw`.
            canvas: The deck-level canvas mapping (size: [w, h]).

        Returns:
            A layer mapping ready to prepend to `visual.layers`, or
            None when no chrome should be emitted.
        """
        deck_chrome = self.deck_config.get("chrome")
        if not deck_chrome:
            return None
        # Per-slide opt-out: `chrome: false` (or null/0)
        slide_chrome = slide.get("chrome", {})
        if slide_chrome is False or slide_chrome == 0:
            return None

        # Normalize deck.chrome — accept either a string (symbol id) or a mapping.
        if isinstance(deck_chrome, str):
            deck_cfg: dict[str, Any] = {"symbol": deck_chrome}
        elif isinstance(deck_chrome, dict):
            deck_cfg = dict(deck_chrome)
        else:
            return None

        symbol = deck_cfg.get("symbol")
        if not symbol or symbol not in self.global_symbols:
            return None

        # Per-slide overrides — merged on top of deck.chrome's defaults.
        override_cfg = dict(slide_chrome) if isinstance(slide_chrome, dict) else {}

        # Build the `use` object. Top-level fields are slot pass-through;
        # `params` is the nested parameter map. Both layers contribute.
        canvas_size = canvas_from_mapping(canvas, fallback=DEFAULT_DECK_CANVAS)
        canvas_box = [0, 0, fnum(canvas_size.width, 960), fnum(canvas_size.height, 540)]

        use_obj: dict[str, Any] = {
            "type": "use",
            "id": "_chrome.use",
            "decorative": True,
            "symbol": str(symbol),
            "box": canvas_box,
        }
        # Slot pass-through fields from deck.chrome (everything that isn't
        # a structural key) become top-level fields on the use object.
        structural_keys = {"symbol", "params", "id"}
        for k, v in deck_cfg.items():
            if k not in structural_keys:
                use_obj[k] = v
        for k, v in override_cfg.items():
            if k not in structural_keys:
                use_obj[k] = v

        # Merged params: deck-level first, slide-level overrides last.
        params: dict[str, Any] = {}
        deck_params = deck_cfg.get("params")
        if isinstance(deck_params, dict):
            params.update(deck_params)
        slide_params = override_cfg.get("params")
        if isinstance(slide_params, dict):
            params.update(slide_params)
        if params:
            use_obj["params"] = params

        return {
            "id": "_chrome",
            "z": deck_cfg.get("z", 0),
            "objects": [use_obj],
        }

    def collect_notes(self) -> dict[str, str]:
        """Return a dict mapping slide_id → notes string for all slides with notes.
        Notes are stripped from SVG output but available here for export.
        """
        result: dict[str, str] = {}
        for slide in self.slides_raw:
            notes = slide.get("notes")
            if notes:
                sid = str(slide.get("id", f"slide_{slide.get('slide', 0):02d}"))
                result[sid] = str(notes).strip()
        return result

    def render_notes(self, output_dir: Path, filename: str = "notes.md") -> Path | None:
        """Write speaker notes to a Markdown file alongside the slide SVGs.
        Returns the path written, or None if no slides had notes.
        Format:
          ## Slide N — <title>
          <id>
          ---
          <notes text>
        """
        notes = self.collect_notes()
        if not notes:
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "---",
            "disclaimer: Speaker notes generated from FrameGraph deck YAML.",
            "---",
            "",
            "# Speaker Notes",
            "",
        ]
        for slide in self.slides_raw:
            sid = str(slide.get("id", f"slide_{slide.get('slide', 0):02d}"))
            n = slide.get("slide", "")
            title = slide.get("title", sid)
            note = notes.get(sid)
            if not note:
                continue
            lines.append(f"## Slide {n} — {title}")
            lines.append(f"*id: `{sid}`*")
            lines.append("")
            lines.append(note)
            lines.append("")
            lines.append("---")
            lines.append("")
        path = output_dir / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def render_all(
        self,
        output_dir: Path,
        *,
        yaml_source_dir: str | Path | None = None,
        target_name: str | None = None,
    ) -> list[Path]:
        """Render every slide; return the per-slide output paths.

        Phase 2 of ADR 0001: the slide loop drives off the FrameSet
        view of `self.raw` (via `coerce_to_frameset`). Per-slide
        enrichment continues to flow through `self.build_slide_doc`
        so deck-merge semantics (`library $theme < deck.tokens <
        $extends < slide.tokens`, master-slide chrome, pattern
        composition) stay byte-identical to Phase 1 output when
        ``target_name`` is None.

        Phase 3 of ADR 0001: when ``target_name`` is given, every
        slide renders at the FrameSet target's canvas dimensions
        (looked up on the per-Frame `targets` first, then the
        FrameSet's `defaults.targets`). This is the
        `framegraph deck --target <name>` entry point;
        `framegraph deck --all-targets` calls this once per target.

        Args:
            output_dir: Directory to receive `slide_<N>_<id>.svg` files.
            yaml_source_dir: Absolute directory of the deck YAML, used by
                `<image>` objects to resolve relative `href`s. When
                None, image paths must be absolute.
            target_name: Optional FrameSet target identifier. When
                None (default), every slide uses the deck-level
                canvas — preserves Phase 1/2 byte-identical output.
                When set, the matching `FrameTarget` is resolved
                (per-Frame override > FrameSet defaults) and its
                `canvas` dimensions override `deck.canvas` per slide.

        Raises:
            KeyError: When ``target_name`` is given and not declared
                on either the slide's Frame or in the FrameSet
                defaults.

        """
        # Deferred import: `framegraph.renderer` imports `framegraph.library`
        # via the package's `__init__.py`, so a top-level import here would
        # close the cycle.
        from framegraph._frameset import coerce_to_frameset
        from framegraph.renderer import FrameGraphRenderer

        # Build the FrameSet view of `self.raw`. `coerce_to_frameset`
        # is total over deck YAML — Phase 1 pinned this. The Frame
        # ids match the slide ids 1:1 (preserves the
        # `slide_<NN>_<id>.svg` filename convention below).
        #
        # `coerce_to_frameset` requires a top-level `dsl: FrameGraph`
        # marker; the deck-renderer constructor accepts dicts
        # without it (the validate-only-when-dsl-set gate matches
        # `FrameGraphRenderer.__init__`). Inject the marker when
        # absent so deck dicts assembled programmatically (the
        # `tests/unit/test_library.py` fixtures, the deck-composer
        # intermediate builds) participate in the FrameSet spine.
        raw_for_coerce = (
            self.raw
            if isinstance(self.raw, dict) and self.raw.get("dsl") == "FrameGraph"
            else {**(self.raw if isinstance(self.raw, dict) else {}), "dsl": "FrameGraph"}
        )
        frameset = coerce_to_frameset(raw_for_coerce)
        slides_by_id = {
            str(slide.get("id", f"slide_{slide.get('slide', i + 1):02d}")): slide
            for i, slide in enumerate(self.slides_raw)
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        source_dir = str(Path(yaml_source_dir).resolve()) if yaml_source_dir else ""
        out_paths: list[Path] = []
        # Aggregate per-slide LayoutReports, populated by the planner
        # via `build_slide_doc` for templated slides. Render is
        # faithful and emits no reports of its own — the planner is
        # the single decision-maker for geometry + uniform typography
        # scale, and the only source of overflow facts.
        self.constraint_reports = []
        for frame in frameset.frames:
            slide = slides_by_id.get(frame.id)
            if slide is None:
                # `coerce_to_frameset` synthesizes an "empty"
                # placeholder Frame for empty deck YAML. Skip it —
                # there's no slide payload to enrich or render.
                continue
            n = slide.get("slide", 0)
            sid = frame.id
            # Phase 3: when `target_name` is given, look up the
            # target on the per-Frame `targets` first, falling back
            # to the FrameSet's `defaults.targets`. Pass the resolved
            # canvas to `build_slide_doc` so deck-merge enrichment
            # uses the target dimensions.
            slide_canvas: dict[str, Any] | None = None
            if target_name is not None:
                target_canvas = _resolve_frame_target_canvas(frame, frameset, target_name)
                slide_canvas = {"size": list(target_canvas), "units": "px"}
            doc = self.build_slide_doc(slide, canvas=slide_canvas)
            renderer = FrameGraphRenderer(doc)
            renderer.yaml_source_dir = source_dir
            svg = renderer.render_svg()
            path = output_dir / f"slide_{n:02d}_{sid}.svg"
            path.write_text(svg, encoding="utf-8")
            kb = path.stat().st_size / 1024
            print(f"  slide {n:02d}  →  {path.name}  ({kb:.1f} KB)", file=sys.stderr)
            out_paths.append(path)

            # One LayoutReport per templated slide.
            report = self._layout_reports.get(sid)
            if report is None:
                continue
            self.constraint_reports.append(
                {
                    "slide_num": n,
                    "slide_id": sid,
                    "slide_title": slide.get("title", ""),
                    "scale": round(float(report.scale), 3),
                    "shrunk": bool(report.shrunk),
                    "fits": bool(report.fits),
                    "overflows": list(report.overflows),
                }
            )

        # Write speaker notes if any slide declares them
        notes_path = self.render_notes(output_dir)
        if notes_path:
            print(f"  notes   →  {notes_path.name}", file=sys.stderr)
        return out_paths


def cmd_render_deck(args: argparse.Namespace, lib: FrameGraphLibrary) -> int:
    """Handle `render-deck` — render every slide of a deck YAML to SVG."""
    deck_data = load_yaml(args.input)
    renderer = FrameGraphDeckRenderer(deck_data, library=lib)
    out_dir = args.output or args.input.parent / "output"
    print(f"Rendering {len(renderer.slides_raw)} slides → {out_dir}", file=sys.stderr)
    paths = renderer.render_all(out_dir, yaml_source_dir=args.input.parent)
    print(f"Done. {len(paths)} SVGs written.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Composer CLI dispatch — `compose`, `list-themes`, `show-theme`,
    `list-symbols`, `render-deck`.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    lib = FrameGraphLibrary(args.lib_path)
    dispatch = {
        "compose": lambda: cmd_compose(args, lib),
        "list-themes": lambda: cmd_list_themes(lib),
        "show-theme": lambda: cmd_show_theme(args, lib),
        "list-symbols": lambda: cmd_list_symbols(lib),
        "render-deck": lambda: cmd_render_deck(args, lib),
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler()


if __name__ == "__main__":
    raise SystemExit(main())
