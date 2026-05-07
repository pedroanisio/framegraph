"""Integration test: the faz-ai-manifesto YAML renders with HD polish wired.

This test pins the *structural* HD wiring of the manifesto artifact —
shadow filters on every card, glow filter on the star moment, hairline
guard active, render hints on root — without coupling to byte-exact
pixel output. The artifact itself is allowed to evolve; what cannot
regress is the HD primitive surface it depends on.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from framegraph.renderer import FrameGraphRenderer

MANIFESTO_YML = Path(__file__).resolve().parents[2] / "static" / "fixture" / "faz-ai-manifesto.yml"


def test_manifesto_yml_exists() -> None:
    assert MANIFESTO_YML.exists(), f"manifesto fixture missing at {MANIFESTO_YML}"


def test_manifesto_renders_with_hd_root_hints() -> None:
    """Rendered manifesto must have HD render hints on the <svg> root."""
    renderer = FrameGraphRenderer.from_yaml_file(MANIFESTO_YML)
    svg = renderer.render_svg()
    root = ET.fromstring(svg)
    assert root.attrib.get("shape-rendering") == "geometricPrecision"
    assert root.attrib.get("text-rendering") == "optimizeLegibility"


def test_manifesto_emits_card_shadow_filter() -> None:
    """Every card carries a shadow filter; one shared <filter> def covers all."""
    renderer = FrameGraphRenderer.from_yaml_file(MANIFESTO_YML)
    svg = renderer.render_svg()
    # 10 cards → at least 10 filter= references on the bg rects
    # (plus the star ring's glow → at least 11 total)
    assert svg.count("filter=") >= 11
    # Shadow filter def is present and shared across cards
    assert svg.count("fg-fx-sh_") >= 11  # 10 references + 1 def


def test_manifesto_emits_star_glow_filter() -> None:
    """The star moment uses a glow primitive (not a plain stroked ring)."""
    renderer = FrameGraphRenderer.from_yaml_file(MANIFESTO_YML)
    svg = renderer.render_svg()
    assert "fg-fx-gl_" in svg, "star moment should use glow filter"


def test_manifesto_hairline_guard_promotes_thin_strokes() -> None:
    """Hairline guard is opted in; no stroke renders below 0.75 px."""
    renderer = FrameGraphRenderer.from_yaml_file(MANIFESTO_YML)
    svg = renderer.render_svg()
    # The pre-HD manifesto used 0.5 px strokes; with the guard on, none should remain
    assert 'stroke-width="0.5"' not in svg
    # And the promoted value should be visible
    assert 'stroke-width="0.75"' in svg


def test_manifesto_well_formed_xml_after_hd_polish() -> None:
    """The HD-polished manifesto remains valid XML."""
    renderer = FrameGraphRenderer.from_yaml_file(MANIFESTO_YML)
    svg = renderer.render_svg()
    # Throws on malformed XML
    ET.fromstring(svg)
    assert svg.rstrip().endswith("</svg>")
