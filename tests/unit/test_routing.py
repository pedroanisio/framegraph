"""Unit tests for `framegraph._routing` — orthogonal connector routing.

Pure-geometry tests; no SVG, no renderer wiring. The integration
counterpart in ``tests/integration/test_connector_routing.py``
verifies the wiring through `render_connector` produces clean
SVG paths.
"""

from __future__ import annotations

import pytest

from framegraph._routing import (
    normalize_side,
    route_orthogonal,
    segment_intersects_box,
)


# ─────────────────────────────────────────────────────────────────
# normalize_side
# ─────────────────────────────────────────────────────────────────


class TestNormalizeSide:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("north", "north"),
            ("South", "south"),
            ("EAST", "east"),
            ("west", "west"),
            ("top", "north"),
            ("bottom", "south"),
            ("right", "east"),
            ("left", "west"),
        ],
    )
    def test_canonical_and_alias_forms(self, raw: str, expected: str) -> None:
        assert normalize_side(raw) == expected

    def test_none_passes_through(self) -> None:
        assert normalize_side(None) is None

    def test_unknown_returns_none(self) -> None:
        assert normalize_side("northeast") is None
        assert normalize_side("center") is None


# ─────────────────────────────────────────────────────────────────
# segment_intersects_box
# ─────────────────────────────────────────────────────────────────


class TestSegmentIntersectsBox:
    BOX = (100.0, 100.0, 200.0, 100.0)  # x in [100,300], y in [100,200]

    def test_horizontal_segment_crossing_box_intersects(self) -> None:
        # Horizontal line at y=150, x from 50 to 350 → cuts the box.
        assert segment_intersects_box((50, 150), (350, 150), self.BOX)

    def test_horizontal_segment_above_box_does_not_intersect(self) -> None:
        assert not segment_intersects_box((50, 50), (350, 50), self.BOX)

    def test_vertical_segment_crossing_box_intersects(self) -> None:
        assert segment_intersects_box((200, 50), (200, 250), self.BOX)

    def test_vertical_segment_outside_box_does_not_intersect(self) -> None:
        assert not segment_intersects_box((400, 50), (400, 250), self.BOX)

    def test_segment_grazing_box_edge_does_not_intersect(self) -> None:
        # Segment runs exactly along y=100 (top edge) — should not be
        # treated as a collision; otherwise every connector terminating
        # on a side anchor would self-collide with its own target box.
        assert not segment_intersects_box((50, 100), (350, 100), self.BOX)

    def test_clearance_inflates_obstacle(self) -> None:
        # Without clearance, a segment at y=99 (one px above the box)
        # does NOT intersect; with clearance=2 it does.
        assert not segment_intersects_box((50, 99), (350, 99), self.BOX)
        assert segment_intersects_box(
            (50, 99), (350, 99), self.BOX, clearance=2
        )

    def test_segment_fully_inside_box_intersects(self) -> None:
        assert segment_intersects_box((150, 150), (250, 150), self.BOX)

    def test_diagonal_segment_raises(self) -> None:
        with pytest.raises(ValueError, match="axis-aligned"):
            segment_intersects_box((0, 0), (100, 100), self.BOX)

    def test_zero_length_segment_inside_box_intersects(self) -> None:
        # A degenerate point-segment strictly inside the box is treated
        # as a collision (covers the `horizontal and vertical` branch).
        assert segment_intersects_box((150, 150), (150, 150), self.BOX)

    def test_zero_length_segment_outside_box_does_not_intersect(self) -> None:
        assert not segment_intersects_box((50, 50), (50, 50), self.BOX)


# ─────────────────────────────────────────────────────────────────
# route_orthogonal — stub clearance
# ─────────────────────────────────────────────────────────────────


class TestStubClearance:
    """The first segment must move the path away from the source box
    perpendicular to ``start_side``; the last segment must approach
    the destination perpendicular to ``end_side``. This prevents the
    Z-routing artifact where the bend sits inside the source box."""

    def test_east_side_stub_extends_to_the_right(self) -> None:
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            stub=20.0,
        )
        # Second point must be 20px east of the start.
        assert path[0] == (100.0, 100.0)
        assert path[1] == (120.0, 100.0)

    def test_west_side_stub_extends_to_the_left(self) -> None:
        path = route_orthogonal(
            (400, 100),
            (100, 200),
            start_side="west",
            end_side="east",
            stub=20.0,
        )
        assert path[1] == (380.0, 100.0)

    def test_north_side_stub_extends_upward(self) -> None:
        path = route_orthogonal(
            (200, 200),
            (200, 50),
            start_side="north",
            end_side="south",
            stub=15.0,
        )
        assert path[1] == (200.0, 185.0)

    def test_south_side_stub_extends_downward(self) -> None:
        path = route_orthogonal(
            (200, 100),
            (200, 300),
            start_side="south",
            end_side="north",
            stub=15.0,
        )
        assert path[1] == (200.0, 115.0)

    def test_end_stub_lands_perpendicular_to_end_side(self) -> None:
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            stub=20.0,
        )
        # Penultimate point is 20px west of the end (east-bound stub).
        assert path[-2] == (380.0, 200.0)
        assert path[-1] == (400.0, 200.0)


# ─────────────────────────────────────────────────────────────────
# route_orthogonal — geometry by side combination
# ─────────────────────────────────────────────────────────────────


class TestRouteShapes:
    def test_horizontal_to_horizontal_uses_h_v_h(self) -> None:
        # east → west: H-V-H route. Expect 6 points (start, s_stub,
        # bend1, bend2, e_stub, end) with the two bends on the same
        # vertical lane.
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            stub=10.0,
        )
        assert len(path) == 6
        # The two intermediate bend points share an x.
        assert path[2][0] == path[3][0]
        # Midway bend at the average of the two stubs.
        assert path[2][0] == pytest.approx((110 + 390) / 2)

    def test_vertical_to_vertical_uses_v_h_v(self) -> None:
        path = route_orthogonal(
            (200, 100),
            (300, 400),
            start_side="south",
            end_side="north",
            stub=10.0,
        )
        assert len(path) == 6
        # The two intermediate bend points share a y.
        assert path[2][1] == path[3][1]

    def test_horizontal_to_vertical_uses_single_elbow(self) -> None:
        # east → north: one elbow, 5 points (start, s_stub, elbow,
        # e_stub, end). The elbow sits at (e_stub.x, s_stub.y).
        path = route_orthogonal(
            (100, 200),
            (400, 100),
            start_side="east",
            end_side="north",
            stub=10.0,
        )
        # Without obstacles the primary candidate is chosen.
        # path = [start, (110,200), (400, 200-10? wait)]
        # s_stub = (110, 200); e_stub = (400, 90); elbow = (400, 200)
        assert path[0] == (100.0, 200.0)
        assert path[1] == (110.0, 200.0)
        assert path[2] == (400.0, 200.0)
        assert path[3] == (400.0, 90.0)
        assert path[4] == (400.0, 100.0)

    def test_unsided_endpoint_falls_back_to_legacy_z(self) -> None:
        # No sides → the original `mid_x` Z is preserved.
        path = route_orthogonal((100, 100), (400, 200))
        # 4-point Z: start, (mid_x, 100), (mid_x, 200), end.
        assert len(path) == 4
        assert path[1][0] == pytest.approx(250.0)
        assert path[2][0] == pytest.approx(250.0)


# ─────────────────────────────────────────────────────────────────
# route_orthogonal — obstacle avoidance
# ─────────────────────────────────────────────────────────────────


class TestObstacleAvoidance:
    """The router must shift its bend lane to avoid passing through
    a registered obstacle box. When no offset works, the function
    must still return a renderable path (best-effort fallback)."""

    def test_route_bends_around_blocking_box(self) -> None:
        # A typical UML scenario: two classifier boxes at different
        # y-levels with a third box between them on the default bend
        # lane. The obstacle (x=[200,300], y=[120,180]) sits squarely
        # at mid_x=250 between the two rows but does not block either
        # endpoint row, so an H-V-H lane shift can route around it.
        obstacle = (200.0, 120.0, 100.0, 60.0)
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            obstacles=[obstacle],
            stub=10.0,
        )
        for i in range(len(path) - 1):
            assert not segment_intersects_box(
                path[i], path[i + 1], obstacle, clearance=4.0
            ), f"segment {path[i]}→{path[i+1]} crosses obstacle"

    def test_route_falls_back_when_obstacle_blocks_both_endpoint_rows(self) -> None:
        # When an obstacle blocks both endpoint rows the simple
        # H-V-H router cannot route around it (a vertical detour
        # would require a 5-segment path the current router does not
        # generate). The function still returns a valid polyline so
        # callers always have something to draw — collision avoidance
        # is best-effort, not a guarantee.
        obstacle = (200.0, 80.0, 100.0, 140.0)
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            obstacles=[obstacle],
        )
        assert len(path) >= 2
        assert path[0] == (100.0, 100.0)
        assert path[-1] == (400.0, 200.0)

    def test_route_skips_obstacle_containing_start(self) -> None:
        # An obstacle that contains the start point shouldn't block
        # the route — that's almost certainly the box being exited.
        # The router silently filters such "self-obstacles".
        own_box = (90.0, 90.0, 30.0, 30.0)  # contains start=(100,100)
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            obstacles=[own_box],
        )
        # Path is non-empty and starts at the source.
        assert path[0] == (100.0, 100.0)

    def test_route_returns_first_candidate_when_all_lanes_blocked(self) -> None:
        # A wall obstacle that spans every candidate lane forces the
        # router to fall back to the first (best-effort) candidate.
        wall = (0.0, 99.0, 1000.0, 102.0)  # huge box covering y=99..201
        path = route_orthogonal(
            (100, 100),
            (400, 200),
            start_side="east",
            end_side="west",
            obstacles=[wall],
        )
        # Function must return a polyline; we don't assert no
        # intersection because no lane fits.
        assert len(path) >= 2
        assert path[0] == (100.0, 100.0)
        assert path[-1] == (400.0, 200.0)


# ─────────────────────────────────────────────────────────────────
# route_orthogonal — determinism + endpoints preserved
# ─────────────────────────────────────────────────────────────────


class TestInvariants:
    def test_endpoints_always_preserved(self) -> None:
        path = route_orthogonal(
            (123, 456),
            (789, 321),
            start_side="east",
            end_side="north",
        )
        assert path[0] == (123.0, 456.0)
        assert path[-1] == (789.0, 321.0)

    def test_repeated_invocations_are_deterministic(self) -> None:
        kwargs = dict(
            start=(100, 100),
            end=(400, 200),
            start_side="east",
            end_side="west",
            obstacles=[(200.0, 80.0, 100.0, 140.0)],
        )
        a = route_orthogonal(**kwargs)
        b = route_orthogonal(**kwargs)
        assert a == b

    def test_no_consecutive_duplicate_points(self) -> None:
        # When the source and destination share a coordinate aligned
        # with the side direction, the dedupe pass should drop the
        # collapsed segment.
        path = route_orthogonal(
            (100, 200),
            (400, 200),
            start_side="east",
            end_side="west",
        )
        for i in range(len(path) - 1):
            dx = path[i + 1][0] - path[i][0]
            dy = path[i + 1][1] - path[i][1]
            assert (abs(dx) > 0.5) or (abs(dy) > 0.5), (
                f"consecutive duplicate points at index {i}: {path[i]}, {path[i+1]}"
            )
