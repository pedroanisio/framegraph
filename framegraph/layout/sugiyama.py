"""Sugiyama hierarchical layout — pure-Python, full 4-stage pipeline.

Computes layered (top-down) layouts for directed graphs. The output
is a mapping from input node id to `(x, y)` plus per-edge polylines
that route through optional intermediate "dummy" nodes inserted for
edges spanning more than one layer.

Algorithm
---------
1. **Cycle removal.** Eades/Lin/Smyth (1993) greedy feedback-edge-set
   heuristic. Reverses a small set of edges to make the input a DAG.
   Reversed edges are tracked so the final output can flip them back
   into their original direction.
2. **Layer assignment.** Longest-path layering on the DAG. Each node
   `v` receives `layer(v) = max(layer(u) + 1 for u in preds(v))`.
   Edges spanning >1 layer are subdivided with synthetic "dummy"
   nodes — one per intermediate layer — so every edge becomes
   single-layer-spanning. Bend points in the final polyline are the
   positions of these dummies.
3. **Crossing minimization.** Iterative median-heuristic sweeps
   between adjacent layers. The order within each layer is recomputed
   based on the median position of each node's neighbours in the
   adjacent layer. Sweeps alternate direction (down then up) and
   stop when no improvement is observed for `passes_without_change`.
4. **X-coordinate assignment.** Brandes-Köpf (2002), four-sweep
   variant. Each of the four passes aligns nodes by a
   (vertical, horizontal) pair (top/bottom × left/right). The four
   resulting x-coordinate sets are then averaged into a final
   balanced layout. Brandes-Köpf is the production-quality
   algorithm for this stage; it produces compact, vertically-
   aligned, horizontally-balanced layouts.

References:
----------
- Sugiyama, Tagawa, Toda (1981). "Methods for visual understanding of
  hierarchical system structures." IEEE Trans. Sys. Man Cybernetics.
- Eades, Lin, Smyth (1993). "A fast and effective heuristic for the
  feedback arc set problem." Information Processing Letters 47.
- Gansner, Koutsofios, North, Vo (1993). "A technique for drawing
  directed graphs." IEEE Trans. Software Engineering.
- Brandes & Köpf (2002). "Fast and Simple Horizontal Coordinate
  Assignment." Graph Drawing 2001 LNCS 2265.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

NodeId = Hashable
"""A node identifier. Any hashable value the caller wants to use."""

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class SugiyamaConfig:
    """Tunable parameters for the Sugiyama pipeline.

    Attributes:
        layer_height: Vertical distance between adjacent layers (px).
        node_width: Default per-node horizontal slot width (px). Used
            as the unit of horizontal spacing in stage 4.
        node_gap: Minimum horizontal gap between adjacent nodes in
            the same layer (px).
        crossing_passes: Maximum number of crossing-minimization
            sweep pairs (down + up = 2 sweeps per pair). The loop
            terminates early when a full sweep produces no
            improvement.
        passes_without_change: Number of consecutive sweeps without
            any node-order change required to stop crossing
            minimization early. Default 2.
    """

    layer_height: float = 80.0
    node_width: float = 60.0
    node_gap: float = 20.0
    crossing_passes: int = 24
    passes_without_change: int = 2


@dataclass
class LayoutResult:
    """Output of `sugiyama_layout`.

    Attributes:
        positions: Mapping `node_id → (x, y)` for every input node.
            Coordinates are in arbitrary units; consumers scale as
            needed. Nodes are positioned at their box center.
        edges: For each input edge `(u, v)`, the polyline that
            routes from `u` through any inserted dummy bend points
            to `v`. The list is keyed by original edge orientation —
            even when stage 1 reverses an edge to break a cycle, the
            output here is in the caller's original direction.
        layers: For diagnostic use, the ordered list of nodes at
            each layer (top-down). Includes only original nodes;
            dummy nodes are excluded.
        reversed_edges: The set of edges that stage 1 reversed to
            break cycles. Each entry is the original `(u, v)`
            orientation as supplied; the renderer should draw an
            arrowhead on `u` (the reversed end) for "back" edges.
        crossings: Final crossing count after stage 3. Lower is
            better; useful for callers comparing alternative
            input orderings.
    """

    positions: dict[NodeId, tuple[float, float]]
    edges: dict[tuple[NodeId, NodeId], list[tuple[float, float]]]
    layers: list[list[NodeId]]
    reversed_edges: set[tuple[NodeId, NodeId]] = field(default_factory=set)
    crossings: int = 0


# ─────────────────────────────────────────────────────────────────
# Internal graph representation
# ─────────────────────────────────────────────────────────────────


@dataclass
class _Graph:
    """Mutable adjacency-list graph used by the pipeline.

    Distinct from `LayoutResult` — this carries the working state
    across stages including dummy nodes and the layer index.
    """

    nodes: list[NodeId]
    """All nodes including dummies. Stable ordering for determinism."""

    succ: dict[NodeId, list[NodeId]]
    """Forward adjacency: succ[u] is the ordered list of v with edge u→v."""

    pred: dict[NodeId, list[NodeId]]
    """Backward adjacency: pred[v] is the ordered list of u with edge u→v."""

    layer: dict[NodeId, int]
    """Layer index per node (0 = top)."""

    is_dummy: dict[NodeId, bool] = field(default_factory=dict)
    """True for synthetic dummy nodes inserted by long-edge subdivision."""

    # When stage 1 reverses an edge, we remember it so stage 4 / output
    # can flip the polyline back to the original direction.
    reversed_in_input: set[tuple[NodeId, NodeId]] = field(default_factory=set)


# ─────────────────────────────────────────────────────────────────
# Stage 1: cycle removal (Eades-Lin-Smyth greedy heuristic)
# ─────────────────────────────────────────────────────────────────


def _remove_cycles(
    nodes: Sequence[NodeId], edges: Sequence[tuple[NodeId, NodeId]]
) -> tuple[list[tuple[NodeId, NodeId]], set[tuple[NodeId, NodeId]]]:
    """Reverse a small set of edges so the result is a DAG.

    Implements the Eades-Lin-Smyth greedy feedback-arc-set heuristic.
    The algorithm peels off sources (in-degree 0) onto an `s1` list
    and sinks (out-degree 0) onto an `s2` list. When neither is
    available, the node with maximum (out-degree − in-degree) is
    appended to `s1`. The final ordering is `s1 + reversed(s2)`;
    edges that go "backward" in this ordering are the feedback set
    and get reversed.

    Args:
        nodes: All node ids.
        edges: Directed edges as `(u, v)` pairs.

    Returns:
        A tuple `(dag_edges, reversed_set)`. `dag_edges` is the input
        with feedback edges flipped; `reversed_set` is the original-
        orientation edges that were flipped (so callers can restore
        direction in their output).
    """
    # Build mutable degree counts and adjacency for the heuristic.
    out_adj: dict[NodeId, set[NodeId]] = defaultdict(set)
    in_adj: dict[NodeId, set[NodeId]] = defaultdict(set)
    edge_set: set[tuple[NodeId, NodeId]] = set()
    for u, v in edges:
        if u == v:
            # Self-loop: not part of any layered layout. Drop and
            # treat as reversed so the caller knows it was special.
            edge_set.add((u, v))
            continue
        out_adj[u].add(v)
        in_adj[v].add(u)
        edge_set.add((u, v))

    remaining: set[NodeId] = set(nodes)
    s1: list[NodeId] = []
    s2: list[NodeId] = []

    def in_deg(n: NodeId) -> int:
        return sum(1 for u in in_adj[n] if u in remaining)

    def out_deg(n: NodeId) -> int:
        return sum(1 for v in out_adj[n] if v in remaining)

    while remaining:
        # Peel sinks first (out-degree 0)
        progress = True
        while progress:
            progress = False
            sinks = [n for n in remaining if out_deg(n) == 0]
            for n in sinks:
                s2.append(n)
                remaining.discard(n)
                progress = True
            sources = [n for n in remaining if in_deg(n) == 0]
            for n in sources:
                s1.append(n)
                remaining.discard(n)
                progress = True
        if not remaining:
            break
        # No source/sink — pick the node with max (out_deg − in_deg)
        # and treat it as a "preferred source".
        best = max(remaining, key=lambda n: (out_deg(n) - in_deg(n), repr(n)))
        s1.append(best)
        remaining.discard(best)

    ordering = s1 + list(reversed(s2))
    pos = {n: i for i, n in enumerate(ordering)}

    dag_edges: list[tuple[NodeId, NodeId]] = []
    reversed_set: set[tuple[NodeId, NodeId]] = set()
    for u, v in edges:
        if u == v:
            # Self-loops dropped — caller can render separately.
            reversed_set.add((u, v))
            continue
        if pos.get(u, 0) < pos.get(v, 0):
            dag_edges.append((u, v))
        else:
            # Backward edge — flip it.
            dag_edges.append((v, u))
            reversed_set.add((u, v))
    return dag_edges, reversed_set


# ─────────────────────────────────────────────────────────────────
# Stage 2: layer assignment + long-edge subdivision
# ─────────────────────────────────────────────────────────────────


def _assign_layers(nodes: Sequence[NodeId], dag_edges: Sequence[tuple[NodeId, NodeId]]) -> _Graph:
    """Assign each node a layer index by longest-path from any source.

    Inserts synthetic dummy nodes with ids `("__dummy__", u, v, k)`
    on each edge whose endpoints span more than one layer; after
    insertion every edge connects nodes on adjacent layers.

    Args:
        nodes: Original node ids.
        dag_edges: Edges of the (acyclic) graph from stage 1.

    Returns:
        A `_Graph` with layer index, adjacency, and dummy-node flags
        populated. Original edges are decomposed into chains of
        single-layer edges through dummy nodes.

    Raises:
        ValueError: If `dag_edges` contains a cycle (which shouldn't
            happen after stage 1, but is checked defensively).
    """
    # Topological sort for longest-path computation
    succ: dict[NodeId, list[NodeId]] = defaultdict(list)
    pred: dict[NodeId, list[NodeId]] = defaultdict(list)
    in_deg: dict[NodeId, int] = defaultdict(int)
    for u, v in dag_edges:
        succ[u].append(v)
        pred[v].append(u)
        in_deg[v] += 1
    topo: list[NodeId] = []
    queue: deque[NodeId] = deque(n for n in nodes if in_deg[n] == 0)
    in_deg_copy = dict(in_deg)
    while queue:
        n = queue.popleft()
        topo.append(n)
        for v in succ[n]:
            in_deg_copy[v] -= 1
            if in_deg_copy[v] == 0:
                queue.append(v)
    if len(topo) != len(nodes):
        raise ValueError("stage 2 received a graph with cycles — stage 1 should have removed them")

    # Longest-path layer index
    layer: dict[NodeId, int] = dict.fromkeys(nodes, 0)
    for n in topo:
        for v in succ[n]:
            if layer[v] < layer[n] + 1:
                layer[v] = layer[n] + 1

    # Subdivide long edges with dummy nodes
    new_succ: dict[NodeId, list[NodeId]] = defaultdict(list)
    new_pred: dict[NodeId, list[NodeId]] = defaultdict(list)
    is_dummy: dict[NodeId, bool] = dict.fromkeys(nodes, False)
    all_nodes: list[NodeId] = list(nodes)

    for u, v in dag_edges:
        span = layer[v] - layer[u]
        if span <= 1:
            new_succ[u].append(v)
            new_pred[v].append(u)
            continue
        # Insert (span - 1) dummy nodes on layers layer[u]+1 … layer[v]-1
        prev = u
        for k in range(1, span):
            dummy: NodeId = ("__dummy__", u, v, k)
            all_nodes.append(dummy)
            is_dummy[dummy] = True
            layer[dummy] = layer[u] + k
            new_succ[prev].append(dummy)
            new_pred[dummy].append(prev)
            prev = dummy
        new_succ[prev].append(v)
        new_pred[v].append(prev)

    return _Graph(
        nodes=all_nodes,
        succ=new_succ,
        pred=new_pred,
        layer=layer,
        is_dummy=is_dummy,
    )


# ─────────────────────────────────────────────────────────────────
# Stage 3: crossing minimization (median heuristic, multi-pass)
# ─────────────────────────────────────────────────────────────────


def _initial_layer_order(g: _Graph) -> list[list[NodeId]]:
    """Group nodes by layer; preserve initial insertion order.

    Returns a list `layers` such that `layers[i]` is the ordered
    sequence of nodes on layer `i`. The initial order is the order
    in which nodes were added to `g.nodes`, which reflects the
    caller's preferred ordering.
    """
    n_layers = max(g.layer.values()) + 1 if g.layer else 0
    layers: list[list[NodeId]] = [[] for _ in range(n_layers)]
    for n in g.nodes:
        layers[g.layer[n]].append(n)
    return layers


def _count_crossings_between_layers(
    upper: Sequence[NodeId],
    lower: Sequence[NodeId],
    succ: dict[NodeId, list[NodeId]],
) -> int:
    """Count edge crossings between two adjacent layers.

    Uses the standard merge-sort-inversion-count approach:
    represent every edge as `(upper_idx, lower_idx)` pairs sorted by
    upper, then count pairs where lower indices are out of order.
    Quadratic in worst case here for clarity — for the graph sizes
    UML class/sequence diagrams produce, this is fine.

    Args:
        upper: Ordered nodes on the upper layer.
        lower: Ordered nodes on the lower layer.
        succ: Forward adjacency `u → list[v]`.

    Returns:
        Number of edge-pair crossings.
    """
    lower_pos = {n: i for i, n in enumerate(lower)}
    edges: list[tuple[int, int]] = []
    for ui, u in enumerate(upper):
        for v in succ.get(u, []):
            if v in lower_pos:
                edges.append((ui, lower_pos[v]))
    edges.sort()
    crossings = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i][1] > edges[j][1]:
                crossings += 1
    return crossings


def _median(values: Sequence[float]) -> float:
    """Median of a numeric sequence; returns -1 for empty input.

    The -1 sentinel keeps nodes with no neighbours stable at the
    front of their layer, which is the convention used throughout
    Sugiyama-style implementations.
    """
    if not values:
        return -1.0
    s = sorted(values)
    m = len(s) // 2
    if len(s) % 2 == 1:
        return float(s[m])
    return (s[m - 1] + s[m]) / 2.0


def _minimize_crossings(g: _Graph, cfg: SugiyamaConfig) -> tuple[list[list[NodeId]], int]:
    """Iteratively re-order each layer to reduce edge crossings.

    Down sweep: for each layer 1..L-1, set each node's sort key to
    the median of its predecessors' positions in the layer above,
    then sort.

    Up sweep: same idea, layers L-2..0, using successors below.

    Continues alternating sweeps until `passes_without_change`
    consecutive passes produce no node-order change, or until
    `crossing_passes` is exhausted.

    Args:
        g: Graph with layers populated.
        cfg: Tunable thresholds.

    Returns:
        `(layers, total_crossings)`. `layers[i]` is the final order
        on layer i; `total_crossings` is the count summed over all
        adjacent layer pairs.
    """
    layers = _initial_layer_order(g)
    if len(layers) < 2:
        return layers, 0

    def total_crossings() -> int:
        return sum(
            _count_crossings_between_layers(layers[i], layers[i + 1], g.succ)
            for i in range(len(layers) - 1)
        )

    best_layers = [list(lyr) for lyr in layers]
    best_count = total_crossings()
    no_change_streak = 0

    for sweep in range(cfg.crossing_passes):
        prev_order = [list(lyr) for lyr in layers]
        going_down = sweep % 2 == 0
        if going_down:
            for i in range(1, len(layers)):
                upper_pos = {n: idx for idx, n in enumerate(layers[i - 1])}
                # Rank nodes on layer i by median predecessor position
                keyed = [
                    (
                        _median([upper_pos[u] for u in g.pred.get(n, []) if u in upper_pos]),
                        idx,  # stable tie-breaker on previous order
                        n,
                    )
                    for idx, n in enumerate(layers[i])
                ]
                # Nodes with median == -1 stay where they were
                keyed.sort(key=lambda t: (t[0] if t[0] >= 0 else float("inf"), t[1]))
                layers[i] = [t[2] for t in keyed]
        else:
            for i in range(len(layers) - 2, -1, -1):
                lower_pos = {n: idx for idx, n in enumerate(layers[i + 1])}
                keyed = [
                    (
                        _median([lower_pos[v] for v in g.succ.get(n, []) if v in lower_pos]),
                        idx,
                        n,
                    )
                    for idx, n in enumerate(layers[i])
                ]
                keyed.sort(key=lambda t: (t[0] if t[0] >= 0 else float("inf"), t[1]))
                layers[i] = [t[2] for t in keyed]

        cur_count = total_crossings()
        if cur_count < best_count:
            best_count = cur_count
            best_layers = [list(lyr) for lyr in layers]
        if all(prev_order[i] == layers[i] for i in range(len(layers))):
            no_change_streak += 1
            if no_change_streak >= cfg.passes_without_change:
                break
        else:
            no_change_streak = 0

    return best_layers, best_count


# ─────────────────────────────────────────────────────────────────
# Stage 4: x-coordinate assignment (Brandes-Köpf)
# ─────────────────────────────────────────────────────────────────


def _mark_type1_conflicts(
    layers: Sequence[Sequence[NodeId]],
    pred: dict[NodeId, list[NodeId]],
    is_dummy: dict[NodeId, bool],
) -> set[tuple[NodeId, NodeId]]:
    """Identify Type-1 conflicts per Brandes-Köpf §3.

    A Type-1 conflict is a pair of edges (a non-inner segment crossing
    an inner segment between two adjacent layers, where "inner
    segment" means both endpoints are dummy nodes — i.e., the edge
    is part of a long-edge chain). The algorithm prefers to keep
    inner segments straight, so non-inner segments lose alignment
    eligibility when they cross an inner segment.

    Args:
        layers: Final node ordering per layer.
        pred: Backward adjacency.
        is_dummy: Per-node dummy flag.

    Returns:
        Set of `(upper_node, lower_node)` edges marked as Type-1
        conflicts. Such edges are excluded from the alignment phase.
    """
    conflicts: set[tuple[NodeId, NodeId]] = set()
    if len(layers) < 2:
        return conflicts

    for i in range(1, len(layers) - 1):
        upper = layers[i]
        lower = layers[i + 1]
        upper_pos = {n: p for p, n in enumerate(upper)}
        k0 = 0
        last = len(lower) - 1
        for li, low_n in enumerate(lower):
            # Find inner segment landing here, if any
            ki = None
            if is_dummy.get(low_n, False):
                for u in pred.get(low_n, []):
                    if is_dummy.get(u, False) and u in upper_pos:
                        ki = upper_pos[u]
                        break
            if ki is not None or li == last:
                k1 = ki if ki is not None else len(upper) - 1
                # All non-inner edges incident to nodes at positions
                # k0..li in the lower layer that connect to upper positions
                # outside [k0..k1] are Type-1 conflicts.
                for j in range(k0, li + 1):
                    n = lower[j]
                    for u in pred.get(n, []):
                        if u not in upper_pos:
                            continue
                        upper_idx = upper_pos[u]
                        if (upper_idx < k0 or upper_idx > k1) and not (
                            is_dummy.get(u, False) and is_dummy.get(n, False)
                        ):
                            conflicts.add((u, n))
                if ki is not None:
                    k0 = ki
    return conflicts


def _vertical_alignment(
    layers: Sequence[Sequence[NodeId]],
    pred: dict[NodeId, list[NodeId]],
    succ: dict[NodeId, list[NodeId]],
    conflicts: set[tuple[NodeId, NodeId]],
    *,
    direction: str,
) -> tuple[dict[NodeId, NodeId], dict[NodeId, NodeId]]:
    """Compute root and align maps for one of the four BK sweeps.

    Args:
        layers: Final node ordering per layer.
        pred: Backward adjacency `v → list[u]` for upward sweeps.
        succ: Forward adjacency `u → list[v]` for downward sweeps.
        conflicts: Type-1 conflicts to skip.
        direction: One of `"up_left"`, `"up_right"`, `"down_left"`,
            `"down_right"`. Combines the vertical sweep direction
            (up = consider neighbours in the layer above; down =
            consider the layer below) with horizontal preference
            (left or right).

    Returns:
        `(root, align)` where `root[v]` is the topmost node in v's
        alignment block and `align[v]` is the next node downwards
        in the block.
    """
    root: dict[NodeId, NodeId] = {n: n for layer in layers for n in layer}
    align: dict[NodeId, NodeId] = {n: n for layer in layers for n in layer}

    vertical_up = direction.startswith("up")
    horizontal_left = direction.endswith("left")

    # Pick layer iteration order
    layer_range = range(1, len(layers)) if vertical_up else range(len(layers) - 2, -1, -1)

    for i in layer_range:
        cur_layer = list(layers[i]) if horizontal_left else list(reversed(layers[i]))
        r = -1  # last-aligned position in the *neighbour* layer
        for v in cur_layer:
            # Neighbours = the layer we're aligning *toward*
            if vertical_up:
                neighbours = pred.get(v, [])
                neighbour_layer = layers[i - 1]
            else:
                neighbours = succ.get(v, [])
                neighbour_layer = layers[i + 1]

            neighbour_pos = {n: p for p, n in enumerate(neighbour_layer)}
            ns = sorted(
                (neighbour_pos[u] for u in neighbours if u in neighbour_pos),
            )
            if not ns:
                continue
            # Median neighbour(s)
            if len(ns) % 2 == 1:
                medians = [ns[len(ns) // 2]]
            else:
                medians = [ns[len(ns) // 2 - 1], ns[len(ns) // 2]]
            # Try the preferred median first
            if not horizontal_left:
                medians = list(reversed(medians))
            for m in medians:
                u = neighbour_layer[m]
                edge = (u, v) if vertical_up else (v, u)
                if edge in conflicts:
                    continue
                # Maintain horizontal monotonicity
                if (horizontal_left and m > r) or (not horizontal_left and m < r):
                    align[u] = v
                    root[v] = root[u]
                    align[v] = root[v]
                    r = m
                    break
    return root, align


def _horizontal_compaction(
    layers: Sequence[Sequence[NodeId]],
    root: dict[NodeId, NodeId],
    align: dict[NodeId, NodeId],
    cfg: SugiyamaConfig,
    *,
    horizontal_left: bool,
) -> dict[NodeId, float]:
    """Compute x coordinates for one BK sweep.

    Uses a recursive sink-and-shift on the alignment-block forest.

    Args:
        layers: Final node ordering per layer.
        root: Output of `_vertical_alignment` — block-root map.
        align: Output of `_vertical_alignment` — alignment-chain map.
        cfg: Spacing constants.
        horizontal_left: True for left-leaning passes (smaller x is
            preferred); False for right-leaning.

    Returns:
        Mapping `node → x` for every node. Coordinates are not
        normalized — they may be negative for right-leaning sweeps;
        the caller averages and normalizes across all four passes.
    """
    sink: dict[NodeId, NodeId] = {n: n for layer in layers for n in layer}
    shift: dict[NodeId, float] = {n: float("inf") for layer in layers for n in layer}
    x: dict[NodeId, float] = {}

    delta = cfg.node_width + cfg.node_gap

    def place_block(v: NodeId) -> None:
        if v in x:
            return
        x[v] = 0.0
        w = v
        while True:
            # w's layer + position
            for li, layer in enumerate(layers):
                if w in layer:
                    pos_in_layer = layer.index(w)
                    layer_idx = li
                    break
            else:
                break  # shouldn't happen
            if (horizontal_left and pos_in_layer > 0) or (
                not horizontal_left and pos_in_layer < len(layers[layer_idx]) - 1
            ):
                pred_in_layer = (
                    layers[layer_idx][pos_in_layer - 1]
                    if horizontal_left
                    else layers[layer_idx][pos_in_layer + 1]
                )
                u = root[pred_in_layer]
                place_block(u)
                if sink[v] == v:
                    sink[v] = sink[u]
                if sink[v] != sink[u]:
                    proposed = x[v] - x[u] - delta if horizontal_left else x[u] - x[v] - delta
                    cur = shift[sink[u]]
                    shift[sink[u]] = (
                        min(cur, proposed)
                        if horizontal_left
                        else max(-float("inf") if cur == float("inf") else cur, proposed)
                    )
                else:
                    if horizontal_left:
                        x[v] = max(x[v], x[u] + delta)
                    else:
                        x[v] = min(x[v], x[u] - delta)
            w = align[w]
            if w == v:
                break

    # Place every block via its root
    for layer in layers:
        for v in layer:
            if root[v] == v:
                place_block(v)

    # Apply shifts: each node inherits its block's x-shift via sink
    result: dict[NodeId, float] = {}
    for layer in layers:
        for v in layer:
            r = root[v]
            base = x.get(r, 0.0)
            s = shift.get(sink[r], 0.0)
            if s == float("inf"):
                s = 0.0
            result[v] = base + s
    return result


def _balance_x(passes: list[dict[NodeId, float]]) -> dict[NodeId, float]:
    """Average the four BK-sweep x-coordinate sets per Brandes-Köpf §4.

    For each node, compute the median of its four x-positions across
    sweeps. To match BK's "balance" step exactly we take the average
    of the two middle values rather than the strict median.
    """
    nodes = passes[0].keys() if passes else []
    out: dict[NodeId, float] = {}
    for n in nodes:
        vals = sorted(p.get(n, 0.0) for p in passes)
        # Average the two middle values
        if len(vals) >= 4:
            out[n] = (vals[1] + vals[2]) / 2.0
        elif vals:
            out[n] = sum(vals) / len(vals)
        else:
            out[n] = 0.0
    # Normalize so the leftmost node sits at x=0
    if out:
        min_x = min(out.values())
        for k in out:
            out[k] -= min_x
    return out


def _assign_x_coords(
    g: _Graph, layers: list[list[NodeId]], cfg: SugiyamaConfig
) -> dict[NodeId, float]:
    """Run all four BK sweeps and average them into a final x for every node."""
    conflicts = _mark_type1_conflicts(layers, g.pred, g.is_dummy)
    passes = []
    for direction in ("up_left", "up_right", "down_left", "down_right"):
        root, align = _vertical_alignment(layers, g.pred, g.succ, conflicts, direction=direction)
        horizontal_left = direction.endswith("left")
        x = _horizontal_compaction(layers, root, align, cfg, horizontal_left=horizontal_left)
        passes.append(x)
    return _balance_x(passes)


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────


def sugiyama_layout(
    nodes: Iterable[NodeId],
    edges: Iterable[tuple[NodeId, NodeId]],
    *,
    config: SugiyamaConfig | None = None,
) -> LayoutResult:
    """Compute a hierarchical layered layout for a directed graph.

    Args:
        nodes: All node ids. Each must be hashable. Determines the
            layer-0 ordering when no other constraint applies.
        edges: Directed edges as `(src, dst)` tuples. May contain
            cycles; stage 1 will reverse a small set to make a DAG.
            Self-loops are permitted but excluded from layout (they
            appear in `LayoutResult.reversed_edges` so callers can
            render them separately).
        config: Spacing and iteration tunables. Defaults to
            `SugiyamaConfig()`.

    Returns:
        A `LayoutResult` with absolute `(x, y)` per node, edge
        polylines (including dummy bend points for long edges), the
        per-layer ordering, the set of reversed edges, and the final
        crossing count.

    Raises:
        ValueError: If stage 2 receives a graph it cannot topologically
            sort (which indicates a bug in stage 1, not malformed
            input — defensive check only).
    """
    cfg = config or SugiyamaConfig()
    node_list = list(nodes)
    edge_list = [(u, v) for u, v in edges]

    # Stage 1: cycle removal
    dag_edges, reversed_set = _remove_cycles(node_list, edge_list)

    # Stage 2: layer assignment + dummy insertion
    g = _assign_layers(node_list, dag_edges)
    g.reversed_in_input = reversed_set

    # Stage 3: crossing minimization
    final_layers, crossings = _minimize_crossings(g, cfg)

    # Stage 4: x-coordinate assignment via Brandes-Köpf
    x_coords = _assign_x_coords(g, final_layers, cfg)

    # Y-coordinate is straightforward: layer * layer_height
    positions: dict[NodeId, tuple[float, float]] = {}
    original_set = set(node_list)
    for n in node_list:
        positions[n] = (x_coords[n], g.layer[n] * cfg.layer_height)

    # Build edge polylines from the original input edges, walking
    # through dummy chains where appropriate.
    edge_polylines: dict[tuple[NodeId, NodeId], list[tuple[float, float]]] = {}
    for u, v in edge_list:
        if u == v:
            # Self-loop — single-point degenerate polyline
            edge_polylines[(u, v)] = [positions[u]]
            continue

        # If this edge was reversed in stage 1, the dummies live on
        # (v, u, k); the graph stored it that way.
        original_reversed = (u, v) in reversed_set
        head, tail = (v, u) if original_reversed else (u, v)

        # Walk dummy chain from head→tail using the dummy-id
        # convention: ("__dummy__", head, tail, k).
        n_layers_spanned = abs(g.layer[tail] - g.layer[head])
        path: list[tuple[float, float]] = [positions[head]]
        for k in range(1, n_layers_spanned):
            dummy_id: NodeId = ("__dummy__", head, tail, k)
            if dummy_id in g.layer:
                # Dummy x lives only in x_coords (not in `positions`,
                # which is restricted to original nodes)
                path.append((x_coords[dummy_id], g.layer[dummy_id] * cfg.layer_height))
        path.append(positions[tail])
        if original_reversed:
            path.reverse()
        edge_polylines[(u, v)] = path

    # Filter the per-layer report to original nodes only.
    final_layers_original_only = [[n for n in lyr if n in original_set] for lyr in final_layers]

    return LayoutResult(
        positions=positions,
        edges=edge_polylines,
        layers=final_layers_original_only,
        reversed_edges={(u, v) for (u, v) in reversed_set},
        crossings=crossings,
    )
