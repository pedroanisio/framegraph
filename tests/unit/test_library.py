"""Unit tests for `framegraph.library`.

Boundaries: real `tmp_path` for synthetic library trees, real YAML I/O.
No mocks of internal symbols.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from framegraph.library import (
    FrameGraphComposer,
    FrameGraphDeckRenderer,
    FrameGraphLibrary,
    build_parser,
    cmd_compose,
    cmd_list_symbols,
    cmd_list_themes,
    cmd_render_deck,
    cmd_show_theme,
    deep_merge,
    dump_yaml,
    load_yaml,
    main,
    strip_meta,
)

# ── lib_tree factory ─────────────────────────────────────────────────


def _make_lib_tree(root: Path) -> Path:
    """Build a synthetic library tree with one token pack and one symbol pack."""
    lib = root / "lib"
    (lib / "tokens").mkdir(parents=True)
    (lib / "symbols" / "shared").mkdir(parents=True)

    (lib / "tokens" / "alpha.yml").write_text(
        yaml.dump(
            {
                "_meta": {"id": "alpha", "name": "Alpha Theme"},
                "colors": {"brand": "#112233", "ink": "#000000"},
                "fonts": {"default": "Inter"},
            }
        ),
        encoding="utf-8",
    )
    (lib / "tokens" / "beta.yml").write_text(
        yaml.dump(
            {
                "_meta": {"name": "Beta Theme", "brand_notes": "Loud and proud."},
                "colors": {"brand": "#aa0000"},
            }
        ),
        encoding="utf-8",
    )
    # Symbol pack (matches *.sym.yml glob)
    (lib / "symbols" / "shared" / "icons.sym.yml").write_text(
        yaml.dump(
            {
                "_meta": {"id": "shared/icons"},
                "symbols": {
                    "node_rect": {"shape": "rect", "fill": "{colors.brand}"},
                    "node_pill": {"shape": "ellipse"},
                },
            }
        ),
        encoding="utf-8",
    )
    return lib


# ── deep_merge ──────────────────────────────────────────────────────


def test_deep_merge_dicts_combines_recursively() -> None:
    base = {"a": {"b": 1, "c": 2}, "d": 9}
    override = {"a": {"c": 20, "e": 30}, "f": 40}
    out = deep_merge(base, override)
    assert out == {"a": {"b": 1, "c": 20, "e": 30}, "d": 9, "f": 40}


def test_deep_merge_override_scalar_wins_on_conflict() -> None:
    assert deep_merge({"x": 1}, {"x": 2}) == {"x": 2}


def test_deep_merge_lists_replaced_not_concatenated() -> None:
    out = deep_merge({"items": [1, 2, 3]}, {"items": [9]})
    assert out == {"items": [9]}


def test_deep_merge_non_dict_override_replaces_base() -> None:
    assert deep_merge({"a": 1}, "scalar") == "scalar"
    assert deep_merge("scalar", {"a": 1}) == {"a": 1}


# ── strip_meta ──────────────────────────────────────────────────────


def test_strip_meta_removes_meta_and_underscore_keys() -> None:
    out = strip_meta({"_meta": {"id": "x"}, "_internal": 1, "colors": {"a": "#000"}})
    assert "_meta" not in out and "_internal" not in out
    assert out == {"colors": {"a": "#000"}}


def test_strip_meta_preserves_normal_keys() -> None:
    assert strip_meta({"colors": 1, "fonts": 2}) == {"colors": 1, "fonts": 2}


# ── load_yaml / dump_yaml ───────────────────────────────────────────


def test_load_yaml_returns_dict_for_valid_file(tmp_path: Path) -> None:
    f = tmp_path / "x.yml"
    f.write_text("a: 1\nb: 2\n")
    assert load_yaml(f) == {"a": 1, "b": 2}


def test_load_yaml_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "empty.yml"
    f.write_text("")
    assert load_yaml(f) == {}


def test_dump_yaml_returns_string_and_writes_file(tmp_path: Path) -> None:
    f = tmp_path / "out.yml"
    text = dump_yaml({"x": 1, "y": [1, 2]}, f)
    assert "x: 1" in text
    assert f.exists()
    assert "x: 1" in f.read_text()


def test_dump_yaml_without_path_returns_string_only(tmp_path: Path) -> None:
    text = dump_yaml({"x": 1})
    assert "x: 1" in text


# ── FrameGraphLibrary ───────────────────────────────────────────────


def test_library_scan_indexes_token_packs_by_meta_id(tmp_path: Path) -> None:
    lib_path = _make_lib_tree(tmp_path)
    lib = FrameGraphLibrary(lib_path)
    ids = lib.token_ids()
    assert "alpha" in ids
    # beta has no _meta.id → falls back to filename stem
    assert "beta" in ids


def test_library_scan_indexes_symbol_packs_by_meta_id(tmp_path: Path) -> None:
    lib_path = _make_lib_tree(tmp_path)
    lib = FrameGraphLibrary(lib_path)
    ids = lib.symbol_ids()
    # both _meta.id and short-stem aliases registered
    assert "shared/icons" in ids
    assert "icons" in ids


def test_library_scan_handles_missing_subdirs(tmp_path: Path) -> None:
    # No tokens/ or symbols/ directories under root
    lib = FrameGraphLibrary(tmp_path / "empty_root")
    assert lib.token_ids() == []
    assert lib.symbol_ids() == []


def test_library_load_tokens_returns_full_dict_without_meta(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    tokens = lib.load_tokens("alpha")
    assert "_meta" not in tokens
    assert tokens["colors"]["brand"] == "#112233"


def test_library_load_tokens_unknown_id_raises_valueerror(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    with pytest.raises(ValueError, match="unknown theme"):
        lib.load_tokens("does-not-exist")


def test_library_load_symbols_returns_symbols_section(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    syms = lib.load_symbols("shared/icons")
    assert "node_rect" in syms
    assert syms["node_rect"]["shape"] == "rect"


def test_library_load_symbols_resolves_relative_path(tmp_path: Path) -> None:
    """When the lookup ID is unknown but a `<id>.sym.yml` exists under symbols/, load it."""
    lib_path = _make_lib_tree(tmp_path)
    # Add an extra unindexed symbol file path
    extra = lib_path / "symbols" / "extra.sym.yml"
    extra.write_text(
        yaml.dump({"symbols": {"foo": {"shape": "rect"}}}), encoding="utf-8"
    )
    lib = FrameGraphLibrary(lib_path)
    # Reach via filename-relative form (no _meta.id pre-registered)
    syms = lib.load_symbols("extra")
    assert "foo" in syms


def test_library_load_symbols_unknown_pack_raises(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    with pytest.raises(ValueError, match="unknown symbol pack"):
        lib.load_symbols("nonexistent")


def test_library_show_theme_prints_palette(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    lib.show_theme("alpha")
    out = capsys.readouterr().out
    assert "Alpha Theme" in out
    assert "brand" in out
    assert "#112233" in out


def test_library_show_theme_unknown_id_prints_not_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    lib.show_theme("missing")
    out = capsys.readouterr().out
    assert "not found" in out


def test_library_show_theme_with_brand_notes_truncates_long_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib_path = tmp_path / "lib"
    (lib_path / "tokens").mkdir(parents=True)
    (lib_path / "tokens" / "long.yml").write_text(
        yaml.dump(
            {
                "_meta": {"id": "long", "name": "Long", "brand_notes": "x" * 200},
                "colors": {"a": "#111"},
            }
        )
    )
    lib = FrameGraphLibrary(lib_path)
    lib.show_theme("long")
    assert "…" in capsys.readouterr().out  # truncation marker


# ── FrameGraphComposer ──────────────────────────────────────────────


def test_composer_compose_inlines_theme_tokens(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram = {"$theme": "alpha", "visual": {"tokens": {"colors": {"accent": "#fff"}}}}
    out = composer.compose(diagram)
    # $theme directive consumed
    assert "$theme" not in out
    # library + diagram tokens merged (diagram wins on conflict)
    assert out["visual"]["tokens"]["colors"]["brand"] == "#112233"
    assert out["visual"]["tokens"]["colors"]["accent"] == "#fff"


def test_composer_compose_theme_override_arg_wins_over_directive(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram = {"$theme": "alpha"}
    out = composer.compose(diagram, theme_override="beta")
    assert out["visual"]["tokens"]["colors"]["brand"] == "#aa0000"


def test_composer_compose_inlines_symbol_pack(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram = {"$symbols": ["shared/icons"]}
    out = composer.compose(diagram)
    assert "$symbols" not in out
    assert "node_rect" in out["visual"]["symbols"]


def test_composer_compose_diagram_local_symbol_wins(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram = {
        "$symbols": ["shared/icons"],
        "visual": {"symbols": {"node_rect": {"shape": "diamond"}}},
    }
    out = composer.compose(diagram)
    assert out["visual"]["symbols"]["node_rect"]["shape"] == "diamond"


def test_composer_compose_extra_symbols_arg_prepended(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram: dict = {}
    out = composer.compose(diagram, extra_symbols=["shared/icons"])
    assert "node_rect" in out["visual"]["symbols"]


def test_composer_compose_no_directives_passes_through(tmp_path: Path) -> None:
    lib = FrameGraphLibrary(_make_lib_tree(tmp_path))
    composer = FrameGraphComposer(lib)
    diagram = {"visual": {"objects": []}}
    out = composer.compose(diagram)
    assert out == {"visual": {"objects": []}}


# ── FrameGraphDeckRenderer ──────────────────────────────────────────


def _make_minimal_deck(root: Path, with_lib: bool = True) -> tuple[Path, dict]:
    """Build a minimal deck YAML and an optional library tree."""
    deck = {
        "dsl": "FrameGraph",
        "version": "1.2",
        "kind": "presentation-deck",
        "deck": {
            "canvas": {"size": [800, 600]},
            "tokens": {"colors": {"deck_color": "#ff0000"}},
            "symbols": {"deck_sym": {"box": [0, 0, 100, 100], "objects": []}},
            "component_defs": {"deck_cdef": {"fill": "#cccccc"}},
        },
        "slides": [
            {
                "slide": 1,
                "id": "s1",
                "title": "Opening",
                "tokens": {"colors": {"slide_color": "#00ff00"}},
                "visual": {"layers": [{"id": "L1", "objects": []}]},
                "notes": "First slide notes.",
            },
            {
                "slide": 2,
                "id": "s2",
                "$extends": "s1",
                "title": "Continuation",
                "visual": {"layers": [{"id": "L1", "objects": []}]},
            },
        ],
    }
    if with_lib:
        _make_lib_tree(root)
        deck["$theme"] = "alpha"
    return root, deck


def test_deck_renderer_init_records_slides(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    assert len(r.slides_raw) == 2
    assert r._slide_index["s1"]["title"] == "Opening"


def test_deck_renderer_build_globals_merges_theme_and_deck_tokens(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    # theme provided "brand", deck added "deck_color"
    assert r.global_tokens["colors"]["brand"] == "#112233"
    assert r.global_tokens["colors"]["deck_color"] == "#ff0000"


def test_deck_renderer_without_library_skips_theme_load(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path, with_lib=False)
    deck.pop("$theme", None)
    r = FrameGraphDeckRenderer(deck, library=None)
    # No theme is applied; only deck-level tokens remain
    assert "brand" not in r.global_tokens.get("colors", {})
    assert r.global_tokens["colors"]["deck_color"] == "#ff0000"


def test_deck_renderer_build_slide_doc_inlines_globals_and_overrides(
    tmp_path: Path,
) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    doc = r.build_slide_doc(deck["slides"][0])
    assert doc["scene"]["id"] == "s1"
    assert doc["scene"]["name"] == "Opening"
    assert doc["visual"]["tokens"]["colors"]["brand"] == "#112233"
    assert doc["visual"]["tokens"]["colors"]["deck_color"] == "#ff0000"
    assert doc["visual"]["tokens"]["colors"]["slide_color"] == "#00ff00"


def test_deck_renderer_extends_inherits_base_slide_tokens(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    doc = r.build_slide_doc(deck["slides"][1])
    # s2 extends s1, so it inherits s1's slide-local tokens
    assert doc["visual"]["tokens"]["colors"]["slide_color"] == "#00ff00"


def test_deck_renderer_extends_unknown_id_warns(tmp_path: Path) -> None:
    _make_lib_tree(tmp_path)
    deck = {
        "$theme": "alpha",
        "slides": [
            {
                "slide": 1,
                "id": "orphan",
                "$extends": "ghost",
                "visual": {"layers": []},
            }
        ],
    }
    r = FrameGraphDeckRenderer(deck, library=FrameGraphLibrary(tmp_path / "lib"))
    with pytest.warns(UserWarning, match="ghost"):
        r.build_slide_doc(deck["slides"][0])


def test_deck_renderer_collect_notes_filters_empty_notes(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    notes = r.collect_notes()
    assert notes == {"s1": "First slide notes."}


def test_deck_renderer_render_notes_writes_markdown(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    out_dir = tmp_path / "out"
    path = r.render_notes(out_dir)
    assert path is not None and path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Speaker Notes" in text
    assert "First slide notes." in text


def test_deck_renderer_render_notes_returns_none_without_notes(tmp_path: Path) -> None:
    _make_lib_tree(tmp_path)
    deck = {
        "$theme": "alpha",
        "slides": [
            {"slide": 1, "id": "s1", "visual": {"layers": []}},
        ],
    }
    r = FrameGraphDeckRenderer(deck, library=FrameGraphLibrary(tmp_path / "lib"))
    assert r.render_notes(tmp_path / "out") is None


def test_deck_renderer_render_all_writes_one_svg_per_slide(tmp_path: Path) -> None:
    _, deck = _make_minimal_deck(tmp_path)
    lib = FrameGraphLibrary(tmp_path / "lib")
    r = FrameGraphDeckRenderer(deck, library=lib)
    out_dir = tmp_path / "rendered"
    paths = r.render_all(out_dir)
    assert len(paths) == 2
    for p in paths:
        assert p.exists() and p.suffix == ".svg" and p.stat().st_size > 0


# ── Library composer CLI (cmd_*, build_parser, main) ────────────────


def test_library_main_no_command_prints_help_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_lib_tree(tmp_path)
    rc = main(["--lib-path", str(tmp_path / "lib")])
    assert rc == 1
    # argparse help printed to stdout
    assert "FrameGraph" in capsys.readouterr().out


def test_library_main_list_themes_prints_theme_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_lib_tree(tmp_path)
    rc = main(["--lib-path", str(tmp_path / "lib"), "list-themes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "Alpha Theme" in out


def test_library_main_show_theme_prints_palette(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_lib_tree(tmp_path)
    rc = main(["--lib-path", str(tmp_path / "lib"), "show-theme", "alpha"])
    assert rc == 0
    assert "Alpha Theme" in capsys.readouterr().out


def test_library_main_list_symbols_prints_symbol_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_lib_tree(tmp_path)
    rc = main(["--lib-path", str(tmp_path / "lib"), "list-symbols"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "icons" in out and "node_rect" in out


def test_library_cmd_compose_writes_yaml_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib_path = _make_lib_tree(tmp_path)
    diagram = tmp_path / "diag.yml"
    diagram.write_text(yaml.dump({"$theme": "alpha", "visual": {"objects": []}}))
    out = tmp_path / "built.yml"

    args = argparse.Namespace(
        input=diagram,
        output=out,
        theme=None,
        symbols=None,
        render=False,
        renderer=None,
    )
    rc = cmd_compose(args, FrameGraphLibrary(lib_path))
    assert rc == 0
    assert out.exists()
    parsed = yaml.safe_load(out.read_text())
    assert parsed["visual"]["tokens"]["colors"]["brand"] == "#112233"


def test_library_cmd_compose_no_output_prints_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib_path = _make_lib_tree(tmp_path)
    diagram = tmp_path / "diag.yml"
    diagram.write_text(yaml.dump({"$theme": "alpha", "visual": {"objects": []}}))
    args = argparse.Namespace(
        input=diagram, output=None, theme=None, symbols=None, render=False, renderer=None
    )
    rc = cmd_compose(args, FrameGraphLibrary(lib_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "visual" in out


def test_library_cmd_compose_with_symbols_arg_includes_symbols(
    tmp_path: Path,
) -> None:
    lib_path = _make_lib_tree(tmp_path)
    diagram = tmp_path / "diag.yml"
    diagram.write_text(yaml.dump({"visual": {"objects": []}}))
    out = tmp_path / "built.yml"
    args = argparse.Namespace(
        input=diagram,
        output=out,
        theme=None,
        symbols="shared/icons",
        render=False,
        renderer=None,
    )
    rc = cmd_compose(args, FrameGraphLibrary(lib_path))
    assert rc == 0
    parsed = yaml.safe_load(out.read_text())
    assert "node_rect" in parsed["visual"]["symbols"]


def test_library_cmd_list_themes_unit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cmd_list_themes(FrameGraphLibrary(_make_lib_tree(tmp_path)))
    assert rc == 0
    assert "Alpha Theme" in capsys.readouterr().out


def test_library_cmd_show_theme_unit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cmd_show_theme(
        argparse.Namespace(theme_id="alpha"),
        FrameGraphLibrary(_make_lib_tree(tmp_path)),
    )
    assert rc == 0
    assert "Alpha Theme" in capsys.readouterr().out


def test_library_cmd_list_symbols_unit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cmd_list_symbols(FrameGraphLibrary(_make_lib_tree(tmp_path)))
    assert rc == 0
    assert "node_rect" in capsys.readouterr().out


def test_library_build_parser_returns_argparse_parser() -> None:
    p = build_parser()
    assert isinstance(p, argparse.ArgumentParser)


def test_library_main_render_deck_writes_svgs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main(["render-deck", ...])` dispatches through `cmd_render_deck`."""
    _make_lib_tree(tmp_path)
    deck_path = tmp_path / "deck.yml"
    deck_path.write_text(
        yaml.dump(
            {
                "$theme": "alpha",
                "slides": [
                    {"slide": 1, "id": "s1", "visual": {"layers": []}},
                ],
            }
        )
    )
    out_dir = tmp_path / "out"
    rc = main(
        [
            "--lib-path",
            str(tmp_path / "lib"),
            "render-deck",
            str(deck_path),
            "-o",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert any(out_dir.glob("*.svg"))


def test_library_cmd_render_deck_uses_default_output_when_none(tmp_path: Path) -> None:
    _make_lib_tree(tmp_path)
    deck_path = tmp_path / "deck.yml"
    deck_path.write_text(
        yaml.dump(
            {
                "$theme": "alpha",
                "slides": [{"slide": 1, "id": "s1", "visual": {"layers": []}}],
            }
        )
    )
    args = argparse.Namespace(input=deck_path, output=None)
    rc = cmd_render_deck(args, FrameGraphLibrary(tmp_path / "lib"))
    assert rc == 0
    # default output dir is <input.parent>/output
    assert (tmp_path / "output").is_dir()
