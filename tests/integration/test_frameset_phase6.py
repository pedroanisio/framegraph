"""Phase 6 of ADR 0001 — link injection tests.

Phase 6 ships:

- `framegraph._frameset._compute_frame_url(frame_id, target_name, *,
  base_url, file_template)` resolves a destination URL via either the
  sitemap-style `<base_url>/<target_name>/<frame_id>` pattern (Phase
  4 compatible) or a Python `str.format` template like
  `"slide_{frame_id}.svg"`.
- `framegraph._frameset.inject_svg_navigation_links(svg, frame,
  frameset, *, target_name, base_url=None, file_template=None)`
  wraps a rendered SVG's body in `<a href="...">` per `frame.next`.
  Click-anywhere-to-advance is the canonical deck-navigation
  contract; survives SVG → PDF (vector) and SVG → HTML embed.
- CLI: `framegraph render --link-base-url <url>` / `--link-template
  <template>` and `framegraph deck --link-base-url <url>` /
  `--link-template <template>`.

These tests pin:

1. URL computation: `_compute_frame_url` requires exactly one of
   `base_url` or `file_template`; both/neither raise; URL escapes
   reserved characters in the sitemap path.
2. Injection contract: with both URL inputs `None`, returns SVG
   unchanged (byte-identical regression). With `frame.next=None`,
   returns SVG unchanged.
3. Wrap shape: `<a href>` lands AFTER `<defs>` (or `<desc>` if no
   defs), `</a>` lands BEFORE `</svg>`. Title and desc stay outside
   the link so screen-readers pick them up first.
4. URL escaping: aria-label and href are XML-escaped via
   `xml.sax.saxutils.quoteattr`.
5. Output is well-formed XML — parses cleanly via ElementTree.
6. CLI: `--link-base-url` and `--link-template` produce expected
   `<a>` wrappers in the output SVGs; mutually exclusive flag check
   exits non-zero; deck path post-processes every per-slide SVG.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
import yaml

from framegraph._frameset import (
    _compute_frame_url,
    coerce_to_frameset,
    inject_svg_navigation_links,
    render_frameset,
    validate_frameset,
)
from framegraph.cli import main as cli_main

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _two_frame_fs(*, with_next: bool = True) -> Any:
    return validate_frameset(
        {
            "dsl": "FrameGraph",
            "version": 2.0,
            "kind": "frameset",
            "frames": [
                {
                    "id": "cover",
                    "title": "Cover",
                    "targets": [{"name": "t", "canvas": [400, 200]}],
                    "next": "agenda" if with_next else None,
                    "scene": {"id": "cover", "canvas": {"size": [400, 200]}},
                    "visual": {
                        "layers": [
                            {
                                "id": "main",
                                "objects": [
                                    {
                                        "type": "rect",
                                        "id": "r",
                                        "decorative": True,
                                        "box": [0, 0, 100, 100],
                                        "fill": "#000",
                                    }
                                ],
                            }
                        ]
                    },
                },
                {
                    "id": "agenda",
                    "title": "Agenda",
                    "targets": [{"name": "t", "canvas": [400, 200]}],
                    "scene": {"id": "agenda", "canvas": {"size": [400, 200]}},
                    "visual": {"layers": [{"id": "main", "objects": []}]},
                },
            ],
        }
    )


def _render_first(fs: Any) -> str:
    return render_frameset(fs)[0].svg


# ─────────────────────────────────────────────────────────────────
# _compute_frame_url
# ─────────────────────────────────────────────────────────────────


class TestComputeFrameUrl:
    def test_base_url_pattern(self) -> None:
        url = _compute_frame_url("agenda", "landscape", base_url="https://example.com/docs")
        assert url == "https://example.com/docs/landscape/agenda"

    def test_base_url_trailing_slash_normalised(self) -> None:
        a = _compute_frame_url("x", "t", base_url="https://example.com/docs/")
        b = _compute_frame_url("x", "t", base_url="https://example.com/docs")
        assert a == b

    def test_base_url_escapes_reserved_chars(self) -> None:
        url = _compute_frame_url("section a/b?c", "a4 print", base_url="https://example.com")
        assert url == "https://example.com/a4%20print/section%20a%2Fb%3Fc"

    def test_file_template(self) -> None:
        url = _compute_frame_url("agenda", "landscape", file_template="slide_{frame_id}.svg")
        assert url == "slide_agenda.svg"

    def test_file_template_with_target(self) -> None:
        url = _compute_frame_url(
            "agenda", "mobile", file_template="{target_name}/{frame_id}.svg"
        )
        assert url == "mobile/agenda.svg"

    def test_neither_raises(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            _compute_frame_url("x", "t")

    def test_both_raises(self) -> None:
        with pytest.raises(ValueError, match="at most one"):
            _compute_frame_url(
                "x", "t", base_url="https://example.com", file_template="x.svg"
            )

    def test_empty_base_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _compute_frame_url("x", "t", base_url="   ")

    def test_malformed_base_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a valid URL"):
            _compute_frame_url("x", "t", base_url="not-a-url")


# ─────────────────────────────────────────────────────────────────
# inject_svg_navigation_links — contract
# ─────────────────────────────────────────────────────────────────


class TestInjectSvgNavigationLinksContract:
    def test_no_url_inputs_returns_svg_unchanged(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(svg, fs.frames[0], fs, target_name="t")
        assert out == svg

    def test_no_next_returns_svg_unchanged(self) -> None:
        fs = _two_frame_fs(with_next=False)
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        assert out == svg

    def test_both_url_inputs_raises(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        with pytest.raises(ValueError, match="at most one"):
            inject_svg_navigation_links(
                svg,
                fs.frames[0],
                fs,
                target_name="t",
                base_url="https://example.com",
                file_template="x.svg",
            )

    def test_last_frame_has_no_next_so_unchanged(self) -> None:
        fs = _two_frame_fs()
        # Render the second frame (which has no `next`).
        svg = render_frameset(fs)[1].svg
        out = inject_svg_navigation_links(
            svg, fs.frames[1], fs, target_name="t", base_url="https://example.com"
        )
        assert out == svg


# ─────────────────────────────────────────────────────────────────
# inject_svg_navigation_links — wrap shape
# ─────────────────────────────────────────────────────────────────


class TestInjectSvgNavigationLinksShape:
    def test_base_url_produces_a_tag(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        assert '<a href="https://example.com/t/agenda"' in out

    def test_file_template_produces_a_tag(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", file_template="slide_{frame_id}.svg"
        )
        assert '<a href="slide_agenda.svg"' in out

    def test_aria_label_uses_target_title(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        assert 'aria-label="Next: Agenda"' in out

    def test_aria_label_falls_back_to_id_when_no_title(self) -> None:
        fs = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "a",
                        "next": "b",
                        "targets": [{"name": "t", "canvas": [400, 200]}],
                        "scene": {"id": "a", "canvas": {"size": [400, 200]}},
                        "visual": {"layers": [{"id": "main", "objects": []}]},
                    },
                    {
                        "id": "b",
                        # no title
                        "targets": [{"name": "t", "canvas": [400, 200]}],
                        "scene": {"id": "b", "canvas": {"size": [400, 200]}},
                        "visual": {"layers": [{"id": "main", "objects": []}]},
                    },
                ],
            }
        )
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        assert 'aria-label="Next: b"' in out

    def test_a_tag_lands_after_defs(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        # The `<a>` tag must come after `</defs>` (or `</desc>` when
        # no defs), and BEFORE the first `<g>` content layer.
        defs_close = out.rfind("</defs>")
        a_open = out.find("<a href=")
        first_g = out.find("<g ")
        assert defs_close < a_open < first_g

    def test_closing_a_lands_before_svg_end(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        a_close = out.rfind("</a>")
        svg_close = out.rfind("</svg>")
        assert a_close < svg_close
        # And no other closing tag between </a> and </svg>.
        assert out[a_close + 4 : svg_close].strip() == ""

    def test_title_and_desc_stay_outside_link(self) -> None:
        # Accessibility: <title> / <desc> must remain top-level
        # children of <svg>, not inside <a>.
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        title_pos = out.find("<title")
        a_pos = out.find("<a href=")
        assert title_pos < a_pos


# ─────────────────────────────────────────────────────────────────
# inject_svg_navigation_links — XML well-formedness
# ─────────────────────────────────────────────────────────────────


class TestInjectSvgNavigationLinksWellFormed:
    def test_parses_as_xml(self) -> None:
        fs = _two_frame_fs()
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        ET.fromstring(out)  # raises on malformed XML

    def test_special_chars_in_url_escaped(self) -> None:
        # Frame id with `&` must produce well-formed XML attribute.
        fs = validate_frameset(
            {
                "dsl": "FrameGraph",
                "version": 2.0,
                "kind": "frameset",
                "frames": [
                    {
                        "id": "a",
                        "next": "b&c",
                        "targets": [{"name": "t", "canvas": [400, 200]}],
                        "scene": {"id": "a", "canvas": {"size": [400, 200]}},
                        "visual": {"layers": [{"id": "main", "objects": []}]},
                    },
                    {
                        "id": "b&c",
                        "targets": [{"name": "t", "canvas": [400, 200]}],
                        "scene": {"id": "b&c", "canvas": {"size": [400, 200]}},
                        "visual": {"layers": [{"id": "main", "objects": []}]},
                    },
                ],
            }
        )
        svg = _render_first(fs)
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="t", base_url="https://example.com"
        )
        # XML must parse cleanly even with `&` in source data.
        ET.fromstring(out)
        # base_url path: `&` is URL-escaped to `%26`.
        assert "b%26c" in out


# ─────────────────────────────────────────────────────────────────
# Coerced inputs — works with deck and legacy single-doc YAML
# ─────────────────────────────────────────────────────────────────


class TestInjectSvgNavigationLinksCoerced:
    def test_coerced_deck_chains_next(self) -> None:
        # Decks coerce to FrameSets where slide order materialises
        # as a `next` chain. Click-to-advance just works.
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [400, 200]}},
            "slides": [
                {
                    "slide": 1,
                    "id": "s1",
                    "visual": {"layers": [{"id": "main", "objects": []}]},
                },
                {
                    "slide": 2,
                    "id": "s2",
                    "visual": {"layers": [{"id": "main", "objects": []}]},
                },
            ],
        }
        fs = coerce_to_frameset(deck)
        # Phase 2 deck-coerced FrameSets have `next` materialised.
        assert fs.frames[0].next == "s2"
        # render_frameset on coerced deck Frames — best-effort per
        # Phase 1/2 docs; this confirms link injection still wraps.
        svg = render_frameset(fs)[0].svg
        out = inject_svg_navigation_links(
            svg, fs.frames[0], fs, target_name="default", base_url="https://example.com"
        )
        assert '<a href="https://example.com/default/s2"' in out


# ─────────────────────────────────────────────────────────────────
# CLI — `framegraph render --link-base-url` / `--link-template`
# ─────────────────────────────────────────────────────────────────


def _two_frame_yaml(tmp_path: Path) -> Path:
    """Write a FrameSet YAML with two linked frames; return its path."""
    payload = {
        "dsl": "FrameGraph",
        "version": 2.0,
        "kind": "frameset",
        "frames": [
            {
                "id": "cover",
                "title": "Cover",
                "next": "agenda",
                "targets": [{"name": "t", "canvas": [400, 200]}],
                "scene": {"id": "cover", "canvas": {"size": [400, 200]}},
                "visual": {
                    "layers": [
                        {
                            "id": "main",
                            "objects": [
                                {
                                    "type": "rect",
                                    "id": "r",
                                    "decorative": True,
                                    "box": [0, 0, 100, 100],
                                    "fill": "#000",
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "id": "agenda",
                "title": "Agenda",
                "targets": [{"name": "t", "canvas": [400, 200]}],
                "scene": {"id": "agenda", "canvas": {"size": [400, 200]}},
                "visual": {"layers": [{"id": "main", "objects": []}]},
            },
        ],
    }
    path = tmp_path / "fs.yml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


class TestCliRenderLinks:
    def test_link_base_url_injects_a_tag(self, tmp_path: Path) -> None:
        in_path = _two_frame_yaml(tmp_path)
        out_path = tmp_path / "out.svg"
        rc = cli_main(
            [
                "render",
                str(in_path),
                "-o",
                str(out_path),
                "--target",
                "t",
                "--link-base-url",
                "https://example.com",
                "--quiet",
            ]
        )
        assert rc == 0
        body = out_path.read_text(encoding="utf-8")
        assert '<a href="https://example.com/t/agenda"' in body

    def test_link_template_injects_a_tag(self, tmp_path: Path) -> None:
        in_path = _two_frame_yaml(tmp_path)
        out_path = tmp_path / "out.svg"
        rc = cli_main(
            [
                "render",
                str(in_path),
                "-o",
                str(out_path),
                "--target",
                "t",
                "--link-template",
                "slide_{frame_id}.svg",
                "--quiet",
            ]
        )
        assert rc == 0
        body = out_path.read_text(encoding="utf-8")
        assert '<a href="slide_agenda.svg"' in body

    def test_link_flags_mutually_exclusive(self, tmp_path: Path) -> None:
        in_path = _two_frame_yaml(tmp_path)
        rc = cli_main(
            [
                "render",
                str(in_path),
                "-o",
                str(tmp_path / "out.svg"),
                "--target",
                "t",
                "--link-base-url",
                "https://example.com",
                "--link-template",
                "x.svg",
                "--quiet",
            ]
        )
        assert rc != 0

    def test_no_link_flags_no_a_tag(self, tmp_path: Path) -> None:
        in_path = _two_frame_yaml(tmp_path)
        out_path = tmp_path / "out.svg"
        rc = cli_main(
            [
                "render",
                str(in_path),
                "-o",
                str(out_path),
                "--target",
                "t",
                "--quiet",
            ]
        )
        assert rc == 0
        body = out_path.read_text(encoding="utf-8")
        assert "<a href=" not in body

    def test_invalid_base_url_returns_nonzero(self, tmp_path: Path) -> None:
        in_path = _two_frame_yaml(tmp_path)
        rc = cli_main(
            [
                "render",
                str(in_path),
                "-o",
                str(tmp_path / "out.svg"),
                "--target",
                "t",
                "--link-base-url",
                "not-a-url",
                "--quiet",
            ]
        )
        assert rc != 0


# ─────────────────────────────────────────────────────────────────
# CLI — `framegraph deck --link-base-url` / `--link-template`
# ─────────────────────────────────────────────────────────────────


def _two_slide_deck_yaml(tmp_path: Path) -> Path:
    deck = {
        "dsl": "FrameGraph",
        "version": 1.2,
        "kind": "presentation-deck",
        "deck": {"canvas": {"size": [400, 200]}},
        "slides": [
            {
                "slide": 1,
                "id": "intro",
                "visual": {
                    "layers": [
                        {
                            "id": "main",
                            "objects": [
                                {
                                    "type": "rect",
                                    "id": "r",
                                    "decorative": True,
                                    "box": [0, 0, 100, 100],
                                    "fill": "#000",
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "slide": 2,
                "id": "body",
                "visual": {"layers": [{"id": "main", "objects": []}]},
            },
        ],
    }
    path = tmp_path / "deck.yml"
    path.write_text(yaml.safe_dump(deck), encoding="utf-8")
    return path


class TestCliDeckLinks:
    def test_deck_link_base_url_injects_into_first_slide(self, tmp_path: Path) -> None:
        in_path = _two_slide_deck_yaml(tmp_path)
        out_dir = tmp_path / "out"
        rc = cli_main(
            [
                "deck",
                str(in_path),
                "-o",
                str(out_dir),
                "--link-base-url",
                "https://example.com",
                "--quiet",
            ]
        )
        assert rc == 0
        # Find the first slide's SVG and confirm it has the <a>.
        svgs = sorted(out_dir.glob("*.svg"))
        assert len(svgs) >= 2
        first = svgs[0].read_text(encoding="utf-8")
        assert '<a href="https://example.com/default/body"' in first

    def test_deck_last_slide_unchanged(self, tmp_path: Path) -> None:
        in_path = _two_slide_deck_yaml(tmp_path)
        out_dir = tmp_path / "out"
        rc = cli_main(
            [
                "deck",
                str(in_path),
                "-o",
                str(out_dir),
                "--link-base-url",
                "https://example.com",
                "--quiet",
            ]
        )
        assert rc == 0
        svgs = sorted(out_dir.glob("*.svg"))
        last = svgs[-1].read_text(encoding="utf-8")
        # Last slide has no `next`, so no <a> wrap.
        assert "<a href=" not in last

    def test_deck_link_flags_mutually_exclusive(self, tmp_path: Path) -> None:
        in_path = _two_slide_deck_yaml(tmp_path)
        rc = cli_main(
            [
                "deck",
                str(in_path),
                "-o",
                str(tmp_path / "out"),
                "--link-base-url",
                "https://example.com",
                "--link-template",
                "x.svg",
                "--quiet",
            ]
        )
        assert rc != 0

    def test_deck_no_link_flags_no_a_tag(self, tmp_path: Path) -> None:
        in_path = _two_slide_deck_yaml(tmp_path)
        out_dir = tmp_path / "out"
        rc = cli_main(
            ["deck", str(in_path), "-o", str(out_dir), "--quiet"]
        )
        assert rc == 0
        for p in out_dir.glob("*.svg"):
            assert "<a href=" not in p.read_text(encoding="utf-8")

    def test_deck_link_template(self, tmp_path: Path) -> None:
        in_path = _two_slide_deck_yaml(tmp_path)
        out_dir = tmp_path / "out"
        rc = cli_main(
            [
                "deck",
                str(in_path),
                "-o",
                str(out_dir),
                "--link-template",
                "slide_{frame_id}.svg",
                "--quiet",
            ]
        )
        assert rc == 0
        svgs = sorted(out_dir.glob("*.svg"))
        first = svgs[0].read_text(encoding="utf-8")
        assert '<a href="slide_body.svg"' in first
