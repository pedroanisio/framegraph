"""Pin the inline-color + arrowhead marker-registration contract.

Context: a debug writeup claimed that a PDF render failed with
``'NoneType' object has no attribute 'get'`` because the renderer
omitted to register the `<marker>` for an edge whose stroke used an
inline theme-token color (`stroke: {color: accent_warm, …}`) with
`arrow_end: true`. Direct investigation at HEAD failed to reproduce
the failure — the renderer registers the marker correctly on this
path via `FrameGraphRenderer.stroke_attrs` (framegraph/renderer.py).

These tests *pin that contract* so the failure mode the writeup
described cannot silently regress. They assert:

  1. An inline-color stroke with the default `filled_triangle`
     arrowhead registers `ah-<HEX>` in `<defs>` and the body
     reference resolves.
  2. The same shape with a non-default kind (`open_arrow`) registers
     `ah-<HEX>-<kind>` and the body reference resolves.
  3. Multiple edges sharing the same inline color register the marker
     exactly once.
  4. Every `url(#ah-…)` reference emitted in the SVG body has a
     matching `<marker id="ah-…">` in `<defs>` (no dangling refs).

The last invariant is the load-bearing one: cairosvg crashes on
unresolved `url(#…)` references, so any future drift between the
URL-emission path and the marker-registration path is caught here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary

ROOT = Path(__file__).resolve().parents[2]
LIB_PATH = ROOT / "framegraph" / "lib"


def _deck_with_inline_color_edge(arrow_kind: str, color_token: str = "accent_warm") -> dict:
    """Build a minimal deck whose one connector uses an inline-token-color stroke.

    `accent_warm` resolves to `#E35205` under the McKinsey theme — the
    same color the original writeup blamed.
    """
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {"canvas": {"size": [1920, 1080]}},
        "slides": [
            {
                "id": "only",
                "title": "marker registration",
                "visual": {
                    "layers": [
                        {
                            "id": "scene",
                            "z": 10,
                            "objects": [
                                {
                                    "type": "rect",
                                    "id": "a",
                                    "box": [100, 200, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                {
                                    "type": "rect",
                                    "id": "b",
                                    "box": [600, 200, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                {
                                    "type": "connector",
                                    "id": "e1",
                                    "from": {"object": "a", "side": "east"},
                                    "to": {"object": "b", "side": "west"},
                                    "stroke": {
                                        "color": color_token,
                                        "width": 1.6,
                                        "arrow_end": True,
                                        "arrow_end_kind": arrow_kind,
                                    },
                                },
                            ],
                        }
                    ]
                },
            }
        ],
    }


@pytest.fixture(scope="module")
def lib() -> FrameGraphLibrary:
    return FrameGraphLibrary(LIB_PATH)


def _render(deck: dict, lib: FrameGraphLibrary, tmp_path: Path) -> str:
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    paths = renderer.render_all(tmp_path)
    return paths[0].read_text(encoding="utf-8")


def _marker_ids_in_defs(svg: str) -> set[str]:
    return set(re.findall(r'<marker id="(ah-[A-Za-z0-9_-]+)"', svg))


def _marker_url_refs_in_body(svg: str) -> set[str]:
    return set(re.findall(r"url\(#(ah-[A-Za-z0-9_-]+)\)", svg))


def test_inline_color_filled_triangle_registers_marker(
    lib: FrameGraphLibrary, tmp_path: Path
) -> None:
    """`stroke: {color: accent_warm}` with default `filled_triangle` arrowhead.

    The marker `ah-E35205` must appear in `<defs>` AND the body
    reference must point to it. This is the exact path the original
    writeup blamed for a cairosvg crash.
    """
    svg = _render(_deck_with_inline_color_edge("filled_triangle"), lib, tmp_path)
    defs = _marker_ids_in_defs(svg)
    refs = _marker_url_refs_in_body(svg)

    assert "ah-E35205" in defs, (
        f"Marker `ah-E35205` for inline color `accent_warm` (#E35205) "
        f"is missing from <defs>. Available: {sorted(defs)}"
    )
    assert "ah-E35205" in refs, (
        f"Body did not emit `url(#ah-E35205)` reference. Refs: {sorted(refs)}"
    )


def test_inline_color_open_arrow_registers_marker(lib: FrameGraphLibrary, tmp_path: Path) -> None:
    """Same as above with a non-default arrow kind.

    Non-default kinds use the `<HEX>-<kind>` id suffix. The renderer's
    `register_marker_kind` must be invoked on the inline-color path
    too, not just for stroke-style refs.
    """
    svg = _render(_deck_with_inline_color_edge("open_arrow"), lib, tmp_path)
    defs = _marker_ids_in_defs(svg)
    refs = _marker_url_refs_in_body(svg)

    assert "ah-E35205-open_arrow" in defs, (
        f"Marker `ah-E35205-open_arrow` (non-default kind, inline color) "
        f"is missing from <defs>. Available: {sorted(defs)}"
    )
    assert "ah-E35205-open_arrow" in refs, (
        f"Body did not emit `url(#ah-E35205-open_arrow)` reference. Refs: {sorted(refs)}"
    )


def test_every_body_marker_ref_has_matching_def(lib: FrameGraphLibrary, tmp_path: Path) -> None:
    """The load-bearing invariant: no dangling `url(#ah-…)` in the SVG.

    Cairosvg crashes on unresolved marker URLs with messages like
    ``'NoneType' object has no attribute 'get'`` — exactly the failure
    mode the original writeup described. Even though the writeup's
    specific scenario didn't reproduce, this test guards the general
    invariant: every body reference resolves to a defs entry.

    Exercises four edges (two arrow kinds × two inline colors) so the
    coverage isn't a single happy path.
    """
    deck = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {"canvas": {"size": [1920, 1080]}},
        "slides": [
            {
                "id": "only",
                "title": "marker integrity",
                "visual": {
                    "layers": [
                        {
                            "id": "scene",
                            "z": 10,
                            "objects": [
                                {
                                    "type": "rect",
                                    "id": "a",
                                    "box": [100, 100, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                {
                                    "type": "rect",
                                    "id": "b",
                                    "box": [600, 100, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                # accent_warm + filled_triangle
                                {
                                    "type": "connector",
                                    "id": "e_aw_ft",
                                    "from": {"object": "a", "side": "east"},
                                    "to": {"object": "b", "side": "west"},
                                    "stroke": {
                                        "color": "accent_warm",
                                        "arrow_end": True,
                                        "arrow_end_kind": "filled_triangle",
                                    },
                                },
                                # accent_warm + open_arrow
                                {
                                    "type": "connector",
                                    "id": "e_aw_oa",
                                    "from": {"object": "a", "side": "south"},
                                    "to": {"object": "b", "side": "south"},
                                    "stroke": {
                                        "color": "accent_warm",
                                        "arrow_end": True,
                                        "arrow_end_kind": "open_arrow",
                                    },
                                },
                                # secondary + filled_triangle (different inline color)
                                {
                                    "type": "connector",
                                    "id": "e_sec_ft",
                                    "from": {"object": "a", "side": "north"},
                                    "to": {"object": "b", "side": "north"},
                                    "stroke": {
                                        "color": "secondary",
                                        "arrow_end": True,
                                        "arrow_end_kind": "filled_triangle",
                                    },
                                },
                                # secondary + hollow_triangle (another non-default kind)
                                {
                                    "type": "connector",
                                    "id": "e_sec_ht",
                                    "from": {"object": "b", "side": "north"},
                                    "to": {"object": "a", "side": "north"},
                                    "stroke": {
                                        "color": "secondary",
                                        "arrow_end": True,
                                        "arrow_end_kind": "hollow_triangle",
                                    },
                                },
                            ],
                        }
                    ]
                },
            }
        ],
    }
    svg = _render(deck, lib, tmp_path)
    defs = _marker_ids_in_defs(svg)
    refs = _marker_url_refs_in_body(svg)

    dangling = refs - defs
    assert not dangling, (
        f"SVG body references markers that are not in <defs>: {sorted(dangling)}. "
        f"This is the exact failure mode that causes cairosvg to crash with "
        f"`'NoneType' object has no attribute 'get'` during PDF rendering. "
        f"Defs available: {sorted(defs)}"
    )

    # Sanity: the test must actually exercise multiple markers — if all
    # four edges resolved to the same marker, the dangling-ref check
    # would be vacuous on a single happy path.
    assert len(refs) >= 3, (
        f"Expected ≥3 distinct marker references across the 4 edges; got "
        f"{sorted(refs)}. The test no longer exercises the diversity it claims to."
    )


def test_inline_color_marker_registered_once(lib: FrameGraphLibrary, tmp_path: Path) -> None:
    """N edges with the same inline color register the marker exactly once.

    Defensive guard: the `stroke_attrs` escape hatch
    (`if color not in self.marker_colors: self.marker_colors.append(...)`)
    is idempotent in code today. This test pins that idempotence —
    converting it to e.g. `marker_colors.append(color)` without the
    membership check would emit duplicate `<marker>` entries and
    cairosvg may or may not tolerate that.
    """
    deck = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "$theme": "mckinsey",
        "deck": {"canvas": {"size": [1920, 1080]}},
        "slides": [
            {
                "id": "only",
                "title": "marker idempotence",
                "visual": {
                    "layers": [
                        {
                            "id": "scene",
                            "z": 10,
                            "objects": [
                                {
                                    "type": "rect",
                                    "id": "a",
                                    "box": [100, 100, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                {
                                    "type": "rect",
                                    "id": "b",
                                    "box": [600, 100, 200, 100],
                                    "fill": "panel",
                                    "stroke": {"color": "border"},
                                },
                                # Three edges with the SAME inline color +
                                # SAME arrowhead kind.
                                {
                                    "type": "connector",
                                    "id": "e1",
                                    "from": {"object": "a", "side": "east"},
                                    "to": {"object": "b", "side": "west"},
                                    "stroke": {
                                        "color": "accent_warm",
                                        "arrow_end": True,
                                    },
                                },
                                {
                                    "type": "connector",
                                    "id": "e2",
                                    "from": {"object": "a", "side": "south"},
                                    "to": {"object": "b", "side": "south"},
                                    "stroke": {
                                        "color": "accent_warm",
                                        "arrow_end": True,
                                    },
                                },
                                {
                                    "type": "connector",
                                    "id": "e3",
                                    "from": {"object": "a", "side": "north"},
                                    "to": {"object": "b", "side": "north"},
                                    "stroke": {
                                        "color": "accent_warm",
                                        "arrow_end": True,
                                    },
                                },
                            ],
                        }
                    ]
                },
            }
        ],
    }
    svg = _render(deck, lib, tmp_path)
    # Count occurrences of the marker id in <defs>.
    n = len(re.findall(r'<marker id="ah-E35205"', svg))
    assert n == 1, (
        f"Marker `ah-E35205` was emitted {n} times in <defs>; expected exactly 1. "
        f"Duplicate marker definitions indicate the inline-color escape hatch "
        f"lost its idempotence."
    )
