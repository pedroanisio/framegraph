"""Image renderer clipping behavior."""

from __future__ import annotations

from framegraph import FrameGraphRenderer

ONE_PIXEL_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACwAAAAAAQABAAA="


def _render_image(obj: dict) -> str:
    return FrameGraphRenderer(
        {
            "visual": {
                "layers": [
                    {
                        "id": "L1",
                        "objects": [obj],
                    }
                ]
            }
        }
    ).render_svg()


def test_image_clip_ellipse_emits_clip_path_and_reference() -> None:
    svg = _render_image(
        {
            "type": "image",
            "id": "portrait",
            "href": ONE_PIXEL_GIF,
            "box": [10, 20, 40, 40],
            "clip": "ellipse",
        }
    )

    assert '<clipPath id="clip_portrait_10_20_40_40">' in svg
    assert '<ellipse cx="30" cy="40" rx="20" ry="20"/>' in svg
    assert 'clip-path="url(#clip_portrait_10_20_40_40)"' in svg


def test_image_clip_rect_honors_radius_and_keeps_outer_ring_unclipped() -> None:
    svg = _render_image(
        {
            "type": "image",
            "id": "rounded",
            "href": ONE_PIXEL_GIF,
            "box": [0, 0, 60, 30],
            "radius": 8,
            "clip": {"shape": "rect", "radius": 6},
            "outer_ring": {"color": "#7A2FB5", "width": 2, "gap": 1},
        }
    )

    assert '<rect x="0" y="0" width="60" height="30" rx="6" ry="6"/>' in svg
    assert 'clip-path="url(#clip_rounded_0_0_60_30)"' in svg
    assert svg.index('fill="none" stroke="#7A2FB5"') < svg.index("<image ")
