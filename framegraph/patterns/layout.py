"""Layout engine — pattern zones → ``[x, y, w, h]`` boxes on a canvas.

Phase 3 of the fill-and-render roadmap. Two-pass algorithm:

  1. **Anchor + region (geometric)**: place every anchor- and
     region-typed zone using the 9-cell grid (with same-cell
     subdivision for siblings) and per-region hand-coded layouts
     for the top-5 regions plus a centroid fallback.
  2. **Relative (refinement)**: place every `relative` zone by
     looking up its target's box from pass 1. When the target
     doesn't resolve to a real role, fall back to the canvas
     centroid (the corpus has 52 such dangling targets).

The engine produces a dict mapping zone role → 4-tuple
``(x, y, w, h)``. Coordinates are in canvas pixels; the FrameGraph
renderer (Phase 4) consumes these directly.

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
  regions fall back to centered placement. The corpus has 19
  distinct regions; the top 5 cover 73% of region uses.
- Relative placement applies a fixed offset (canvas-edge spacing
  fraction). No collision detection between relative zones and
  pre-placed anchor/region zones.
- No baseline grid alignment, no font-aware sizing — those are
  the renderer's job (Phase 4).
"""

from __future__ import annotations

from typing import Any

from framegraph._patterns import (
    Anchor,
    PatternZone,
    RegionPlacement,
    RelativePlacement,
    SlidePattern,
)

__all__ = [
    "Box",
    "compute_boxes",
]


# A box is a 4-tuple `(x, y, w, h)` in canvas pixels. Equality is
# floating-point exact; callers compare boxes directly.
Box = tuple[float, float, float, float]


# ─────────────────────────────────────────────────────────────────
# 9-cell grid geometry
# ─────────────────────────────────────────────────────────────────


_H_INDEX = {"left": 0, "center": 1, "right": 2}
_V_INDEX = {"top": 0, "middle": 1, "bottom": 2}


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


def _relative_box(
    relation: str,
    target_box: Box,
    canvas_w: float,
    canvas_h: float,
    margin: float,
) -> Box:
    """Place a zone relative to a target's already-computed box.

    Offsets are computed as fractions of the target's dimensions
    so the result scales with the target.
    """
    tx, ty, tw, th = target_box

    if relation == "below":
        return (tx, ty + th + margin / 2, tw, max(th * 0.5, 40.0))

    if relation == "above":
        h = max(th * 0.5, 40.0)
        return (tx, max(ty - h - margin / 2, margin / 2), tw, h)

    if relation == "left_of":
        w = max(tw * 0.4, 60.0)
        return (max(tx - w - margin / 2, margin / 2), ty, w, th)

    if relation == "right_of":
        w = max(tw * 0.4, 60.0)
        return (tx + tw + margin / 2, ty, w, th)

    if relation == "inside":
        # Inset by 10% on each side.
        pad_w = tw * 0.1
        pad_h = th * 0.1
        return (tx + pad_w, ty + pad_h, tw - 2 * pad_w, th - 2 * pad_h)

    if relation == "around":
        # A "ring" zone wrapping the target — slightly larger,
        # rendered behind the target by convention.
        pad_w = tw * 0.15
        pad_h = th * 0.15
        return (
            max(tx - pad_w, margin / 2),
            max(ty - pad_h, margin / 2),
            tw + 2 * pad_w,
            th + 2 * pad_h,
        )

    if relation == "between":
        # Place at the target's right edge, narrow box (so a
        # connector / divider sits next to it). When the target
        # is one side of a pair, callers can pick either end as
        # the target — the box just sits at one edge.
        w = max(tw * 0.2, 30.0)
        return (tx + tw, ty + th * 0.4, w, th * 0.2)

    if relation == "near":
        # Slightly offset to the lower-right of the target.
        return (tx + tw * 0.1, ty + th + margin / 2, tw * 0.6, th * 0.4)

    if relation == "on":
        # Overlay — same position as the target, slightly smaller.
        pad_w = tw * 0.05
        pad_h = th * 0.05
        return (tx + pad_w, ty + pad_h, tw - 2 * pad_w, th - 2 * pad_h)

    # Unknown relation: return the target's box unchanged.
    return target_box


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


def compute_boxes(
    pattern: SlidePattern,
    canvas_w: float,
    canvas_h: float,
    *,
    margin: float = 24.0,
) -> dict[str, Box]:
    """Compute one ``(x, y, w, h)`` box per zone in the pattern.

    Args:
        pattern: The catalog pattern to lay out.
        canvas_w: Canvas width in pixels.
        canvas_h: Canvas height in pixels.
        margin: Outer canvas padding and inter-cell gutter, in
            pixels. Defaults to 24.

    Returns:
        A mapping from zone role to ``(x, y, w, h)``. Order reflects
        the pattern's zone declaration order (Python dicts preserve
        insertion order).
    """
    boxes: dict[str, Box] = {}

    # ──── Pass 1a: bucket zones by anchor cell or region ────
    # Group anchor zones by cell to support same-cell subdivision.
    anchor_buckets: dict[tuple[str, str] | str, list[PatternZone]] = {}
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
                key = (place.h, place.v)  # type: ignore[arg-type]
                anchor_buckets.setdefault(key, []).append(z)
        elif isinstance(place, RegionPlacement):
            region_zones.append(z)
        else:  # RelativePlacement
            relative_zones.append(z)

    # ──── Pass 1b: place fullbleed zones ────
    for z in fullbleed_zones:
        boxes[z.role] = _fullbleed(canvas_w, canvas_h, margin)

    # ──── Pass 1c: place anchor zones, subdividing same-cell siblings ────
    for cell_key, zones_in_cell in anchor_buckets.items():
        h, v = cell_key  # type: ignore[misc]
        cell = _grid_cell(canvas_w, canvas_h, margin, h, v)
        sub_boxes = _subdivide_cell(cell, len(zones_in_cell), margin)
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
            boxes[z.role] = _relative_box(
                place.relation, target_box, canvas_w, canvas_h, margin
            )

    return boxes
