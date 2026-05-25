from framegraph import FrameGraphRenderer


def test_inline_markdown_text_preserves_hard_line_breaks_in_rendered_svg() -> None:
    doc = {
        "dsl": "FrameGraph",
        "version": "1.5",
        "kind": "diagram",
        "scene": {"id": "rich_text_newlines", "canvas": {"size": [400, 220]}},
        "tokens": {
            "colors": {"ink": "#10002B"},
            "fonts": {"primary": "Arial, sans-serif"},
        },
        "visual": {
            "layers": [
                {
                    "id": "content",
                    "objects": [
                        {
                            "type": "text",
                            "id": "rich",
                            "text": "**Lead phrase** continues\nsecond **bold** line",
                            "box": [20, 20, 320, 120],
                            "style": {
                                "font": "primary",
                                "size": 16,
                                "weight": 400,
                                "color": "ink",
                                "line_height": 20,
                                "wrap": True,
                                "v_align": "top",
                            },
                        }
                    ],
                }
            ]
        },
    }

    svg = FrameGraphRenderer(doc).render_svg()

    assert svg.count('x="20" dy=') == 2
    assert 'font-weight="bold">Lead phrase</tspan>' in svg
    assert "second" in svg
    assert 'font-weight="bold"> bold</tspan>' in svg
