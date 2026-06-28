from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image


def _load_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "framegraph_golden_harness",
        Path(__file__).resolve().parents[1] / "run_tests.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compare_accepts_sparse_high_intensity_antialias_drift() -> None:
    harness = _load_harness()
    golden = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
    current = golden.copy()
    current.putpixel((50, 50), (255, 255, 255, 255))

    passed, max_delta, mean_delta_pct = harness.compare(current, golden, 1.0)

    assert passed is True
    assert max_delta == 255.0
    assert mean_delta_pct == pytest.approx(0.01)


def test_compare_rejects_broad_low_intensity_drift() -> None:
    harness = _load_harness()
    golden = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
    current = Image.new("RGBA", (100, 100), (4, 4, 4, 255))

    passed, max_delta, mean_delta_pct = harness.compare(current, golden, 1.0)

    assert passed is False
    assert max_delta == 4.0
    assert mean_delta_pct == pytest.approx(4 / 255 * 100)
