from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_ebnf.py"
GRAMMAR = ROOT / "docs" / "framegraph.ebnf"
MAKEFILE = ROOT / "Makefile"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_ebnf", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_ebnf_is_deterministic_and_lists_document_roots() -> None:
    generator = _load_generator()

    first = generator.generate()
    second = generator.generate()

    assert first == second
    assert "framegraph-document = Document | DeckDocument | FrameSetDocument ;" in first
    assert "VisualObject =" in first


def test_committed_ebnf_matches_live_schema() -> None:
    generator = _load_generator()

    assert GRAMMAR.read_text(encoding="utf-8") == generator.generate()


def test_generate_ebnf_check_detects_stale_output(tmp_path: Path) -> None:
    generator = _load_generator()
    stale = tmp_path / "framegraph.ebnf"
    stale.write_text("stale\n", encoding="utf-8")

    assert generator.main(["--check", "-o", str(stale)]) == 1

    stale.write_text(generator.generate(), encoding="utf-8")

    assert generator.main(["--check", "-o", str(stale)]) == 0


def test_make_check_runs_ebnf_drift_gate() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "ebnf-check" in makefile
    assert "check: lint typecheck test ebnf-check goldens validate-fills" in makefile
