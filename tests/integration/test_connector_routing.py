"""Integration tests for connector routing through `render_connector`.

The pure-geometry routing primitives are exercised in
``tests/unit/test_routing.py``. These tests verify the wiring:

- side-aware routing kicks in when endpoints declare cardinal sides;
- obstacle avoidance picks UML classifier boxes from the renderer's
  index and steers the path around them;
- backward compatibility — legacy decks without sides still get the
  original Z-shaped output, and explicit ``route.points`` still wins.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from framegraph import FrameGraphRenderer


def _doc_with(objects: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dsl": "FrameGraph",
        "version": 1.5,
        "scene": {"id": "t", "canvas": {"size": [800, 600]}},
        "visual": {
            "layers": [{"id": "main", "z": 0, "objects": objects}],
        },
    }


def _classifier(oid: str, x: float, y: float, w: float = 120, h: float = 60) -> dict:
    return {
        "type": "uml.classifier_box",
        "id": oid,
        "name": oid,
        "box": [x, y, w, h],
    }


def _connector(
    oid: str,
    src: dict | str,
    dst: dict | str,
    *,
    route: dict | None = None,
) -> dict:
    return {
        "type": "connector",
        "id": oid,
        "from": src,
        "to": dst,
        "route": route or {"type": "orthogonal"},
        "stroke": {"color": "#1A1A1A", "width": 1, "arrow_end": True},
    }


def _path_d(svg: str, conn_id: str) -> str:
    """Extract the `d` attribute of the connector with the given id."""
    pattern = (
        rf'<g id="{re.escape(conn_id)}" data-type="connector">\s*'
        r'<path d="([^"]+)"'
    )
    m = re.search(pattern, svg)
    assert m, f"connector {conn_id!r} not found in SVG"
    return m.group(1)


def _path_points(d: str) -> list[tuple[float, float]]:
    """Parse a `d` attribute consisting of `M x y L x y L x y …` into points."""
    out: list[tuple[float, float]] = []
    tokens = re.findall(r"[ML]\s+([0-9.\-]+)\s+([0-9.\-]+)", d)
    for x, y in tokens:
        out.append((float(x), float(y)))
    return out


# ─────────────────────────────────────────────────────────────────
# 1. Side-aware routing kicks in when endpoints declare a side
# ─────────────────────────────────────────────────────────────────


class TestSideAwareWiring:
    def test_side_endpoints_produce_stub_segments(self) -> None:
        """Endpoints with `side` produce a stub perpendicular to the
        side as the second point of the path (the renderer routes the
        connector through `route_orthogonal`)."""
        a = _classifier("a", 100, 100)  # box covers x=100..220, y=100..160
        b = _classifier("b", 400, 200)  # box covers x=400..520, y=200..260
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Start at a's east anchor (x=220, y=130).
        assert pts[0] == (220.0, 130.0)
        # First stub: 16 px east of the start.
        assert pts[1] == (236.0, 130.0)
        # Last point at b's west anchor (x=400, y=230).
        assert pts[-1] == (400.0, 230.0)
        # Penultimate stub: 16 px west of the end.
        assert pts[-2] == (384.0, 230.0)

    def test_legacy_centred_endpoint_keeps_z_route(self) -> None:
        """A connector with no side declarations preserves the legacy
        4-point Z route (centred bend at midpoint) — backward
        compatibility for decks that route between point objects."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 100)
        edge = _connector("e", {"object": "a"}, {"object": "b"})
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Centre-to-centre with mid_x bend: 4 distinct points.
        assert len(pts) == 4
        # Centres: a=(160,130), b=(460,130). mid_x = 310.
        assert pts[0] == (160.0, 130.0)
        assert pts[1] == (310.0, 130.0)
        assert pts[2] == (310.0, 130.0)
        assert pts[3] == (460.0, 130.0)

    def test_explicit_route_points_bypass_side_routing(self) -> None:
        """When the user supplies `route.points`, the explicit polyline
        wins regardless of side declarations — `route_orthogonal` is
        never invoked."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 200)
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
            route={
                "type": "orthogonal",
                "points": [[300, 130], [300, 230]],
            },
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Just the four explicit points (start, two waypoints, end).
        assert pts == [
            (220.0, 130.0),
            (300.0, 130.0),
            (300.0, 230.0),
            (400.0, 230.0),
        ]


# ─────────────────────────────────────────────────────────────────
# 2. Obstacle avoidance picks classifier boxes from object_index
# ─────────────────────────────────────────────────────────────────


class TestObstacleIntegration:
    def test_route_avoids_classifier_box_between_endpoints(self) -> None:
        """A third classifier box on the default bend lane causes the
        router to shift to a free lane. Verifies obstacles are
        discovered automatically from the renderer's object_index —
        the connector YAML doesn't need to enumerate them."""
        a = _classifier("a", 100, 100, w=80, h=40)   # x=100..180
        b = _classifier("b", 400, 200, w=80, h=40)   # x=400..480
        # Obstacle squarely on the default bend lane (mid_x ≈ 290).
        # Spans y=145..205 — between the two endpoint rows so the
        # router can dodge by shifting the bend lane east or west.
        block = _classifier("block", 240, 145, w=120, h=60)
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, block, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # The chosen vertical lane (the x of the H-V-H bend) must lie
        # outside the obstacle's strict interior.
        bend_x = pts[2][0]
        assert not (240.0 < bend_x < 360.0), (
            f"bend lane x={bend_x} lies inside the obstacle x=[240,360]"
        )

    def test_route_ignores_obstacle_that_is_an_endpoint_object(self) -> None:
        """The source / destination boxes are not treated as
        obstacles. Otherwise side-anchored endpoints would always
        report a self-collision and routing would degrade to the
        fallback path on every connector."""
        a = _classifier("a", 100, 100, w=200, h=80)  # generous box
        b = _classifier("b", 500, 200, w=200, h=80)
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Path is a clean H-V-H without any "fallback" markers — the
        # endpoints' own boxes were correctly excluded from obstacles.
        # Six points total: start, s_stub, bend1, bend2, e_stub, end.
        assert len(pts) == 6


# ─────────────────────────────────────────────────────────────────
# 3. The path actually leaves the source box (no self-overlap)
# ─────────────────────────────────────────────────────────────────


class TestVisualHygiene:
    def test_first_segment_does_not_re_enter_source_box(self) -> None:
        """Regression: with the previous Z-routing the first segment
        could bend back through the source box when the bend lane
        landed inside it. Side-aware routing emits a stub first, so
        the first move is always perpendicular outward from the
        source side."""
        # Source east anchor at x=220; without a stub, the legacy
        # routing's first segment would jog left to mid_x=210 — INSIDE
        # the source box. The new router must move RIGHT first.
        a = _classifier("a", 100, 100, w=120, h=60)
        b = _classifier("b", 200, 200, w=120, h=60)  # end's centre west of start's east
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Start at (220, 130). Stub must move east → x increases.
        assert pts[1][0] > pts[0][0], (
            f"stub at {pts[1]} did not extend east of start at {pts[0]}"
        )

    def test_dot_notation_endpoint_routes_with_side(self) -> None:
        """The shorthand `"obj.east"` must produce the same routing as
        the equivalent `{object: "obj", side: "east"}` form. Covers the
        string-split branch of `_endpoint_side`."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 200)
        edge = _connector("e", "a.east", "b.west")
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        assert pts[0] == (220.0, 130.0)
        assert pts[1] == (236.0, 130.0)
        assert pts[-1] == (400.0, 230.0)

    def test_decorative_classifier_is_not_an_obstacle(self) -> None:
        """`decorative: true` classifier boxes must NOT be treated as
        obstacles — they're stylistic backdrops, not structural nodes."""
        a = _classifier("a", 100, 100, w=80, h=40)
        b = _classifier("b", 400, 200, w=80, h=40)
        # A decorative box squarely on the default bend lane.
        deco = {
            "type": "uml.classifier_box",
            "id": "deco",
            "name": "deco",
            "box": [240, 145, 120, 60],
            "decorative": True,
        }
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, deco, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Default bend lane (mid_x = 296) is taken because deco is
        # excluded from obstacles.
        bend_x = pts[2][0]
        assert 240.0 < bend_x < 360.0, (
            f"bend lane shifted to x={bend_x}; decorative box was wrongly "
            "treated as an obstacle"
        )

    def test_literal_coordinate_endpoint_keeps_legacy_z(self) -> None:
        """A connector with literal `[x, y]` endpoints (no object
        reference, no side) preserves the legacy 4-point Z route."""
        a = _classifier("a", 100, 100)
        edge = _connector("e", [50, 50], [600, 400])
        doc = _doc_with([a, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Centre Z bend at mid_x=325.
        assert len(pts) == 4
        assert pts[1][0] == pytest.approx(325.0)

    def test_path_endpoints_match_resolved_anchors(self) -> None:
        """Routing must never alter the anchor coordinates — the
        first and last points of the path are exactly the resolved
        endpoints, otherwise marker placement and label binding break."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 200)
        edge = _connector(
            "e",
            {"object": "a", "side": "south"},
            {"object": "b", "side": "north"},
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # a south anchor: (160, 160). b north anchor: (460, 200).
        assert pts[0] == (160.0, 160.0)
        assert pts[-1] == (460.0, 200.0)
