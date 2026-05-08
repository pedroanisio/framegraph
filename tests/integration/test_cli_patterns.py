"""Integration tests for `framegraph patterns` subcommands — Phase 5.

Phase 5 acceptance criteria (per `docs/ROADMAP-FILL-RENDER.md`):

  - ``framegraph patterns list --category=generic`` prints exactly
    50 patterns.
  - ``framegraph patterns show 44`` prints the BMC definition
    without crashing.
  - ``framegraph patterns build 44 --fill <bmc_example_fill> -o
    /tmp/bmc.svg`` produces a valid SVG file.
  - All three subcommands exit 0 on success, non-zero on
    validation/render failure with a clear stderr message.

Tests drive `framegraph.cli.main(argv)` directly (no subprocess
overhead); stdout/stderr are captured via pytest's ``capsys``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from framegraph.cli import main

# ─────────────────────────────────────────────────────────────────
# `patterns list`
# ─────────────────────────────────────────────────────────────────


class TestPatternsList:
    def test_list_all_patterns(self, capsys) -> None:
        rc = main(["patterns", "list"])
        assert rc == 0
        out = capsys.readouterr().out
        # Bundled catalog has 375 patterns; expect at least one line per.
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Allow for a header line; the body must have ≥ 375 entries.
        assert len(lines) >= 375

    def test_list_filters_generic_category(self, capsys) -> None:
        """Acceptance: `--category=generic` prints exactly 50 patterns."""
        rc = main(["patterns", "list", "--category", "generic"])
        assert rc == 0
        out = capsys.readouterr().out
        # Each non-empty line is one pattern. Allow an optional header.
        body_lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
        # If there's a column-header line, the body still has 50 entries.
        # Generous count check: 50 ± a single header.
        assert 50 <= len(body_lines) <= 51

    def test_list_filters_consulting_category(self, capsys) -> None:
        rc = main(["patterns", "list", "--category", "consulting"])
        assert rc == 0
        out = capsys.readouterr().out
        body_lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
        # 275 consulting patterns in the bundled catalog.
        assert 275 <= len(body_lines) <= 276

    def test_list_filters_expert_category(self, capsys) -> None:
        rc = main(["patterns", "list", "--category", "expert"])
        assert rc == 0
        out = capsys.readouterr().out
        body_lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]
        # 50 expert patterns in the bundled catalog.
        assert 50 <= len(body_lines) <= 51

    def test_list_invalid_category_rejected(self, capsys) -> None:
        with pytest.raises(SystemExit):
            main(["patterns", "list", "--category", "made_up"])


# ─────────────────────────────────────────────────────────────────
# `patterns show`
# ─────────────────────────────────────────────────────────────────


class TestPatternsShow:
    def test_show_bmc_does_not_crash(self, capsys) -> None:
        """Acceptance: `show 44` prints the BMC definition without crashing."""
        rc = main(["patterns", "show", "44"])
        assert rc == 0
        out = capsys.readouterr().out
        # Output must mention the pattern's name and at least one zone role.
        assert "Business Model Canvas" in out
        assert "key_partners" in out

    def test_show_includes_zone_count(self, capsys) -> None:
        rc = main(["patterns", "show", "44"])
        assert rc == 0
        out = capsys.readouterr().out
        # 9 zones in BMC — somewhere in the output we should see the count.
        assert "9" in out

    def test_show_unknown_id_exits_nonzero(self, capsys) -> None:
        rc = main(["patterns", "show", "99999"])
        assert rc != 0
        err = capsys.readouterr().err
        # Error message must mention the offending id.
        assert "99999" in err


# ─────────────────────────────────────────────────────────────────
# `patterns build` — end-to-end render
# ─────────────────────────────────────────────────────────────────


class TestPatternsBuild:
    @pytest.fixture
    def bmc_fill_file(self, tmp_path: Path) -> Path:
        """Write a BMC fill YAML mirroring the sidecar's example_fill."""
        from framegraph.patterns import BMC_SIDECAR_PATH, load_sidecar

        sidecar = load_sidecar(BMC_SIDECAR_PATH)
        path = tmp_path / "bmc_fill.yml"
        path.write_text(yaml.safe_dump(sidecar.example_fill), encoding="utf-8")
        return path

    def test_build_bmc_writes_valid_svg(self, capsys, tmp_path: Path, bmc_fill_file: Path) -> None:
        out_path = tmp_path / "bmc.svg"
        rc = main(
            [
                "patterns",
                "build",
                "44",
                "--fill",
                str(bmc_fill_file),
                "-o",
                str(out_path),
            ]
        )
        assert rc == 0
        assert out_path.exists()
        svg = out_path.read_text(encoding="utf-8")
        # Must parse as XML, root element must be SVG.
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")
        # Must contain rendered fill text.
        assert "Subscription" in svg or "Engineering" in svg

    def test_build_to_stdout_when_no_output_flag(self, capsys, bmc_fill_file: Path) -> None:
        rc = main(["patterns", "build", "44", "--fill", str(bmc_fill_file)])
        assert rc == 0
        out = capsys.readouterr().out
        # Stdout receives the SVG.
        assert out.startswith("<?xml") or out.startswith("<svg")

    def test_build_unknown_id_exits_nonzero(self, capsys, bmc_fill_file: Path) -> None:
        rc = main(["patterns", "build", "99999", "--fill", str(bmc_fill_file)])
        assert rc != 0
        err = capsys.readouterr().err
        assert "99999" in err

    def test_build_missing_fill_file_exits_nonzero(self, capsys, tmp_path: Path) -> None:
        rc = main(
            [
                "patterns",
                "build",
                "44",
                "--fill",
                str(tmp_path / "does_not_exist.yml"),
            ]
        )
        assert rc != 0

    def test_build_invalid_fill_payload_exits_nonzero(self, capsys, tmp_path: Path) -> None:
        """A fill missing required zones surfaces a validation error."""
        bad = tmp_path / "bad_fill.yml"
        # BMC requires 9 zones; this fill has only 1.
        bad.write_text(
            yaml.safe_dump({"key_partners": ["Only one zone"]}),
            encoding="utf-8",
        )
        rc = main(["patterns", "build", "44", "--fill", str(bad)])
        assert rc != 0
        err = capsys.readouterr().err
        # Error should be informative — mention validation or a missing role.
        assert err.strip() != ""


# ─────────────────────────────────────────────────────────────────
# `patterns deck` — agent-facing one-shot corpus walk-through
# ─────────────────────────────────────────────────────────────────


class TestPatternsDeck:
    """`patterns deck` renders every sidecared pattern's example_fill.

    These tests pin the CLI contract documented in
    `docs/AUTHORING-FILLS.md` and `AGENTS.md` — the command must
    produce both per-pattern SVGs and per-pattern fill payloads,
    must respect `--ids` / `--category` filters, and must fail
    cleanly when the filter selects no sidecared patterns.
    """

    def test_deck_renders_single_id_to_svgs_and_fills(self, capsys, tmp_path: Path) -> None:
        out_dir = tmp_path / "deck-out"
        rc = main(
            [
                "patterns",
                "deck",
                "--ids",
                "10",
                "-o",
                str(out_dir),
                "--quiet",
            ]
        )
        assert rc == 0
        svg = out_dir / "svgs" / "010-swot-analysis.svg"
        fill = out_dir / "fills" / "010-swot-analysis.fill.yml"
        assert svg.exists() and svg.stat().st_size > 0
        assert fill.exists() and fill.stat().st_size > 0
        # SVG must parse as XML.
        ET.fromstring(svg.read_text(encoding="utf-8"))
        # Fill must be the flat {role: content} shape (no `pattern_id:` /
        # `zones:` / `example_fill:` sidecar wrappers).
        loaded = yaml.safe_load(fill.read_text(encoding="utf-8"))
        assert "pattern_id" not in loaded
        assert "zones" not in loaded
        assert "example_fill" not in loaded
        assert "strengths" in loaded  # SWOT zone

    def test_deck_renders_multiple_ids(self, capsys, tmp_path: Path) -> None:
        out_dir = tmp_path / "deck-out"
        rc = main(
            [
                "patterns",
                "deck",
                "--ids",
                "10,44",
                "-o",
                str(out_dir),
                "--quiet",
            ]
        )
        assert rc == 0
        svgs = sorted((out_dir / "svgs").glob("*.svg"))
        assert len(svgs) == 2
        names = [p.name for p in svgs]
        assert "010-swot-analysis.svg" in names
        assert "044-business-model-canvas.svg" in names

    def test_deck_filters_by_category(self, capsys, tmp_path: Path) -> None:
        """`--category=consulting` only keeps consulting-tagged sidecared patterns."""
        out_dir = tmp_path / "deck-out"
        rc = main(
            [
                "patterns",
                "deck",
                "--category",
                "consulting",
                "-o",
                str(out_dir),
                "--quiet",
            ]
        )
        assert rc == 0
        # At least one consulting sidecar exists in the corpus
        # (091-communications-plan.yml, 093-raid-log.yml, …).
        svgs = list((out_dir / "svgs").glob("*.svg"))
        assert svgs, "expected at least one consulting-category sidecared pattern"

    def test_deck_empty_filter_exits_nonzero(self, capsys, tmp_path: Path) -> None:
        """A filter that matches nothing prints an error and exits non-zero."""
        rc = main(
            [
                "patterns",
                "deck",
                "--ids",
                "999999",
                "-o",
                str(tmp_path / "empty"),
                "--quiet",
            ]
        )
        assert rc != 0
        err = capsys.readouterr().err
        assert "no sidecared patterns" in err.lower()

    def test_deck_invalid_ids_string_exits_nonzero(self, capsys, tmp_path: Path) -> None:
        """`--ids` must be a comma-separated integer list."""
        rc = main(
            [
                "patterns",
                "deck",
                "--ids",
                "swot,bmc",  # slugs are not allowed here
                "-o",
                str(tmp_path / "bad"),
                "--quiet",
            ]
        )
        assert rc != 0
        err = capsys.readouterr().err
        assert "--ids" in err
