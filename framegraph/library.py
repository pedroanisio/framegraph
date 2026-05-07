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
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def strip_meta(d: dict) -> dict:
    """Remove _meta keys — they are library metadata, not FrameGraph fields."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_yaml(data: dict, path: Path | None = None) -> str:
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

    def symbol_ids(self) -> list[str]:
        """Return the sorted ids of every discovered symbol pack."""
        return sorted(self._symbol_packs)

    def load_tokens(self, theme_id: str) -> dict:
        """Return the tokens section of a token pack (stripped of _meta)."""
        path = self._token_packs.get(theme_id)
        if not path:
            raise ValueError(
                f"unknown theme '{theme_id}'.  Available: {', '.join(self.token_ids())}"
            )
        raw = load_yaml(path)
        return strip_meta(raw)  # {colors, fonts, text_styles, stroke_styles, …}

    def load_symbols(self, sym_ref: str) -> dict:
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
        return raw.get("symbols", {})

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
        self.library = library

    def compose(
        self,
        diagram: dict,
        theme_override: str | None = None,
        extra_symbols: list[str] | None = None,
    ) -> dict:
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
            lib_symbols: dict = {}
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
    composer = FrameGraphComposer(lib)
    diagram = load_yaml(args.input)

    extra_syms = args.symbols.split(",") if args.symbols else None
    built = composer.compose(diagram, theme_override=args.theme, extra_symbols=extra_syms)

    output = args.output
    if args.render:
        # Write to a temp YAML, then invoke the renderer
        import tempfile

        tmp = Path(tempfile.mkstemp(suffix=".yml")[1])
        dump_yaml(built, tmp)
        svg_out = output or args.input.with_suffix(".svg")
        renderer = args.renderer or (Path(__file__).parent.parent / "framegraph_to_svg_v3.py")
        rc = subprocess.run(
            [sys.executable, str(renderer), str(tmp), "-o", str(svg_out)], check=False
        ).returncode
        tmp.unlink(missing_ok=True)
        return rc
    if output:
        dump_yaml(built, output)
        print(f"wrote {output}", file=sys.stderr)
    else:
        print(dump_yaml(built), end="")

    return 0


def cmd_list_themes(lib: FrameGraphLibrary) -> int:
    print("\nAvailable themes:")
    for tid in lib.token_ids():
        path = lib._token_packs[tid]
        raw = load_yaml(path)
        name = raw.get("_meta", {}).get("name", tid)
        print(f"  {tid:20s}  {name}")
    print()
    return 0


def cmd_show_theme(args: argparse.Namespace, lib: FrameGraphLibrary) -> int:
    lib.show_theme(args.theme_id)
    return 0


def cmd_list_symbols(lib: FrameGraphLibrary) -> int:
    print("\nAvailable symbol packs:")
    for sid in lib.symbol_ids():
        path = lib._symbol_packs[sid]
        raw = load_yaml(path)
        syms = raw.get("symbols", {})
        print(f"  {sid:40s}  symbols: {', '.join(syms.keys())}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
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
    cp.add_argument("-o", "--output", type=Path, help="Output path (.yml or .svg with --render)")
    cp.add_argument("-t", "--theme", help="Theme id (overrides $theme in file)")
    cp.add_argument("-s", "--symbols", help="Comma-separated extra symbol refs")
    cp.add_argument("--render", action="store_true", help="Pipe to renderer, emit SVG")
    cp.add_argument("--renderer", type=Path, help="Path to framegraph_to_svg_v3.py")

    # list-themes
    sub.add_parser("list-themes", help="List available token packs")

    # show-theme
    sp = sub.add_parser("show-theme", help="Print theme color palette")
    sp.add_argument("theme_id")

    # list-symbols
    sub.add_parser("list-symbols", help="List available symbol packs")

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    lib = FrameGraphLibrary(args.lib_path)

    if args.command == "compose":
        return cmd_compose(args, lib)
    if args.command == "list-themes":
        return cmd_list_themes(lib)
    if args.command == "show-theme":
        return cmd_show_theme(args, lib)
    if args.command == "list-symbols":
        return cmd_list_symbols(lib)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Deck renderer  (v1.2 extension — multi-page)
# ---------------------------------------------------------------------------


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
        deck_yaml: dict,
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

        """
        self.raw = deck_yaml
        self.library = library
        self.deck_config = deck_yaml.get("deck", {}) or {}
        self.slides_raw = deck_yaml.get("slides", []) or []
        self.global_tokens, self.global_symbols, self.global_cdefs = self._build_globals()
        # Index slides by id for $extends resolution
        self._slide_index: dict = {str(s["id"]): s for s in self.slides_raw if s.get("id")}

    def _build_globals(self):
        theme_id = self.raw.get("$theme")
        base_tokens: dict = {}
        if theme_id and self.library:
            base_tokens = self.library.load_tokens(theme_id)
        deck_tokens = deep_merge(base_tokens, self.deck_config.get("tokens") or {})
        deck_symbols = {**(self.deck_config.get("symbols") or {})}
        deck_cdefs = {**(self.deck_config.get("component_defs") or {})}
        return deck_tokens, deck_symbols, deck_cdefs

    def build_slide_doc(self, slide: dict) -> dict:
        """Assemble a complete FrameGraph document for a single slide.

        Merge order (each layer wins over the one above):
          library $theme tokens
            ↓ deck.tokens
              ↓ $extends base slide tokens   ← SP-5a
                ↓ this slide tokens
        """
        canvas = self.deck_config.get("canvas", {"size": [960, 540]})
        slide_num = slide.get("slide", 0)
        slide_id = slide.get("id", f"slide_{slide_num:02d}")

        # ── SP-5a: $extends — inherit from a named base slide ────────────
        extends_id = slide.get("$extends")
        base_slide: dict = {}
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

        # visual block: tokens + symbols + component_defs + whatever the slide declares
        slide_visual = dict(slide.get("visual") or {})
        slide_visual["tokens"] = slide_tokens
        slide_visual["symbols"] = slide_symbols
        if slide_cdefs:
            slide_visual["component_defs"] = slide_cdefs

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

    def collect_notes(self) -> dict:
        """Return a dict mapping slide_id → notes string for all slides with notes.
        Notes are stripped from SVG output but available here for export.
        """
        result = {}
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

    def render_all(self, output_dir: Path) -> list[Path]:
        """Render every slide, return list of output paths."""
        import importlib.util
        import sys as _sys

        # Locate the v3 renderer relative to this file
        renderer_path = Path(__file__).parent / "renderer.py"
        spec = importlib.util.spec_from_file_location("fg_renderer", renderer_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        FGR = mod.FrameGraphRenderer

        output_dir.mkdir(parents=True, exist_ok=True)
        out_paths: list[Path] = []
        for slide in self.slides_raw:
            n = slide.get("slide", 0)
            sid = slide.get("id", f"slide_{n:02d}")
            doc = self.build_slide_doc(slide)
            renderer = FGR(doc)
            svg = renderer.render_svg()
            path = output_dir / f"slide_{n:02d}_{sid}.svg"
            path.write_text(svg, encoding="utf-8")
            kb = path.stat().st_size / 1024
            print(f"  slide {n:02d}  →  {path.name}  ({kb:.1f} KB)", file=_sys.stderr)
            out_paths.append(path)
        # Write speaker notes if any slide declares them
        notes_path = self.render_notes(output_dir)
        if notes_path:
            print(f"  notes   →  {notes_path.name}", file=_sys.stderr)
        return out_paths


def cmd_render_deck(args, lib):
    deck_data = load_yaml(args.input)
    renderer = FrameGraphDeckRenderer(deck_data, library=lib)
    out_dir = args.output or args.input.parent / "output"
    print(f"Rendering {len(renderer.slides_raw)} slides → {out_dir}", file=sys.stderr)
    paths = renderer.render_all(out_dir)
    print(f"Done. {len(paths)} SVGs written.", file=sys.stderr)
    return 0


# Patch build_parser to add render-deck subcommand
_orig_build_parser = build_parser


def build_parser():
    p = _orig_build_parser()
    sub = p._subparsers._group_actions[0]
    rp = sub.add_parser("render-deck", help="Render a multi-page deck YAML into per-slide SVGs")
    rp.add_argument("input", type=Path, help="Deck YAML (.deck.yml)")
    rp.add_argument("-o", "--output", type=Path, help="Output directory (default: ./output)")
    return p


build_parser_original = build_parser  # keep reference


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    lib = FrameGraphLibrary(args.lib_path)
    if args.command == "compose":
        return cmd_compose(args, lib)
    if args.command == "list-themes":
        return cmd_list_themes(lib)
    if args.command == "show-theme":
        return cmd_show_theme(args, lib)
    if args.command == "list-symbols":
        return cmd_list_symbols(lib)
    if args.command == "render-deck":
        return cmd_render_deck(args, lib)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
