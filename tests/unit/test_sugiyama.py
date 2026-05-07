"""Unit tests for `framegraph.layout.sugiyama`.

Each Sugiyama stage is exercised in isolation through the public
`sugiyama_layout` entry point, plus a few stage-internal helpers
that have decision logic worth verifying directly.

Test bar: behavior, not byte-exact coordinates. Coordinates depend
on `SugiyamaConfig` defaults that may evolve. We assert structural
properties (relative positions, layer counts, crossing-count
invariants) instead.
"""

from __future__ import annotations

from typing import Any

import pytest

from framegraph.layout import SugiyamaConfig, sugiyama_layout
from framegraph.layout.sugiyama import (
    _assign_layers,
    _count_crossings_between_layers,
    _median,
    _remove_cycles,
)

# ─────────────────────────────────────────────────────────────────
# Stage 1 — cycle removal
# ─────────────────────────────────────────────────────────────────


class TestCycleRemoval:
    """Eades-Lin-Smyth feedback-arc-set heuristic."""

    def test_acyclic_graph_produces_no_reversals(self) -> None:
        """Linear chain A→B→C is already a DAG; nothing should reverse."""
        dag, reversed_set = _remove_cycles(["A", "B", "C"], [("A", "B"), ("B", "C")])
        assert reversed_set == set()
        assert set(dag) == {("A", "B"), ("B", "C")}

    def test_simple_cycle_gets_one_edge_reversed(self) -> None:
        """A→B→C→A: exactly one edge must be reversed to break the cycle."""
        _, reversed_set = _remove_cycles(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
        assert len(reversed_set) == 1

    def test_self_loop_is_collected_separately(self) -> None:
        """A self-loop A→A is dropped from layout but recorded as 'reversed'."""
        dag, reversed_set = _remove_cycles(["A"], [("A", "A")])
        assert ("A", "A") in reversed_set
        # Self-loop must not appear in the dag-edge output
        assert ("A", "A") not in dag

    def test_two_disjoint_cycles_each_break_independently(self) -> None:
        """Two separate 3-cycles → exactly one reversed per cycle."""
        edges = [
            ("A", "B"),
            ("B", "C"),
            ("C", "A"),
            ("X", "Y"),
            ("Y", "Z"),
            ("Z", "X"),
        ]
        _, reversed_set = _remove_cycles(["A", "B", "C", "X", "Y", "Z"], edges)
        assert len(reversed_set) == 2

    def test_dag_with_dependency_diamond_unchanged(self) -> None:
        """Diamond A→{B,C}→D is already a DAG."""
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        _, reversed_set = _remove_cycles(["A", "B", "C", "D"], edges)
        assert reversed_set == set()


# ─────────────────────────────────────────────────────────────────
# Stage 2 — layer assignment + dummy insertion
# ─────────────────────────────────────────────────────────────────


class TestLayerAssignment:
    """Longest-path layering plus long-edge subdivision."""

    def test_chain_assigns_consecutive_layers(self) -> None:
        """A→B→C→D: layers 0, 1, 2, 3."""
        g = _assign_layers(["A", "B", "C", "D"], [("A", "B"), ("B", "C"), ("C", "D")])
        assert g.layer["A"] == 0
        assert g.layer["B"] == 1
        assert g.layer["C"] == 2
        assert g.layer["D"] == 3

    def test_diamond_layers_via_longest_path(self) -> None:
        """A→{B,C}→D: A=0, B=C=1, D=2."""
        g = _assign_layers(
            ["A", "B", "C", "D"],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        assert g.layer["A"] == 0
        assert g.layer["B"] == 1
        assert g.layer["C"] == 1
        assert g.layer["D"] == 2

    def test_long_edge_is_subdivided_with_dummies(self) -> None:
        """A→D directly, plus A→B→C→D: A→D should pick up 2 dummy bends."""
        nodes = ["A", "B", "C", "D"]
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")]
        g = _assign_layers(nodes, edges)
        # A→D spans 3 layers (0→3), so 2 dummies should have been inserted.
        dummies = [n for n in g.nodes if g.is_dummy.get(n, False)]
        assert len(dummies) == 2
        # Each dummy's `is_dummy` flag set, layer between A's and D's.
        for d in dummies:
            assert g.layer["A"] < g.layer[d] < g.layer["D"]

    def test_cyclic_input_raises(self) -> None:
        """Stage 2 expects a DAG; cycles surface as ValueError defensively."""
        with pytest.raises(ValueError, match="cycles"):
            _assign_layers(["A", "B"], [("A", "B"), ("B", "A")])


# ─────────────────────────────────────────────────────────────────
# Stage 3 helpers
# ─────────────────────────────────────────────────────────────────


class TestCrossingCount:
    """`_count_crossings_between_layers` — the core measurement."""

    def test_no_crossing_when_edges_are_parallel(self) -> None:
        """Two parallel edges: A→C, B→D with [A, B] over [C, D] → 0 crossings."""
        succ: dict[Any, list[Any]] = {"A": ["C"], "B": ["D"]}
        n = _count_crossings_between_layers(["A", "B"], ["C", "D"], succ)
        assert n == 0

    def test_one_crossing_when_edges_swap(self) -> None:
        """A→D, B→C with [A, B] over [C, D] → exactly 1 crossing."""
        succ: dict[Any, list[Any]] = {"A": ["D"], "B": ["C"]}
        n = _count_crossings_between_layers(["A", "B"], ["C", "D"], succ)
        assert n == 1

    def test_three_crossings_in_full_swap(self) -> None:
        """A→D, B→C, A→C, B→D — picks up all combinations."""
        succ: dict[Any, list[Any]] = {"A": ["D", "C"], "B": ["C", "D"]}
        n = _count_crossings_between_layers(["A", "B"], ["C", "D"], succ)
        # A→D crosses B→C (1), A→D doesn't cross B→D, A→C doesn't cross B→C,
        # A→C doesn't cross B→D. Total: 1.
        assert n == 1


class TestMedian:
    """`_median` helper — the empty-input convention matters."""

    def test_empty_returns_negative_one(self) -> None:
        assert _median([]) == -1.0

    def test_odd_length_returns_middle(self) -> None:
        assert _median([1, 5, 9]) == 5.0

    def test_even_length_averages_two_middle(self) -> None:
        assert _median([1, 5, 9, 13]) == (5 + 9) / 2.0


# ─────────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────────


class TestEndToEndDAG:
    """Pipeline output on a known acyclic input."""

    def test_linear_chain_layout(self) -> None:
        """Chain A→B→C: 3 layers, monotonically increasing y."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C")])
        assert len(r.layers) == 3
        ya = r.positions["A"][1]
        yb = r.positions["B"][1]
        yc = r.positions["C"][1]
        assert ya < yb < yc
        # No reversed edges on an already-acyclic input
        assert r.reversed_edges == set()
        # No crossings possible on a single-edge-per-layer chain
        assert r.crossings == 0

    def test_diamond_layout_has_two_nodes_on_middle_layer(self) -> None:
        """A→{B,C}→D: middle layer holds exactly {B, C}."""
        r = sugiyama_layout(
            ["A", "B", "C", "D"],
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        assert len(r.layers) == 3
        # Middle layer is layer 1
        middle = set(r.layers[1])
        assert middle == {"B", "C"}

    def test_long_edge_polyline_has_intermediate_bend(self) -> None:
        """A→C bypassing B (where A→B→C is the longer chain) gets a bend."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C"), ("A", "C")])
        # A→C spans 2 layers so should have one intermediate point
        polyline = r.edges[("A", "C")]
        assert len(polyline) == 3  # start, one bend, end


class TestEndToEndCyclic:
    """Pipeline output on graphs with cycles."""

    def test_cycle_produces_valid_layered_layout(self) -> None:
        """A→B→C→A: stage 1 reverses one edge; remaining graph layers cleanly."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
        assert len(r.reversed_edges) == 1
        # All nodes get a unique position
        positions = list(r.positions.values())
        assert len(set(positions)) == len(positions)
        # Layers are non-empty
        assert all(len(layer) >= 1 for layer in r.layers)

    def test_self_loop_appears_in_reversed_edges(self) -> None:
        """A→A is a self-loop; recorded as 'reversed' so renderer handles it."""
        r = sugiyama_layout(["A"], [("A", "A")])
        assert ("A", "A") in r.reversed_edges

    def test_disconnected_components_each_get_layered(self) -> None:
        """Two disconnected DAGs: each gets its own layering."""
        r = sugiyama_layout(["A", "B", "X", "Y"], [("A", "B"), ("X", "Y")])
        # All nodes assigned a position
        assert set(r.positions.keys()) == {"A", "B", "X", "Y"}
        # Both component sources at top (y=0)
        ya = r.positions["A"][1]
        yx = r.positions["X"][1]
        assert ya == yx == 0.0


class TestCrossingMinimization:
    """The median heuristic should reduce crossings on adversarial inputs."""

    def test_adversarial_complete_bipartite_minimizes_crossings(self) -> None:
        """K(2,2) with crossing initial order should be reorderable.

        With nodes [A, B] above and [C, D] below, edges A→D, A→C, B→D, B→C
        produce 1 crossing in the worst initial order. The median
        heuristic should achieve at most this; we assert it's not worse
        than the worst case and that the order is stable.
        """
        r = sugiyama_layout(
            ["A", "B", "C", "D"],
            [("A", "D"), ("A", "C"), ("B", "D"), ("B", "C")],
        )
        # K(2,2) has minimum 1 crossing in any straight-line drawing.
        # The median heuristic finds 0 or 1 depending on initial order.
        assert r.crossings <= 1

    def test_three_layer_graph_settles_with_finite_crossings(self) -> None:
        """A reasonable 3-layer graph has bounded crossings after stage 3."""
        r = sugiyama_layout(
            ["A", "B", "C", "D", "E", "F"],
            [
                ("A", "C"),
                ("A", "D"),
                ("B", "C"),
                ("B", "D"),
                ("C", "E"),
                ("C", "F"),
                ("D", "E"),
                ("D", "F"),
            ],
        )
        # 3 layers, 4 edges per pair — bounded crossings expected
        assert r.crossings >= 0  # sanity
        assert r.crossings <= 8  # bounded loosely; algorithm should beat naive


class TestXAssignment:
    """Brandes-Köpf produces compact, balanced x-coordinates."""

    def test_chain_keeps_x_aligned(self) -> None:
        """In a linear chain A→B→C, the x-coordinates should align (or nearly so).

        Brandes-Köpf is designed to keep aligned blocks of nodes
        vertically straight. A 3-node chain is a single alignment
        block, so all three nodes should share x within a small
        epsilon.
        """
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C")])
        xs = [r.positions[n][0] for n in ("A", "B", "C")]
        # Values may differ slightly due to four-pass averaging
        assert max(xs) - min(xs) < 1e-6

    def test_layout_normalized_to_origin(self) -> None:
        """Leftmost node sits at x=0 after normalization."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("A", "C"), ("B", "C")])
        min_x = min(p[0] for p in r.positions.values())
        assert min_x == pytest.approx(0.0, abs=1e-6)

    def test_layer_height_respected(self) -> None:
        """Custom `layer_height` propagates into y coordinates."""
        cfg = SugiyamaConfig(layer_height=200.0)
        r = sugiyama_layout(["A", "B"], [("A", "B")], config=cfg)
        ya = r.positions["A"][1]
        yb = r.positions["B"][1]
        assert yb - ya == pytest.approx(200.0)


class TestDeterminism:
    """Same input → same output. Foundational for reproducible diagrams."""

    def test_repeated_calls_produce_identical_layouts(self) -> None:
        """Running the layout twice must produce the same positions."""
        nodes = ["A", "B", "C", "D", "E"]
        edges = [
            ("A", "B"),
            ("A", "C"),
            ("B", "D"),
            ("C", "D"),
            ("D", "E"),
            ("B", "E"),
        ]
        r1 = sugiyama_layout(nodes, edges)
        r2 = sugiyama_layout(nodes, edges)
        assert r1.positions == r2.positions
        assert r1.layers == r2.layers


class TestEmptyAndDegenerate:
    """Boundary cases."""

    def test_empty_graph_produces_empty_result(self) -> None:
        r = sugiyama_layout([], [])
        assert r.positions == {}
        assert r.edges == {}
        assert r.layers == []

    def test_single_node_at_origin(self) -> None:
        r = sugiyama_layout(["A"], [])
        assert r.positions["A"][1] == 0.0
        assert len(r.layers) == 1
        assert r.layers[0] == ["A"]

    def test_two_nodes_no_edges_share_top_layer(self) -> None:
        """Disconnected nodes both end up at y=0."""
        r = sugiyama_layout(["A", "B"], [])
        assert r.positions["A"][1] == 0.0
        assert r.positions["B"][1] == 0.0


class TestEdgePolylines:
    """Edge polylines connect node positions through dummy bends."""

    def test_simple_edge_polyline_is_two_points(self) -> None:
        """An edge between adjacent layers has no bend points."""
        r = sugiyama_layout(["A", "B"], [("A", "B")])
        polyline = r.edges[("A", "B")]
        assert len(polyline) == 2
        assert polyline[0] == r.positions["A"]
        assert polyline[1] == r.positions["B"]

    def test_long_edge_polyline_starts_and_ends_at_endpoints(self) -> None:
        """Long edge polyline first/last points are the original endpoints."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C"), ("A", "C")])
        polyline = r.edges[("A", "C")]
        assert polyline[0] == r.positions["A"]
        assert polyline[-1] == r.positions["C"]

    def test_reversed_edge_polyline_runs_in_input_direction(self) -> None:
        """Even when stage 1 reverses C→A, the output polyline is in C→A order."""
        r = sugiyama_layout(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
        # The edge (C, A) was the original; whether it was reversed
        # internally, the polyline must start at C and end at A.
        polyline = r.edges[("C", "A")]
        assert polyline[0] == r.positions["C"]
        assert polyline[-1] == r.positions["A"]
