"""Layout engine — pattern zones → ``[x, y, w, h]`` boxes on a canvas.

Originally Phase 3 of the Round 1 roadmap; Round 2 Phase 2 adds
**span-aware** and **density-aware** allocation while preserving
backwards compatibility.

Two-pass algorithm:

  1. **Anchor + region (geometric)**: place every anchor- and
     region-typed zone using the 9-cell grid (with span-aware
     base boxes and density-weighted same-cell subdivision when
     a fill is supplied) and per-region hand-coded layouts for
     the top-5 regions plus a centroid fallback.
  2. **Relative (refinement)**: place every `relative` zone by
     looking up its target's box from pass 1. When the target
     doesn't resolve to a real role, fall back to the canvas
     centroid (the corpus has 52 such dangling targets).

The engine produces a dict mapping zone role → 4-tuple
``(x, y, w, h)``. Coordinates are in canvas pixels; the FrameGraph
renderer consumes these directly.

Round 2 Phase 2 additions
-------------------------

- **Span**: a zone with ``span: {h: N}`` claims N adjacent cells
  along the row, gaining ``(N-1)`` cells of width plus the
  inter-cell gutters. Annotation enforces no overlap with
  sibling-anchored zones.
- **Density**: when ``compute_boxes(..., fill=<validated fill>)``
  is called, same-cell siblings are allocated proportional to
  estimated content density (table_data > chart_data >
  list_items > title_body > metric > others). Without a fill,
  same-cell siblings split uniformly (Round 1 behavior).
- **Backwards compatible**: ``compute_boxes(pattern, w, h)``
  with no ``fill`` argument and a pattern whose zones all use
  ``span: {h: 1, v: 1}`` produces byte-identical results to
  Round 1. The corpus-coverage and BMC-golden tests rely on
  this.

Design principles
-----------------

- **Deterministic.** Same pattern + canvas → same boxes. No RNG;
  zone ordering follows the pattern's declaration order.
- **Total.** Every zone gets a box. Unknown regions and dangling
  relative targets get sensible fallbacks rather than errors.
- **Bounded.** No box exceeds canvas + 1px (rounding tolerance).
- **No overlap among same-cell anchor siblings.** Cells with N
  zones split N ways (horizontal then vertical when needed).

Limitations (deferred to later phases)
--------------------------------------

- Region layouts cover the top-5 named regions; less-common
  regions fall back to centered placement.
- Relative placement applies a fixed offset (canvas-edge spacing
  fraction). No collision detection between relative zones and
  pre-placed anchor/region zones.
- Density estimation reads content_type and (when available) the
  fill payload; it does not measure actual rendered text width.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from framegraph._patterns import (
    Anchor,
    PatternZone,
    RegionPlacement,
    RelativePlacement,
    SlidePattern,
)

__all__ = [
    "Box",
    "LayoutPlan",
    "LayoutReport",
    "compute_boxes",
    "compute_layout_plan",
]


# A box is a 4-tuple `(x, y, w, h)` in canvas pixels. Equality is
# floating-point exact; callers compare boxes directly.
Box = tuple[float, float, float, float]


# ─────────────────────────────────────────────────────────────────
# 9-cell grid geometry
# ─────────────────────────────────────────────────────────────────


_H_INDEX = {"left": 0, "center": 1, "right": 2}
_V_INDEX = {"top": 0, "middle": 1, "bottom": 2}


# ─────────────────────────────────────────────────────────────────
# Wrap-aware string measurer — used by the planner to estimate
# real wrapped-text height per zone before deciding geometry.
# Mirrors the renderer's per-character-class width tables so the
# planner's measurement matches what the renderer will draw.
# ─────────────────────────────────────────────────────────────────

_CW_NORMAL: dict[str, float] = {
    "narrow": 0.34,
    "normal": 0.50,
    "wide": 0.65,
    "space": 0.25,
    "digit": 0.52,
    "punct": 0.30,
}
_CW_BOLD: dict[str, float] = {
    "narrow": 0.38,
    "normal": 0.56,
    "wide": 0.72,
    "space": 0.28,
    "digit": 0.58,
    "punct": 0.34,
}
_NARROW_CH: set[str] = set("ijlfrт:;!|1()")
_WIDE_CH: set[str] = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw@#%")
_DIGIT_CH: set[str] = set("0123456789")
_PUNCT_CH: set[str] = set(",.'\"-–—")


def _char_em(c: str, bold: bool) -> float:
    d = _CW_BOLD if bold else _CW_NORMAL
    if c in (" ", "\t"):
        return d["space"]
    if c in _NARROW_CH:
        return d["narrow"]
    if c in _WIDE_CH:
        return d["wide"]
    if c in _DIGIT_CH:
        return d["digit"]
    if c in _PUNCT_CH:
        return d["punct"]
    return d["normal"]


def _str_width(text: str, fs: float, bold: bool = False) -> float:
    """Estimate rendered width of `text` in pixels at `fs` font size."""
    return sum(_char_em(c, bold) for c in text) * fs


def _count_wrapped_lines(text: str, fs: float, avail_w: float, bold: bool = False) -> int:
    """Count how many wrapped lines `text` occupies at `fs` and `avail_w`.

    Mirrors the renderer's word-wrapping. Used by the planner so its
    height estimate matches what the renderer will actually draw.
    """
    if not text:
        return 1
    if avail_w <= 0:
        return 1
    n = 0
    # Apply the same 8% safety margin the renderers use.
    safe = avail_w * 0.92
    for paragraph in str(text).split("\n"):
        words = paragraph.split()
        if not words:
            n += 1
            continue
        line = ""
        for word in words:
            test = (line + " " + word).strip()
            if line and _str_width(test, fs, bold) > safe:
                n += 1
                line = word
            else:
                line = test
        if line:
            n += 1
    return max(1, n)


# ─────────────────────────────────────────────────────────────────
# AnchorGrid — universal NxM partition derived from used anchors
# ─────────────────────────────────────────────────────────────────


class _AnchorGrid:
    """The rectilinear partition implied by a pattern's anchor zones.

    A pattern declares each zone's anchor as one of nine ``(h, v)``
    positions — ``(left|center|right) × (top|middle|bottom)``. The
    grid this implies is **not** a fixed 3×3; it is the cross product
    of the *unique* h-coordinates and v-coordinates the pattern
    actually uses, expanded to cover any spans. SWOT's four corner
    anchors imply a 2×2 partition; a one-row 3-up implies a 1×3; the
    full 9-block BMC implies a 3×3.

    Cells fill the inner canvas (canvas minus outer margin) with
    equal-sized columns and rows separated by gutters of one margin.

    The grid is total over the pattern's anchor cells (every used
    ``(h, v)`` resolves to a cell). Asking for an unused ``(h, v)``
    raises KeyError — by construction no caller does.
    """

    __slots__ = (
        "cols",
        "rows",
        "_col_x",
        "_col_w",
        "_row_y",
        "_row_h",
        "_margin",
    )

    def __init__(
        self,
        cols: list[str],
        rows: list[str],
        col_x: list[float],
        col_w: list[float],
        row_y: list[float],
        row_h: list[float],
        margin: float,
    ) -> None:
        self.cols = cols
        self.rows = rows
        self._col_x = col_x
        self._col_w = col_w
        self._row_y = row_y
        self._row_h = row_h
        self._margin = margin

    @classmethod
    def from_zones(
        cls,
        zones: list[PatternZone],
        canvas_w: float,
        canvas_h: float,
        margin: float,
        fill: BaseModel | None = None,
    ) -> _AnchorGrid:
        """Derive the partition from the union of anchor coordinates.

        Two universal rules apply:

        1. **Used coordinates only.** The grid's columns and rows are
           the unique (h, v) values the pattern's anchors actually
           use, expanded by spans. Unused axes don't appear, so dead
           bands never exist.

        2. **Weighted by demand.** Column widths are proportional to
           the maximum content density across all cells in that
           column (and analogously for row heights). A column whose
           cell holds two table-data zones gets more width than a
           column whose cell holds one short list. Without this rule,
           equal-width columns force same-cell siblings to fight over
           too narrow a slice; with it, demand follows usage.

        Without any zones the grid degenerates to a 1×1 covering the
        full inner canvas.
        """
        used_cols: set[str] = set()
        used_rows: set[str] = set()
        # cell_demand_w / cell_demand_h: per-cell width / height
        # demand from each zone, indexed by (col, row).
        cell_demand_w: dict[tuple[str, str], list[float]] = {}
        cell_demand_h: dict[tuple[str, str], list[float]] = {}
        for z in zones:
            place = z.placement
            if not isinstance(place, Anchor) or place.fullbleed:
                continue
            assert place.h is not None and place.v is not None
            col_idx = _H_INDEX[place.h]
            row_idx = _V_INDEX[place.v]
            cells_for_zone: list[tuple[str, str]] = []
            for c in range(col_idx, min(3, col_idx + max(1, z.span.h))):
                used_cols.add(_inv(_H_INDEX, c))
                for r in range(row_idx, min(3, row_idx + max(1, z.span.v))):
                    used_rows.add(_inv(_V_INDEX, r))
                    cells_for_zone.append((_inv(_H_INDEX, c), _inv(_V_INDEX, r)))
            w_demand = _density_weight(z, fill)
            h_demand = _row_demand_weight(z, fill)
            for cell_key in cells_for_zone:
                cell_demand_w.setdefault(cell_key, []).append(w_demand)
                cell_demand_h.setdefault(cell_key, []).append(h_demand)

        cols = sorted(used_cols, key=lambda c: _H_INDEX[c]) or ["left"]
        rows = sorted(used_rows, key=lambda r: _V_INDEX[r]) or ["top"]

        # Per-column width demand. For columns whose cells contain
        # siblings that will stack vertically (wide-content types),
        # the column-width demand is the *max* across siblings (not
        # sum) since they share full width. For horizontally-split
        # siblings, sum applies.
        wide_types = {"table_data", "chart_data", "list_items"}
        col_weight: list[float] = []
        for col in cols:
            best = 0.0
            for row in rows:
                key = (col, row)
                widths = cell_demand_w.get(key, [])
                # Look at the actual zones in this cell to decide
                # split vs. stack.
                zones_here = [
                    z
                    for z in zones
                    if isinstance(z.placement, Anchor)
                    and not z.placement.fullbleed
                    and z.placement.h == col
                    and z.placement.v == row
                ]
                n_wide = sum(1 for z in zones_here if (z.content_type or "") in wide_types)
                stacks = n_wide >= (len(zones_here) + 1) // 2
                if not widths:
                    cell_w = 0.0
                else:
                    cell_w = (max(widths) if stacks else sum(widths)) or 1.0
                best = max(best, cell_w)
            col_weight.append(best)

        # Per-row height demand. Stacking siblings need the SUM of
        # their heights (each gets full width but its own row slot);
        # split siblings need only the max (they share row height).
        row_weight: list[float] = []
        for row in rows:
            best = 0.0
            for col in cols:
                key = (col, row)
                heights = cell_demand_h.get(key, [])
                zones_here = [
                    z
                    for z in zones
                    if isinstance(z.placement, Anchor)
                    and not z.placement.fullbleed
                    and z.placement.h == col
                    and z.placement.v == row
                ]
                n_wide = sum(1 for z in zones_here if (z.content_type or "") in wide_types)
                stacks = n_wide >= (len(zones_here) + 1) // 2 and len(zones_here) > 1
                cell_h = sum(heights) if stacks else (max(heights) if heights else 0.0)
                best = max(best, cell_h)
            row_weight.append(best or 1.0)

        n_cols = len(cols)
        n_rows = len(rows)
        inner_w = canvas_w - 2 * margin
        inner_h = canvas_h - 2 * margin
        avail_w = inner_w - (n_cols - 1) * margin
        avail_h = inner_h - (n_rows - 1) * margin

        total_cw = sum(col_weight) or 1.0
        total_rw = sum(row_weight) or 1.0
        col_w = [avail_w * (w / total_cw) for w in col_weight]
        row_h = [avail_h * (w / total_rw) for w in row_weight]

        # Enforce minimum row heights up to the available canvas
        # height — but never push the layout *past* the canvas
        # surface the deck reserved. When the natural floors fit
        # within `avail_h`, raise short rows to their floor and
        # shrink over-allocated rows proportionally to absorb the
        # difference. When floors exceed `avail_h`, allocate every
        # row its weighted share of `avail_h` (so cards always stay
        # inside the slide's content area) and let the renderer
        # auto-shrink + report violations from there.
        row_min_h: list[float] = []
        for row in rows:
            best_min = 0.0
            for col in cols:
                zones_here = [
                    z
                    for z in zones
                    if isinstance(z.placement, Anchor)
                    and not z.placement.fullbleed
                    and z.placement.h == col
                    and z.placement.v == row
                ]
                if not zones_here:
                    continue
                wide_types = {"table_data", "chart_data", "list_items"}
                n_wide = sum(1 for z in zones_here if (z.content_type or "") in wide_types)
                stacks = n_wide >= (len(zones_here) + 1) // 2 and len(zones_here) > 1
                if stacks:
                    cell_min = sum(_min_natural_height(z, fill) for z in zones_here)
                    cell_min += (len(zones_here) - 1) * (margin / 2)
                else:
                    cell_min = max(_min_natural_height(z, fill) for z in zones_here)
                best_min = max(best_min, cell_min)
            row_min_h.append(best_min)

        # Apply floors when they fit; otherwise scale them down
        # proportionally so the *whole* layout fits within `avail_h`.
        # The render layer handles further shrinking and reporting.
        total_min = sum(row_min_h)
        if total_min <= avail_h:
            # Fit comfortably. Raise short rows to their floor and
            # rebalance the surplus across over-weighted rows.
            for i in range(n_rows):
                if row_h[i] < row_min_h[i]:
                    row_h[i] = row_min_h[i]
            overshoot = sum(row_h) - avail_h
            if overshoot > 0:
                # Shrink rows that are above their floor by the
                # overshoot, weighted by their headroom.
                headroom = [max(0.0, row_h[i] - row_min_h[i]) for i in range(n_rows)]
                total_head = sum(headroom)
                if total_head > 0:
                    for i in range(n_rows):
                        row_h[i] -= overshoot * (headroom[i] / total_head)
        else:
            # Floors exceed the canvas. Allocate every row a
            # proportional share of `avail_h` so cards stay in
            # bounds; the renderer's auto-shrink + constraint report
            # tells the operator which zones got squeezed.
            scale = avail_h / total_min
            for i in range(n_rows):
                row_h[i] = row_min_h[i] * scale

        col_x: list[float] = []
        x = margin
        for w in col_w:
            col_x.append(x)
            x += w + margin
        row_y: list[float] = []
        y = margin
        for h in row_h:
            row_y.append(y)
            y += h + margin

        return cls(cols, rows, col_x, col_w, row_y, row_h, margin)

    def cell(self, h: str, v: str) -> Box:
        """Return the box for a single ``(h, v)`` cell."""
        ci = self.cols.index(h)
        ri = self.rows.index(v)
        return (self._col_x[ci], self._row_y[ri], self._col_w[ci], self._row_h[ri])

    def span_box(self, h: str, v: str, h_span: int, v_span: int) -> Box:
        """Return the box covering ``h_span × v_span`` cells starting at ``(h, v)``.

        The span is clamped to the grid's actual extent — a span past
        the last column collapses to 1 in that axis, never extends
        beyond the canvas.
        """
        ci = self.cols.index(h)
        ri = self.rows.index(v)
        h_span = max(1, min(h_span, len(self.cols) - ci))
        v_span = max(1, min(v_span, len(self.rows) - ri))
        x = self._col_x[ci]
        y = self._row_y[ri]
        # Sum cell widths in the span plus inter-cell gutters.
        w = sum(self._col_w[ci : ci + h_span]) + (h_span - 1) * self._margin
        h_box = sum(self._row_h[ri : ri + v_span]) + (v_span - 1) * self._margin
        return (x, y, w, h_box)


def _inv(idx: dict[str, int], v: int) -> str:
    """Inverse lookup for the H_INDEX / V_INDEX maps."""
    for k, n in idx.items():
        if n == v:
            return k
    raise KeyError(v)


def _grid_cell(
    canvas_w: float,
    canvas_h: float,
    margin: float,
    h: str,
    v: str,
) -> Box:
    """Return the box for one of the nine grid cells.

    The grid divides the canvas (minus an outer margin) into a 3×3
    array of equally-sized cells separated by a margin gutter.
    """
    inner_w = canvas_w - 2 * margin
    inner_h = canvas_h - 2 * margin
    # Two gutters between three cells per axis.
    cell_w = (inner_w - 2 * margin) / 3
    cell_h = (inner_h - 2 * margin) / 3
    col = _H_INDEX[h]
    row = _V_INDEX[v]
    x = margin + col * (cell_w + margin)
    y = margin + row * (cell_h + margin)
    return (x, y, cell_w, cell_h)


def _fullbleed(canvas_w: float, canvas_h: float, margin: float) -> Box:
    """Full-bleed zone — covers the entire canvas (margin-aware)."""
    return (margin / 2, margin / 2, canvas_w - margin, canvas_h - margin)


def _grid_span_box(
    canvas_w: float,
    canvas_h: float,
    margin: float,
    h: str,
    v: str,
    h_span: int,
    v_span: int,
) -> Box:
    """Return the box covering ``h_span × v_span`` cells starting at ``(h, v)``.

    A spanning zone claims its anchor cell plus ``h_span-1`` cells
    to the right (and ``v_span-1`` below). The resulting box covers
    those cells plus the gutters between them.

    Spans are clamped so the zone never extends past the canvas
    edge (a zone at ``(right, middle)`` with ``span: {h: 3}``
    behaves like ``span: {h: 1}`` because there are no cells to
    the right).
    """
    inner_w = canvas_w - 2 * margin
    inner_h = canvas_h - 2 * margin
    cell_w = (inner_w - 2 * margin) / 3
    cell_h = (inner_h - 2 * margin) / 3
    col = _H_INDEX[h]
    row = _V_INDEX[v]

    # Clamp the span so it doesn't extend past the canvas edge.
    h_span = max(1, min(h_span, 3 - col))
    v_span = max(1, min(v_span, 3 - row))

    x = margin + col * (cell_w + margin)
    y = margin + row * (cell_h + margin)
    # (h_span-1) cell widths plus (h_span-1) gutters of `margin`.
    w = h_span * cell_w + (h_span - 1) * margin
    h_box = v_span * cell_h + (v_span - 1) * margin
    return (x, y, w, h_box)


# ─────────────────────────────────────────────────────────────────
# Density estimator — drives same-cell sibling allocation
# ─────────────────────────────────────────────────────────────────


# Base weights per content_type. Higher = more horizontal space
# claimed when same-cell siblings differ. Tables and charts crave
# width; metrics and short texts don't.
_BASE_DENSITY: dict[str, float] = {
    "table_data": 3.0,
    "chart_data": 2.5,
    "list_items": 1.8,
    "title_body": 1.0,
    "comparison": 1.5,
    "metric": 0.8,
    "key_value": 1.0,
    "image": 2.0,
    "axis_label": 0.5,
    "decorative": 0.5,
}


# Multipliers applied on top of _BASE_DENSITY based on the zone's
# declared visual `size`. A `xl` title or a `full`-bleed image claims
# more layout space than an `xs` caption, regardless of their
# content_type. `equal` and `medium` are the neutral baseline; the
# others scale around them.
_SIZE_MULTIPLIER: dict[str, float] = {
    "xs": 0.4,
    "small": 0.65,
    "medium": 1.0,
    "equal": 1.0,
    "variable": 1.0,
    "contextual": 1.0,
    "large": 1.5,
    "xl": 2.0,
    "full": 2.5,
}


def _row_demand_weight(zone: PatternZone, fill: BaseModel | None) -> float:
    """Estimate a zone's relative VERTICAL demand.

    Row heights need a different weighting than column widths: a
    list with 8 items demands much more vertical space than a list
    with 2, even if both have the same content_type. This function
    is the row-height analogue of `_density_weight` (which estimates
    horizontal demand).

    Without a fill, returns the size multiplier — patterns get
    unweighted rows. With a fill, refines based on item count for
    list_items and key_value, and row count for tables.
    """
    weight = _SIZE_MULTIPLIER.get(zone.size, 1.0)
    if fill is None:
        return weight
    value = getattr(fill, zone.role, None)
    if value is None:
        return weight
    ct = zone.content_type or "title_body"
    try:
        if ct == "list_items":
            n = len(list(value or []))
            # Each item ≈ 1 unit; baseline of 2 to avoid zero rows.
            weight *= max(2.0, float(n))
        elif ct == "key_value":
            n = len(dict(value or {}))
            weight *= max(2.0, float(n))
        elif ct == "table_data":
            rows = list(getattr(value, "rows", None) or [])
            n = len(rows) + (1 if getattr(value, "headers", None) else 0)
            weight *= max(2.0, float(n))
        elif ct == "chart_data":
            weight *= 4.0  # charts need vertical room
        elif ct in ("title_body", "comparison"):
            weight *= 2.5
        elif ct == "metric":
            weight *= 2.0
    except (TypeError, AttributeError):
        pass
    return weight


# Minimum pixel heights per content_type — the layout must guarantee
# at least this much vertical room per zone, before chrome and card
# padding. List_items and table_data scale with item count.
_MIN_BODY_LINE_PX: float = 19.0  # one body line at 14px font with line-height 1.35
_MIN_CARD_OVERHEAD_PX: float = 36.0  # label band + card padding (top+bottom)


def _min_natural_height(zone: PatternZone, fill: BaseModel | None) -> float:
    """Minimum pixel height a zone needs to render its content honestly.

    This is the floor the layout module must respect — anything less
    means content is crushed or hidden. The estimate is intentionally
    conservative; real rendered content may need a bit more, which
    the renderer accommodates by drawing slightly past the box.
    """
    base = _MIN_CARD_OVERHEAD_PX
    if fill is None:
        return base + _MIN_BODY_LINE_PX * 2  # default: room for ≈2 lines
    value = getattr(fill, zone.role, None)
    ct = zone.content_type or "title_body"
    if value is None:
        return base + _MIN_BODY_LINE_PX * 2
    try:
        if ct == "list_items":
            n = max(1, len(list(value or [])))
            return base + _MIN_BODY_LINE_PX * n
        if ct == "key_value":
            n = max(1, len(dict(value or {})))
            return base + _MIN_BODY_LINE_PX * n
        if ct == "table_data":
            rows = list(getattr(value, "rows", None) or [])
            n = len(rows) + (1 if getattr(value, "headers", None) else 0)
            # Tables need a bit more per row than a list line.
            return base + 26.0 * max(1, n)
        if ct == "chart_data":
            return base + 120.0
        if ct in ("title_body", "comparison"):
            return base + _MIN_BODY_LINE_PX * 4
        if ct == "metric":
            return base + 70.0
    except (TypeError, AttributeError):
        pass
    return base + _MIN_BODY_LINE_PX * 2


def _density_weight(zone: PatternZone, fill: BaseModel | None) -> float:
    """Estimate a zone's relative width demand.

    The weight combines three signals:

      1. Base demand for the zone's ``content_type`` (tables claim
         more than captions).
      2. The declared visual ``size`` (``xl`` claims more than
         ``xs``).
      3. Optional content-aware refinement when ``fill`` is supplied
         (a 5-column table claims more than a 2-column table).

    The function is total: any zone returns a positive float.
    """
    ct = zone.content_type or "title_body"
    weight = _BASE_DENSITY.get(ct, 1.0) * _SIZE_MULTIPLIER.get(zone.size, 1.0)

    if fill is None:
        return weight

    # Pull the per-role payload off the fill object.
    value = getattr(fill, zone.role, None)
    if value is None:
        return weight

    # Refinements per content_type.
    if ct == "table_data":
        # Width scales with column count; floor of 1, cap at 6×.
        try:
            cols = len(getattr(value, "headers", None) or [])
        except TypeError:
            cols = 0
        if cols > 0:
            weight = _BASE_DENSITY["table_data"] * (cols / 3.0)
            weight = max(1.5, min(weight, 6.0))
    elif ct == "list_items":
        # Width scales with longest item's char count, capped.
        try:
            items = list(value or [])
            longest = max((len(str(it)) for it in items), default=10)
        except TypeError:
            longest = 10
        weight = _BASE_DENSITY["list_items"] * (longest / 20.0)
        weight = max(1.0, min(weight, 4.0))
    elif ct == "chart_data":
        try:
            n_series = len(getattr(value, "series", None) or [])
        except TypeError:
            n_series = 0
        # More series → more width up to 4×.
        weight = _BASE_DENSITY["chart_data"] * (1 + n_series * 0.2)
        weight = min(weight, 4.0)

    return weight


# ─────────────────────────────────────────────────────────────────
# Same-cell sibling subdivision
# ─────────────────────────────────────────────────────────────────


def _subdivide_cell(cell: Box, n: int, margin: float) -> list[Box]:
    """Split a cell box into ``n`` child boxes.

    Strategy:
      - n=1: full cell
      - n=2: side-by-side (horizontal split)
      - n=3: three columns
      - n=4+: horizontal split into ceil(sqrt(n)) columns × rows.

    Inter-sibling gutter is half the canvas margin so children
    stay inside the parent cell with breathing room.
    """
    cx, cy, cw, ch = cell
    if n <= 1:
        return [cell]

    # Pick a column count that keeps cells roughly square.
    if n == 2:
        cols, rows = 2, 1
    elif n == 3:
        cols, rows = 3, 1
    elif n == 4:
        cols, rows = 2, 2
    else:
        # Generic: square-ish grid.
        cols = int(n**0.5 + 0.5)
        if cols < 1:
            cols = 1
        rows = (n + cols - 1) // cols

    gutter = margin / 2
    sub_w = (cw - (cols - 1) * gutter) / cols
    sub_h = (ch - (rows - 1) * gutter) / rows

    boxes: list[Box] = []
    for i in range(n):
        col = i % cols
        row = i // cols
        x = cx + col * (sub_w + gutter)
        y = cy + row * (sub_h + gutter)
        boxes.append((x, y, sub_w, sub_h))
    return boxes


# ─────────────────────────────────────────────────────────────────
# Region resolvers — top-5 hand-coded layouts + fallback
# ─────────────────────────────────────────────────────────────────


def _region_box(
    region: str,
    canvas_w: float,
    canvas_h: float,
    margin: float,
) -> Box:
    """Return the box for a named region.

    Top-5 regions get hand-coded layouts:
      - matrix_body    — central 60% of the canvas
      - highlighted    — central emphasis (smaller, centered)
      - timeline_body  — full-width horizontal band, lower-middle
      - roadmap_body   — full-width horizontal band, middle
      - ring           — central area (typically holds the hub of
                         a wheel pattern; surrounding nodes use
                         relative placements around it)

    Other regions (quadrant, canvas, scale_body, swimlanes, …)
    fall back to centered.
    """
    inner_w = canvas_w - 2 * margin
    inner_h = canvas_h - 2 * margin

    if region == "matrix_body":
        # Central 60% × 60% box.
        w = inner_w * 0.6
        h = inner_h * 0.6
        return (margin + (inner_w - w) / 2, margin + (inner_h - h) / 2, w, h)

    if region == "highlighted":
        # Smaller central emphasis (~40% × 40%).
        w = inner_w * 0.4
        h = inner_h * 0.4
        return (margin + (inner_w - w) / 2, margin + (inner_h - h) / 2, w, h)

    if region in ("timeline_body", "roadmap_body"):
        # Full-width band, vertically centered.
        w = inner_w
        h = inner_h * 0.4
        return (margin, margin + (inner_h - h) / 2, w, h)

    if region == "ring":
        # Central hub (small, surrounded by satellites positioned
        # via relative placements).
        w = inner_w * 0.3
        h = inner_h * 0.3
        return (margin + (inner_w - w) / 2, margin + (inner_h - h) / 2, w, h)

    # Fallback: centered medium box (~50% × 50%).
    w = inner_w * 0.5
    h = inner_h * 0.5
    return (margin + (inner_w - w) / 2, margin + (inner_h - h) / 2, w, h)


# ─────────────────────────────────────────────────────────────────
# Relative resolver — second pass over a target's box
# ─────────────────────────────────────────────────────────────────


_MIN_VISIBLE = 12.0


def _clamp_to_canvas(box: Box, canvas_w: float, canvas_h: float, margin: float) -> Box:
    """Clamp a `(x, y, w, h)` box to the canvas inside the outer margin.

    Every relative placement runs its candidate box through this so
    `_relative_box` outputs stay within `[margin/2, canvas - margin/2]`
    on both axes — without it, a "below" placement against a tall
    target lands past the canvas edge (Round 2 regression noticed
    on `Title Slide` #1 and `Milestone Tracker` #13, where the
    subtitle / dates zone's natural placement put it past the 1080-px
    canvas bottom).

    When clipping would leave a degenerate (zero-size) box, the
    origin is pulled back so the final box has at least `_MIN_VISIBLE`
    pixels on each axis. That keeps zones visible and on-canvas at
    the cost of a small overlap with the target. The corpus
    invariant ``w > 0 and h > 0`` holds; the relative ordering
    (`subtitle.y >= title.y + title.h - tolerance`) holds within the
    `_MIN_VISIBLE` tolerance band.
    """
    x, y, w, h = box
    half_m = margin / 2
    max_x = canvas_w - half_m
    max_y = canvas_h - half_m
    # Pull origin inside the inner band before clipping.
    x = max(x, half_m)
    y = max(y, half_m)
    # Clip width / height to the remaining canvas room.
    w = min(w, max_x - x)
    h = min(h, max_y - y)
    # Restore a minimum visible size at the canvas edge if the clip
    # left the box degenerate.
    if w < _MIN_VISIBLE:
        w = min(_MIN_VISIBLE, max_x - half_m)
        x = min(x, max_x - w)
    if h < _MIN_VISIBLE:
        h = min(_MIN_VISIBLE, max_y - half_m)
        y = min(y, max_y - h)
    return (x, max(y, half_m), max(w, 0.0), max(h, 0.0))


def _relative_box(
    relation: str,
    target_box: Box,
    canvas_w: float,
    canvas_h: float,
    margin: float,
) -> Box:
    """Place a zone relative to a target's already-computed box.

    Offsets are computed as fractions of the target's dimensions
    so the result scales with the target. Every result is clamped
    to the canvas via `_clamp_to_canvas` — the relative pass cannot
    push a box past the slide edge.
    """
    tx, ty, tw, th = target_box

    if relation == "below":
        candidate = (tx, ty + th + margin / 2, tw, max(th * 0.5, 40.0))
    elif relation == "above":
        h = max(th * 0.5, 40.0)
        candidate = (tx, max(ty - h - margin / 2, margin / 2), tw, h)
    elif relation == "left_of":
        w = max(tw * 0.4, 60.0)
        candidate = (max(tx - w - margin / 2, margin / 2), ty, w, th)
    elif relation == "right_of":
        w = max(tw * 0.4, 60.0)
        candidate = (tx + tw + margin / 2, ty, w, th)
    elif relation == "inside":
        # Inset by 10% on each side.
        pad_w = tw * 0.1
        pad_h = th * 0.1
        candidate = (tx + pad_w, ty + pad_h, tw - 2 * pad_w, th - 2 * pad_h)
    elif relation == "around":
        # A "ring" zone wrapping the target — slightly larger,
        # rendered behind the target by convention.
        pad_w = tw * 0.15
        pad_h = th * 0.15
        candidate = (
            tx - pad_w,
            ty - pad_h,
            tw + 2 * pad_w,
            th + 2 * pad_h,
        )
    elif relation == "between":
        # Place at the target's right edge, narrow box (so a
        # connector / divider sits next to it). When the target
        # is one side of a pair, callers can pick either end as
        # the target — the box just sits at one edge.
        w = max(tw * 0.2, 30.0)
        candidate = (tx + tw, ty + th * 0.4, w, th * 0.2)
    elif relation == "near":
        # Slightly offset to the lower-right of the target.
        candidate = (tx + tw * 0.1, ty + th + margin / 2, tw * 0.6, th * 0.4)
    elif relation == "on":
        # Overlay — same position as the target, slightly smaller.
        pad_w = tw * 0.05
        pad_h = th * 0.05
        candidate = (tx + pad_w, ty + pad_h, tw - 2 * pad_w, th - 2 * pad_h)
    else:
        # Unknown relation: return the target's box unchanged
        # (already known to be on-canvas — pass-through, no clamp).
        return target_box

    return _clamp_to_canvas(candidate, canvas_w, canvas_h, margin)


def _canvas_centroid(canvas_w: float, canvas_h: float, margin: float) -> Box:
    """Fallback box for relative zones whose target doesn't resolve.

    Centered, 30% × 30% — visible but not dominant. The corpus has
    52 such dangling targets; this keeps them from breaking the
    layout entirely.
    """
    inner_w = canvas_w - 2 * margin
    inner_h = canvas_h - 2 * margin
    w = inner_w * 0.3
    h = inner_h * 0.3
    return (margin + (inner_w - w) / 2, margin + (inner_h - h) / 2, w, h)


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────


def _density_subdivide(
    cell: Box,
    zones_in_cell: list[PatternZone],
    fill: BaseModel | None,
    margin: float,
) -> list[Box]:
    """Subdivide a cell among same-cell siblings.

    Universal rule:

      - **Wide-content siblings** (``table_data``, ``chart_data``,
        ``list_items``) stack **vertically** — each gets full cell
        width, sized proportional to its content's vertical demand
        (so a 7-row table ends up taller than a 2-row sibling).
      - **Narrow-content siblings** (``metric``, ``axis_label``,
        short ``title_body``) split **horizontally** by density
        weight.

    Decision is by majority of zones in the cell. ``n >= 4`` falls
    through to a uniform 2D grid (Round 1 deterministic behavior).
    """
    n = len(zones_in_cell)
    if n <= 1:
        return [cell]
    if n >= 4:
        return _subdivide_cell(cell, n, margin)

    cx, cy, cw, ch = cell
    gutter = margin / 2
    wide_types = {"table_data", "chart_data", "list_items"}
    n_wide = sum(1 for z in zones_in_cell if (z.content_type or "") in wide_types)

    if n_wide >= (n + 1) // 2:
        # Vertical stack, weighted by row-demand when fill present.
        weights = (
            [_row_demand_weight(z, fill) for z in zones_in_cell] if fill is not None else [1.0] * n
        )
        total = sum(weights) or 1.0
        available_h = ch - (n - 1) * gutter
        boxes: list[Box] = []
        y = cy
        for w_i in weights:
            sub_h = available_h * (w_i / total)
            boxes.append((cx, y, cw, sub_h))
            y += sub_h + gutter
        return boxes

    # Horizontal split for narrow-content siblings.
    if fill is None:
        return _subdivide_cell(cell, n, margin)
    weights = [_density_weight(z, fill) for z in zones_in_cell]
    total = sum(weights)
    if total <= 0:
        return _subdivide_cell(cell, n, margin)
    if max(weights) - min(weights) < 0.01:
        return _subdivide_cell(cell, n, margin)
    available_w = cw - (n - 1) * gutter
    sub_widths = [available_w * (w / total) for w in weights]
    boxes = []
    x = cx
    for sub_w in sub_widths:
        boxes.append((x, cy, sub_w, ch))
        x += sub_w + gutter
    return boxes


def compute_boxes(
    pattern: SlidePattern,
    canvas_w: float,
    canvas_h: float,
    *,
    margin: float = 24.0,
    fill: BaseModel | None = None,
) -> dict[str, Box]:
    """Compute one ``(x, y, w, h)`` box per zone in the pattern.

    Round 2 Phase 2: honors `PatternZone.span` for spanning zones
    and (when `fill` is supplied) allocates same-cell-sibling widths
    by content density.

    Args:
        pattern: The catalog pattern to lay out.
        canvas_w: Canvas width in pixels.
        canvas_h: Canvas height in pixels.
        margin: Outer canvas padding and inter-cell gutter, in
            pixels. Defaults to 24.
        fill: Optional validated fill (a Pydantic model with one
            attribute per zone role). When supplied, same-cell
            siblings are allocated proportional to estimated
            content density. When None, siblings split uniformly
            (matches Round 1 behavior).

    Returns:
        A mapping from zone role to ``(x, y, w, h)``. Order reflects
        the pattern's zone declaration order (Python dicts preserve
        insertion order).
    """
    boxes: dict[str, Box] = {}

    # ──── Pass 1a: bucket zones by anchor cell or region ────
    # A zone with span > 1 still belongs to its anchor cell — but
    # by construction (annotation invariant) it does not share its
    # anchor cell with sibling-anchored zones, so subdivision logic
    # below sees either {one spanning zone} or {N non-spanning zones}
    # in any given cell, never a mix.
    anchor_buckets: dict[tuple[str, str], list[PatternZone]] = {}
    region_zones: list[PatternZone] = []
    relative_zones: list[PatternZone] = []
    fullbleed_zones: list[PatternZone] = []

    for z in pattern.zones:
        place = z.placement
        if isinstance(place, Anchor):
            if place.fullbleed:
                fullbleed_zones.append(z)
            else:
                # h and v are guaranteed non-None when not fullbleed.
                assert place.h is not None and place.v is not None
                key = (place.h, place.v)
                anchor_buckets.setdefault(key, []).append(z)
        elif isinstance(place, RegionPlacement):
            region_zones.append(z)
        else:  # RelativePlacement
            relative_zones.append(z)

    # ──── Pass 1b: place fullbleed zones ────
    for z in fullbleed_zones:
        boxes[z.role] = _fullbleed(canvas_w, canvas_h, margin)

    # ──── Pass 1c: place anchor zones ────
    #
    # The anchor grid is **derived from the anchor positions actually
    # used by the pattern**, not a fixed 3×3. This is the universal
    # rule: a pattern's grid is its rectilinear partition.
    #
    #   SWOT (corners only)          → 2 cols × 2 rows
    #   2-up comparison (one row)    → 2 cols × 1 row
    #   3-up trio                    → 3 cols × 1 row
    #   BMC nine-block               → 3 cols × 3 rows
    #
    # We project every anchor zone — including its row/column span
    # extent — onto the (h, v) coordinate axes, take the union of
    # used coordinates, sort them, and compute pixel offsets so each
    # column/row gets a proportional slice of the inner canvas. This
    # collapses dead space when the pattern doesn't use the full 3×3
    # grid, while remaining a no-op when it does.
    grid = _AnchorGrid.from_zones(
        zones=[z for zs in anchor_buckets.values() for z in zs],
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        margin=margin,
        fill=fill,
    )

    # When a single zone occupies the cell *and* declares span > 1,
    # use its full spanning box. Otherwise treat as a normal cell
    # and subdivide among same-cell siblings.
    for cell_key, zones_in_cell in anchor_buckets.items():
        h, v = cell_key

        # Single-zone cell — honor span.
        if len(zones_in_cell) == 1:
            z = zones_in_cell[0]
            boxes[z.role] = grid.span_box(h, v, z.span.h, z.span.v)
            continue

        # Multi-zone cell — span is guaranteed default (1, 1) by
        # annotation invariant; subdivide.
        cell = grid.cell(h, v)
        sub_boxes = _density_subdivide(cell, zones_in_cell, fill, margin)
        for z, box in zip(zones_in_cell, sub_boxes):
            boxes[z.role] = box

    # ──── Pass 1d: place region zones ────
    for z in region_zones:
        place = z.placement
        assert isinstance(place, RegionPlacement)
        boxes[z.role] = _region_box(place.region, canvas_w, canvas_h, margin)

    # ──── Pass 2: place relative zones (now that targets are resolved) ────
    for z in relative_zones:
        place = z.placement
        assert isinstance(place, RelativePlacement)
        target_box = boxes.get(place.target)
        if target_box is None:
            # Dangling target — fall back to canvas centroid.
            boxes[z.role] = _canvas_centroid(canvas_w, canvas_h, margin)
        else:
            boxes[z.role] = _relative_box(place.relation, target_box, canvas_w, canvas_h, margin)

    return boxes


# ─────────────────────────────────────────────────────────────────
# Layout planner — single decision-maker for geometry + scale
# ─────────────────────────────────────────────────────────────────


class LayoutReport:
    """Outcome record for one slide's layout pass.

    The planner emits exactly one report per slide. It records:

    - the global typography scale that was applied (1.0 = nominal,
      < 1.0 = uniformly shrunk),
    - any zones whose content overflows even at the floor scale, with
      ``required_h`` / ``available_h`` per zone.

    Render is faithful — it does not look at this. Downstream
    consumers (deck loader, CLI) read the report to surface honest
    feedback to the operator.
    """

    __slots__ = ("scale", "min_scale", "overflows")

    def __init__(
        self,
        scale: float,
        min_scale: float,
        overflows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.scale = scale
        self.min_scale = min_scale
        self.overflows = overflows or []

    @property
    def fits(self) -> bool:
        """True when no zone overflows at the applied scale."""
        return not self.overflows

    @property
    def shrunk(self) -> bool:
        """True when the planner had to scale typography below 1.0."""
        return self.scale < 0.999


class LayoutPlan:
    """Result of `compute_layout_plan`: boxes + scale + report.

    Attributes:
        boxes: Per-zone box mapping ``role → (x, y, w, h)``.
        scale: Uniform typography scale to apply across the slide.
            1.0 = nominal stylesheet sizes; smaller values mean every
            text style on the slide is shrunk by this factor for
            visual coherence.
        report: `LayoutReport` carrying scale + per-zone overflow
            info for the operator.
    """

    __slots__ = ("boxes", "scale", "report")

    def __init__(
        self,
        boxes: dict[str, Box],
        scale: float,
        report: LayoutReport,
    ) -> None:
        self.boxes = boxes
        self.scale = scale
        self.report = report


# Floor for global typography scale. Anything below this is unreadable
# regardless of what the renderer would draw, so the planner caps and
# reports overflow instead of going further.
_MIN_GLOBAL_SCALE: float = 0.6


def _zone_min_h_at_scale(
    zone: PatternZone,
    fill: BaseModel | None,
    scale: float,
) -> float:
    """Estimated minimum pixel height the zone needs at a given scale.

    Layered on top of `_min_natural_height`, applies the planner's
    uniform scale factor to typography-derived demands. Card chrome
    (label band, padding) doesn't scale with the global font.
    """
    base = _MIN_CARD_OVERHEAD_PX
    natural = _min_natural_height(zone, fill)
    text_demand = max(0.0, natural - _MIN_CARD_OVERHEAD_PX)
    return base + text_demand * scale


def _solve_layout_at_scale(
    pattern: SlidePattern,
    canvas_w: float,
    canvas_h: float,
    margin: float,
    fill: BaseModel | None,
    scale: float,
) -> tuple[dict[str, Box], dict[str, float]]:
    """Compute boxes for the pattern at the given typography scale.

    Returns ``(boxes, demand_h_by_role)`` where demand is the
    estimated content-height each zone needs at this scale. The
    caller compares each ``boxes[role][3]`` to demand to detect
    overflow.
    """
    boxes = compute_boxes(pattern, canvas_w, canvas_h, margin=margin, fill=fill)
    demand_h = {z.role: _zone_min_h_at_scale(z, fill, scale) for z in pattern.zones}
    return boxes, demand_h


def compute_layout_plan(
    pattern: SlidePattern,
    canvas_w: float,
    canvas_h: float,
    *,
    margin: float = 24.0,
    fill: BaseModel | None = None,
) -> LayoutPlan:
    """Plan a slide layout — single decision-maker for geometry + scale.

    Algorithm:

      1. Try the layout at scale = 1.0 (nominal typography).
      2. If every zone's allocated box height ≥ the zone's
         estimated content-height demand, return scale = 1.0.
      3. Otherwise, find the largest scale factor in
         [_MIN_GLOBAL_SCALE, 1.0] at which all zones fit (binary
         search to ~0.01 precision).
      4. If even at the floor scale some zones overflow, return
         floor scale + a `LayoutReport` listing offenders.

    Renderer downstream applies `scale` uniformly to every text
    style on the slide. Render itself is faithful — it never
    decides scale or geometry.
    """
    # 1) try nominal
    boxes, demand = _solve_layout_at_scale(pattern, canvas_w, canvas_h, margin, fill, scale=1.0)

    def overflows_at(boxes: dict[str, Box], demand: dict[str, float]) -> list[dict[str, Any]]:
        return [
            {
                "role": role,
                "required_h": round(demand[role], 1),
                "available_h": round(box[3], 1),
            }
            for role, box in boxes.items()
            if demand.get(role, 0.0) > box[3] + 0.5
        ]

    overflows = overflows_at(boxes, demand)
    if not overflows:
        return LayoutPlan(
            boxes=boxes,
            scale=1.0,
            report=LayoutReport(scale=1.0, min_scale=_MIN_GLOBAL_SCALE),
        )

    # 2) binary-search for the largest fitting scale in [floor, 1.0)
    lo, hi = _MIN_GLOBAL_SCALE, 1.0
    best_fit_scale: float | None = None
    for _ in range(8):  # ~0.005 precision over [0.6, 1.0]
        mid = (lo + hi) / 2.0
        b, d = _solve_layout_at_scale(pattern, canvas_w, canvas_h, margin, fill, scale=mid)
        if not overflows_at(b, d):
            best_fit_scale = mid
            lo = mid  # try larger
        else:
            hi = mid  # try smaller

    if best_fit_scale is not None:
        boxes, demand = _solve_layout_at_scale(
            pattern, canvas_w, canvas_h, margin, fill, scale=best_fit_scale
        )
        return LayoutPlan(
            boxes=boxes,
            scale=best_fit_scale,
            report=LayoutReport(scale=best_fit_scale, min_scale=_MIN_GLOBAL_SCALE),
        )

    # 3) doesn't fit even at floor — emit boxes at floor and report
    #    every offending zone so the operator can act.
    boxes, demand = _solve_layout_at_scale(
        pattern, canvas_w, canvas_h, margin, fill, scale=_MIN_GLOBAL_SCALE
    )
    return LayoutPlan(
        boxes=boxes,
        scale=_MIN_GLOBAL_SCALE,
        report=LayoutReport(
            scale=_MIN_GLOBAL_SCALE,
            min_scale=_MIN_GLOBAL_SCALE,
            overflows=overflows_at(boxes, demand),
        ),
    )
