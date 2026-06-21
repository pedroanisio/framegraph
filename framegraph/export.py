"""Typed SVG, PNG, and PDF export helpers.

Rendering produces SVG first. This module owns the post-render export
boundary: SVG file writes, 4K PNG rasterization, raster PDF wrapping, and
vector PDF conversion. Keeping this code outside the CLI gives canvas and
DPI features one tested place to evolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from framegraph.canvas import svg_canvas_size as _parse_svg_canvas_size

ExportFormat = Literal["svg", "png", "pdf"]
"""Supported export formats."""

DpiPreset = Literal["screen", "print", "archive", "high-quality"]
"""Named raster quality presets."""

_DPI_PRESETS: dict[str, int] = {
    "screen": 150,
    "print": 300,
    "archive": 600,
    "high-quality": 600,
    "high_quality": 600,
}
"""Raster DPI presets for PNG-backed PDF export."""


@dataclass(frozen=True)
class ExportOptions:
    """Options shared by export writers.

    Attributes:
        format: Destination format.
        raster_dpi: DPI used by raster PDF output.
        vector: Whether PDF export should use the vector backend.
        png_width: Output width used by PNG export.
    """

    format: ExportFormat = "svg"
    raster_dpi: int = 300
    vector: bool = False
    png_width: int = 3840


@dataclass(frozen=True)
class ExportResult:
    """Result metadata for one export write."""

    path: Path
    format: ExportFormat
    page_count: int = 1
    raster_dpi: int | None = None
    vector: bool = False


def _normalize_key(value: str) -> str:
    """Return a lower-case preset key with whitespace normalized."""
    return value.strip().lower().replace(" ", "-")


def resolve_dpi_preset(name: str) -> int:
    """Resolve a named raster DPI preset.

    Args:
        name: Preset name. Supported values are ``screen`` (150),
            ``print`` (300), ``archive`` (600), and ``high-quality`` (600).

    Returns:
        Raster DPI value.

    Raises:
        ValueError: If the preset is unknown.
    """
    preset_key = _normalize_key(name)
    try:
        return _DPI_PRESETS[preset_key]
    except KeyError as exc:
        supported = ", ".join(sorted({"screen", "print", "archive", "high-quality"}))
        raise ValueError(f"unknown DPI preset {name!r}; expected one of: {supported}") from exc


def _coerce_pdf_options(
    options: ExportOptions | None,
    *,
    dpi: int,
    vector: bool,
) -> ExportOptions:
    """Return explicit options while preserving legacy keyword arguments."""
    if options is not None:
        return options
    return ExportOptions(format="pdf", raster_dpi=dpi, vector=vector)


def write_svg(svg: str, out: Path) -> ExportResult:
    """Write an SVG string to disk."""
    out.write_text(svg, encoding="utf-8")
    return ExportResult(path=out, format="svg")


def rasterize_png(svg: str, out: Path, *, output_width: int = 3840) -> None:
    """Rasterize an SVG string to PNG at the requested width."""
    try:
        import cairosvg
    except ImportError as exc:
        raise ImportError(
            "cairosvg is required for --4k PNG output. Install with: pip install cairosvg"
        ) from exc
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(out),
        output_width=output_width,
    )


def write_png(
    svg: str,
    out: Path,
    *,
    options: ExportOptions | None = None,
) -> ExportResult:
    """Write a raster PNG from an SVG string."""
    opts = options if options is not None else ExportOptions(format="png")
    rasterize_png(svg, out, output_width=opts.png_width)
    return ExportResult(path=out, format="png")


def write_png_4k(svg: str, out: Path) -> ExportResult:
    """Rasterize an SVG string to a 3840-wide PNG."""
    return write_png(svg, out, options=ExportOptions(format="png", png_width=3840))


def svg_canvas_size(svg: str) -> tuple[float, float]:
    """Extract the canvas `(width, height)` in SVG user units."""
    return _parse_svg_canvas_size(svg).size


def svg_to_raster_pdf_page(svg: str, *, dpi: int) -> Any:
    """Rasterize an SVG to a Pillow image sized for a DPI-aware PDF page."""
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

    svg_w, _svg_h = svg_canvas_size(svg)
    output_width = max(1, int(round(svg_w * dpi / 96.0)))

    import io

    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=output_width,
    )
    img = PILImage.open(io.BytesIO(png_bytes))
    img.info["dpi"] = (float(dpi), float(dpi))
    if img.mode in ("RGBA", "LA"):
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        bg.info["dpi"] = (float(dpi), float(dpi))
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def prepare_svg_for_vector_pdf(svg: str) -> str:
    """Prefix `Liberation Sans` to any `Arial`-fronted font-family stack."""
    import re

    return re.sub(
        r'font-family="Arial, Helvetica, sans-serif"',
        'font-family="Liberation Sans, Arial, Helvetica, sans-serif"',
        svg,
    )


def svg_to_vector_pdf_bytes(svg: str) -> bytes:
    """Convert an SVG string to a single-page vector PDF via weasyprint."""
    try:
        import weasyprint
    except ImportError as exc:
        raise ImportError(
            "weasyprint is required for --pdf --vector output. "
            'Install with: pip install "framegraph[pdf-vector]"'
        ) from exc
    svg_w, svg_h = svg_canvas_size(svg)
    svg_adjusted = prepare_svg_for_vector_pdf(svg)
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


def write_pdf(
    svg: str,
    out: Path,
    *,
    options: ExportOptions | None = None,
    dpi: int = 300,
    vector: bool = False,
) -> ExportResult:
    """Convert an SVG string to a single-page PDF."""
    opts = _coerce_pdf_options(options, dpi=dpi, vector=vector)
    if opts.vector:
        out.write_bytes(svg_to_vector_pdf_bytes(svg))
        return ExportResult(path=out, format="pdf", vector=True)
    page = svg_to_raster_pdf_page(svg, dpi=opts.raster_dpi)
    page.save(str(out), format="PDF", resolution=float(opts.raster_dpi))
    return ExportResult(path=out, format="pdf", raster_dpi=opts.raster_dpi)


def write_deck_pdf(
    svg_paths: list[Path],
    out: Path,
    *,
    options: ExportOptions | None = None,
    dpi: int = 300,
    vector: bool = False,
) -> ExportResult:
    """Convert a list of slide SVGs into a single multi-page PDF."""
    if not svg_paths:
        raise ValueError("write_deck_pdf called with no slide paths")

    opts = _coerce_pdf_options(options, dpi=dpi, vector=vector)
    if opts.vector:
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
            pdf_bytes = svg_to_vector_pdf_bytes(svg_path.read_text(encoding="utf-8"))
            writer.append(io.BytesIO(pdf_bytes))
        with out.open("wb") as fh:
            writer.write(fh)
        return ExportResult(path=out, format="pdf", page_count=len(svg_paths), vector=True)

    pages = [
        svg_to_raster_pdf_page(p.read_text(encoding="utf-8"), dpi=opts.raster_dpi)
        for p in svg_paths
    ]
    first, rest = pages[0], pages[1:]
    first.save(
        str(out),
        format="PDF",
        save_all=True,
        append_images=rest,
        resolution=float(opts.raster_dpi),
    )
    return ExportResult(
        path=out,
        format="pdf",
        page_count=len(svg_paths),
        raster_dpi=opts.raster_dpi,
    )
