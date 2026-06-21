"""Unit tests for the typed export pipeline."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY

import pytest

from framegraph import export as export_mod
from framegraph.export import ExportOptions, resolve_dpi_preset, svg_canvas_size


def test_svg_canvas_size_prefers_root_width_height() -> None:
    svg = '<svg width="1920px" height="1080" viewBox="0 0 10 10"></svg>'

    assert svg_canvas_size(svg) == (1920.0, 1080.0)


def test_svg_canvas_size_falls_back_to_viewbox() -> None:
    svg = '<svg viewBox="0 0 960 540"></svg>'

    assert svg_canvas_size(svg) == (960.0, 540.0)


def test_svg_canvas_size_uses_default_when_svg_has_no_canvas() -> None:
    assert svg_canvas_size("<svg></svg>") == (960.0, 540.0)


def test_resolve_dpi_preset_maps_named_quality_levels() -> None:
    assert resolve_dpi_preset("screen") == 150
    assert resolve_dpi_preset("print") == 300
    assert resolve_dpi_preset("archive") == 600


def test_resolve_dpi_preset_normalizes_case_and_separator() -> None:
    assert resolve_dpi_preset("Screen") == 150
    assert resolve_dpi_preset("high-quality") == 600


def test_resolve_dpi_preset_rejects_unknown_preset() -> None:
    with pytest.raises(ValueError, match="unknown DPI preset"):
        resolve_dpi_preset("poster")


def test_write_svg_writes_file_and_metadata(tmp_path: Path) -> None:
    out = tmp_path / "slide.svg"

    result = export_mod.write_svg("<svg/>", out)

    assert out.read_text(encoding="utf-8") == "<svg/>"
    assert result.path == out
    assert result.format == "svg"


def test_prepare_svg_for_vector_pdf_is_idempotent() -> None:
    svg = '<text font-family="Arial, Helvetica, sans-serif">A</text>'

    once = export_mod.prepare_svg_for_vector_pdf(svg)
    twice = export_mod.prepare_svg_for_vector_pdf(once)

    assert once == twice
    assert 'font-family="Liberation Sans, Arial, Helvetica, sans-serif"' in once


def test_write_pdf_vector_uses_vector_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "slide.pdf"

    def fake_vector(svg: str) -> bytes:
        assert svg == "<svg/>"
        return b"%PDF vector"

    def fail_raster(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("raster backend should not run for vector PDF")

    monkeypatch.setattr(export_mod, "svg_to_vector_pdf_bytes", fake_vector)
    monkeypatch.setattr(export_mod, "svg_to_raster_pdf_page", fail_raster)

    result = export_mod.write_pdf(
        "<svg/>",
        out,
        options=ExportOptions(format="pdf", raster_dpi=150, vector=True),
    )

    assert out.read_bytes() == b"%PDF vector"
    assert result.path == out
    assert result.format == "pdf"
    assert result.vector is True
    assert result.raster_dpi is None
    assert result.page_count == 1


def test_write_pdf_raster_uses_raster_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "slide.pdf"
    saves: list[tuple[str, dict[str, Any]]] = []

    class FakePage:
        def save(self, path: str, **kwargs: Any) -> None:
            saves.append((path, kwargs))

    def fake_raster(svg: str, *, dpi: int) -> FakePage:
        assert svg == "<svg/>"
        assert dpi == 200
        return FakePage()

    monkeypatch.setattr(export_mod, "svg_to_raster_pdf_page", fake_raster)
    monkeypatch.setattr(
        export_mod,
        "svg_to_vector_pdf_bytes",
        lambda _svg: (_ for _ in ()).throw(AssertionError("vector backend should not run")),
    )

    result = export_mod.write_pdf(
        "<svg/>",
        out,
        options=ExportOptions(format="pdf", raster_dpi=200),
    )

    assert saves == [(str(out), {"format": "PDF", "resolution": 200.0})]
    assert result.path == out
    assert result.vector is False
    assert result.raster_dpi == 200


def test_write_pdf_preserves_legacy_dpi_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "slide.pdf"
    saves: list[tuple[str, dict[str, Any]]] = []

    class FakePage:
        def save(self, path: str, **kwargs: Any) -> None:
            saves.append((path, kwargs))

    monkeypatch.setattr(export_mod, "svg_to_raster_pdf_page", lambda _svg, *, dpi: FakePage())

    result = export_mod.write_pdf("<svg/>", out, dpi=96)

    assert saves == [(str(out), {"format": "PDF", "resolution": 96.0})]
    assert result.raster_dpi == 96


def test_write_deck_pdf_rejects_empty_deck(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no slide paths"):
        export_mod.write_deck_pdf([], tmp_path / "deck.pdf")


def test_write_deck_pdf_raster_saves_multipage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_svg = tmp_path / "one.svg"
    second_svg = tmp_path / "two.svg"
    first_svg.write_text("<svg>one</svg>", encoding="utf-8")
    second_svg.write_text("<svg>two</svg>", encoding="utf-8")
    out = tmp_path / "deck.pdf"
    saves: list[tuple[str, dict[str, Any]]] = []

    class FakePage:
        def __init__(self, name: str) -> None:
            self.name = name

        def save(self, path: str, **kwargs: Any) -> None:
            saves.append((path, kwargs))

    pages: list[FakePage] = []

    def fake_raster(svg: str, *, dpi: int) -> FakePage:
        assert dpi == 144
        page = FakePage(svg)
        pages.append(page)
        return page

    monkeypatch.setattr(export_mod, "svg_to_raster_pdf_page", fake_raster)

    result = export_mod.write_deck_pdf(
        [first_svg, second_svg],
        out,
        options=ExportOptions(format="pdf", raster_dpi=144),
    )

    assert result.path == out
    assert result.page_count == 2
    assert saves == [
        (
            str(out),
            {
                "format": "PDF",
                "save_all": True,
                "append_images": [pages[1]],
                "resolution": 144.0,
            },
        )
    ]


def test_write_deck_pdf_vector_appends_each_slide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_svg = tmp_path / "one.svg"
    second_svg = tmp_path / "two.svg"
    first_svg.write_text("<svg>one</svg>", encoding="utf-8")
    second_svg.write_text("<svg>two</svg>", encoding="utf-8")
    out = tmp_path / "deck.pdf"
    appended_payloads: list[bytes] = []
    written: list[bytes] = []

    class FakePdfWriter:
        def append(self, stream: Any) -> None:
            appended_payloads.append(stream.read())

        def write(self, stream: Any) -> None:
            stream.write(b"joined")
            written.append(b"joined")

    monkeypatch.setitem(
        sys.modules,
        "pypdf",
        SimpleNamespace(PdfWriter=FakePdfWriter),
    )
    monkeypatch.setattr(export_mod, "svg_to_vector_pdf_bytes", lambda svg: svg.encode())

    result = export_mod.write_deck_pdf(
        [first_svg, second_svg],
        out,
        options=ExportOptions(format="pdf", vector=True),
    )

    assert appended_payloads == [b"<svg>one</svg>", b"<svg>two</svg>"]
    assert written == [b"joined"]
    assert out.read_bytes() == b"joined"
    assert result.page_count == 2
    assert result.vector is True


def test_write_png_uses_configured_width(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "slide.png"
    calls: list[tuple[str, Path, int]] = []

    def fake_png(svg: str, path: Path, *, output_width: int) -> None:
        calls.append((svg, path, output_width))

    monkeypatch.setattr(export_mod, "rasterize_png", fake_png)

    result = export_mod.write_png(
        "<svg/>",
        out,
        options=ExportOptions(format="png", png_width=2048),
    )

    assert calls == [("<svg/>", out, 2048)]
    assert result.path == out
    assert result.format == "png"


def test_write_png_4k_uses_default_width(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "slide.png"
    calls: list[int] = []

    def fake_png(_svg: str, _path: Path, *, output_width: int) -> None:
        calls.append(output_width)

    monkeypatch.setattr(export_mod, "rasterize_png", fake_png)

    result = export_mod.write_png_4k("<svg/>", out)

    assert calls == [3840]
    assert result.format == "png"


def test_rasterize_png_reports_missing_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "cairosvg":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(ImportError, match="cairosvg is required"):
        export_mod.rasterize_png("<svg/>", tmp_path / "slide.png")


def test_rasterize_png_uses_configured_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "slide.png"
    calls: list[dict[str, Any]] = []

    def fake_svg2png(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "cairosvg", SimpleNamespace(svg2png=fake_svg2png))

    export_mod.rasterize_png("<svg/>", out, output_width=1200)

    assert calls == [
        {
            "bytestring": b"<svg/>",
            "write_to": str(out),
            "output_width": 1200,
        }
    ]


def test_svg_to_raster_pdf_page_flattens_alpha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations: list[tuple[str, Any]] = []

    class FakeImage:
        mode = "RGBA"
        size = (10, 10)
        info: dict[str, Any] = {}

        def split(self) -> list[str]:
            return ["r", "g", "b", "alpha"]

    class FakeBackground:
        mode = "RGB"
        size = (10, 10)

        def __init__(self) -> None:
            self.info: dict[str, Any] = {}

        def paste(self, img: FakeImage, *, mask: str) -> None:
            operations.append(("paste", (img, mask)))

    fake_bg = FakeBackground()

    def fake_new(mode: str, size: tuple[int, int], color: tuple[int, int, int]) -> FakeBackground:
        operations.append(("new", (mode, size, color)))
        return fake_bg

    monkeypatch.setitem(
        sys.modules,
        "cairosvg",
        SimpleNamespace(svg2png=lambda **_kwargs: b"png"),
    )
    monkeypatch.setitem(
        sys.modules,
        "PIL",
        SimpleNamespace(Image=SimpleNamespace(open=lambda _stream: FakeImage(), new=fake_new)),
    )

    page = export_mod.svg_to_raster_pdf_page('<svg width="96" height="96"></svg>', dpi=192)

    assert page is fake_bg
    assert operations == [
        ("new", ("RGB", (10, 10), (255, 255, 255))),
        ("paste", (ANY, "alpha")),
    ]
    assert fake_bg.info["dpi"] == (192.0, 192.0)


def test_svg_to_raster_pdf_page_converts_non_rgb_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeImage:
        mode = "L"
        info: dict[str, Any] = {}

        def __init__(self) -> None:
            self.converted_to: str | None = None

        def convert(self, mode: str) -> FakeImage:
            self.converted_to = mode
            return self

    image = FakeImage()
    svg2png_calls: list[dict[str, Any]] = []

    def fake_svg2png(**kwargs: Any) -> bytes:
        svg2png_calls.append(kwargs)
        return b"png"

    monkeypatch.setitem(sys.modules, "cairosvg", SimpleNamespace(svg2png=fake_svg2png))
    monkeypatch.setitem(
        sys.modules,
        "PIL",
        SimpleNamespace(Image=SimpleNamespace(open=lambda _stream: image)),
    )

    page = export_mod.svg_to_raster_pdf_page('<svg width="96" height="96"></svg>', dpi=192)

    assert page is image
    assert image.converted_to == "RGB"
    assert image.info["dpi"] == (192.0, 192.0)
    assert svg2png_calls[0]["output_width"] == 192


def test_svg_to_vector_pdf_bytes_uses_weasyprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_inputs: list[str] = []

    class FakeHTML:
        def __init__(self, *, string: str) -> None:
            html_inputs.append(string)

        def write_pdf(self) -> bytes:
            return b"%PDF"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

    pdf = export_mod.svg_to_vector_pdf_bytes(
        '<svg width="100" height="50"><text font-family="Arial, Helvetica, sans-serif">A</text></svg>'
    )

    assert pdf == b"%PDF"
    assert "@page { size: 100.0px 50.0px; margin: 0; }" in html_inputs[0]
    assert "Liberation Sans, Arial" in html_inputs[0]
