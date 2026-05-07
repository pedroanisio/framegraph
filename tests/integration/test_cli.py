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
from framegraph.cli import build_parser, main as cli_main

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
STANDALONE_FIXTURES = sorted(
    p for p in FIXTURE_DIR.glob("*.yml") if ".deck." not in p.name
)
DECK_FIXTURES = sorted(FIXTURE_DIR.glob("*.deck.yml"))
LIB_DIR = Path(__file__).resolve().parents[2] / "framegraph" / "lib"


# ── render subcommand ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture", STANDALONE_FIXTURES, ids=lambda p: p.stem
)
def test_cli_render_writes_svg_for_each_fixture(
    fixture: Path, tmp_path: Path
) -> None:
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
def test_cli_deck_renders_each_slide_to_output_dir(
    deck_fixture: Path, tmp_path: Path
) -> None:
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
    args = build_parser().parse_args(
        ["render", "in.yml", "-o", "out.svg", "--strict", "--quiet"]
    )
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
