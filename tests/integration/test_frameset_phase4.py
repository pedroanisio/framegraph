"""Phase 4 of ADR 0001 — sitemap emission tests.

Phase 4 ships:

- `framegraph._frameset.emit_sitemap(fs, base_url, *, target_filter=…)`
  walks the FrameSet's `frames` × per-Frame target set and emits a
  `sitemap.xml` document conforming to the sitemap.org 0.9 schema.
- `framegraph._frameset.list_frameset_target_union(fs)` enumerates
  the union of every declared target name (defaults + per-Frame).
- `framegraph sitemap <input.yml> --base-url <url> [-o <path>]
  [--target <name>]` CLI — accepts any FrameGraph YAML (frameset,
  deck, or legacy single-doc) by coercing through
  `coerce_to_frameset`.

These tests pin:

1. Output is well-formed XML and validates structurally against the
   sitemap.org 0.9 namespace.
2. URL pattern is ``<base_url>/<target>/<frame_id>``, with frame
   ids and target names URL-escaped via `urllib.parse.quote`.
3. Emission is deterministic: Frames walk in declaration order;
   per-Frame targets walk in declaration order; defaults supply
   the target set when a Frame has no per-Frame `targets:`.
4. `target_filter` constrains the emitted URL set to one or more
   named targets without changing the frame ordering.
5. `base_url` validation rejects empty / malformed prefixes.
6. CLI integration — `--base-url` is required; `-o` writes to file;
   omitting `-o` writes to stdout; `--target` filters; legacy and
   deck inputs work.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
import yaml

from framegraph._frameset import (
    coerce_to_frameset,
    emit_sitemap,
    list_frameset_target_union,
    validate_frameset,
)
from framegraph.cli import main as cli_main

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _native_frameset(frames: list[dict[str, Any]], **frameset_kwargs: Any) -> dict[str, Any]:
    """Build a minimal frameset YAML mapping for tests."""
    return {
        "dsl": "FrameGraph",
        "version": 2.0,
        "kind": "frameset",
        "frameset": frameset_kwargs or {},
        "frames": frames,
    }


def _parse_sitemap(xml: str) -> list[str]:
    """Return the list of `<loc>` text values, in document order."""
    root = ET.fromstring(xml)
    return [
        loc.text or ""
        for url in root.findall(f"{{{SITEMAP_NS}}}url")
        for loc in url.findall(f"{{{SITEMAP_NS}}}loc")
    ]


# ─────────────────────────────────────────────────────────────────
# list_frameset_target_union
# ─────────────────────────────────────────────────────────────────


class TestListFramesetTargetUnion:
    def test_defaults_only(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "a"}, {"id": "b"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        assert list_frameset_target_union(fs) == ["landscape"]

    def test_per_frame_targets_appended_in_order(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [
                    {"id": "a", "targets": [{"name": "portrait", "canvas": [1080, 1920]}]},
                    {"id": "b", "targets": [{"name": "mobile", "canvas": [375, 812]}]},
                ],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        assert list_frameset_target_union(fs) == ["landscape", "portrait", "mobile"]

    def test_no_targets_anywhere_yields_default(self) -> None:
        fs = validate_frameset(_native_frameset([{"id": "solo"}]))
        assert list_frameset_target_union(fs) == ["default"]

    def test_duplicates_dedup_first_seen(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [
                    {"id": "a", "targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
                    {"id": "b", "targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
                ],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        assert list_frameset_target_union(fs) == ["landscape"]


# ─────────────────────────────────────────────────────────────────
# emit_sitemap — happy path + structural invariants
# ─────────────────────────────────────────────────────────────────


class TestEmitSitemapStructure:
    def test_xml_prolog_and_namespace(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "f"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        out = emit_sitemap(fs, "https://example.com")
        assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
        root = ET.fromstring(out)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"

    def test_one_url_per_frame_target_pair(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [
                    {"id": "cover"},
                    {"id": "agenda"},
                ],
                defaults={
                    "targets": [
                        {"name": "landscape", "canvas": [1920, 1080]},
                        {"name": "mobile", "canvas": [375, 812]},
                    ]
                },
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert urls == [
            "https://example.com/landscape/cover",
            "https://example.com/mobile/cover",
            "https://example.com/landscape/agenda",
            "https://example.com/mobile/agenda",
        ]

    def test_per_frame_targets_override_defaults(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [
                    {"id": "cover"},
                    {
                        "id": "appendix",
                        "targets": [{"name": "portrait", "canvas": [1080, 1920]}],
                    },
                ],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert urls == [
            "https://example.com/landscape/cover",
            "https://example.com/portrait/appendix",
        ]

    def test_no_targets_anywhere_uses_default_label(self) -> None:
        fs = validate_frameset(_native_frameset([{"id": "solo"}]))
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert urls == ["https://example.com/default/solo"]

    def test_base_url_with_path_prefix(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "x"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com/docs"))
        assert urls == ["https://example.com/docs/landscape/x"]

    def test_base_url_trailing_slash_normalised(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "x"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        a = emit_sitemap(fs, "https://example.com/docs/")
        b = emit_sitemap(fs, "https://example.com/docs")
        assert a == b


# ─────────────────────────────────────────────────────────────────
# emit_sitemap — escaping and edge cases
# ─────────────────────────────────────────────────────────────────


class TestEmitSitemapEscaping:
    def test_frame_id_with_reserved_chars_url_escaped(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "section a/b?c"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        # space → %20, '/' → %2F, '?' → %3F
        assert urls == ["https://example.com/landscape/section%20a%2Fb%3Fc"]

    def test_target_name_with_special_chars_url_escaped(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "x"}],
                defaults={"targets": [{"name": "a4 print", "canvas": [2480, 3508]}]},
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert urls == ["https://example.com/a4%20print/x"]

    def test_xml_special_chars_in_id_escaped_by_etree(self) -> None:
        # Frame ids containing < > & must not break the XML — ET
        # escapes element text automatically.
        fs = validate_frameset(
            _native_frameset(
                [{"id": "a&b<c>d"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        out = emit_sitemap(fs, "https://example.com")
        # Must parse back cleanly.
        urls = _parse_sitemap(out)
        # `&`, `<`, `>` are URL-escaped to %26, %3C, %3E.
        assert urls == ["https://example.com/landscape/a%26b%3Cc%3Ed"]

    def test_empty_base_url_rejected(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "x"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        with pytest.raises(ValueError, match="non-empty"):
            emit_sitemap(fs, "")
        with pytest.raises(ValueError, match="non-empty"):
            emit_sitemap(fs, "   ")

    def test_malformed_base_url_rejected(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "x"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        with pytest.raises(ValueError, match="not a valid URL"):
            emit_sitemap(fs, "not-a-url")
        with pytest.raises(ValueError, match="not a valid URL"):
            emit_sitemap(fs, "/relative/only")


# ─────────────────────────────────────────────────────────────────
# emit_sitemap — determinism
# ─────────────────────────────────────────────────────────────────


class TestEmitSitemapDeterminism:
    def test_repeated_calls_byte_identical(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [
                    {"id": "f1"},
                    {"id": "f2"},
                    {"id": "f3", "targets": [{"name": "portrait", "canvas": [1080, 1920]}]},
                ],
                defaults={
                    "targets": [
                        {"name": "landscape", "canvas": [1920, 1080]},
                        {"name": "mobile", "canvas": [375, 812]},
                    ]
                },
            )
        )
        a = emit_sitemap(fs, "https://example.com")
        b = emit_sitemap(fs, "https://example.com")
        assert a == b

    def test_order_matches_declaration(self) -> None:
        fs = validate_frameset(
            _native_frameset(
                [{"id": "z"}, {"id": "a"}, {"id": "m"}],
                defaults={"targets": [{"name": "landscape", "canvas": [1920, 1080]}]},
            )
        )
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert urls == [
            "https://example.com/landscape/z",
            "https://example.com/landscape/a",
            "https://example.com/landscape/m",
        ]


# ─────────────────────────────────────────────────────────────────
# emit_sitemap — target_filter
# ─────────────────────────────────────────────────────────────────


class TestEmitSitemapTargetFilter:
    def _three_target_fs(self) -> Any:
        return validate_frameset(
            _native_frameset(
                [
                    {"id": "cover"},
                    {"id": "appendix", "targets": [{"name": "portrait", "canvas": [1080, 1920]}]},
                ],
                defaults={
                    "targets": [
                        {"name": "landscape", "canvas": [1920, 1080]},
                        {"name": "mobile", "canvas": [375, 812]},
                    ]
                },
            )
        )

    def test_single_target_filter(self) -> None:
        fs = self._three_target_fs()
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com", target_filter=["landscape"]))
        assert urls == ["https://example.com/landscape/cover"]

    def test_multi_target_filter(self) -> None:
        fs = self._three_target_fs()
        urls = _parse_sitemap(
            emit_sitemap(fs, "https://example.com", target_filter=["landscape", "mobile"])
        )
        assert urls == [
            "https://example.com/landscape/cover",
            "https://example.com/mobile/cover",
        ]

    def test_filter_unknown_target_yields_empty_urlset(self) -> None:
        fs = self._three_target_fs()
        out = emit_sitemap(fs, "https://example.com", target_filter=["spaceship"])
        urls = _parse_sitemap(out)
        assert urls == []
        # But the urlset element must still exist.
        root = ET.fromstring(out)
        assert root.tag == f"{{{SITEMAP_NS}}}urlset"

    def test_empty_filter_list_yields_empty_urlset(self) -> None:
        fs = self._three_target_fs()
        out = emit_sitemap(fs, "https://example.com", target_filter=[])
        assert _parse_sitemap(out) == []

    def test_none_filter_emits_all(self) -> None:
        fs = self._three_target_fs()
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com", target_filter=None))
        assert len(urls) == 3


# ─────────────────────────────────────────────────────────────────
# emit_sitemap — coerced inputs (legacy + deck)
# ─────────────────────────────────────────────────────────────────


class TestEmitSitemapCoerced:
    def test_legacy_single_doc_yields_one_url(self) -> None:
        legacy = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "kind": "hybrid-semantic-visual-diagram",
            "scene": {"id": "x", "canvas": {"size": [200, 100]}},
            "visual": {"layers": []},
        }
        fs = coerce_to_frameset(legacy)
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        assert len(urls) == 1
        assert urls[0].startswith("https://example.com/")

    def test_deck_yields_one_url_per_slide(self) -> None:
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [1280, 720]}},
            "slides": [
                {"slide": 1, "id": "intro"},
                {"slide": 2, "id": "body"},
                {"slide": 3, "id": "outro"},
            ],
        }
        fs = coerce_to_frameset(deck)
        urls = _parse_sitemap(emit_sitemap(fs, "https://example.com"))
        # Coerced decks get one synthesized "default" target name.
        assert urls == [
            "https://example.com/default/intro",
            "https://example.com/default/body",
            "https://example.com/default/outro",
        ]


# ─────────────────────────────────────────────────────────────────
# CLI — `framegraph sitemap`
# ─────────────────────────────────────────────────────────────────


class TestCliSitemap:
    def _native_yaml(self, tmp_path: Path) -> Path:
        path = tmp_path / "site.yml"
        path.write_text(
            yaml.safe_dump(
                _native_frameset(
                    [
                        {"id": "cover"},
                        {"id": "agenda"},
                    ],
                    defaults={
                        "targets": [
                            {"name": "landscape", "canvas": [1920, 1080]},
                            {"name": "mobile", "canvas": [375, 812]},
                        ]
                    },
                )
            ),
            encoding="utf-8",
        )
        return path

    def test_writes_sitemap_to_output_path(self, tmp_path: Path) -> None:
        in_path = self._native_yaml(tmp_path)
        out_path = tmp_path / "sitemap.xml"
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "-o",
                str(out_path),
                "--quiet",
            ]
        )
        assert rc == 0
        assert out_path.exists()
        urls = _parse_sitemap(out_path.read_text(encoding="utf-8"))
        assert urls == [
            "https://example.com/landscape/cover",
            "https://example.com/mobile/cover",
            "https://example.com/landscape/agenda",
            "https://example.com/mobile/agenda",
        ]

    def test_stdout_when_no_output_flag(self, tmp_path: Path, capsys: Any) -> None:
        in_path = self._native_yaml(tmp_path)
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        urls = _parse_sitemap(captured.out)
        assert len(urls) == 4

    def test_target_filter(self, tmp_path: Path) -> None:
        in_path = self._native_yaml(tmp_path)
        out_path = tmp_path / "sitemap.xml"
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "--target",
                "mobile",
                "-o",
                str(out_path),
                "--quiet",
            ]
        )
        assert rc == 0
        urls = _parse_sitemap(out_path.read_text(encoding="utf-8"))
        assert urls == [
            "https://example.com/mobile/cover",
            "https://example.com/mobile/agenda",
        ]

    def test_missing_base_url_argparse_errors(self, tmp_path: Path) -> None:
        in_path = self._native_yaml(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            cli_main(["sitemap", str(in_path)])
        # argparse exits with code 2 on missing required arg.
        assert excinfo.value.code == 2

    def test_invalid_base_url_returns_nonzero(self, tmp_path: Path) -> None:
        in_path = self._native_yaml(tmp_path)
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "not-a-url",
                "--quiet",
            ]
        )
        assert rc != 0

    def test_legacy_single_doc_input(self, tmp_path: Path) -> None:
        legacy = {
            "dsl": "FrameGraph",
            "version": 1.5,
            "kind": "hybrid-semantic-visual-diagram",
            "scene": {"id": "lonely", "canvas": {"size": [200, 100]}},
            "visual": {"layers": []},
        }
        in_path = tmp_path / "legacy.yml"
        in_path.write_text(yaml.safe_dump(legacy), encoding="utf-8")
        out_path = tmp_path / "sitemap.xml"
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "-o",
                str(out_path),
                "--quiet",
            ]
        )
        assert rc == 0
        urls = _parse_sitemap(out_path.read_text(encoding="utf-8"))
        assert len(urls) == 1

    def test_deck_input(self, tmp_path: Path) -> None:
        deck = {
            "dsl": "FrameGraph",
            "version": 1.2,
            "kind": "presentation-deck",
            "deck": {"canvas": {"size": [1280, 720]}},
            "slides": [
                {"slide": 1, "id": "s1"},
                {"slide": 2, "id": "s2"},
            ],
        }
        in_path = tmp_path / "deck.yml"
        in_path.write_text(yaml.safe_dump(deck), encoding="utf-8")
        out_path = tmp_path / "sitemap.xml"
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "-o",
                str(out_path),
                "--quiet",
            ]
        )
        assert rc == 0
        urls = _parse_sitemap(out_path.read_text(encoding="utf-8"))
        assert urls == [
            "https://example.com/default/s1",
            "https://example.com/default/s2",
        ]

    def test_load_failure_returns_nonzero(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.yml"
        rc = cli_main(
            [
                "sitemap",
                str(missing),
                "--base-url",
                "https://example.com",
                "--quiet",
            ]
        )
        assert rc != 0

    def test_coercion_failure_returns_nonzero(self, tmp_path: Path) -> None:
        # YAML that parses fine but cannot be coerced (kind is wrong
        # and there's nothing for the shim to lift). Hits the
        # coerce exception branch in cmd_sitemap.
        in_path = tmp_path / "bogus.yml"
        in_path.write_text(
            yaml.safe_dump({"kind": "totally-unknown-shape"}),
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "--quiet",
            ]
        )
        assert rc != 0

    def test_progress_message_on_success(self, tmp_path: Path, capsys: Any) -> None:
        in_path = self._native_yaml(tmp_path)
        out_path = tmp_path / "sitemap.xml"
        rc = cli_main(
            [
                "sitemap",
                str(in_path),
                "--base-url",
                "https://example.com",
                "-o",
                str(out_path),
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "wrote" in captured.out
        assert "URLs" in captured.out
