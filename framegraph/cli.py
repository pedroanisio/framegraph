#!/usr/bin/env python3
"""framegraph CLI — entry point for `framegraph` command after pip install.

Usage
-----
    framegraph render  diagram.yml [-o output.svg] [--strict] [--quiet]
    framegraph deck    deck.yml    [-o output_dir/] [--quiet]
    framegraph version
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def cmd_render(args: argparse.Namespace) -> int:
    """Handle `framegraph render` — render a single document to SVG.

    Args:
        args: Parsed `argparse` namespace. Required: `args.input` (YAML
            path). Optional: `args.output` (SVG path; defaults to
            `<input>.svg`), `args.strict`, `args.quiet`.

    Returns:
        Process exit code: 0 on success, 1 on YAML load or render
        failure (the underlying error is printed to stderr).

    """
    from framegraph import FrameGraphRenderer

    try:
        doc = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR loading {args.input}: {e}", file=sys.stderr)
        return 1
    try:
        renderer = FrameGraphRenderer(doc)
        renderer.yaml_source_dir = str(Path(args.input).parent.resolve())
        svg = renderer.render_svg()
    except Exception as e:
        print(f"ERROR rendering: {e}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else Path(args.input).with_suffix(".svg")
    out.write_text(svg, encoding="utf-8")
    if not args.quiet:
        print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    return 0


def cmd_deck(args: argparse.Namespace) -> int:
    """Handle `framegraph deck` — render a multi-slide deck to per-slide SVGs.

    Args:
        args: Parsed `argparse` namespace. Required: `args.input` (deck
            YAML path). Optional: `args.output` (output directory;
            defaults to `<input_dir>/output`), `args.lib` (path to
            `lib/` token directory; defaults to the package's bundled
            `lib/`), `args.quiet`.

    Returns:
        Process exit code: 0 on success, 1 on YAML load failure.
        Render failures for individual slides are reported via
        `FrameGraphRenderer.warnings` rather than failing the command.

    """
    from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary

    try:
        data = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR loading {args.input}: {e}", file=sys.stderr)
        return 1

    lib_path = Path(args.lib) if args.lib else Path(__file__).parent / "lib"
    lib = FrameGraphLibrary(lib_path)
    deck = FrameGraphDeckRenderer(data, library=lib)
    out_dir = Path(args.output) if args.output else Path(args.input).parent / "output"

    if not args.quiet:
        print(f"Rendering {len(deck.slides_raw)} slide(s) → {out_dir}")
    paths = deck.render_all(out_dir)
    if not args.quiet:
        for p in paths:
            print(f"  wrote {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    """Handle `framegraph version` — print the package version and exit 0."""
    from framegraph import __version__

    print(f"framegraph {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level `framegraph` argparse parser with all subcommands.

    Returns:
        Configured `ArgumentParser`. Subcommands: `render`, `deck`,
        `version`. The returned parser requires a subcommand
        (`required=True`); calling it without one exits with usage.

    """
    p = argparse.ArgumentParser(
        prog="framegraph",
        description="FrameGraph YAML → SVG renderer",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # render
    rp = sub.add_parser("render", help="Render a single FrameGraph document to SVG")
    rp.add_argument("input", help="Input YAML file")
    rp.add_argument("-o", "--output", help="Output SVG path (default: <input>.svg)")
    rp.add_argument("--strict", action="store_true", help="Error on unknown keys")
    rp.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # deck
    dp = sub.add_parser("deck", help="Render a multi-slide deck.yml to per-slide SVGs")
    dp.add_argument("input", help="Input deck YAML file")
    dp.add_argument("-o", "--output", help="Output directory (default: ./output)")
    dp.add_argument("--lib", help="Path to lib/ token directory")
    dp.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # version
    sub.add_parser("version", help="Print version and exit")

    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `framegraph` console script.

    Args:
        argv: Argument vector. When None (default), `argparse` reads
            `sys.argv[1:]`.

    Returns:
        Process exit code from the dispatched subcommand handler.

    """
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {"render": cmd_render, "deck": cmd_deck, "version": cmd_version}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
