"""Orthogonal connector routing with stub clearance and obstacle avoidance.

Pure-geometry helpers — no SVG, no I/O. Consumed by
`framegraph.renderers.lines.render_connector` to produce visually
clean orthogonal paths between two endpoints when each endpoint
declares the cardinal `side` of the box it anchors to.

The previous renderer always produced a Z-shaped path bent at
``mid_x = (start.x + end.x) / 2`` with no awareness of:

  - which side of the source/destination box the line should leave;
  - whether the bend lane crosses through other boxes.

This module fixes both. Its public surface is :func:`route_orthogonal`;
the private helpers exist purely so they can be unit-tested in
isolation.
"""

from __future__ import annotations

from collections.abc import Sequence

from framegraph._helpers import Box, Point


__all__ = ["route_orthogonal", "segment_intersects_box", "normalize_side"]


_SIDE_ALIASES: dict[str, str] = {
    "north": "north", "top": "north",
    "south": "south", "bottom": "south",
    "east":  "east",  "right": "east",
    "west":  "west",  "left": "west",
}

# Outward unit vector for each cardinal side.
_SIDE_VECTOR: dict[str, tuple[float, float]] = {
    "north": (0.0, -1.0),
    "south": (0.0,  1.0),
    "east":  (1.0,  0.0),
    "west":  (-1.0, 0.0),
}


def normalize_side(side: str | None) -> str | None:
    """Map any accepted side spelling to canonical `north/south/east/west`.

    Returns None when ``side`` is None or unrecognised, so the caller can
    treat "no side info" and "explicit literal" uniformly.
    """
    if side is None:
        return None
    return _SIDE_ALIASES.get(str(side).lower())


def segment_intersects_box(
    p0: Point,
    p1: Point,
    rect: Box,
    *,
    clearance: float = 0.0,
) -> bool:
    """True when the axis-aligned segment ``p0→p1`` intersects ``rect``.

    Both segment endpoints lying *on* the box boundary do NOT count as
    an intersection — the path just touches the obstacle. ``clearance``
    inflates the obstacle by that many pixels on every side before the
    test, which is how callers reserve a visual buffer around boxes.

    Only horizontal and vertical segments are supported (this is for
    orthogonal routing); diagonal segments raise. Endpoints that lie on
    the inflated rectangle edge are treated as outside, not inside, so
    a connector terminating *at* a side anchor doesn't self-report as a
    collision with its own target box.
    """
    x, y, w, h = rect
    rx0 = x - clearance
    ry0 = y - clearance
    rx1 = x + w + clearance
    ry1 = y + h + clearance

    x0, y0 = p0
    x1, y1 = p1
    horizontal = abs(y0 - y1) < 1e-9
    vertical = abs(x0 - x1) < 1e-9

    if horizontal and vertical:
        # Zero-length point — touches if strictly inside the box.
        return rx0 < x0 < rx1 and ry0 < y0 < ry1
    if not (horizontal or vertical):
        raise ValueError("segment_intersects_box only supports axis-aligned segments")

    if horizontal:
        # Y must be strictly inside the inflated box, and the segment's
        # x range must overlap the inflated box's x range with positive
        # interior intersection.
        if not (ry0 < y0 < ry1):
            return False
        seg_lo, seg_hi = (x0, x1) if x0 <= x1 else (x1, x0)
        return seg_hi > rx0 and seg_lo < rx1
    # vertical
    if not (rx0 < x0 < rx1):
        return False
    seg_lo, seg_hi = (y0, y1) if y0 <= y1 else (y1, y0)
    return seg_hi > ry0 and seg_lo < ry1


def _step(p: Point, side: str | None, distance: float) -> Point:
    """Return ``p`` translated ``distance`` units outward along ``side``."""
    if side is None:
        return p
    dx, dy = _SIDE_VECTOR[side]
    return p[0] + dx * distance, p[1] + dy * distance


def _is_horizontal_side(side: str | None) -> bool:
    return side in ("east", "west")


def _is_vertical_side(side: str | None) -> bool:
    return side in ("north", "south")


def _dedupe(points: Sequence[Point]) -> list[Point]:
    """Drop consecutive duplicate points (within 0.5px)."""
    out: list[Point] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 0.5 or abs(p[1] - out[-1][1]) > 0.5:
            out.append((float(p[0]), float(p[1])))
    return out


def _path_hits_obstacles(
    path: Sequence[Point],
    obstacles: Sequence[Box],
    clearance: float,
) -> bool:
    """True when any segment of ``path`` intersects any obstacle box."""
    if not obstacles or len(path) < 2:
        return False
    for i in range(len(path) - 1):
        for rect in obstacles:
            if segment_intersects_box(path[i], path[i + 1], rect, clearance=clearance):
                return True
    return False


def _candidate_lanes(a: float, b: float, spread: int = 5) -> list[float]:
    """Generate candidate bend-line positions between ``a`` and ``b``.

    Yields the midpoint first, then progressively wider offsets in
    alternating directions. ``spread`` controls how many offsets the
    router will try before giving up. Spacing of 32 px matches the
    framework's typical inter-box gutter; finer grids produce more
    options at the cost of longer search.
    """
    mid = (a + b) / 2.0
    out: list[float] = [mid]
    for k in range(1, spread + 1):
        for sign in (-1, 1):
            out.append(mid + sign * k * 32.0)
    return out


def route_orthogonal(
    start: Point,
    end: Point,
    *,
    start_side: str | None = None,
    end_side: str | None = None,
    obstacles: Sequence[Box] = (),
    stub: float = 16.0,
    clearance: float = 4.0,
) -> list[Point]:
    """Compute an obstacle-aware orthogonal polyline from ``start`` to ``end``.

    Args:
        start, end: Endpoint coordinates in canvas space.
        start_side, end_side: Cardinal direction the path must
            leave / enter, expressed as ``"north"``/``"south"``/``"east"``/
            ``"west"`` or any alias accepted by :func:`normalize_side`.
            None means the corresponding endpoint is unconstrained;
            the router treats it as a free point and skips the stub.
        obstacles: Iterable of axis-aligned boxes the routed path
            must not pass through (typically other classifier boxes).
            Boxes that contain or touch the start/end are treated as
            non-blocking (the router cannot leave its own anchor point).
        stub: Minimum perpendicular clearance from each side anchor
            before the first bend, in pixels. Prevents the line from
            crossing back into the box it just left.
        clearance: Inflate each obstacle by this many pixels before
            collision testing — adds a visual buffer.

    Returns:
        A polyline starting at ``start`` and ending at ``end``,
        consisting of axis-aligned segments. When no obstacle-free
        route is found the function returns the best-effort first
        candidate so callers always receive a renderable polyline.
    """
    s_side = normalize_side(start_side)
    e_side = normalize_side(end_side)

    s_stub = _step(start, s_side, stub)
    e_stub = _step(end, e_side, stub)

    # Filter out obstacles that contain either endpoint — those are
    # almost certainly the source/destination boxes themselves, and the
    # router cannot route around its own anchor.
    obstacles = [
        rect for rect in obstacles
        if not _box_contains_point(rect, start, slack=1.0)
        and not _box_contains_point(rect, end, slack=1.0)
    ]

    s_horiz = _is_horizontal_side(s_side)
    e_horiz = _is_horizontal_side(e_side)
    s_vert = _is_vertical_side(s_side)
    e_vert = _is_vertical_side(e_side)

    candidates: list[list[Point]] = []

    if s_horiz and e_horiz:
        # H-V-H: bend on a vertical lane between the two horizontal stubs.
        for mx in _candidate_lanes(s_stub[0], e_stub[0]):
            candidates.append([
                start, s_stub, (mx, s_stub[1]), (mx, e_stub[1]), e_stub, end,
            ])
        # H-V-H-V-H escape detour: step onto a free horizontal lane
        # (above or below the obstacle band), traverse to the dest
        # column at that lane, then drop down inside the destination's
        # own column (which is by definition obstacle-free at e_stub.y,
        # otherwise the destination box itself would clash). Resolves
        # the common case where source and destination sit in the same
        # row of components — a direct H-V-H must cross at least one
        # of them.
        for my in _escape_lanes_y(obstacles, s_stub[1], e_stub[1], clearance):
            candidates.append([
                start, s_stub,
                (s_stub[0], my), (e_stub[0], my),
                e_stub, end,
            ])
    elif s_vert and e_vert:
        # V-H-V: bend on a horizontal lane between the two vertical stubs.
        for my in _candidate_lanes(s_stub[1], e_stub[1]):
            candidates.append([
                start, s_stub, (s_stub[0], my), (e_stub[0], my), e_stub, end,
            ])
        # V-H-V-H-V escape detour: step onto a free vertical lane
        # (east or west of the obstacle column), descend at that
        # lane to the dest row, then approach the destination
        # horizontally inside its own row.
        for mx in _escape_lanes_x(obstacles, s_stub[0], e_stub[0], clearance):
            candidates.append([
                start, s_stub,
                (mx, s_stub[1]), (mx, e_stub[1]),
                e_stub, end,
            ])
    elif s_horiz and e_vert:
        # Single elbow: go horizontally past s_stub.x to e_stub.x, then
        # vertically. The elbow sits at (e_stub.x, s_stub.y).
        candidates.append([start, s_stub, (e_stub[0], s_stub[1]), e_stub, end])
        # Alternate elbow at (s_stub.x, e_stub.y) — used as fallback
        # when the primary route hits an obstacle.
        candidates.append([start, s_stub, (s_stub[0], e_stub[1]), e_stub, end])
    elif s_vert and e_horiz:
        candidates.append([start, s_stub, (s_stub[0], e_stub[1]), e_stub, end])
        candidates.append([start, s_stub, (e_stub[0], s_stub[1]), e_stub, end])
    else:
        # No side info on at least one end — fall back to the legacy Z
        # (kept for byte-stable output on existing decks that don't
        # declare sides).
        mid_x = (start[0] + end[0]) / 2.0
        candidates.append([start, (mid_x, start[1]), (mid_x, end[1]), end])

    deduped = [_dedupe(c) for c in candidates]
    for cand in deduped:
        if not _path_hits_obstacles(cand, obstacles, clearance):
            return cand
    return deduped[0]


def _escape_lanes_x(
    obstacles: Sequence[Box],
    sx: float,
    ex: float,
    clearance: float,
    *,
    margin: float = 8.0,
) -> list[float]:
    """Vertical escape lanes (x-coordinates) for V-H-V-H-V detours.

    For every obstacle the function proposes two candidate x-lanes:
    one ``margin`` px to the *east* of the obstacle's right edge and
    one ``margin`` px to the *west* of its left edge (each adjusted
    by ``clearance``). The full set of per-obstacle lanes is
    deduplicated and returned sorted by increasing distance from the
    midpoint of ``sx`` and ``ex``, so the closest detour is tried
    first.

    The previous implementation only considered the *global* extremes
    (min over all obstacles, max over all obstacles), which produced
    detour lanes far outside the relevant region — paths to those
    lanes had to cross every intervening obstacle and never resolved.
    """
    if not obstacles:
        return []
    raw: set[float] = set()
    for x, _y, w, _h in obstacles:
        raw.add(x - clearance - margin)
        raw.add(x + w + clearance + margin)
    mid = (sx + ex) / 2.0
    return sorted(raw, key=lambda v: abs(v - mid))


def _escape_lanes_y(
    obstacles: Sequence[Box],
    sy: float,
    ey: float,
    clearance: float,
    *,
    margin: float = 8.0,
) -> list[float]:
    """Horizontal escape lanes (y-coordinates) for H-V-H-V-H detours.

    The H-H counterpart of :func:`_escape_lanes_x`. See its docstring
    for the per-obstacle enumeration rationale.
    """
    if not obstacles:
        return []
    raw: set[float] = set()
    for _x, y, _w, h in obstacles:
        raw.add(y - clearance - margin)
        raw.add(y + h + clearance + margin)
    mid = (sy + ey) / 2.0
    return sorted(raw, key=lambda v: abs(v - mid))


def _box_contains_point(rect: Box, p: Point, *, slack: float = 0.0) -> bool:
    """True when ``p`` lies inside ``rect`` (strict + ``slack`` margin)."""
    x, y, w, h = rect
    return x - slack <= p[0] <= x + w + slack and y - slack <= p[1] <= y + h + slack
