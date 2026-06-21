"""Unit tests for the wrap-aware planner in `framegraph.patterns.layout`.

Targets the planner code added in `fd0aca2` (wrap-aware height
estimation): `_measure_zone_height`, the `_zone_min_h_at_scale`
back-compat wrapper, and `compute_layout_plan`'s scale-search.

These complement the integration tests, which only exercise the
`list_items` and `table_data` content_types via the BMC pattern.
The unit tests below cover the remaining content_type branches
(`key_value`, `chart_data`, `title_body`, `comparison`, `metric`,
`image`, `axis_label`, `decorative`), the early-return paths
(`fill is None`, `value is None`), the exception-fallback path,
and the three scale-search outcomes (fits at 1.0; binary-search
hit; floor-scale floor).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from framegraph._patterns import SlidePattern
from framegraph.patterns import LayoutPlan, LayoutReport, compute_layout_plan
from framegraph.patterns.layout import (
    _count_wrapped_lines,
    _measure_zone_height,
    _solve_layout_at_scale,
    _zone_min_h_at_scale,
)

CANVAS_W = 1920.0
CANVAS_H = 1080.0


def _zone(role: str, content_type: str | None = "title_body") -> dict:
    return {
        "role": role,
        "size": "medium",
        "placement": {"anchor": {"h": "center", "v": "middle"}},
        "content_type": content_type,
    }


def _pattern(zones: list[dict], pattern_id: int = 99500) -> SlidePattern:
    return SlidePattern.model_validate(
        {
            "id": pattern_id,
            "name": "T",
            "layout_disposition": "x",
            "zones": zones,
        }
    )


def _make_zone(role: str, content_type: str | None) -> object:
    """Build a single PatternZone via the SlidePattern validator."""
    return _pattern([_zone(role, content_type)]).zones[0]


# ─────────────────────────────────────────────────────────────────
# 1. Early-return paths
# ─────────────────────────────────────────────────────────────────


class TestEarlyReturns:
    def test_no_fill_returns_default_two_lines(self) -> None:
        z = _make_zone("body", "title_body")
        h = _measure_zone_height(z, fill=None, box_w=300.0, scale=1.0)
        # chrome_overhead (14 + 20 = 34) + 2 lines × 13 px = 60
        assert h == pytest.approx(60.0)

    def test_value_none_returns_default(self) -> None:
        z = _make_zone("body", "title_body")
        fill = SimpleNamespace(body=None)
        h = _measure_zone_height(z, fill=fill, box_w=300.0, scale=1.0)
        assert h == pytest.approx(60.0)

    def test_no_fill_at_half_scale(self) -> None:
        z = _make_zone("body", "title_body")
        h = _measure_zone_height(z, fill=None, box_w=300.0, scale=0.5)
        # chrome (34) + 2 × 13 × 0.5 = 47
        assert h == pytest.approx(47.0)


# ─────────────────────────────────────────────────────────────────
# 2. Per content_type branches
# ─────────────────────────────────────────────────────────────────


class TestListItemsBranches:
    def test_string_items(self) -> None:
        z = _make_zone("items", "list_items")
        fill = SimpleNamespace(items=["alpha", "beta", "gamma"])
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        # 3 short items, 1 wrapped line each → chrome (34) + 3 × 13 = 73
        assert h == pytest.approx(73.0)

    def test_dict_items_with_label_metric(self) -> None:
        z = _make_zone("rows", "list_items")
        fill = SimpleNamespace(
            rows=[{"label": "Revenue", "metric": "$1.2M"}, {"label": "Cost", "metric": "$0.4M"}]
        )
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        assert h == pytest.approx(60.0)  # chrome + 2 × 13

    def test_pydantic_like_items_with_label_metric(self) -> None:
        """Object items exposing `.label` and `.metric` follow the
        Pydantic-item branch (line 1303→1305)."""
        z = _make_zone("rows", "list_items")
        items = [
            SimpleNamespace(label="Engineering", metric="$8.4M"),
            SimpleNamespace(label="Marketing", metric="$3.2M"),
        ]
        fill = SimpleNamespace(rows=items)
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        assert h == pytest.approx(60.0)

    def test_long_item_wraps_to_multiple_lines(self) -> None:
        z = _make_zone("items", "list_items")
        long_text = " ".join(["word"] * 80)  # forces wrap at any reasonable width
        fill = SimpleNamespace(items=[long_text])
        h = _measure_zone_height(z, fill, box_w=200.0, scale=1.0)
        # > 1 wrapped line → height exceeds the 1-line baseline (47)
        assert h > 47.0


class TestTableDataBranches:
    def test_table_with_headers_and_rows(self) -> None:
        z = _make_zone("data", "table_data")
        fill = SimpleNamespace(
            data=SimpleNamespace(
                headers=["A", "B", "C"],
                rows=[["1", "2", "3"], ["4", "5", "6"]],
            )
        )
        h = _measure_zone_height(z, fill, box_w=600.0, scale=1.0)
        # chrome (34) + header (14 + 4) + 2 rows × (12 + 4) = 84
        assert h == pytest.approx(84.0)

    def test_table_without_headers_uses_first_row_width(self) -> None:
        """Hits the `if headers:` false branch (line 1320→1323)."""
        z = _make_zone("data", "table_data")
        fill = SimpleNamespace(data=SimpleNamespace(headers=[], rows=[["x", "y"], ["z", "w"]]))
        h = _measure_zone_height(z, fill, box_w=600.0, scale=1.0)
        # chrome (34) + 0 header + 2 rows × (12 + 4) = 66
        assert h == pytest.approx(66.0)


class TestKeyValueBranch:
    def test_key_value_uses_at_least_two_lines(self) -> None:
        z = _make_zone("kv", "key_value")
        fill = SimpleNamespace(kv={"a": 1})
        h = _measure_zone_height(z, fill, box_w=300.0, scale=1.0)
        # max(2, 1) × 13 + chrome (34) = 60
        assert h == pytest.approx(60.0)

    def test_key_value_scales_with_entry_count(self) -> None:
        z = _make_zone("kv", "key_value")
        fill = SimpleNamespace(kv={"a": 1, "b": 2, "c": 3, "d": 4})
        h = _measure_zone_height(z, fill, box_w=300.0, scale=1.0)
        # 4 × 13 + chrome (34) = 86
        assert h == pytest.approx(86.0)


class TestChartDataBranch:
    def test_chart_data_returns_fixed_demand(self) -> None:
        z = _make_zone("chart", "chart_data")
        fill = SimpleNamespace(chart=SimpleNamespace(series=[]))
        h = _measure_zone_height(z, fill, box_w=600.0, scale=1.0)
        # chrome (34) + 120 = 154
        assert h == pytest.approx(154.0)

    def test_chart_data_scales(self) -> None:
        z = _make_zone("chart", "chart_data")
        fill = SimpleNamespace(chart=SimpleNamespace(series=[]))
        h = _measure_zone_height(z, fill, box_w=600.0, scale=0.5)
        assert h == pytest.approx(34.0 + 120.0 * 0.5)


class TestTitleBodyAndComparisonBranches:
    def test_title_body_with_attributes(self) -> None:
        z = _make_zone("text", "title_body")
        fill = SimpleNamespace(text=SimpleNamespace(title="Headline", body="Some body."))
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        # short text → 1 wrapped line + chrome
        assert h == pytest.approx(34.0 + 13.0)

    def test_title_body_with_string_value(self) -> None:
        z = _make_zone("text", "title_body")
        fill = SimpleNamespace(text="Just a string")
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        assert h == pytest.approx(34.0 + 13.0)

    def test_comparison_branch(self) -> None:
        z = _make_zone("cmp", "comparison")
        fill = SimpleNamespace(cmp="left vs right")
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        assert h == pytest.approx(34.0 + 13.0)


class TestMetricImageAxisDecorativeBranches:
    def test_metric_branch(self) -> None:
        z = _make_zone("kpi", "metric")
        fill = SimpleNamespace(kpi=SimpleNamespace(value="42", label="Answers"))
        h = _measure_zone_height(z, fill, box_w=300.0, scale=1.0)
        # chrome (34) + 60 + body_lh (13) = 107
        assert h == pytest.approx(107.0)

    def test_image_branch(self) -> None:
        z = _make_zone("img", "image")
        fill = SimpleNamespace(img=SimpleNamespace(src="x.png"))
        h = _measure_zone_height(z, fill, box_w=300.0, scale=1.0)
        # chrome (34) + 100 = 134
        assert h == pytest.approx(134.0)

    def test_axis_label_branch(self) -> None:
        z = _make_zone("axis", "axis_label")
        fill = SimpleNamespace(axis="X axis (units)")
        h = _measure_zone_height(z, fill, box_w=300.0, scale=1.0)
        # chrome × 0.5 (17) + body_lh (13) = 30
        assert h == pytest.approx(30.0)

    def test_decorative_branch_returns_constant(self) -> None:
        z = _make_zone("bg", "decorative")
        fill = SimpleNamespace(bg=SimpleNamespace(color="#fff"))
        h = _measure_zone_height(z, fill, box_w=600.0, scale=1.0)
        assert h == pytest.approx(4.0)


class TestExceptionFallback:
    def test_table_data_with_unsupported_value_falls_back(self) -> None:
        """A `table_data` value whose `headers` attribute is non-iterable
        triggers `TypeError` inside the try block. The except clause
        swallows it and the function returns the safe default."""
        z = _make_zone("data", "table_data")
        # `headers` resolves to an int — `list(int)` raises TypeError.
        fill = SimpleNamespace(data=SimpleNamespace(headers=42, rows=[]))
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        # Falls through to `chrome_overhead + 2 * body_lh` = 60
        assert h == pytest.approx(60.0)


# ─────────────────────────────────────────────────────────────────
# 3. _zone_min_h_at_scale back-compat wrapper
# ─────────────────────────────────────────────────────────────────


class TestBackCompatWrapper:
    def test_wrapper_delegates_to_measure_zone_height(self) -> None:
        z = _make_zone("kv", "key_value")
        fill = SimpleNamespace(kv={"a": 1, "b": 2})
        direct = _measure_zone_height(z, fill, box_w=200.0, scale=1.0)
        via_wrapper = _zone_min_h_at_scale(z, fill, scale=1.0, box_w=200.0)
        assert via_wrapper == pytest.approx(direct)

    def test_wrapper_default_box_w(self) -> None:
        """Wrapper uses 200.0 when `box_w` is omitted."""
        z = _make_zone("kv", "key_value")
        fill = SimpleNamespace(kv={"a": 1})
        h = _zone_min_h_at_scale(z, fill, scale=1.0)
        # max(2, 1) × 13 + chrome (34) = 60
        assert h == pytest.approx(60.0)


# ─────────────────────────────────────────────────────────────────
# 4. _solve_layout_at_scale and compute_layout_plan
# ─────────────────────────────────────────────────────────────────


class TestSolveLayoutAtScale:
    def test_returns_boxes_and_demand_per_zone(self) -> None:
        p = _pattern([_zone("body", "list_items")])
        boxes, demand = _solve_layout_at_scale(
            p, CANVAS_W, CANVAS_H, margin=24.0, fill=None, scale=1.0
        )
        assert "body" in boxes
        assert "body" in demand
        assert demand["body"] > 0


class TestCountWrappedLinesEdges:
    """`_count_wrapped_lines` is the wrap-aware planner's measurement
    primitive. The integration tests exercise its happy path; these
    cover the early-return edges and the empty-paragraph branch."""

    def test_empty_text_returns_one(self) -> None:
        assert _count_wrapped_lines("", fs=12.0, avail_w=200.0) == 1

    def test_zero_avail_width_returns_one(self) -> None:
        assert _count_wrapped_lines("non-empty", fs=12.0, avail_w=0.0) == 1

    def test_negative_avail_width_returns_one(self) -> None:
        assert _count_wrapped_lines("non-empty", fs=12.0, avail_w=-5.0) == 1

    def test_double_newline_yields_blank_paragraph_line(self) -> None:
        """A blank line between paragraphs counts as one line — the
        `not words: n += 1; continue` branch."""
        n = _count_wrapped_lines("first\n\nthird", fs=12.0, avail_w=400.0)
        assert n == 3

    def test_trailing_newline_does_not_inflate_count(self) -> None:
        """Last paragraph empty: the `if line:` tail-add loop iteration
        ends without adding a line."""
        n = _count_wrapped_lines("only\n", fs=12.0, avail_w=400.0)
        assert n == 2  # "only" + the empty trailing paragraph

    def test_multiple_non_empty_paragraphs_loop_back(self) -> None:
        """Two consecutive non-empty paragraphs exercise the
        `176->163` branch: after `if line: n += 1` for paragraph A,
        control loops back to line 163 for paragraph B."""
        n = _count_wrapped_lines("first\nsecond", fs=12.0, avail_w=400.0)
        assert n == 2


class TestMeasureZoneHeightEdges:
    """Branches in `_measure_zone_height` that the main happy-path
    tests don't exercise."""

    def test_pydantic_like_item_with_only_label_falls_back_to_str(self) -> None:
        """When a Pydantic-like item exposes `.label` but `.metric` is
        None, the formatted-text branch is skipped and `str(it)` is
        used. Covers the `1303->1305` False transition."""
        z = _make_zone("rows", "list_items")
        items = [SimpleNamespace(label="Has label", metric=None)]
        fill = SimpleNamespace(rows=items)
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        # Exact value depends on the str() of SimpleNamespace, but
        # the call must not raise and must return a positive height.
        assert h > 0.0

    def test_title_body_value_without_title_attribute(self) -> None:
        """A `title_body` whose value is a plain integer (no `.title`)
        falls into the `else: text_full = str(value)` branch (line 1347)."""
        z = _make_zone("text", "title_body")
        fill = SimpleNamespace(text=42)  # plain int — no .title attribute
        h = _measure_zone_height(z, fill, box_w=400.0, scale=1.0)
        assert h == pytest.approx(34.0 + 13.0)

    def test_unknown_content_type_falls_through_to_default(self) -> None:
        """Bypass Pydantic validation by passing a stand-in zone whose
        `content_type` is a string that matches none of the known
        branches. Covers the `1360->1365` False transition (decorative
        check fails, control falls through past the except clause to
        the safe-default return)."""
        zone = SimpleNamespace(role="x", content_type="never_a_real_type")
        fill = SimpleNamespace(x="ignored")
        h = _measure_zone_height(zone, fill, box_w=400.0, scale=1.0)
        # Falls through to `chrome_overhead + 2 * body_lh` = 60
        assert h == pytest.approx(60.0)


class TestSolveLayoutSkipsZonesWithoutBoxes:
    """`_solve_layout_at_scale` guards against `compute_boxes` returning
    no entry for a declared zone (line 1397-1398). Trigger via a
    monkeypatched `compute_boxes` so the skip-branch is observable."""

    def test_skips_zone_when_compute_boxes_omits_it(self, monkeypatch) -> None:
        from framegraph.patterns import layout as layout_mod

        p = _pattern([_zone("a", "list_items"), _zone("b", "list_items")])

        original = layout_mod.compute_boxes

        def stub_compute_boxes(*args, **kwargs):  # type: ignore[no-untyped-def]
            full = original(*args, **kwargs)
            return {"a": full["a"]}  # drop "b" so the planner skips it

        monkeypatch.setattr(layout_mod, "compute_boxes", stub_compute_boxes)
        boxes, demand = _solve_layout_at_scale(
            p, CANVAS_W, CANVAS_H, margin=24.0, fill=None, scale=1.0
        )
        assert "a" in demand
        assert "b" not in demand


class TestComputeLayoutPlan:
    def test_fits_at_nominal_scale(self) -> None:
        """A small list in a roomy center cell fits at scale 1.0
        — exercises the fast-path return at line ~1444."""
        p = _pattern([_zone("body", "list_items")])
        fill = SimpleNamespace(body=["one", "two"])
        plan = compute_layout_plan(p, CANVAS_W, CANVAS_H, fill=fill)
        assert isinstance(plan, LayoutPlan)
        assert plan.scale == pytest.approx(1.0)
        assert isinstance(plan.report, LayoutReport)
        assert plan.report.overflows == []

    def test_overflow_triggers_scale_down(self) -> None:
        """A zone in a cramped 200×80 canvas with bulky list_items
        content cannot fit at scale 1.0; the planner binary-searches
        and returns either a smaller-than-1.0 scale or, if even the
        floor doesn't fit, the floor scale + overflow report."""
        p = _pattern([_zone("body", "list_items")])
        # 50 long items — well over what 80 px can hold even after
        # shrinkage.
        fill = SimpleNamespace(body=[f"item-{i} with extra text" for i in range(50)])
        plan = compute_layout_plan(p, 200.0, 80.0, fill=fill)
        assert plan.scale < 1.0
        # At the floor we expect overflows to be reported (the
        # content cannot fit at any scale).
        if plan.scale == pytest.approx(plan.report.min_scale):
            assert plan.report.overflows  # at-floor path populates this
