#!/usr/bin/env python3
"""
SP-6: FrameGraph golden-snapshot test harness.

Usage
-----
  # Bless current output as golden (first run, or after intentional change):
  python tests/run_tests.py --bless

  # Run regression suite:
  python tests/run_tests.py

  # Show per-pixel diff details on failures:
  python tests/run_tests.py --verbose

  # Override pixel tolerance (default: 1.0%):
  python tests/run_tests.py --tolerance 2.0

Exit codes: 0 = all pass, 1 = failures, 2 = configuration error.

Architecture
------------
- Fixtures: tests/fixtures/*.yml  (standalone FG docs or deck.yml files)
- Goldens:  tests/goldens/<fixture_stem>/<slide_id>.png  (2× rasterised)
- Tolerance: tests/tolerance.cfg  (single float, %)
- Renderer:  framegraph.renderer.FrameGraphRenderer (standalone docs)
             or framegraph.library.FrameGraphDeckRenderer (deck.yml files)

The harness rasterises at 2× scale (1920×1080 for 960×540 canvas) via
cairosvg, then computes the per-channel max delta across all pixels.
A slide passes if max_delta / 255 <= tolerance / 100.
"""

from __future__ import annotations

import argparse
import configparser
import importlib.util
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

# ── Dependency check ─────────────────────────────────────────────────────────
try:
    import cairosvg
except ImportError:
    print(
        "ERROR: cairosvg not found.  pip install cairosvg --break-system-packages", file=sys.stderr
    )
    sys.exit(2)

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print(
        "ERROR: Pillow + numpy required.  pip install Pillow numpy --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(2)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDENS_DIR = Path(__file__).parent / "goldens"
TOLERANCE_CFG = Path(__file__).parent / "tolerance.cfg"
RENDERER_PATH = REPO_ROOT / "framegraph" / "renderer.py"
LIBRARY_PATH = REPO_ROOT / "framegraph" / "library.py"
LIB_TOKENS = REPO_ROOT / "framegraph" / "lib"

SCALE = 2  # rasterisation scale factor


# ── Load modules lazily ───────────────────────────────────────────────────────
_renderer_mod = None
_library_mod = None


def _load_renderer():
    global _renderer_mod
    if _renderer_mod is None:
        spec = importlib.util.spec_from_file_location("fg_renderer", RENDERER_PATH)
        _renderer_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_renderer_mod)
    return _renderer_mod


def _load_library():
    global _library_mod
    if _library_mod is None:
        spec = importlib.util.spec_from_file_location("fg_library", LIBRARY_PATH)
        _library_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_library_mod)
    return _library_mod


# ── Tolerance ─────────────────────────────────────────────────────────────────
DEFAULT_TOLERANCE = 1.0  # percent


def load_tolerance() -> float:
    if TOLERANCE_CFG.exists():
        cfg = configparser.ConfigParser()
        cfg.read(TOLERANCE_CFG)
        try:
            return float(cfg["harness"]["tolerance"])
        except (KeyError, ValueError):
            pass
    return DEFAULT_TOLERANCE


def save_tolerance(t: float) -> None:
    cfg = configparser.ConfigParser()
    cfg["harness"] = {"tolerance": str(t)}
    TOLERANCE_CFG.write_text(
        configparser.ConfigParser.__module__ and cfg.write(io.StringIO()) or ""
    )
    # write properly
    with open(TOLERANCE_CFG, "w") as f:
        cfg.write(f)


# ── SVG rendering ─────────────────────────────────────────────────────────────
@dataclass
class RenderedSlide:
    slide_id: str
    svg: str
    width: int
    height: int


def render_fixture(path: Path) -> list[RenderedSlide]:
    """Return a list of RenderedSlide for a fixture file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    kind = data.get("kind", "")
    results: list[RenderedSlide] = []

    if kind == "presentation-deck":
        lib = _load_library()
        FGL = lib.FrameGraphLibrary
        FGDR = lib.FrameGraphDeckRenderer
        library = FGL(LIB_TOKENS)
        deck = FGDR(data, library=library)
        for slide in deck.slides_raw:
            doc = deck.build_slide_doc(slide)
            FGR = _load_renderer().FrameGraphRenderer
            svg = FGR(doc).render_svg()
            canvas = doc.get("scene", {}).get("canvas", {})
            w, h = canvas.get("size", [960, 540])
            results.append(
                RenderedSlide(
                    slide_id=slide.get("id", f"slide_{slide.get('slide', 0):02d}"),
                    svg=svg,
                    width=w,
                    height=h,
                )
            )
    else:
        FGR = _load_renderer().FrameGraphRenderer
        renderer = FGR(data)
        renderer.yaml_source_dir = str(path.parent.resolve())
        svg = renderer.render_svg()
        canvas = data.get("scene", {}).get("canvas", {})
        w, h = canvas.get("size", [960, 540])
        scene_id = data.get("scene", {}).get("id", path.stem)
        results.append(
            RenderedSlide(
                slide_id=scene_id,
                svg=svg,
                width=w,
                height=h,
            )
        )

    return results


# ── Rasterisation ─────────────────────────────────────────────────────────────
def rasterise(svg: str, width: int, height: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=width * SCALE,
        output_height=height * SCALE,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


# ── Comparison ────────────────────────────────────────────────────────────────
@dataclass
class SlideResult:
    fixture: str
    slide_id: str
    passed: bool
    max_delta: float  # 0–255
    tolerance: float  # percent
    elapsed_ms: float
    error: str | None = None

    @property
    def pct_delta(self) -> float:
        return self.max_delta / 255 * 100

    @property
    def tolerance_px(self) -> float:
        return self.tolerance / 100 * 255


def compare(
    img_new: Image.Image, img_golden: Image.Image, tolerance_pct: float
) -> tuple[bool, float]:
    arr_new = np.asarray(img_new, dtype=np.int32)
    arr_golden = np.asarray(img_golden, dtype=np.int32)
    if arr_new.shape != arr_golden.shape:
        # Size mismatch — always fails
        return False, 255.0
    diff = np.abs(arr_new - arr_golden)
    max_delta = float(diff.max())
    passed = (max_delta / 255 * 100) <= tolerance_pct
    return passed, max_delta


# ── Bless ─────────────────────────────────────────────────────────────────────
def bless_fixture(path: Path, verbose: bool = False) -> int:
    """Render fixture and write goldens. Returns number of slides blessed."""
    slides = render_fixture(path)
    golden_dir = GOLDENS_DIR / path.stem
    golden_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for sl in slides:
        img = rasterise(sl.svg, sl.width, sl.height)
        out = golden_dir / f"{sl.slide_id}.png"
        img.save(out, "PNG")
        if verbose:
            print(f"  blessed  {out.relative_to(GOLDENS_DIR.parent)}")
        count += 1
    return count


# ── Test run ──────────────────────────────────────────────────────────────────
def test_fixture(path: Path, tolerance_pct: float, verbose: bool) -> list[SlideResult]:
    results: list[SlideResult] = []
    golden_dir = GOLDENS_DIR / path.stem

    try:
        t0 = time.perf_counter()
        slides = render_fixture(path)
        elapsed_total = (time.perf_counter() - t0) * 1000
    except Exception as e:
        results.append(
            SlideResult(
                fixture=path.name,
                slide_id="(render error)",
                passed=False,
                max_delta=255,
                tolerance=tolerance_pct,
                elapsed_ms=0,
                error=str(e),
            )
        )
        return results

    per_slide_ms = elapsed_total / max(len(slides), 1)

    for sl in slides:
        golden_path = golden_dir / f"{sl.slide_id}.png"
        if not golden_path.exists():
            results.append(
                SlideResult(
                    fixture=path.name,
                    slide_id=sl.slide_id,
                    passed=False,
                    max_delta=255,
                    tolerance=tolerance_pct,
                    elapsed_ms=per_slide_ms,
                    error="No golden found — run with --bless first",
                )
            )
            continue

        try:
            img_new = rasterise(sl.svg, sl.width, sl.height)
            img_golden = Image.open(golden_path).convert("RGBA")
            passed, max_delta = compare(img_new, img_golden, tolerance_pct)
        except Exception as e:
            results.append(
                SlideResult(
                    fixture=path.name,
                    slide_id=sl.slide_id,
                    passed=False,
                    max_delta=255,
                    tolerance=tolerance_pct,
                    elapsed_ms=per_slide_ms,
                    error=str(e),
                )
            )
            continue

        results.append(
            SlideResult(
                fixture=path.name,
                slide_id=sl.slide_id,
                passed=passed,
                max_delta=max_delta,
                tolerance=tolerance_pct,
                elapsed_ms=per_slide_ms,
            )
        )

        if verbose and not passed:
            print(
                f"  FAIL  {path.name}/{sl.slide_id}  "
                f"max_delta={max_delta:.1f}  "
                f"({max_delta / 255 * 100:.2f}% > {tolerance_pct:.2f}% tolerance)"
            )

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="FrameGraph golden-snapshot harness")
    parser.add_argument(
        "--bless", action="store_true", help="Write golden PNGs (overwrites existing)"
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-slide detail on failure")
    parser.add_argument(
        "--tolerance", type=float, default=None, help="Override tolerance %% (default: 1.0)"
    )
    parser.add_argument(
        "--fixture", type=str, default=None, help="Run only this fixture (stem or filename)"
    )
    args = parser.parse_args(argv)

    tolerance = args.tolerance if args.tolerance is not None else load_tolerance()
    GOLDENS_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = sorted(FIXTURES_DIR.glob("*.yml"))
    if not fixtures:
        print(f"ERROR: No fixtures found in {FIXTURES_DIR}", file=sys.stderr)
        return 2

    if args.fixture:
        stem = Path(args.fixture).stem
        fixtures = [f for f in fixtures if f.stem == stem]
        if not fixtures:
            print(f"ERROR: Fixture '{args.fixture}' not found", file=sys.stderr)
            return 2

    # ── Bless mode ───────────────────────────────────────────────────────────
    if args.bless:
        print(f"Blessing {len(fixtures)} fixture(s) at {SCALE}× scale…")
        total = 0
        t0 = time.perf_counter()
        for path in fixtures:
            n = bless_fixture(path, verbose=args.verbose)
            total += n
            print(f"  {path.name:<48} {n} slide(s) blessed")
        elapsed = time.perf_counter() - t0
        save_tolerance(tolerance)
        print(f"\n{total} golden(s) written in {elapsed:.2f}s  (tolerance set to {tolerance:.1f}%)")
        return 0

    # ── Test mode ────────────────────────────────────────────────────────────
    print(f"Running {len(fixtures)} fixture(s)  tolerance={tolerance:.1f}%  scale={SCALE}×")
    print()

    all_results: list[SlideResult] = []
    t0 = time.perf_counter()
    for path in fixtures:
        results = test_fixture(path, tolerance, args.verbose)
        all_results.extend(results)
        passes = sum(1 for r in results if r.passed)
        fails = sum(1 for r in results if not r.passed)
        avg_ms = sum(r.elapsed_ms for r in results) / max(len(results), 1)
        status = "PASS" if fails == 0 else "FAIL"
        print(f"  {status}  {path.name:<44}  {passes}/{len(results)} slides  {avg_ms:.0f}ms/slide")
        if args.verbose:
            for r in results:
                if not r.passed:
                    err = r.error or f"delta={r.max_delta:.1f} ({r.pct_delta:.2f}%)"
                    print(f"         ✗  {r.slide_id}  {err}")

    elapsed = time.perf_counter() - t0
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed

    print()
    print("─" * 64)
    print(
        f"  {'PASSED' if failed == 0 else 'FAILED'}  "
        f"{passed}/{total} slides  "
        f"wall time {elapsed:.2f}s"
    )

    if failed:
        print(f"\n  {failed} failure(s):")
        for r in all_results:
            if not r.passed:
                err = r.error or f"max delta {r.max_delta:.1f}px ({r.pct_delta:.2f}%)"
                print(f"    ✗  {r.fixture}/{r.slide_id}  — {err}")

    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
