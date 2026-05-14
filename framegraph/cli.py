#!/usr/bin/env python3
"""framegraph CLI — entry point for `framegraph` command after pip install.

Usage
-----
    framegraph render   diagram.yml [-o output.svg] [--strict] [--quiet]
                                    [--4k] [--pdf [--vector] [--dpi N]]
    framegraph deck     deck.yml    [-o output_dir/] [--quiet]
                                    [--4k] [--pdf [--vector] [--dpi N]]
    framegraph validate input.yml [--kind auto|framegraph|pattern-sidecar|pattern-catalog]
    framegraph docs     [-o catalog.json]
    framegraph patterns list [--category=generic|consulting|expert]
                             [--has-sidecar] [--json]
    framegraph patterns show <id>
    framegraph patterns example <id> [-o fill.yml] [--format=yaml|json]
    framegraph patterns build <id> --fill content.yml [-o out.svg]
                                   [--canvas-w N] [--canvas-h N]
    framegraph patterns deck [-o output_dir/] [--ids=10,44,91]
                             [--category=consulting] [--pdf [--vector]]
    framegraph sitemap  input.yml --base-url=URL [-o sitemap.xml]
                                  [--target=NAME] [--quiet]
    framegraph version

Agent-oriented quick reference: see `AGENTS.md` at the repo root.

The framework's primary surface is `framegraph deck`, which consumes
deck.yml files where each slide can be a one-liner pattern reference:

    slides:
      - use: 10            # by id (or by slug, e.g. "swot-analysis")
        fill: { … }        # flat {role: content} payload

The deck-level `$theme:` and `stylesheet:` declarations bind every
slide into one coherent visual identity. `patterns build` is the
debug entry point for inspecting one pattern in isolation;
`patterns deck` renders every sidecared pattern's curated example
in one shot — useful for a smoke check or a corpus walk-through.

PDF backends
------------
    --pdf          Raster PDF (default). cairosvg → high-DPI PNG → PDF page.
                   Pixel-perfect; text is NOT selectable; larger files.
                   Robust to any system font configuration.
    --pdf --vector Vector PDF via weasyprint. Selectable / searchable text,
                   smaller files, scalable. Requires the [pdf-vector] extra
                   and a font on the system whose metrics roughly match
                   what framegraph used for layout (Liberation Sans is a
                   good Arial substitute and is typically present on Linux).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from PIL import Image as PILImage


def _detect_validation_kind(data: Any) -> str | None:
    """Infer which schema family a YAML payload most likely belongs to."""
    if not isinstance(data, dict):
        return None
    if data.get("dsl") == "FrameGraph":
        return "framegraph"
    if "slide_template_patterns" in data:
        return "pattern-catalog"
    if "pattern_id" in data and ("zones" in data or "example_fill" in data):
        return "pattern-sidecar"
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle `framegraph validate` — schema-check a YAML file without rendering.

    Auto-detects the project's supported YAML families:

    - FrameGraph documents / decks / framesets (`dsl: FrameGraph`)
    - pattern sidecars (`pattern_id`, `zones`, optional `example_fill`)
    - pattern catalogs (`slide_template_patterns`)

    Returns 0 on success and 1 on parse/validation failure.
    """
    from pydantic import ValidationError

    try:
        data = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR loading {args.input}: {e}", file=sys.stderr)
        return 1

    kind = args.kind
    if kind == "auto":
        kind = _detect_validation_kind(data)
        if kind is None:
            print(
                "ERROR: could not infer YAML kind. Expected one of: "
                "`dsl: FrameGraph`, `slide_template_patterns`, or "
                "`pattern_id` + `zones`/`example_fill`.",
                file=sys.stderr,
            )
            return 1

    try:
        if kind == "framegraph":
            from framegraph._schema import validate_any

            model = validate_any(data)
            label = model.__class__.__name__
        elif kind == "pattern-sidecar":
            from framegraph.patterns.sidecar import load_sidecar

            model = load_sidecar(args.input)
            label = model.__class__.__name__
        elif kind == "pattern-catalog":
            from framegraph._patterns import load_pattern_catalog

            model = load_pattern_catalog(args.input)
            label = model.__class__.__name__
        else:
            print(f"ERROR: unsupported validation kind {kind!r}", file=sys.stderr)
            return 1
    except ValidationError as exc:
        print(f"ERROR: validation failed:\n{exc}", file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, NotImplementedError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR validating: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"VALID: {args.input}  [{kind} → {label}]")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Handle `framegraph render` — render a single document to SVG.

    Phase 3 of ADR 0001: when `args.target` is set, the document is
    coerced to a FrameSet and rendered at that target's canvas
    dimensions via `framegraph._frameset.render_frameset`. When None,
    the legacy single-render path runs unchanged.

    Args:
        args: Parsed `argparse` namespace. Required: `args.input` (YAML
            path). Optional: `args.output` (SVG path; defaults to
            `<input>.svg`), `args.strict`, `args.quiet`, `args.four_k`
            (also write a 3840-wide PNG alongside the SVG),
            `args.target` (Phase 3 — FrameSet target identifier).

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

    # Friendly hint: detect a deck file pointed at the wrong subcommand.
    # Decks have `slides:` (a list) and no top-level `scene:`; standalone
    # documents have `scene:` and no `slides:`. Catching this here gives a
    # clearer error than the schema layer's "scene field required".
    if isinstance(doc, dict) and isinstance(doc.get("slides"), list) and "scene" not in doc:
        print(
            f"ERROR: {args.input} looks like a deck (has top-level 'slides:'), "
            f"not a single diagram document.\n"
            f"       Use:  framegraph deck {args.input} -o <output_dir>",
            file=sys.stderr,
        )
        return 1

    target_name = getattr(args, "target", None)
    link_base_url = getattr(args, "link_base_url", None)
    link_template = getattr(args, "link_template", None)
    if link_base_url is not None and link_template is not None:
        print(
            "ERROR: --link-base-url and --link-template are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    try:
        if target_name is not None or link_base_url is not None or link_template is not None:
            # Phase 3 / Phase 6: FrameSet path. Required when
            # `--target` is set (canvas comes from the target) or
            # when link injection is requested (the Frame is the
            # source of `next`).
            from framegraph._frameset import (
                coerce_to_frameset,
                inject_svg_navigation_links,
                render_frameset,
            )

            fs = coerce_to_frameset(doc)
            rendered = render_frameset(fs, target_name=target_name)
            if not rendered:
                print(
                    f"ERROR: no frames matched target {target_name!r}",
                    file=sys.stderr,
                )
                return 1
            # `render` is a single-document command — emit the first
            # frame's SVG. Multi-frame FrameSets passed to `render`
            # would silently drop everything past the first; for
            # those, `framegraph deck --target` is the right entry.
            svg = rendered[0].svg
            if link_base_url is not None or link_template is not None:
                # Active target name comes from the rendered frame's
                # resolved target (matches what the URL needs).
                active_target = rendered[0].target_name
                svg = inject_svg_navigation_links(
                    svg,
                    fs.frames[0],
                    fs,
                    target_name=active_target,
                    base_url=link_base_url,
                    file_template=link_template,
                )
        else:
            renderer = FrameGraphRenderer(doc)
            renderer.yaml_source_dir = str(Path(args.input).parent.resolve())
            svg = renderer.render_svg()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR rendering: {e}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else Path(args.input).with_suffix(".svg")
    out.write_text(svg, encoding="utf-8")
    if not args.quiet:
        suffix = f" [target={target_name}]" if target_name else ""
        print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB){suffix}")
    if getattr(args, "four_k", False):
        png_out = out.with_suffix(".png")
        try:
            _write_png_4k(svg, png_out)
        except Exception as e:
            print(f"ERROR writing PNG: {e}", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"wrote {png_out}  ({png_out.stat().st_size / 1024:.1f} KB)")
    if getattr(args, "pdf", False):
        pdf_out = out.with_suffix(".pdf")
        vector = getattr(args, "vector", False)
        try:
            _write_pdf(svg, pdf_out, dpi=getattr(args, "dpi", 300), vector=vector)
        except Exception as e:
            print(f"ERROR writing PDF: {e}", file=sys.stderr)
            return 1
        if not args.quiet:
            mode = "vector" if vector else f"raster {getattr(args, 'dpi', 300)} DPI"
            print(f"wrote {pdf_out}  ({pdf_out.stat().st_size / 1024:.1f} KB, {mode})")
    return 0


def _write_png_4k(svg: str, out: Path) -> None:
    """Rasterize an SVG string to a 3840-wide PNG (4K UHD width).

    cairosvg auto-derives the height from the SVG's aspect ratio, so
    the resulting raster is 3840 × (3840 × svg_h / svg_w).

    Raises:
        ImportError: When `cairosvg` is not installed. Surfaced as a
            clear actionable message rather than a stack trace.
    """
    try:
        import cairosvg
    except ImportError as exc:
        raise ImportError(
            "cairosvg is required for --4k PNG output. Install with: pip install cairosvg"
        ) from exc
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(out),
        output_width=3840,
    )


def _svg_canvas_size(svg: str) -> tuple[float, float]:
    """Extract the canvas (width, height) in SVG user units from the root.

    Reads `width="…"` / `height="…"` first, then falls back to the third and
    fourth tokens of the `viewBox`. Returns (960.0, 540.0) when neither is
    parseable — the FrameGraph default — so callers always get usable values.

    Args:
        svg: SVG document as a string.

    Returns:
        A `(width, height)` pair in SVG user units (effectively pixels).
    """
    import re

    m_w = re.search(r'<svg\b[^>]*\bwidth="([0-9.]+)(?:px)?"', svg)
    m_h = re.search(r'<svg\b[^>]*\bheight="([0-9.]+)(?:px)?"', svg)
    if m_w and m_h:
        return float(m_w.group(1)), float(m_h.group(1))
    m_vb = re.search(r'<svg\b[^>]*\bviewBox="([^"]+)"', svg)
    if m_vb:
        parts = m_vb.group(1).split()
        if len(parts) >= 4:
            return float(parts[2]), float(parts[3])
    return 960.0, 540.0


def _svg_to_raster_pdf_page(svg: str, *, dpi: int) -> PILImage.Image:
    """Rasterize an SVG to a Pillow image sized for a `dpi`-DPI PDF page.

    Why rasterize instead of svg2pdf:
        cairosvg's vector PDF path runs cairo's text shaper (pango +
        harfbuzz) on the system fonts, which often disagree with framegraph's
        font-agnostic per-character width tables used during SVG layout.
        That mismatch shows up as broken kerning / spread-out characters
        when the system lacks the requested font (e.g. Arial → Liberation
        Sans substitute). Rasterizing locks framegraph's layout into pixels
        before the PDF wraps it, eliminating the whole class of issue.

    Page sizing:
        SVG user units are treated as CSS pixels at 96 DPI. The PNG is
        rendered at `dpi` so 1 SVG unit becomes `dpi/96` raster pixels.
        The Pillow image's own DPI metadata is set to `dpi` so the PDF page
        is sized at exactly the SVG's intended physical dimensions
        (svg_w/96 × svg_h/96 inches).

    Args:
        svg: SVG document as a string.
        dpi: Target rasterization DPI. 300 is print-grade; 150 is screen-grade.

    Returns:
        A Pillow `Image` (RGB, with `info["dpi"] = (dpi, dpi)`) ready for
        `Image.save(format="PDF")`.

    Raises:
        ImportError: When `cairosvg` or `Pillow` is not installed.
    """
    try:
        import cairosvg
    except ImportError as exc:
        raise ImportError(
            "cairosvg is required for --pdf output. Install with: pip install cairosvg"
        ) from exc
    try:
        from PIL import Image as PILImage
    except ImportError as exc:
        raise ImportError(
            "Pillow is required for --pdf output. Install with: pip install Pillow"
        ) from exc

    svg_w, svg_h = _svg_canvas_size(svg)
    # CSS pixels are 96 DPI by convention; scale up by dpi/96 for the raster.
    output_width = max(1, int(round(svg_w * dpi / 96.0)))

    import io

    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=output_width,
    )
    img = PILImage.open(io.BytesIO(png_bytes))
    # Pillow's PDF writer sizes pages from img.info["dpi"]; without this it
    # defaults to 72 DPI and the page comes out oversized.
    img.info["dpi"] = (float(dpi), float(dpi))
    # PDF pages with alpha sometimes render unpredictably across viewers.
    # Flatten onto white to match the deck's slide background.
    if img.mode in ("RGBA", "LA"):
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        bg.info["dpi"] = (float(dpi), float(dpi))
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def _prepare_svg_for_vector_pdf(svg: str) -> str:
    """Prefix `Liberation Sans` to any `Arial`-fronted font-family stack.

    framegraph's SVG output declares `font-family="Arial, Helvetica, sans-serif"`
    on every text run. On systems without Arial (most Linux distros), cairo /
    pango falls back via metric guess — usually finding Liberation Sans, but
    not always; the indirection occasionally produces unstable shaping.
    Naming Liberation Sans first removes that ambiguity. People with Arial
    installed are unaffected (their `font-family` stack still honors Arial
    via the explicit fallback chain we leave in place).

    Args:
        svg: SVG document string emitted by FrameGraph.

    Returns:
        SVG string with the font-family stack adjusted. Idempotent — calling
        it on already-adjusted input is a no-op.
    """
    import re

    return re.sub(
        r'font-family="Arial, Helvetica, sans-serif"',
        'font-family="Liberation Sans, Arial, Helvetica, sans-serif"',
        svg,
    )


def _svg_to_vector_pdf_bytes(svg: str) -> bytes:
    """Convert an SVG string to a single-page vector PDF via weasyprint.

    weasyprint preserves text as text runs in the PDF (rather than the
    per-glyph positioning emitted by cairosvg's PDF backend), so output
    is selectable / searchable / extractable cleanly with `pdftotext`.

    Page sizing: the SVG canvas size is read from `width`/`height` /
    `viewBox` and used as an `@page size` in CSS pixels. weasyprint maps
    1 CSS px → 1/96 inch — same convention as the raster path — so a
    960×540 SVG produces a 10in × 5.625in page.

    Args:
        svg: SVG document string.

    Returns:
        PDF document as bytes (single page).

    Raises:
        ImportError: When `weasyprint` is not installed.
    """
    try:
        import weasyprint
    except ImportError as exc:
        raise ImportError(
            "weasyprint is required for --pdf --vector output. "
            'Install with: pip install "framegraph[pdf-vector]"'
        ) from exc
    svg_w, svg_h = _svg_canvas_size(svg)
    svg_adjusted = _prepare_svg_for_vector_pdf(svg)
    # weasyprint takes HTML; embedding the SVG in a zero-margin page sized
    # exactly to the SVG canvas reproduces the layout faithfully.
    html = (
        "<html><head><style>"
        f"@page {{ size: {svg_w}px {svg_h}px; margin: 0; }}"
        " html, body { margin: 0; padding: 0; }"
        f" svg {{ width: {svg_w}px; height: {svg_h}px; display: block; }}"
        "</style></head><body>"
        f"{svg_adjusted}"
        "</body></html>"
    )
    pdf_bytes: bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf_bytes


def _write_pdf(svg: str, out: Path, *, dpi: int = 300, vector: bool = False) -> None:
    """Convert an SVG string to a single-page PDF.

    Two backends:
        - `vector=False` (default): rasterize via `_svg_to_raster_pdf_page`
          at `dpi`. Pixel-perfect match to the SVG; text not selectable;
          robust to any font configuration.
        - `vector=True`: vector PDF via weasyprint. Selectable text;
          requires weasyprint installed and a sensible system font for
          framegraph's `Arial`-first font stack (Liberation Sans on Linux
          is good).

    Args:
        svg: SVG document as a string.
        out: Destination `.pdf` path.
        dpi: Rasterization resolution (raster backend only). Default 300.
        vector: When True, use the weasyprint vector backend. The `dpi`
            argument is ignored in this mode (vector output is resolution-
            independent).

    Raises:
        ImportError: When the backend's required package is missing.
    """
    if vector:
        out.write_bytes(_svg_to_vector_pdf_bytes(svg))
        return
    page = _svg_to_raster_pdf_page(svg, dpi=dpi)
    page.save(str(out), format="PDF", resolution=float(dpi))


def _write_deck_pdf(
    svg_paths: list[Path], out: Path, *, dpi: int = 300, vector: bool = False
) -> bool:
    """Convert a list of slide SVGs into a single multi-page PDF.

    Two backends, mirroring `_write_pdf`:
        - Raster (default): each SVG is rasterized at `dpi` and Pillow's
          native multi-page PDF writer concatenates the images. No extra
          dependency beyond Pillow.
        - Vector (`vector=True`): each SVG is rendered to a vector PDF
          via weasyprint and the per-slide PDFs are merged with `pypdf`.
          Selectable text across the whole deck. Requires weasyprint and
          pypdf (both pulled in by the `[pdf-vector]` extra).

    Args:
        svg_paths: Per-slide SVG paths in slide order.
        out: Destination merged `.pdf` path.
        dpi: Rasterization resolution (raster backend only). Default 300.
        vector: When True, use the weasyprint vector backend.

    Returns:
        Always True.

    Raises:
        ImportError: When the backend's required packages are missing.
        ValueError: When `svg_paths` is empty.
    """
    if not svg_paths:
        raise ValueError("_write_deck_pdf called with no slide paths")

    if vector:
        try:
            from pypdf import PdfWriter
        except ImportError as exc:
            raise ImportError(
                "pypdf is required for --pdf --vector deck output. "
                'Install with: pip install "framegraph[pdf-vector]"'
            ) from exc
        import io

        writer = PdfWriter()
        for svg_path in svg_paths:
            pdf_bytes = _svg_to_vector_pdf_bytes(svg_path.read_text(encoding="utf-8"))
            writer.append(io.BytesIO(pdf_bytes))
        with out.open("wb") as fh:
            writer.write(fh)
        return True

    # Raster path
    pages = [_svg_to_raster_pdf_page(p.read_text(encoding="utf-8"), dpi=dpi) for p in svg_paths]
    first, rest = pages[0], pages[1:]
    first.save(
        str(out),
        format="PDF",
        save_all=True,
        append_images=rest,
        resolution=float(dpi),
    )
    return True


def cmd_deck(args: argparse.Namespace) -> int:
    """Handle `framegraph deck` — render a multi-slide deck to per-slide SVGs.

    Phase 3 of ADR 0001: when `args.target` is given, every slide
    renders at the FrameSet target's canvas (looked up via
    `framegraph.library._resolve_frame_target_canvas`). When
    `args.all_targets` is given, the command loops over every
    target the FrameSet declares and writes per-target subdirectories
    (e.g. `<out>/landscape/slide_*.svg`, `<out>/portrait/slide_*.svg`).
    When neither flag is given, the legacy single-target path runs
    unchanged.

    Args:
        args: Parsed `argparse` namespace. Required: `args.input` (deck
            YAML path). Optional: `args.output` (output directory;
            defaults to `<input_dir>/output`), `args.lib` (path to
            `lib/` token directory; defaults to the package's bundled
            `lib/`), `args.quiet`, `args.target`, `args.all_targets`.

    Returns:
        Process exit code: 0 on success, 1 on YAML load or
        target-not-found failure.

    """
    from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary
    from framegraph.library import list_frameset_targets

    try:
        data = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR loading {args.input}: {e}", file=sys.stderr)
        return 1

    lib_path = Path(args.lib) if args.lib else Path(__file__).parent / "lib"
    lib = FrameGraphLibrary(lib_path)
    deck = FrameGraphDeckRenderer(data, library=lib)
    out_dir = Path(args.output) if args.output else Path(args.input).parent / "output"

    target_name = getattr(args, "target", None)
    all_targets = getattr(args, "all_targets", False)
    if target_name is not None and all_targets:
        print(
            "ERROR: --target and --all-targets are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    link_base_url = getattr(args, "link_base_url", None)
    link_template = getattr(args, "link_template", None)
    if link_base_url is not None and link_template is not None:
        print(
            "ERROR: --link-base-url and --link-template are mutually exclusive",
            file=sys.stderr,
        )
        return 1

    # Phase 3 multi-target loop. When `--all-targets` is set, render
    # the deck once per declared target into a per-target subdir.
    if all_targets:
        targets = list_frameset_targets(data)
        if not targets:
            print(
                f"ERROR: --all-targets requires the input to declare at least one "
                f"target; {args.input} declares none. Use a `kind: frameset` "
                f"document with `frameset.defaults.targets:` or per-Frame "
                f"`targets:`.",
                file=sys.stderr,
            )
            return 1
        all_paths: list[Path] = []
        for tname in targets:
            sub_out = out_dir / tname
            if not args.quiet:
                print(f"Rendering {len(deck.slides_raw)} slide(s) → {sub_out}  [target={tname}]")
            try:
                tpaths = deck.render_all(
                    sub_out,
                    yaml_source_dir=Path(args.input).parent,
                    target_name=tname,
                )
            except KeyError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
            all_paths.extend(tpaths)
        paths = all_paths
    else:
        if not args.quiet:
            suffix = f"  [target={target_name}]" if target_name else ""
            print(f"Rendering {len(deck.slides_raw)} slide(s) → {out_dir}{suffix}")
        try:
            paths = deck.render_all(
                out_dir,
                yaml_source_dir=Path(args.input).parent,
                target_name=target_name,
            )
        except KeyError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    # Phase 6 — link injection. Wrap each per-slide SVG body in
    # `<a href="next-url">` for click-to-advance navigation. The
    # frame.next chain was materialised at coercion time so every
    # slide except the last has a `next`; the last one is left
    # un-wrapped.
    if link_base_url is not None or link_template is not None:
        from framegraph._frameset import (
            coerce_to_frameset,
            inject_svg_navigation_links,
        )

        try:
            fs = coerce_to_frameset(data)
        except Exception as e:
            print(f"ERROR validating FrameSet for link injection: {e}", file=sys.stderr)
            return 1
        # Map frame_id → Frame for O(1) lookup. Each path's stem
        # encodes the slide id (deck renderer convention:
        # `slide_<index>_<id>.svg` or similar). The simplest
        # mapping is by ordinal: frames[i] ↔ paths[i] within a
        # single-target render. For --all-targets the loop ran
        # once per target, so paths length is len(frames) * len(targets);
        # we re-iterate over (target, frame) in the same order
        # `render_all` produced.
        targets_for_iteration: list[str]
        if all_targets:
            from framegraph.library import list_frameset_targets

            targets_for_iteration = list(list_frameset_targets(data))
        else:
            targets_for_iteration = [target_name if target_name is not None else "default"]
        i = 0
        for active_target in targets_for_iteration:
            for frame in fs.frames:
                if i >= len(paths):
                    break
                path = paths[i]
                try:
                    svg_text = path.read_text(encoding="utf-8")
                    new_svg = inject_svg_navigation_links(
                        svg_text,
                        frame,
                        fs,
                        target_name=active_target,
                        base_url=link_base_url,
                        file_template=link_template,
                    )
                    if new_svg != svg_text:
                        path.write_text(new_svg, encoding="utf-8")
                except ValueError as e:
                    print(f"ERROR injecting links for {path.name}: {e}", file=sys.stderr)
                    return 1
                i += 1

    if not args.quiet:
        for p in paths:
            print(f"  wrote {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    if getattr(args, "four_k", False):
        for p in paths:
            png_out = p.with_suffix(".png")
            try:
                _write_png_4k(p.read_text(encoding="utf-8"), png_out)
            except Exception as e:
                print(f"ERROR writing PNG for {p.name}: {e}", file=sys.stderr)
                return 1
            if not args.quiet:
                print(f"  wrote {png_out.name}  ({png_out.stat().st_size / 1024:.1f} KB)")
    if getattr(args, "pdf", False):
        dpi = getattr(args, "dpi", 300)
        vector = getattr(args, "vector", False)
        deck_pdf = out_dir / f"{Path(args.input).stem}.pdf"
        try:
            _write_deck_pdf(paths, deck_pdf, dpi=dpi, vector=vector)
        except Exception as e:
            print(f"ERROR writing PDF: {e}", file=sys.stderr)
            return 1
        if not args.quiet:
            mode = "vector, selectable text" if vector else f"raster, {dpi} DPI"
            print(
                f"  wrote {deck_pdf.name}  "
                f"({deck_pdf.stat().st_size / 1024:.1f} KB, "
                f"{len(paths)} pages, {mode})"
            )

    # ── Layout report ──
    # The planner is the single decision-maker for geometry + uniform
    # typography scale. Render is faithful and reports nothing. For
    # each templated slide the planner emits one LayoutReport with:
    #   - scale:     uniform typography scale applied (1.0 = nominal)
    #   - shrunk:    whether the planner had to drop below 1.0
    #   - fits:      whether all zones fit at the applied scale
    #   - overflows: per-zone (role, required_h, available_h) facts
    #
    # Operator reads this to edit content, swap pattern, or accept
    # overflow. Exit code stays 0 — the deck rendered honestly.
    reports = list(getattr(deck, "constraint_reports", []) or [])
    interesting = [r for r in reports if r.get("shrunk") or not r.get("fits", True)]
    if interesting and not args.quiet:
        print()
        print(
            f"⚠  layout report — {len(interesting)} slide(s) "
            f"required typography shrink and/or overflow:"
        )
        for v in interesting:
            slide_num = v.get("slide_num")
            slide_id = v.get("slide_id", "")
            slide_title = v.get("slide_title", "")
            scale = v.get("scale", 1.0)
            fits = v.get("fits", True)
            overflows = v.get("overflows") or []
            tag = "OK" if fits else "OVERFLOW"
            print(f"   slide {slide_num:>2}  {slide_id:<28}  scale={scale:>4}  {tag}")
            if slide_title:
                print(f"        title: {slide_title}")
            for ov in overflows:
                print(
                    f"        zone {ov.get('role', ''):<28}  "
                    f"needs {ov.get('required_h', '?')}px / "
                    f"has {ov.get('available_h', '?')}px"
                )
        # One-line guidance for the operator.
        print()
        print(
            "   Render is faithful — every word the author wrote is drawn. "
            "Edit content, widen canvas, or pick a different pattern."
        )
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    """Handle `framegraph docs` — emit the machine-readable API catalog.

    Walks every name in `__all__` of every public module and emits a
    JSON document an LLM agent can ingest to learn the framegraph
    public API in one read. Includes docstrings, signatures, and
    Pydantic JSON Schemas.

    Args:
        args: Parsed namespace. Optional: ``args.output`` (path; if
            absent, writes to stdout), ``args.quiet`` (suppress the
            "wrote …" line).

    Returns:
        Process exit code 0 on success.
    """
    from framegraph.docs import build_catalog, render_catalog_json

    text = render_catalog_json(build_catalog())
    if args.output:
        out = Path(args.output)
        out.write_text(text, encoding="utf-8")
        if not args.quiet:
            print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")
    return 0


def _find_sidecar(pattern_id: int) -> Path | None:
    """Locate a sidecar YAML for the given pattern id.

    Returns the first match in `framegraph/data/fills/<id_zero_padded>-*.yml`
    (the package-shipped catalog), or None when no sidecar exists.
    Pattern fills work without a sidecar via the content_type-derived
    defaults.
    """
    fills_dir = Path(__file__).resolve().parent / "data" / "fills"
    if not fills_dir.exists():
        return None
    matches = sorted(fills_dir.glob(f"{pattern_id:03d}-*.yml"))
    return matches[0] if matches else None


def _sidecar_slug(sidecar_path: Path) -> str:
    """Extract the catalog slug from a sidecar filename.

    `framegraph/data/fills/010-swot-analysis.yml` → `"swot-analysis"`. Used
    by `patterns deck` to name per-pattern outputs predictably.
    """
    return sidecar_path.stem.split("-", 1)[1] if "-" in sidecar_path.stem else sidecar_path.stem


def _build_pattern_svg(
    pattern_id: int,
    fill_payload: dict[str, Any],
    *,
    canvas_w: float = 1920.0,
    canvas_h: float = 1080.0,
) -> str:
    """Validate `fill_payload` against the pattern's effective schema and render to SVG.

    Used by both `patterns build` (single pattern) and `patterns deck`
    (every sidecared pattern). Raises `KeyError` when the pattern id
    is not in the catalog, `pydantic.ValidationError` when the fill
    fails the effective schema, and `Exception` from the render core
    otherwise — callers translate these into CLI exit codes.
    """
    from framegraph._patterns import load_pattern_catalog
    from framegraph.patterns import (
        compute_boxes,
        derive_default_fill_schema,
        derive_fill_schema_with_sidecar,
        load_sidecar,
        render_pattern_svg,
    )

    catalog = load_pattern_catalog()
    pattern = catalog.get(pattern_id)
    sidecar_path = _find_sidecar(pattern.id)
    if sidecar_path is not None:
        sidecar = load_sidecar(sidecar_path)
        Model = derive_fill_schema_with_sidecar(pattern, sidecar)
    else:
        Model = derive_default_fill_schema(pattern)
    fill = Model.model_validate(fill_payload)
    layout = compute_boxes(pattern, canvas_w, canvas_h)
    return render_pattern_svg(pattern, fill, layout, canvas_w, canvas_h)


def cmd_patterns_list(args: argparse.Namespace) -> int:
    """Handle `framegraph patterns list` — enumerate catalog patterns.

    Args:
        args: Parsed namespace. Optional: ``args.category`` filters
            to one of generic / consulting / expert; ``args.has_sidecar``
            restricts to patterns shipping a sidecar; ``args.as_json``
            switches to JSON output (one record per pattern, suitable
            for agent consumption).

    Returns:
        Process exit code 0 on success.
    """
    import json

    from framegraph._patterns import load_pattern_catalog

    catalog = load_pattern_catalog()
    rows = catalog.slide_template_patterns
    if args.category:
        rows = [p for p in rows if p.category == args.category]

    sidecar_for = {p.id: _find_sidecar(p.id) for p in rows}
    if getattr(args, "has_sidecar", False):
        rows = [p for p in rows if sidecar_for[p.id] is not None]

    if not rows:
        if getattr(args, "as_json", False):
            print("[]")
        return 0

    if getattr(args, "as_json", False):
        records = []
        for p in rows:
            sc_path = sidecar_for[p.id]
            records.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "zones": len(p.zones),
                    "sidecar": sc_path.name if sc_path is not None else None,
                }
            )
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    print(f"# {'id':>4}  {'category':<11}  {'zones':>5}  {'sidecar':<8}  name")
    for p in rows:
        sc = "yes" if sidecar_for[p.id] else "—"
        print(f"  {p.id:>4}  {p.category:<11}  {len(p.zones):>5}  {sc:<8}  {p.name}")
    return 0


def cmd_patterns_show(args: argparse.Namespace) -> int:
    """Handle `framegraph patterns show <id>` — print one pattern.

    Args:
        args: Parsed namespace. Required: ``args.pattern_id``.

    Returns:
        Process exit code 0 on success, 1 on unknown id.
    """
    from framegraph._patterns import load_pattern_catalog

    catalog = load_pattern_catalog()
    try:
        p = catalog.get(args.pattern_id)
    except KeyError:
        print(
            f"ERROR: pattern id {args.pattern_id} not found in catalog "
            f"(valid range: 1..{len(catalog.slide_template_patterns)})",
            file=sys.stderr,
        )
        return 1

    print(f"id:          {p.id}")
    print(f"name:        {p.name}")
    print(f"category:    {p.category}")
    if p.use_case:
        print(f"use_case:    {p.use_case}")
    print(f"layout:      {p.layout_disposition}")
    print(f"zones:       {len(p.zones)}")
    sidecar_path = _find_sidecar(p.id)
    if sidecar_path:
        print(f"sidecar:     {sidecar_path.name}")

    print()
    print("Zones (role: content_type, size, placement):")
    for z in p.zones:
        place_repr: str
        from framegraph._patterns import Anchor, RegionPlacement

        if isinstance(z.placement, Anchor):
            if z.placement.fullbleed:
                place_repr = "fullbleed"
            else:
                place_repr = f"anchor[{z.placement.h},{z.placement.v}]"
        elif isinstance(z.placement, RegionPlacement):
            place_repr = f"region[{z.placement.region}]"
        else:
            place_repr = f"relative[{z.placement.relation}→{z.placement.target}]"
        ct = z.content_type or "(unannotated)"
        shape_part = f" shape={z.shape}" if z.shape else ""
        print(f"  - {z.role:30s}  {ct:<12} {z.size:<10} {place_repr}{shape_part}")
    return 0


def cmd_patterns_example(args: argparse.Namespace) -> int:
    """Handle `framegraph patterns example <id>` — emit example fill.

    Reads the sidecar at ``framegraph/data/fills/<id>-*.yml`` and writes
    its ``example_fill`` payload as a flat ``{role: content}`` mapping
    — exactly the shape `patterns build --fill` expects. This closes
    the agent loop: discover → introspect → fetch example → render,
    all via the CLI without reading sidecar internals.

    Args:
        args: Parsed namespace. Required: ``args.pattern_id``.
            Optional: ``args.output`` (default: stdout),
            ``args.format`` (yaml | json, default: yaml).

    Returns:
        Process exit code 0 on success, 1 if no sidecar exists for
        the pattern or the sidecar has no ``example_fill``.
    """
    import json

    from framegraph._patterns import load_pattern_catalog
    from framegraph.patterns import load_sidecar

    catalog = load_pattern_catalog()
    try:
        pattern = catalog.get(args.pattern_id)
    except KeyError:
        print(
            f"ERROR: pattern id {args.pattern_id} not found in catalog",
            file=sys.stderr,
        )
        return 1

    sidecar_path = _find_sidecar(pattern.id)
    if sidecar_path is None:
        print(
            f"ERROR: pattern {pattern.id} has no sidecar in framegraph/data/fills/. "
            f"Without a sidecar there is no curated example_fill to emit. "
            f"Construct a fill payload from `patterns show {pattern.id}` "
            f"and the default content_type shapes documented in "
            f"docs/AUTHORING-FILLS.md.",
            file=sys.stderr,
        )
        return 1

    sidecar = load_sidecar(sidecar_path)
    if not sidecar.example_fill:
        print(
            f"ERROR: sidecar {sidecar_path.name} has no example_fill. "
            f"Add one or render with a hand-authored fill payload.",
            file=sys.stderr,
        )
        return 1

    fmt = getattr(args, "format", "yaml")
    if fmt == "json":
        rendered = json.dumps(sidecar.example_fill, indent=2, ensure_ascii=False)
    else:
        rendered = yaml.safe_dump(sidecar.example_fill, sort_keys=False, allow_unicode=True)

    if args.output:
        out = Path(args.output)
        out.write_text(rendered, encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB, source: {sidecar_path.name})")
    else:
        sys.stdout.write(rendered)
        if fmt == "json":
            sys.stdout.write("\n")
    return 0


def cmd_patterns_build(args: argparse.Namespace) -> int:
    """Handle `framegraph patterns build <id> --fill content.yml [-o out.svg]`.

    Renders a pattern + fill payload to SVG. Looks up a sidecar at
    ``framegraph/data/fills/<id>-*.yml`` if one exists; falls back to
    content_type-derived defaults otherwise.

    Args:
        args: Parsed namespace. Required: ``args.pattern_id``,
            ``args.fill``. Optional: ``args.output`` (default: stdout),
            ``args.canvas_w`` (default 1920), ``args.canvas_h``
            (default 1080), ``args.quiet``.

    Returns:
        Process exit code 0 on success, 1 on validation/render failure.
    """
    from pydantic import ValidationError

    fill_path = Path(args.fill)
    if not fill_path.exists():
        print(f"ERROR: fill file not found: {fill_path}", file=sys.stderr)
        return 1
    try:
        payload = yaml.safe_load(fill_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"ERROR: could not parse fill YAML: {exc}", file=sys.stderr)
        return 1

    canvas_w = float(args.canvas_w)
    canvas_h = float(args.canvas_h)
    try:
        svg = _build_pattern_svg(args.pattern_id, payload, canvas_w=canvas_w, canvas_h=canvas_h)
    except KeyError:
        print(
            f"ERROR: pattern id {args.pattern_id} not found in catalog",
            file=sys.stderr,
        )
        return 1
    except ValidationError as exc:
        print(f"ERROR: fill validation failed:\n{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: render failed: {exc}", file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output)
        out.write_text(svg, encoding="utf-8")
        if not args.quiet:
            print(
                f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)",
                file=sys.stderr,
            )
    else:
        sys.stdout.write(svg)
        if not svg.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def cmd_patterns_deck(args: argparse.Namespace) -> int:
    """Handle `framegraph patterns deck` — render every sidecared pattern's example to SVG.

    For each pattern that ships a sidecar with an ``example_fill``,
    validate that fill against the pattern's effective schema and
    render to SVG. Per-pattern fill payloads are also persisted so
    an agent can audit / fork them. With ``--pdf``, the SVGs are
    assembled into a single multi-page PDF.

    Output layout in ``args.output`` (default ``./patterns-deck``)::

        patterns-deck/
          svgs/<pid_padded>-<slug>.svg
          fills/<pid_padded>-<slug>.fill.yml
          patterns-deck.pdf      # only when --pdf is passed

    Args:
        args: Parsed namespace. Optional: ``args.output`` (output
            directory; default ``./patterns-deck``), ``args.category``
            (filter to one of generic / consulting / expert),
            ``args.ids`` (comma-separated id allow-list),
            ``args.canvas_w`` / ``args.canvas_h`` (canvas size in
            pixels; default 1920 × 1080), ``args.pdf`` (also write
            multi-page PDF), ``args.vector`` (use weasyprint vector
            backend), ``args.dpi`` (raster DPI when ``--pdf``
            without ``--vector``; default 300), ``args.quiet``.

    Returns:
        Process exit code 0 on success, 1 if no patterns match the
        filters or if any pattern fails to validate / render.
    """
    from pydantic import ValidationError

    from framegraph._patterns import load_pattern_catalog
    from framegraph.patterns import load_sidecar

    catalog = load_pattern_catalog()
    rows = catalog.slide_template_patterns
    if args.category:
        rows = [p for p in rows if p.category == args.category]

    id_filter: set[int] | None = None
    if args.ids:
        try:
            id_filter = {int(s.strip()) for s in args.ids.split(",") if s.strip()}
        except ValueError:
            print(
                f"ERROR: --ids expects a comma-separated list of integers, got {args.ids!r}",
                file=sys.stderr,
            )
            return 1
        rows = [p for p in rows if p.id in id_filter]

    # Restrict to patterns that ship a sidecar with example_fill — that's
    # the contract of this command. Filling a non-sidecared pattern
    # belongs to `patterns build` with a hand-authored fill.
    sidecared: list[tuple[Any, Path]] = [
        (p, sp) for p in rows if (sp := _find_sidecar(p.id)) is not None
    ]
    if not sidecared:
        print(
            "ERROR: no sidecared patterns matched the filter. "
            "Run `framegraph patterns list --has-sidecar` to see what's available.",
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.output) if args.output else Path("patterns-deck")
    svgs_dir = out_dir / "svgs"
    fills_dir = out_dir / "fills"
    svgs_dir.mkdir(parents=True, exist_ok=True)
    fills_dir.mkdir(parents=True, exist_ok=True)

    canvas_w = float(args.canvas_w)
    canvas_h = float(args.canvas_h)

    if not args.quiet:
        print(f"Rendering {len(sidecared)} pattern(s) → {out_dir}", file=sys.stderr)

    svg_paths: list[Path] = []
    for pattern, sidecar_path in sidecared:
        slug = _sidecar_slug(sidecar_path)
        sidecar = load_sidecar(sidecar_path)
        if not sidecar.example_fill:
            print(
                f"  skip pattern {pattern.id:>4} ({pattern.name}): "
                f"sidecar {sidecar_path.name} has no example_fill",
                file=sys.stderr,
            )
            continue

        # Persist the flat fill payload for audit / forking.
        fill_out = fills_dir / f"{pattern.id:03d}-{slug}.fill.yml"
        fill_out.write_text(
            yaml.safe_dump(sidecar.example_fill, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        try:
            svg = _build_pattern_svg(
                pattern.id,
                dict(sidecar.example_fill),
                canvas_w=canvas_w,
                canvas_h=canvas_h,
            )
        except ValidationError as exc:
            print(
                f"ERROR: pattern {pattern.id} ({pattern.name}) example fill "
                f"failed validation:\n{exc}",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            print(
                f"ERROR: pattern {pattern.id} ({pattern.name}) render failed: {exc}",
                file=sys.stderr,
            )
            return 1

        svg_path = svgs_dir / f"{pattern.id:03d}-{slug}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        svg_paths.append(svg_path)
        if not args.quiet:
            print(
                f"  ✓ pattern {pattern.id:>4}  {pattern.name}  → {svg_path.name}",
                file=sys.stderr,
            )

    if not svg_paths:
        print(
            "ERROR: no patterns were rendered (every match had an empty example_fill).",
            file=sys.stderr,
        )
        return 1

    if getattr(args, "pdf", False):
        pdf_out = out_dir / "patterns-deck.pdf"
        try:
            _write_deck_pdf(
                svg_paths,
                pdf_out,
                dpi=getattr(args, "dpi", 300),
                vector=getattr(args, "vector", False),
            )
        except Exception as exc:
            print(f"ERROR: writing PDF failed: {exc}", file=sys.stderr)
            return 1
        if not args.quiet:
            mode = "vector" if getattr(args, "vector", False) else f"raster {args.dpi} DPI"
            print(
                f"wrote {pdf_out}  "
                f"({pdf_out.stat().st_size / 1024:.1f} KB, "
                f"{len(svg_paths)} pages, {mode})",
                file=sys.stderr,
            )

    return 0


def cmd_sitemap(args: argparse.Namespace) -> int:
    """Handle `framegraph sitemap` — emit `sitemap.xml` from a FrameSet.

    Phase 4 of ADR 0001. Loads any FrameGraph YAML (frameset, deck, or
    legacy single-document), coerces to a `FrameSetDocument`, and walks
    the (Frame × declared target) product to emit one `<url>` entry
    per pair. URL pattern: ``<base_url>/<target>/<frame_id>``.

    Args:
        args: Parsed `argparse` namespace. Required: `args.input`
            (YAML path), `args.base_url` (site root). Optional:
            `args.output` (default: stdout), `args.target` (filter to
            one target name), `args.quiet`.

    Returns:
        Process exit code: 0 on success, 1 on YAML load, validation,
        or emission failure.
    """
    from framegraph._frameset import coerce_to_frameset, emit_sitemap

    try:
        doc = yaml.safe_load(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR loading {args.input}: {e}", file=sys.stderr)
        return 1

    try:
        fs = coerce_to_frameset(doc)
    except Exception as e:
        print(f"ERROR validating FrameSet: {e}", file=sys.stderr)
        return 1

    target_filter = [args.target] if args.target else None
    try:
        xml = emit_sitemap(fs, args.base_url, target_filter=target_filter)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.output:
        out = Path(args.output)
        out.write_text(xml, encoding="utf-8")
        if not args.quiet:
            url_count = xml.count("<loc>")
            print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB, {url_count} URLs)")
    else:
        sys.stdout.write(xml)
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    """Handle `framegraph version` — print the package version and exit 0."""
    from framegraph import __version__

    print(f"framegraph {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level `framegraph` argparse parser with all subcommands.

    Returns:
        Configured `ArgumentParser`. Top-level subcommands: `render`,
        `deck`, `validate`, `docs`, `sitemap`, `version`, `patterns`
        (with nested `list`, `show`, `example`, `build`, `deck`).
        The returned parser requires a subcommand (`required=True`);
        calling it without one exits with usage. The authoritative list
        is the dispatch table at the bottom of `main()` — keep this
        docstring in sync with it (regression-guarded by
        `tests/integration/test_cli_subcommands.py`).

    """
    p = argparse.ArgumentParser(
        prog="framegraph",
        description=(
            "FrameGraph — YAML-first presentation and diagram generator. "
            "Render single documents (`render`), multi-slide decks (`deck`), "
            "or curated slide-pattern examples (`patterns`). Run "
            "`framegraph docs -o catalog.json` for a machine-readable API "
            "catalog (LLM-agent-friendly). See AGENTS.md at the repo root "
            "for end-to-end agent workflows."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # render
    rp = sub.add_parser("render", help="Render a single FrameGraph document to SVG")
    rp.add_argument("input", help="Input YAML file")
    rp.add_argument("-o", "--output", help="Output SVG path (default: <input>.svg)")
    rp.add_argument("--strict", action="store_true", help="Error on unknown keys")
    rp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    rp.add_argument(
        "--4k",
        dest="four_k",
        action="store_true",
        help="Also write a 3840-wide PNG alongside the SVG (requires cairosvg)",
    )
    rp.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "Also write a single-page PDF alongside the SVG. "
            "Default backend rasterizes at --dpi (requires Pillow + cairosvg, "
            "available via the [pdf] extra). Pair with --vector for "
            "selectable text via weasyprint."
        ),
    )
    rp.add_argument(
        "--vector",
        action="store_true",
        help=(
            "Use the weasyprint vector backend for --pdf output: selectable / "
            "searchable text, smaller files, no DPI needed. Requires the "
            '[pdf-vector] extra: pip install "framegraph[pdf-vector]"'
        ),
    )
    rp.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Rasterization DPI for --pdf output (default: 300; ignored with --vector)",
    )
    rp.add_argument(
        "--target",
        default=None,
        help=(
            "Phase 3 of ADR 0001 — render at the named FrameSet target's "
            "canvas dimensions (one of `landscape`, `portrait`, `mobile`, "
            "or whatever the document declares). When omitted, the source "
            "document's canvas is used. Coerces the document to a FrameSet "
            "internally; works with both legacy and `kind: frameset` YAML."
        ),
    )
    rp.add_argument(
        "--link-base-url",
        dest="link_base_url",
        default=None,
        help=(
            "Phase 6 of ADR 0001 — wrap the rendered SVG body in an "
            "<a href> pointing at the Frame's `next` link. URL pattern: "
            "<link-base-url>/<target>/<frame_id> (matches `framegraph "
            "sitemap`). Mutually exclusive with --link-template."
        ),
    )
    rp.add_argument(
        "--link-template",
        dest="link_template",
        default=None,
        help=(
            "Phase 6 of ADR 0001 — wrap the rendered SVG body in an "
            "<a href> pointing at the Frame's `next` link. URL is "
            "`template.format(frame_id=…, target_name=…)`, e.g. "
            "'slide_{frame_id}.svg' for static-export workflows. "
            "Mutually exclusive with --link-base-url."
        ),
    )

    # deck
    dp = sub.add_parser(
        "deck",
        help=(
            "Render a multi-slide deck.yml to per-slide SVGs. Each slide can be "
            "a verbose visual block OR a one-liner pattern reference "
            "(`use: <id>` + `fill: {role: content}`) — the primary "
            "AI-agent authoring surface."
        ),
    )
    dp.add_argument("input", help="Input deck YAML file")
    dp.add_argument("-o", "--output", help="Output directory (default: ./output)")
    dp.add_argument("--lib", help="Path to lib/ token directory")
    dp.add_argument("--quiet", action="store_true", help="Suppress progress output")
    dp.add_argument(
        "--4k",
        dest="four_k",
        action="store_true",
        help="Also write a 3840-wide PNG per slide (requires cairosvg)",
    )
    dp.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "Also write a multi-page PDF for the deck. Default backend "
            "rasterizes each slide at --dpi (requires the [pdf] extra). "
            "Pair with --vector for selectable text via weasyprint."
        ),
    )
    dp.add_argument(
        "--vector",
        action="store_true",
        help=(
            "Use the weasyprint vector backend for --pdf output: selectable / "
            "searchable text, smaller files. Requires the [pdf-vector] extra: "
            'pip install "framegraph[pdf-vector]"'
        ),
    )
    dp.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Rasterization DPI for --pdf output (default: 300; ignored with --vector)",
    )
    dp.add_argument(
        "--target",
        default=None,
        help=(
            "Phase 3 of ADR 0001 — render every slide at the named FrameSet "
            "target's canvas dimensions. The target is looked up on each "
            "slide's per-Frame `targets:` first, then the FrameSet's "
            "`defaults.targets`. When omitted, the deck's `deck.canvas` "
            "applies. Mutually exclusive with --all-targets."
        ),
    )
    dp.add_argument(
        "--all-targets",
        dest="all_targets",
        action="store_true",
        help=(
            "Phase 3 of ADR 0001 — render the deck once per declared target. "
            "Outputs go to per-target subdirectories: "
            "`<output>/landscape/`, `<output>/portrait/`, etc. The target "
            "set is the union of `frameset.defaults.targets` and every "
            "Frame's per-Frame `targets:`. Requires the input to declare at "
            "least one target. Mutually exclusive with --target."
        ),
    )
    dp.add_argument(
        "--link-base-url",
        dest="link_base_url",
        default=None,
        help=(
            "Phase 6 of ADR 0001 — wrap each rendered slide's SVG body "
            "in an <a href> pointing at the slide's `next` link. URL "
            "pattern: <link-base-url>/<target>/<frame_id> (matches "
            "`framegraph sitemap`). Mutually exclusive with --link-template."
        ),
    )
    dp.add_argument(
        "--link-template",
        dest="link_template",
        default=None,
        help=(
            "Phase 6 of ADR 0001 — wrap each rendered slide's SVG body "
            "in an <a href> pointing at the slide's `next` link. URL is "
            "`template.format(frame_id=…, target_name=…)`, e.g. "
            "'slide_{frame_id}.svg'. Mutually exclusive with --link-base-url."
        ),
    )

    # docs
    vp = sub.add_parser(
        "validate",
        help=(
            "Validate a YAML file against FrameGraph schemas without rendering. "
            "Auto-detects FrameGraph documents/decks/framesets, pattern sidecars, "
            "and pattern catalogs."
        ),
    )
    vp.add_argument("input", help="Input YAML file")
    vp.add_argument(
        "--kind",
        choices=["auto", "framegraph", "pattern-sidecar", "pattern-catalog"],
        default="auto",
        help="Validation schema family (default: auto-detect)",
    )
    vp.add_argument("--quiet", action="store_true", help="Suppress success output")

    # docs
    docs_p = sub.add_parser(
        "docs",
        help=(
            "Emit a machine-readable JSON catalog of the public Python API "
            "(modules, classes, signatures, docstrings, Pydantic JSON schemas). "
            "Designed for LLM-agent consumption — feed it into a planner or "
            "use it to ground tool-use reasoning."
        ),
    )
    docs_p.add_argument(
        "-o",
        "--output",
        help="Output JSON path (default: write to stdout)",
    )
    docs_p.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # patterns — nested list / show / build
    pp = sub.add_parser(
        "patterns",
        help="List, show, or render slide-template patterns from the catalog",
    )
    pp_sub = pp.add_subparsers(dest="patterns_subcommand", required=True)

    # patterns list
    pl = pp_sub.add_parser("list", help="List patterns in the bundled catalog")
    pl.add_argument(
        "--category",
        choices=["generic", "consulting", "expert"],
        help="Filter by pattern category",
    )
    pl.add_argument(
        "--has-sidecar",
        dest="has_sidecar",
        action="store_true",
        help="Only show patterns that ship a sidecar in framegraph/data/fills/",
    )
    pl.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON records instead of a human-readable table",
    )

    # patterns show
    ps = pp_sub.add_parser("show", help="Print one pattern's definition")
    ps.add_argument("pattern_id", type=int, help="Catalog pattern id")

    # patterns example
    pe = pp_sub.add_parser(
        "example",
        help="Emit the sidecar's example_fill payload for a pattern",
    )
    pe.add_argument("pattern_id", type=int, help="Catalog pattern id")
    pe.add_argument(
        "-o",
        "--output",
        help="Output fill file path (default: write to stdout)",
    )
    pe.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml — same shape as patterns build --fill)",
    )
    pe.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # patterns build
    pb = pp_sub.add_parser(
        "build",
        help="Render a pattern + fill payload to SVG",
    )
    pb.add_argument("pattern_id", type=int, help="Catalog pattern id")
    pb.add_argument(
        "--fill",
        required=True,
        help="Path to a YAML file with the per-zone content payload",
    )
    pb.add_argument(
        "-o",
        "--output",
        help="Output SVG path (default: write to stdout)",
    )
    pb.add_argument(
        "--canvas-w",
        dest="canvas_w",
        type=float,
        default=1920.0,
        help="Canvas width in pixels (default: 1920)",
    )
    pb.add_argument(
        "--canvas-h",
        dest="canvas_h",
        type=float,
        default=1080.0,
        help="Canvas height in pixels (default: 1080)",
    )
    pb.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # patterns deck
    pd = pp_sub.add_parser(
        "deck",
        help=(
            "Render every sidecared pattern's example_fill into per-pattern SVGs "
            "(plus optional multi-page PDF). End-to-end smoke check of the "
            "patterns surface."
        ),
    )
    pd.add_argument(
        "-o",
        "--output",
        help="Output directory (default: ./patterns-deck)",
    )
    pd.add_argument(
        "--category",
        choices=["generic", "consulting", "expert"],
        help="Filter patterns by catalog category",
    )
    pd.add_argument(
        "--ids",
        help="Comma-separated pattern id allow-list, e.g. --ids=10,44,91",
    )
    pd.add_argument(
        "--canvas-w",
        dest="canvas_w",
        type=float,
        default=1920.0,
        help="Canvas width in pixels (default: 1920)",
    )
    pd.add_argument(
        "--canvas-h",
        dest="canvas_h",
        type=float,
        default=1080.0,
        help="Canvas height in pixels (default: 1080)",
    )
    pd.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "Also assemble a multi-page PDF (patterns-deck.pdf) from the rendered "
            "SVGs. Default backend rasterizes at --dpi (requires the [pdf] extra)."
        ),
    )
    pd.add_argument(
        "--vector",
        action="store_true",
        help=(
            "Use the weasyprint vector backend for --pdf output: selectable / "
            "searchable text. Requires the [pdf-vector] extra."
        ),
    )
    pd.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Rasterization DPI for --pdf output (default: 300; ignored with --vector)",
    )
    pd.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # sitemap (Phase 4 of ADR 0001)
    sm = sub.add_parser(
        "sitemap",
        help=(
            "Emit a sitemap.xml from a FrameSet's (Frame × target) link graph. "
            "Walks every Frame in declaration order and emits one URL per "
            "declared render target. Works with any input — frameset, deck, or "
            "legacy single-document YAML — by coercing to a FrameSet first."
        ),
    )
    sm.add_argument("input", help="Input FrameGraph YAML file")
    sm.add_argument(
        "--base-url",
        dest="base_url",
        required=True,
        help=(
            "Site root for emitted URLs (e.g. 'https://example.com' or "
            "'https://example.com/docs'). Combined as "
            "<base_url>/<target>/<frame_id>."
        ),
    )
    sm.add_argument(
        "-o",
        "--output",
        help="Output sitemap path (default: write to stdout)",
    )
    sm.add_argument(
        "--target",
        default=None,
        help=(
            "Optional single target name filter. When omitted, every "
            "(Frame × declared target) pair contributes one URL."
        ),
    )
    sm.add_argument("--quiet", action="store_true", help="Suppress progress output")

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
    if args.command == "patterns":
        # Nested subcommand dispatch.
        patterns_dispatch = {
            "list": cmd_patterns_list,
            "show": cmd_patterns_show,
            "example": cmd_patterns_example,
            "build": cmd_patterns_build,
            "deck": cmd_patterns_deck,
        }
        return patterns_dispatch[args.patterns_subcommand](args)
    dispatch = {
        "render": cmd_render,
        "deck": cmd_deck,
        "validate": cmd_validate,
        "docs": cmd_docs,
        "sitemap": cmd_sitemap,
        "version": cmd_version,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
