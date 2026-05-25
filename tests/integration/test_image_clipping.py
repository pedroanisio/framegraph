"""Integration coverage for clipped image rendering."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from framegraph import FrameGraphDeckRenderer


def test_deck_render_embeds_relative_image_with_ellipse_clip(tmp_path: Path) -> None:
    """Deck rendering composes relative image embedding with SVG clipping."""
    deck_dir = tmp_path / "deck_root"
    deck_dir.mkdir()
    asset = deck_dir / "portrait.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n")

    deck_yaml = deck_dir / "deck.yml"
    deck_yaml.write_text(
        yaml.dump(
            {
                "slides": [
                    {
                        "slide": 1,
                        "id": "s1",
                        "visual": {
                            "layers": [
                                {
                                    "id": "L",
                                    "objects": [
                                        {
                                            "type": "image",
                                            "id": "portrait",
                                            "box": [10, 20, 48, 48],
                                            "href": "portrait.png",
                                            "clip": "ellipse",
                                            "preserve_aspect_ratio": "xMidYMid slice",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    deck = FrameGraphDeckRenderer(yaml.safe_load(deck_yaml.read_text(encoding="utf-8")))
    paths = deck.render_all(tmp_path / "out", yaml_source_dir=deck_dir)

    assert len(paths) == 1
    svg = paths[0].read_text(encoding="utf-8")
    ET.fromstring(svg)
    assert "data:image/png;base64," in svg
    assert 'href="portrait.png"' not in svg
    assert '<clipPath id="clip_portrait_10_20_48_48">' in svg
    assert '<ellipse cx="34" cy="44" rx="24" ry="24"/>' in svg
    assert 'clip-path="url(#clip_portrait_10_20_48_48)"' in svg
    assert 'preserveAspectRatio="xMidYMid slice"' in svg
