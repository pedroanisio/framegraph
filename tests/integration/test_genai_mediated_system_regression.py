"""Regression tests for the genai_mediated_system_v2* fixtures.

These two fixtures were the *only* documents in the corpus that exposed
the v2.0 modular-split regression at the visual level: their goldens
were captured while `r.text_svg` and `r.render_rect` were silently
failing, so the goldens themselves were missing the inner text of
nested containers, all chip-row labels, and the legend rect-samples.

The goldens were re-blessed alongside commit `1bc5547` (modular-split
repair) and a follow-up bless. This test locks the *content* invariant
the rebless represents — namely that every label that the regression
used to drop now appears in the rendered SVG.

A pure pixel-diff golden test would catch a re-emerged regression but
would not explain *what* broke. Asserting on string presence makes the
failure mode legible: a missing label here points directly at the
modular-split contract, not at any incidental drift.
"""

from __future__ import annotations

import html
from pathlib import Path

import pytest
import yaml

from framegraph import FrameGraphRenderer

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _appears_in_svg(needle: str, svg: str) -> bool:
    """`needle` is present in `svg` either literally or HTML-escaped.

    The renderer escapes `&`, `<`, `>`, `"`, `'` per `html.escape`.
    Test assertions express the user-facing label; the SVG contains
    the escaped form. Compare both.
    """
    return needle in svg or html.escape(needle, quote=True) in svg


# ── Strings the modular-split regression used to drop ───────────────
#
# Every label below sits inside a structure that depends on r.text_svg
# (text-inside-container or chip-row item) or r.render_rect (legend
# rect-sample). If any of these strings disappears from the SVG, the
# regression has likely returned.

CONTAINER_HEADINGS = (
    "Humans",
    "Systems",
    "GenAI Systems",
    "Foundation Model",
    "Training & Knowledge Sources",
    "Reasoning & Planning",
    "Execution Interfaces",
    "Interaction & Context",
)

CHIP_LABELS = (
    "intent",     # actors.humans chip row
    "agents",     # actors.genai_systems chip row
    "tools",      # execution interfaces chip row
)

LEGEND_LABELS = (
    "direct mediation flow",
    "GenAI-to-GenAI recursive loop",
    "dependency / grounding relationship",
    "cross-cutting control layer",
)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "framegraph_genai_mediated_system_v2.yml",
        "framegraph_genai_mediated_system_v2.1.yml",
    ],
    ids=["v2", "v2.1"],
)
def test_genai_fixture_renders_container_headings(fixture_name: str) -> None:
    """Container-headings — `r.text_svg` from `render_text_object` inside containers.

    These are the section labels nested inside the actor / orchestration /
    substrate containers. The modular-split regression dropped every text
    object whose render path resolved through `r.text_svg`.
    """
    doc = yaml.safe_load(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    )
    svg = FrameGraphRenderer(doc).render_svg()
    missing = [s for s in CONTAINER_HEADINGS if not _appears_in_svg(s, svg)]
    assert not missing, (
        f"{fixture_name}: container headings missing from SVG — "
        f"likely modular-split regression: {missing!r}"
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "framegraph_genai_mediated_system_v2.yml",
        "framegraph_genai_mediated_system_v2.1.yml",
    ],
    ids=["v2", "v2.1"],
)
def test_genai_fixture_renders_chip_row_items(fixture_name: str) -> None:
    """`chip_row` items — text emitted by `_text_svg_helper`.

    The regression dropped the per-chip text labels because layout's
    helper called the missing `r.text_svg`. After the repair every
    chip's text appears in the SVG.
    """
    doc = yaml.safe_load(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    )
    svg = FrameGraphRenderer(doc).render_svg()
    missing = [s for s in CHIP_LABELS if not _appears_in_svg(s, svg)]
    assert not missing, (
        f"{fixture_name}: chip-row labels missing from SVG: {missing!r}"
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "framegraph_genai_mediated_system_v2.yml",
        "framegraph_genai_mediated_system_v2.1.yml",
    ],
    ids=["v2", "v2.1"],
)
def test_genai_fixture_renders_legend_labels(fixture_name: str) -> None:
    """Legend labels — text emitted alongside legend samples.

    Legend items combine `r.render_rect` (or `r.line_svg`) for the swatch
    with `r.text_svg` for the label. Both legs of the regression are
    exercised here; if either reverts, the legend label disappears.
    """
    doc = yaml.safe_load(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    )
    svg = FrameGraphRenderer(doc).render_svg()
    missing = [s for s in LEGEND_LABELS if not _appears_in_svg(s, svg)]
    assert not missing, (
        f"{fixture_name}: legend labels missing from SVG: {missing!r}"
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "framegraph_genai_mediated_system_v2.yml",
        "framegraph_genai_mediated_system_v2.1.yml",
    ],
    ids=["v2", "v2.1"],
)
def test_genai_fixture_emits_minimum_text_object_count(fixture_name: str) -> None:
    """Coarse structural floor on emitted `<text>` elements.

    A re-emergence of the modular-split regression would manifest as a
    sharp drop in the number of `<text>` elements — `r.text_svg` calls
    that used to silently return empty would no longer contribute.
    50 is well below the current count (>100) but well above what the
    pre-fix output produced.
    """
    doc = yaml.safe_load(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    )
    svg = FrameGraphRenderer(doc).render_svg()
    text_count = svg.count("<text")
    assert text_count >= 50, (
        f"{fixture_name}: only {text_count} `<text>` elements emitted — "
        "modular-split regression suspected"
    )
