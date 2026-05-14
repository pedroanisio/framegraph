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
    def test_side_endpoints_route_perpendicular_to_anchors(self) -> None:
        """Endpoints with `side` produce a path that leaves and enters
        perpendicular to the declared face. After the renderer's
        polyline simplifier collapses collinear stub vertices, the
        important visual invariants are that endpoints match the
        anchors AND the first/last segments depart along the
        cardinal direction implied by the `side`."""
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
        # Endpoints lock to the side anchors.
        assert pts[0] == (220.0, 130.0)
        assert pts[-1] == (400.0, 230.0)
        # First move is east (a.east → outward); last move is east
        # (approaching b.west from west).
        assert pts[1][0] > pts[0][0], (
            f"first segment did not depart east of {pts[0]}: {pts[1]}"
        )
        assert pts[-2][0] < pts[-1][0], (
            f"last segment did not approach west of {pts[-1]}: {pts[-2]}"
        )

    def test_legacy_centred_endpoint_keeps_z_route(self) -> None:
        """A connector with no side declarations preserves the legacy
        Z route. After polyline simplification a centre-to-centre
        link between two boxes at the same y collapses to a single
        flat segment — visually identical, fewer vertices."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 100)
        edge = _connector("e", {"object": "a"}, {"object": "b"})
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Centres: a=(160,130), b=(460,130) — both on y=130.
        assert pts[0] == (160.0, 130.0)
        assert pts[-1] == (460.0, 130.0)
        # Every point lies on y=130 (collinear → simplified flat).
        for x, y in pts:
            assert y == 130.0

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
        # Endpoints lock; first move east of source, last move east
        # toward destination. After polyline simplification, the
        # collinear stub vertices (s_stub, e_stub) collapse — the
        # remaining vertices describe the visible H-V-H corners.
        assert pts[0] == (300.0, 140.0)  # a.east at (100+200, 100+80/2)
        assert pts[-1] == (500.0, 240.0)  # b.west at (500, 200+80/2)
        assert pts[1][0] > pts[0][0]
        assert pts[-2][0] < pts[-1][0]


# ─────────────────────────────────────────────────────────────────
# 3. The path actually leaves the source box (no self-overlap)
# ─────────────────────────────────────────────────────────────────


class TestVisualHygiene:
    def test_first_segment_does_not_re_enter_source_box(self) -> None:
        """Regression: with the previous Z-routing the first segment
        could bend back through the source box when the bend lane
        landed inside it. Side-aware routing emits a stub first, so
        the first move is always perpendicular outward from the
        source side. After polyline simplification the stub may be
        collapsed if collinear with the next segment, but the first
        visible move must still be east of the source anchor."""
        a = _classifier("a", 100, 100, w=120, h=60)
        b = _classifier("b", 200, 200, w=120, h=60)
        edge = _connector(
            "e",
            {"object": "a", "side": "east"},
            {"object": "b", "side": "west"},
        )
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        # Start at (220, 130). First move must be east → x increases,
        # AND must clear the source box's east edge (x=220).
        assert pts[1][0] > pts[0][0], (
            f"first move at {pts[1]} did not extend east of start at {pts[0]}"
        )

    def test_dot_notation_endpoint_routes_with_side(self) -> None:
        """The shorthand `"obj.east"` must produce the same routing as
        the equivalent `{object: "obj", side: "east"}` form."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 200)
        edge = _connector("e", "a.east", "b.west")
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        pts = _path_points(_path_d(svg, "e"))
        assert pts[0] == (220.0, 130.0)
        assert pts[-1] == (400.0, 230.0)
        # First move east of source.
        assert pts[1][0] > pts[0][0]

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

class TestAutoLabelPlacement:
    """When a connector declares an inline `label` without an explicit
    `box`, the renderer must compute a label position that does NOT
    overlap the connector's own path. The deployment-slide defects
    that motivated this — three connector labels sitting directly on
    their lines — would have been caught by this rule."""

    def test_horizontal_segment_label_sits_above_path(self) -> None:
        a = _classifier("a", 100, 100)  # box (100,100,120,60)
        b = _classifier("b", 400, 100)  # box (400,100,120,60)
        edge = {
            "type": "connector",
            "id": "e",
            "from": {"object": "a", "side": "east"},
            "to": {"object": "b", "side": "west"},
            "route": {"type": "orthogonal"},
            "stroke": {"color": "#1A1A1A", "width": 1, "arrow_end": True},
            "label": {"text": "uses", "style": {"size": 12}},
        }
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        # Path is a flat horizontal line at y=130 (anchors share y).
        # Label baseline must sit above y=130 with a clearance gap.
        m = re.search(
            r'<g id="e"[^>]*>.*?<text[^>]*y="([0-9.\-]+)"',
            svg, re.DOTALL,
        )
        assert m, "label not emitted"
        label_y = float(m.group(1))
        assert label_y < 130 - 4, (
            f"label baseline y={label_y} should sit at least 4px "
            "above the path at y=130"
        )

    def test_vertical_segment_label_sits_beside_path(self) -> None:
        a = _classifier("a", 100, 100)
        b = _classifier("b", 100, 400)  # b directly below a
        edge = {
            "type": "connector",
            "id": "e",
            "from": {"object": "a", "side": "south"},
            "to": {"object": "b", "side": "north"},
            "route": {"type": "orthogonal"},
            "stroke": {"color": "#1A1A1A", "width": 1, "arrow_end": True},
            "label": {"text": "calls", "style": {"size": 12}},
        }
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        m = re.search(
            r'<g id="e"[^>]*>.*?<text[^>]*x="([0-9.\-]+)"',
            svg, re.DOTALL,
        )
        assert m, "label not emitted"
        label_x = float(m.group(1))
        # The path's vertical segment is at x=160 (a.south = b.north
        # when boxes share the same x). Label x should sit to the
        # right of that line by the configured gap.
        assert label_x > 160 + 4, (
            f"label x={label_x} should sit at least 4px right of the "
            "vertical path at x=160"
        )

    def test_explicit_label_box_wins(self) -> None:
        """When the author supplies `label.box`, the auto-placement
        is bypassed — explicit positioning is always honoured."""
        a = _classifier("a", 100, 100)
        b = _classifier("b", 400, 100)
        edge = {
            "type": "connector",
            "id": "e",
            "from": {"object": "a", "side": "east"},
            "to": {"object": "b", "side": "west"},
            "route": {"type": "orthogonal"},
            "stroke": {"color": "#1A1A1A", "width": 1, "arrow_end": True},
            "label": {"text": "uses", "box": [200, 200, 100, 14]},
        }
        doc = _doc_with([a, b, edge])
        svg = FrameGraphRenderer(doc).render_svg()
        # The text element must use the explicit y=200-ish coordinate.
        m = re.search(
            r'<g id="e"[^>]*>.*?<text[^>]*y="([0-9.\-]+)"',
            svg, re.DOTALL,
        )
        assert m and 195 < float(m.group(1)) < 215


class TestAutoPortDistribution:
    """When multiple connectors target the same `(object, side)` without
    explicit `offset` or `port_index`, the renderer's pre-pass must
    auto-fan their attachment points along the side instead of letting
    every connector terminate at the same midpoint. Resolves the
    "many edges to one hub" marker pile-up that the original
    classifier-box class diagrams suffered from."""

    def test_two_edges_to_same_side_get_distributed(self) -> None:
        """Two `north` connectors converging on a hub get ports 1 and 2
        of 2 — the midpoint anchor is replaced with two evenly spaced
        attachment points."""
        hub = _classifier("hub", 200, 100, w=200, h=60)
        a = _classifier("a", 100, 300)
        b = _classifier("b", 400, 300)
        e1 = _connector("e1", {"object": "a", "side": "north"},
                              {"object": "hub", "side": "south"})
        e2 = _connector("e2", {"object": "b", "side": "north"},
                              {"object": "hub", "side": "south"})
        doc = _doc_with([hub, a, b, e1, e2])
        svg = FrameGraphRenderer(doc).render_svg()
        e1_end = _path_points(_path_d(svg, "e1"))[-1]
        e2_end = _path_points(_path_d(svg, "e2"))[-1]
        # Both end at the hub's south edge (y=160) but at different x.
        assert e1_end[1] == 160.0 and e2_end[1] == 160.0
        assert e1_end[0] != e2_end[0], (
            f"both connectors landed at the same x={e1_end[0]} — "
            "auto-distribution did not fire"
        )
        # And the leftmost source (a, x=100) lands left of the
        # rightmost source (b, x=400) — sort order preserves visual
        # adjacency.
        assert e1_end[0] < e2_end[0]

    def test_explicit_offset_wins_over_auto_distribution(self) -> None:
        """When the author commits to a specific `offset`, the
        pre-pass leaves that endpoint alone and only auto-distributes
        the siblings that don't have offsets."""
        hub = _classifier("hub", 200, 100, w=200, h=60)
        a = _classifier("a", 100, 300)
        b = _classifier("b", 400, 300)
        # e1 explicitly anchors at hub.south + offset=80 (x=380).
        e1 = _connector("e1", {"object": "a", "side": "north"},
                              {"object": "hub", "side": "south", "offset": 80})
        e2 = _connector("e2", {"object": "b", "side": "north"},
                              {"object": "hub", "side": "south"})
        doc = _doc_with([hub, a, b, e1, e2])
        svg = FrameGraphRenderer(doc).render_svg()
        e1_end = _path_points(_path_d(svg, "e1"))[-1]
        # Hub south midpoint = (300, 160); explicit offset → x = 380.
        assert e1_end == (380.0, 160.0)

    def test_single_connector_to_a_side_is_not_distributed(self) -> None:
        """A lone connector keeps the side-midpoint anchor."""
        hub = _classifier("hub", 200, 100, w=200, h=60)
        a = _classifier("a", 100, 300)
        e1 = _connector("e1", {"object": "a", "side": "north"},
                              {"object": "hub", "side": "south"})
        doc = _doc_with([hub, a, e1])
        svg = FrameGraphRenderer(doc).render_svg()
        e1_end = _path_points(_path_d(svg, "e1"))[-1]
        # Hub.south midpoint x = 200 + 200/2 = 300.
        assert e1_end == (300.0, 160.0)


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
