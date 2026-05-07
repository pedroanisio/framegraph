"""Integration: drive `framegraph.cli.main()` end-to-end.

Each subcommand is exercised against real fixtures with `tmp_path` for
output and `capsys` for stdout/stderr assertions. No internal symbols
are mocked — only the OS-level boundaries (argv via the function's
`argv` parameter, file I/O via `tmp_path`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framegraph import __version__
from framegraph.cli import build_parser
from framegraph.cli import main as cli_main

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
STANDALONE_FIXTURES = sorted(p for p in FIXTURE_DIR.glob("*.yml") if ".deck." not in p.name)
DECK_FIXTURES = sorted(FIXTURE_DIR.glob("*.deck.yml"))
LIB_DIR = Path(__file__).resolve().parents[2] / "framegraph" / "lib"


# ── render subcommand ────────────────────────────────────────────────


@pytest.mark.parametrize("fixture", STANDALONE_FIXTURES, ids=lambda p: p.stem)
def test_cli_render_writes_svg_for_each_fixture(fixture: Path, tmp_path: Path) -> None:
    """`framegraph render <fixture> -o <out>` exits 0 and writes a non-empty SVG."""
    out = tmp_path / f"{fixture.stem}.svg"
    rc = cli_main(["render", str(fixture), "-o", str(out), "--quiet"])
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0
    head = out.read_text(encoding="utf-8").lstrip()
    assert head.startswith(("<?xml", "<svg"))


def test_cli_render_default_output_path_uses_input_with_svg_suffix(
    tmp_path: Path,
) -> None:
    """Without `-o`, output path is `<input>.svg` next to the input file."""
    src = STANDALONE_FIXTURES[0]
    # Copy fixture into tmp_path so the implicit output lands there
    dest = tmp_path / src.name
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    rc = cli_main(["render", str(dest), "--quiet"])
    assert rc == 0
    expected = dest.with_suffix(".svg")
    assert expected.exists() and expected.stat().st_size > 0


def test_cli_render_prints_progress_when_not_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `--quiet`, render prints a progress line to stdout."""
    out = tmp_path / "out.svg"
    rc = cli_main(["render", str(STANDALONE_FIXTURES[0]), "-o", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "wrote" in captured.out
    assert str(out) in captured.out


def test_cli_render_missing_input_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pointing render at a non-existent file exits non-zero with a stderr message."""
    bogus = tmp_path / "does_not_exist.yml"
    rc = cli_main(["render", str(bogus), "-o", str(tmp_path / "out.svg")])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_render_invalid_yaml_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed YAML at the input path triggers an error exit."""
    bad = tmp_path / "broken.yml"
    bad.write_text("key: : :\n  - [unclosed", encoding="utf-8")
    rc = cli_main(["render", str(bad), "-o", str(tmp_path / "out.svg")])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_render_unrenderable_doc_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A document whose contents make the renderer raise reports stderr + exit 1."""
    # YAML that parses but blows up the renderer (top-level `null` is not a dict)
    bad = tmp_path / "null_doc.yml"
    bad.write_text("null\n", encoding="utf-8")
    rc = cli_main(["render", str(bad), "-o", str(tmp_path / "out.svg")])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


# ── deck subcommand ─────────────────────────────────────────────────


@pytest.mark.parametrize("deck_fixture", DECK_FIXTURES, ids=lambda p: p.stem)
def test_cli_deck_renders_each_slide_to_output_dir(deck_fixture: Path, tmp_path: Path) -> None:
    """`framegraph deck <fixture> -o <dir>` writes one SVG per slide."""
    rc = cli_main(
        [
            "deck",
            str(deck_fixture),
            "-o",
            str(tmp_path),
            "--lib",
            str(LIB_DIR),
            "--quiet",
        ]
    )
    assert rc == 0
    svg_files = list(tmp_path.glob("*.svg"))
    assert len(svg_files) >= 1


def test_cli_deck_uses_default_lib_when_not_specified(tmp_path: Path) -> None:
    """When `--lib` is omitted, the bundled `framegraph/lib/` is used."""
    rc = cli_main(
        [
            "deck",
            str(DECK_FIXTURES[0]),
            "-o",
            str(tmp_path),
            "--quiet",
        ]
    )
    assert rc == 0
    assert list(tmp_path.glob("*.svg"))


def test_cli_deck_default_output_directory_is_input_parent_output(
    tmp_path: Path,
) -> None:
    """Without `-o`, deck output goes to `<input_dir>/output/`."""
    deck_src = DECK_FIXTURES[0]
    dest = tmp_path / deck_src.name
    dest.write_text(deck_src.read_text(encoding="utf-8"), encoding="utf-8")

    rc = cli_main(["deck", str(dest), "--lib", str(LIB_DIR), "--quiet"])
    assert rc == 0
    assert (tmp_path / "output").is_dir()
    assert list((tmp_path / "output").glob("*.svg"))


def test_cli_deck_prints_progress_when_not_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `--quiet`, deck prints rendering progress lines."""
    rc = cli_main(
        [
            "deck",
            str(DECK_FIXTURES[0]),
            "-o",
            str(tmp_path),
            "--lib",
            str(LIB_DIR),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Rendering" in out or "wrote" in out


def test_cli_deck_missing_input_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pointing deck at a non-existent file exits non-zero."""
    rc = cli_main(
        [
            "deck",
            str(tmp_path / "missing.yml"),
            "-o",
            str(tmp_path / "out"),
            "--quiet",
        ]
    )
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


# ── version subcommand ──────────────────────────────────────────────


def test_cli_version_prints_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`framegraph version` prints the `framegraph __version__` and exits 0."""
    rc = cli_main(["version"])
    assert rc == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert "framegraph" in out


# ── parser and dispatch internals ───────────────────────────────────


def test_cli_build_parser_returns_parser_with_required_subcommand() -> None:
    """`build_parser()` configures a subparser with `required=True`."""
    parser = build_parser()
    # Without a subcommand, the parser must error (SystemExit on parse_args)
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_cli_build_parser_render_args_round_trip() -> None:
    """`render` subcommand parses input + flags into the expected namespace."""
    args = build_parser().parse_args(["render", "in.yml", "-o", "out.svg", "--strict", "--quiet"])
    assert args.command == "render"
    assert args.input == "in.yml"
    assert args.output == "out.svg"
    assert args.strict is True
    assert args.quiet is True


def test_cli_build_parser_deck_args_round_trip() -> None:
    """`deck` subcommand parses input + flags into the expected namespace."""
    args = build_parser().parse_args(
        ["deck", "deck.yml", "-o", "out_dir", "--lib", "lib_dir", "--quiet"]
    )
    assert args.command == "deck"
    assert args.input == "deck.yml"
    assert args.output == "out_dir"
    assert args.lib == "lib_dir"
    assert args.quiet is True


# ── --4k flag (PNG companion output) ────────────────────────────────

cairosvg = pytest.importorskip(
    "cairosvg",
    reason="cairosvg required for --4k PNG output tests",
)


def test_cli_build_parser_render_4k_flag_round_trip() -> None:
    """`--4k` on render maps to `args.four_k` (digit-prefixed dest renamed)."""
    args = build_parser().parse_args(["render", "in.yml", "-o", "out.svg", "--4k"])
    assert args.four_k is True


def test_cli_build_parser_render_4k_default_false() -> None:
    """When `--4k` is omitted, `args.four_k` defaults to False."""
    args = build_parser().parse_args(["render", "in.yml", "-o", "out.svg"])
    assert args.four_k is False


def test_cli_build_parser_deck_4k_flag_round_trip() -> None:
    """`--4k` is also wired on the deck subcommand."""
    args = build_parser().parse_args(["deck", "deck.yml", "-o", "out_dir", "--4k"])
    assert args.four_k is True


def test_cli_render_4k_writes_png_alongside_svg(tmp_path: Path) -> None:
    """`render --4k` writes both an SVG and a sibling 3840-wide PNG."""
    out = tmp_path / "out.svg"
    rc = cli_main(["render", str(STANDALONE_FIXTURES[0]), "-o", str(out), "--4k", "--quiet"])
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0
    png = out.with_suffix(".png")
    assert png.exists() and png.stat().st_size > 0
    # PNG width is exactly 3840; height is auto-derived from SVG aspect ratio
    from PIL import Image

    with Image.open(png) as im:
        assert im.size[0] == 3840
        assert im.size[1] > 0


def test_cli_render_without_4k_does_not_write_png(tmp_path: Path) -> None:
    """Without `--4k`, no PNG is produced (SVG-only path is unchanged)."""
    out = tmp_path / "out.svg"
    rc = cli_main(["render", str(STANDALONE_FIXTURES[0]), "-o", str(out), "--quiet"])
    assert rc == 0
    assert not out.with_suffix(".png").exists()


def test_cli_render_4k_prints_png_path_when_not_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-quiet `render --4k` prints both wrote-lines (SVG and PNG)."""
    out = tmp_path / "out.svg"
    rc = cli_main(["render", str(STANDALONE_FIXTURES[0]), "-o", str(out), "--4k"])
    assert rc == 0
    captured = capsys.readouterr().out
    assert str(out) in captured
    assert str(out.with_suffix(".png")) in captured


def test_cli_deck_4k_writes_png_per_slide(tmp_path: Path) -> None:
    """`deck --4k` writes a PNG sibling for every slide SVG."""
    rc = cli_main(
        [
            "deck",
            str(DECK_FIXTURES[0]),
            "-o",
            str(tmp_path),
            "--lib",
            str(LIB_DIR),
            "--4k",
            "--quiet",
        ]
    )
    assert rc == 0
    svgs = list(tmp_path.glob("*.svg"))
    pngs = list(tmp_path.glob("*.png"))
    assert len(svgs) >= 1
    # One PNG per SVG, with matching stems
    assert {p.stem for p in pngs} == {p.stem for p in svgs}
    # Every PNG is 3840 wide
    from PIL import Image

    for png in pngs:
        with Image.open(png) as im:
            assert im.size[0] == 3840


def test_cli_render_4k_png_uses_manifesto_aspect_ratio(tmp_path: Path) -> None:
    """The PNG height matches the SVG aspect ratio (no distortion).

    Manifesto canvas is 960 × 660 → aspect 16:11 → PNG should be
    3840 × 2640 (or within 1 px of the rounded ratio).
    """
    manifesto = Path(__file__).resolve().parents[2] / "faz-ai-manifesto.yml"
    if not manifesto.exists():
        pytest.skip("manifesto fixture not present")
    out = tmp_path / "manifesto.svg"
    rc = cli_main(["render", str(manifesto), "-o", str(out), "--4k", "--quiet"])
    assert rc == 0
    from PIL import Image

    with Image.open(out.with_suffix(".png")) as im:
        w, h = im.size
        assert w == 3840
        # 3840 * 660 / 960 = 2640
        assert abs(h - 2640) <= 1, f"expected ~2640px tall, got {h}"
