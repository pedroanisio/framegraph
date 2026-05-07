"""Regression tests for the v2.0 layout features.

Three feature batteries, schema + render coverage each:

  1. Master-slide chrome   — `deck.chrome:` auto-prepends a layer
                              to every slide; per-slide opt-out and
                              override.
  2. Grid container         — `kind: grid` with `columns`, `gap`,
                              `padding`, `row_height`.
  3. Table object           — `type: table` with `columns`, `header`,
                              `rows`, `zebra`.

The byte-identity bar from the schema-migration suite is intentionally
NOT applied here — these are new features whose output is not pre-
locked, and locking it now would create churn on every later renderer
tweak (e.g. tightening a font-size default would invalidate every
hash).
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from framegraph import FrameGraphDeckRenderer, FrameGraphRenderer
from framegraph._schema import validate_deck, validate_document, validate_object

# ─────────────────────────────────────────────────────────────────
# Common test fixtures
# ─────────────────────────────────────────────────────────────────


def _minimal_deck(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid deck with a chrome symbol available."""
    deck: dict[str, Any] = {
        "dsl": "FrameGraph",
        "version": 1.5,
        "kind": "presentation-deck",
        "deck": {
            "canvas": {"size": [800, 600]},
            "symbols": {
                "chrome": {
                    "box": [0, 0, 800, 600],
                    "slots": ["section_label", "slide_num"],
                    "objects": [
                        {
                            "type": "rect",
                            "id": "bg",
                            "box": [0, 0, 800, 600],
                            "fill": "#ffffff",
                        },
                        {
                            "type": "text",
                            "id": "lbl",
                            "box": [40, 20, 720, 24],
                            "text": "$section_label",
                            "style": {"size": 12, "weight": 700, "color": "#1a1a1a"},
                        },
                    ],
                }
            },
        },
        "slides": [
            {
                "slide": 1,
                "id": "s1",
                "visual": {"layers": [{"id": "content", "z": 10, "objects": []}]},
            },
        ],
    }
    deck.update(overrides)
    return deck


def _minimal_doc_with_object(obj: dict[str, Any]) -> dict[str, Any]:
    """Wrap a single visual object in a minimal valid Document."""
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "test", "canvas": {"size": [800, 600]}},
        "visual": {
            "layers": [{"id": "main", "z": 0, "objects": [obj]}],
        },
    }


# ─────────────────────────────────────────────────────────────────
# Feature 1 — Master-slide chrome
# ─────────────────────────────────────────────────────────────────


class TestMasterSlideChromeSchema:
    """Schema-level tests for `deck.chrome` and `slide.chrome`."""

    def test_deck_chrome_as_string_is_accepted(self) -> None:
        """Shorthand: `deck.chrome: <symbol_id>` (string) validates."""
        deck = _minimal_deck()
        deck["deck"]["chrome"] = "chrome"
        validate_deck(deck)

    def test_deck_chrome_as_mapping_is_accepted(self) -> None:
        """Long form: `deck.chrome: {symbol: …, params: {…}}` validates."""
        deck = _minimal_deck()
        deck["deck"]["chrome"] = {
            "symbol": "chrome",
            "params": {"phase_color": "#1B2940"},
            "section_label": "Default",
        }
        validate_deck(deck)

    def test_deck_chrome_missing_symbol_field_is_rejected(self) -> None:
        """A mapping without `symbol:` fails validation."""
        deck = _minimal_deck()
        deck["deck"]["chrome"] = {"params": {"phase_color": "#1B2940"}}
        with pytest.raises(ValidationError):
            validate_deck(deck)

    def test_slide_chrome_false_is_accepted(self) -> None:
        """Per-slide opt-out: `chrome: false` validates."""
        deck = _minimal_deck()
        deck["deck"]["chrome"] = "chrome"
        deck["slides"][0]["chrome"] = False
        validate_deck(deck)

    def test_slide_chrome_mapping_is_accepted(self) -> None:
        """Per-slide override: `chrome: {section_label: …}` validates."""
        deck = _minimal_deck()
        deck["deck"]["chrome"] = "chrome"
        deck["slides"][0]["chrome"] = {"section_label": "Special"}
        validate_deck(deck)


class TestMasterSlideChromeRender:
    """End-to-end behavior of master-slide chrome through `build_slide_doc`."""

    def test_chrome_layer_is_prepended_to_every_slide(self) -> None:
        """When `deck.chrome:` is set, every slide gets a `_chrome` layer at z=0."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = "chrome"
        deck_yaml["slides"].append(
            {
                "slide": 2,
                "id": "s2",
                "visual": {"layers": [{"id": "content", "z": 10, "objects": []}]},
            }
        )
        deck = FrameGraphDeckRenderer(deck_yaml)
        for s in deck.slides_raw:
            doc = deck.build_slide_doc(s)
            layers = doc["visual"]["layers"]
            assert layers[0]["id"] == "_chrome", (
                f"slide {s['id']}: chrome layer missing or misplaced"
            )
            assert layers[0]["z"] == 0
            chrome_use = layers[0]["objects"][0]
            assert chrome_use["type"] == "use"
            assert chrome_use["symbol"] == "chrome"

    def test_deck_level_slot_passthrough_propagates(self) -> None:
        """Slot fields declared on `deck.chrome:` reach the use object."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = {
            "symbol": "chrome",
            "section_label": "Default Section",
            "slide_num": "01",
        }
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        chrome_use = doc["visual"]["layers"][0]["objects"][0]
        assert chrome_use["section_label"] == "Default Section"
        assert chrome_use["slide_num"] == "01"

    def test_slide_level_overrides_replace_deck_level(self) -> None:
        """Per-slide `chrome: {…}` overrides win on conflict."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = {
            "symbol": "chrome",
            "section_label": "Default",
        }
        deck_yaml["slides"][0]["chrome"] = {"section_label": "Special"}
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        chrome_use = doc["visual"]["layers"][0]["objects"][0]
        assert chrome_use["section_label"] == "Special"

    def test_slide_chrome_false_opts_out(self) -> None:
        """`chrome: false` on a slide skips the auto-prepend."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = "chrome"
        deck_yaml["slides"][0]["chrome"] = False
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        layer_ids = [lyr["id"] for lyr in doc["visual"]["layers"]]
        assert "_chrome" not in layer_ids

    def test_no_chrome_when_deck_chrome_is_absent(self) -> None:
        """Without `deck.chrome:`, no chrome layer is prepended."""
        deck_yaml = _minimal_deck()  # has no `chrome:` field
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        layer_ids = [lyr["id"] for lyr in doc["visual"]["layers"]]
        assert "_chrome" not in layer_ids

    def test_unknown_chrome_symbol_silently_skips(self) -> None:
        """A `deck.chrome:` symbol that does not exist in `deck.symbols`
        produces no chrome layer (and no exception)."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = "nonexistent_symbol"
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        layer_ids = [lyr["id"] for lyr in doc["visual"]["layers"]]
        assert "_chrome" not in layer_ids

    def test_params_merge_deck_then_slide(self) -> None:
        """`params:` mappings merge with slide overriding deck on conflict."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = {
            "symbol": "chrome",
            "params": {"phase_color": "#000000", "shared": "deck"},
        }
        deck_yaml["slides"][0]["chrome"] = {"params": {"phase_color": "#ff0000", "extra": "slide"}}
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        chrome_use = doc["visual"]["layers"][0]["objects"][0]
        params = chrome_use["params"]
        assert params["phase_color"] == "#ff0000"  # slide wins
        assert params["shared"] == "deck"
        assert params["extra"] == "slide"

    def test_chrome_renders_to_svg_without_warnings(self) -> None:
        """Full path: deck → composer → renderer produces clean SVG."""
        deck_yaml = _minimal_deck()
        deck_yaml["deck"]["chrome"] = {
            "symbol": "chrome",
            "section_label": "Hello",
            "slide_num": "01",
        }
        deck = FrameGraphDeckRenderer(deck_yaml)
        doc = deck.build_slide_doc(deck.slides_raw[0])
        renderer = FrameGraphRenderer(doc)
        svg = renderer.render_svg()
        assert renderer.warnings == []
        # The chrome use's slot pass-through should resolve to "Hello"
        # in the rendered SVG (the symbol declares `text: "$section_label"`).
        assert "Hello" in svg


# ─────────────────────────────────────────────────────────────────
# Feature 2 — Grid container
# ─────────────────────────────────────────────────────────────────


class TestGridContainerSchema:
    """The grid container reuses `ContainerObject` — schema is forward-compatible."""

    def test_container_kind_grid_validates(self) -> None:
        """A `container` with `kind: grid` passes schema validation."""
        doc = _minimal_doc_with_object(
            {
                "type": "container",
                "id": "g",
                "box": [0, 0, 400, 300],
                "layout": {"kind": "grid", "columns": 3, "gap": 10},
                "children": [],
            }
        )
        validate_document(doc)

    def test_container_grid_with_full_layout_validates(self) -> None:
        """All grid-layout knobs pass through."""
        doc = _minimal_doc_with_object(
            {
                "type": "container",
                "id": "g",
                "box": [0, 0, 400, 300],
                "layout": {
                    "kind": "grid",
                    "columns": 4,
                    "gap": [20, 12],
                    "padding": [8, 8],
                    "row_height": 80,
                },
                "children": [{"type": "rect", "id": f"c{i}", "fill": "#cccccc"} for i in range(8)],
            }
        )
        validate_document(doc)


class TestGridContainerRender:
    """Layout math + dispatch behavior for grid containers."""

    def _render_grid(
        self, layout: dict[str, Any], n_children: int = 6
    ) -> tuple[FrameGraphRenderer, str]:
        doc = _minimal_doc_with_object(
            {
                "type": "container",
                "id": "g",
                "box": [40, 40, 320, 220],
                "layout": layout,
                "children": [
                    {"type": "rect", "id": f"c{i}", "fill": "#cccccc"} for i in range(n_children)
                ],
            }
        )
        r = FrameGraphRenderer(doc)
        return r, r.render_svg()

    def test_grid_three_columns_two_rows(self) -> None:
        """6 children in a 3-col grid → 2 rows; cells uniform width."""
        r, _ = self._render_grid({"kind": "grid", "columns": 3, "gap": 10}, n_children=6)
        # Cell width = (320 - 2*10) / 3 = 100; row height = (220 - 1*10) / 2 = 105
        for i in range(6):
            rec = r.object_index.get(f"c{i}")
            assert rec is not None, f"c{i} not indexed"
            x, y, w, h = rec["box"]
            assert w == pytest.approx(100.0)
            assert h == pytest.approx(105.0)
        # Row 1: y = 40; row 2: y = 40 + 105 + 10 = 155
        assert r.object_index["c0"]["box"][1] == pytest.approx(40.0)
        assert r.object_index["c3"]["box"][1] == pytest.approx(155.0)
        # Cols: c0 x=40, c1 x=40+100+10=150, c2 x=40+200+20=260
        assert r.object_index["c0"]["box"][0] == pytest.approx(40.0)
        assert r.object_index["c1"]["box"][0] == pytest.approx(150.0)
        assert r.object_index["c2"]["box"][0] == pytest.approx(260.0)

    def test_grid_partial_last_row(self) -> None:
        """5 children in 3 cols → 2 rows, last row has 2 children at cols 0 & 1."""
        r, _ = self._render_grid({"kind": "grid", "columns": 3, "gap": 0}, n_children=5)
        assert r.object_index["c3"]["box"][0] == pytest.approx(40.0)  # col 0
        assert r.object_index["c4"]["box"][0] == pytest.approx(40 + 320 / 3)  # col 1
        # c5 was never created
        assert "c5" not in r.object_index

    def test_grid_explicit_row_height(self) -> None:
        """`row_height` overrides the auto-distribute math."""
        r, _ = self._render_grid(
            {"kind": "grid", "columns": 2, "row_height": 50, "gap": 0},
            n_children=4,
        )
        for i in range(4):
            assert r.object_index[f"c{i}"]["box"][3] == pytest.approx(50.0)

    def test_grid_axis_specific_gaps(self) -> None:
        """`row_gap`/`col_gap` override the unified `gap`."""
        r, _ = self._render_grid(
            {"kind": "grid", "columns": 2, "col_gap": 30, "row_gap": 5},
            n_children=4,
        )
        # Cell width = (320 - 30) / 2 = 145
        # Row height = (220 - 5) / 2 = 107.5
        assert r.object_index["c0"]["box"][2] == pytest.approx(145.0)
        assert r.object_index["c0"]["box"][3] == pytest.approx(107.5)
        # c2 is in row 2 (y = 40 + 107.5 + 5 = 152.5)
        assert r.object_index["c2"]["box"][1] == pytest.approx(152.5)

    def test_grid_padding_is_applied_to_content_area(self) -> None:
        """`padding: [hp, vp]` insets the cell area on all sides."""
        r, _ = self._render_grid(
            {"kind": "grid", "columns": 1, "padding": [12, 8], "gap": 0},
            n_children=1,
        )
        rec = r.object_index["c0"]
        # x = 40 + 12 = 52; y = 40 + 8 = 48
        # w = 320 - 24 = 296; h = 220 - 16 = 204
        assert rec["box"] == pytest.approx((52.0, 48.0, 296.0, 204.0))

    def test_grid_zero_children_renders_clean(self) -> None:
        """Empty grid emits a wrapping `<g>` with no child errors."""
        r, svg = self._render_grid({"kind": "grid", "columns": 2}, n_children=0)
        assert r.warnings == []
        assert "<g " in svg

    def test_grid_default_columns_is_one(self) -> None:
        """No `columns` declared → 1 column (vertical list)."""
        r, _ = self._render_grid({"kind": "grid", "gap": 0}, n_children=3)
        # All children in column 0
        assert r.object_index["c0"]["box"][0] == pytest.approx(40.0)
        assert r.object_index["c1"]["box"][0] == pytest.approx(40.0)
        assert r.object_index["c2"]["box"][0] == pytest.approx(40.0)


# ─────────────────────────────────────────────────────────────────
# Feature 3 — Table object
# ─────────────────────────────────────────────────────────────────


class TestTableSchema:
    """Schema-level tests for the new `table` object type."""

    def test_minimal_table_validates(self) -> None:
        """`type: table` with just box + rows validates."""
        obj = validate_object(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 200],
                "rows": [["a", "b"], ["c", "d"]],
            }
        )
        assert obj.type == "table"

    def test_table_with_header_and_columns_validates(self) -> None:
        obj = validate_object(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 200],
                "columns": [200, "30%", None],
                "header": ["Metric", "Before", "After"],
                "rows": [["x", "1", "2"]],
                "zebra": True,
                "row_height": 36,
            }
        )
        assert obj.type == "table"

    def test_table_inside_layer_validates_through_discriminator(self) -> None:
        """Validates as a Document so the discriminated-union path is exercised."""
        validate_document(
            _minimal_doc_with_object(
                {
                    "type": "table",
                    "id": "t",
                    "box": [0, 0, 400, 200],
                    "rows": [["a", "b"]],
                }
            )
        )


class TestTableRender:
    """Output structure of the table renderer."""

    def _render_table(self, obj: dict[str, Any]) -> str:
        doc = _minimal_doc_with_object(obj)
        r = FrameGraphRenderer(doc)
        svg = r.render_svg()
        assert r.warnings == [], f"table render produced warnings: {r.warnings}"
        return svg

    def test_table_emits_one_text_per_cell(self) -> None:
        """Header (3) + 2 body rows × 3 cells = 9 → 9 `<text>` elements."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 200],
                "header": ["A", "B", "C"],
                "rows": [["1", "2", "3"], ["4", "5", "6"]],
            }
        )
        texts = re.findall(r"<text[^>]*>[^<]*</text>", svg)
        # 3 header cells + 6 body cells = 9
        assert len(texts) == 9

    def test_table_zebra_emits_alt_row_backgrounds(self) -> None:
        """`zebra: true` paints an extra rect per odd-indexed body row."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 200],
                "rows": [["a"], ["b"], ["c"], ["d"]],  # 4 rows; odd indices 1, 3
                "zebra": True,
            }
        )
        # Outer frame + 2 zebra rows = 3 rects
        rects = re.findall(r"<rect[^/]*/>", svg)
        assert len(rects) == 3

    def test_table_explicit_column_widths_resolve_correctly(self) -> None:
        """`columns: [200, "25%", null]` → fixed + percent + auto distribute."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 100],
                "columns": [200, "25%", None],
                "header": ["A", "B", "C"],
            }
        )
        # The vertical column-separator lines should fall at x = 200 and x = 300
        # (200 + 25% of 400 = 200 + 100). Look for `x1` values.
        lines = re.findall(
            r'<line x1="([0-9.]+)"[^>]*y1="[0-9.]+"[^>]*y2="[0-9.]+"',
            svg,
        )
        # Three lines: header rule (x1=0) + two column dividers
        x1_values = sorted({float(x) for x in lines})
        assert 200.0 in x1_values
        assert 300.0 in x1_values

    def test_table_cell_alignment_emits_text_anchor(self) -> None:
        """`style.cell_align: right` produces `text-anchor="end"` on cells."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 100],
                "rows": [["a", "b"]],
                "style": {"cell_align": "right"},
            }
        )
        end_count = svg.count('text-anchor="end"')
        assert end_count == 2

    def test_table_per_cell_align_overrides_global(self) -> None:
        """A cell mapping `{text, align: 'center'}` wins over `style.cell_align`."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 100],
                "rows": [["a", {"text": "b", "align": "center"}]],
                "style": {"cell_align": "left"},
            }
        )
        # One left-anchored cell ("a") and one middle-anchored cell ("b")
        assert svg.count('text-anchor="start"') == 1
        assert svg.count('text-anchor="middle"') == 1

    def test_table_no_rows_renders_only_frame(self) -> None:
        """Empty `rows: []` → just the outer rect, no text."""
        svg = self._render_table(
            {
                "type": "table",
                "id": "t",
                "box": [0, 0, 400, 200],
                "rows": [],
            }
        )
        texts = re.findall(r"<text[^>]*>[^<]*</text>", svg)
        assert len(texts) == 0
        # Outer frame still emitted
        assert "<rect" in svg
