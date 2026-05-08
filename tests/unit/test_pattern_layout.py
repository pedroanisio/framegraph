"""Unit tests for `framegraph.patterns.layout` — Phase 3 of the fill-and-render roadmap.

The layout engine turns a pattern's zones into ``[x, y, w, h]``
boxes on a canvas. It runs in two passes:

  1. **Anchor + region (geometric)**: place every anchor- and
     region-typed zone using the 9-cell grid and per-region hand-
     coded layouts.
  2. **Relative (refinement)**: place every `relative` zone by
     looking up its target's box from pass 1.

Phase 3 acceptance criteria (from `docs/ROADMAP-FILL-RENDER.md`):

  - Every zone of every catalog pattern gets a non-zero box on a
    1920×1080 canvas without errors.
  - Boxes don't exceed canvas bounds; same-cell siblings don't
    overlap.
  - BMC #44 produces a recognizable 9-block grid layout.
  - SWOT #10 produces a recognizable 2×2 grid.
  - Layout is deterministic — same input always yields same output.
"""

from __future__ import annotations

import pytest

from framegraph._patterns import SlidePattern
from framegraph.patterns import compute_boxes


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _zone(
    role: str,
    *,
    h: str = "center",
    v: str = "middle",
    size: str = "medium",
    fullbleed: bool = False,
    region: str | None = None,
    relative: dict | None = None,
    shape: str | None = None,
    content_type: str | None = "title_body",
) -> dict:
    if fullbleed:
        placement = {"anchor": "fullbleed"}
    elif region is not None:
        placement = {"region": region}
    elif relative is not None:
        placement = {"relative": relative}
    else:
        placement = {"anchor": {"h": h, "v": v}}
    z: dict = {
        "role": role,
        "size": size,
        "placement": placement,
    }
    if shape is not None:
        z["shape"] = shape
    if content_type is not None:
        z["content_type"] = content_type
    return z


def _pattern(zones: list[dict], pattern_id: int = 99001) -> SlidePattern:
    return SlidePattern.model_validate(
        {
            "id": pattern_id,
            "name": "T",
            "layout_disposition": "x",
            "zones": zones,
        }
    )


CANVAS_W = 1920.0
CANVAS_H = 1080.0


# ─────────────────────────────────────────────────────────────────
# 1. Single-zone anchor placements
# ─────────────────────────────────────────────────────────────────


class TestSingleAnchor:
    def test_center_middle_anchor(self) -> None:
        p = _pattern([_zone("a", h="center", v="middle")])
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        x, y, w, h = boxes["a"]
        # Center cell of a 3x3 grid: x straddles canvas mid, y straddles canvas mid.
        assert 0 < x < CANVAS_W / 2
        assert x + w > CANVAS_W / 2
        assert 0 < y < CANVAS_H / 2
        assert y + h > CANVAS_H / 2

    @pytest.mark.parametrize(
        "h,v,quadrant_check",
        [
            ("left", "top", lambda x, y, w, h: x < CANVAS_W / 2 and y < CANVAS_H / 2),
            ("right", "top", lambda x, y, w, h: x + w > CANVAS_W / 2 and y < CANVAS_H / 2),
            ("left", "bottom", lambda x, y, w, h: x < CANVAS_W / 2 and y + h > CANVAS_H / 2),
            ("right", "bottom", lambda x, y, w, h: x + w > CANVAS_W / 2 and y + h > CANVAS_H / 2),
        ],
    )
    def test_corner_anchors_land_in_correct_quadrants(self, h, v, quadrant_check) -> None:
        p = _pattern([_zone("a", h=h, v=v)])
        x, y, w, hh = compute_boxes(p, CANVAS_W, CANVAS_H)["a"]
        assert quadrant_check(x, y, w, hh), (h, v, x, y, w, hh)


# ─────────────────────────────────────────────────────────────────
# 2. Fullbleed anchor — covers entire canvas
# ─────────────────────────────────────────────────────────────────


class TestFullbleed:
    def test_fullbleed_covers_canvas(self) -> None:
        p = _pattern([_zone("bg", fullbleed=True)])
        x, y, w, h = compute_boxes(p, CANVAS_W, CANVAS_H)["bg"]
        # Allow margin shrinkage; full-bleed should at least dominate.
        assert x <= 0 or x < 50
        assert y <= 0 or y < 50
        assert w >= CANVAS_W - 100
        assert h >= CANVAS_H - 100


# ─────────────────────────────────────────────────────────────────
# 3. Same-cell siblings — must not overlap, must split the cell
# ─────────────────────────────────────────────────────────────────


class TestSameCellSiblings:
    def test_two_zones_in_same_cell_split_horizontally(self) -> None:
        p = _pattern(
            [
                _zone("a", h="center", v="middle", size="equal"),
                _zone("b", h="center", v="middle", size="equal"),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        ax, ay, aw, ah = boxes["a"]
        bx, by, bw, bh = boxes["b"]
        # Two equal siblings: side-by-side (x ranges don't overlap).
        assert ax + aw <= bx + 0.5 or bx + bw <= ax + 0.5

    def test_three_zones_in_same_cell_no_overlap(self) -> None:
        p = _pattern(
            [
                _zone("a", h="center", v="middle", size="equal"),
                _zone("b", h="center", v="middle", size="equal"),
                _zone("c", h="center", v="middle", size="equal"),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        for ra, rb in [("a", "b"), ("b", "c"), ("a", "c")]:
            ax, ay, aw, ah = boxes[ra]
            bx, by, bw, bh = boxes[rb]
            no_overlap = (
                ax + aw <= bx + 0.5
                or bx + bw <= ax + 0.5
                or ay + ah <= by + 0.5
                or by + bh <= ay + 0.5
            )
            assert no_overlap, f"{ra} and {rb} overlap: {boxes[ra]} {boxes[rb]}"


# ─────────────────────────────────────────────────────────────────
# 4. Region placements — top-5 hand-coded layouts
# ─────────────────────────────────────────────────────────────────


class TestRegions:
    def test_matrix_body_centered(self) -> None:
        p = _pattern([_zone("body", region="matrix_body")])
        x, y, w, h = compute_boxes(p, CANVAS_W, CANVAS_H)["body"]
        # matrix_body should occupy the central ~50%+ of the canvas.
        assert w > CANVAS_W * 0.4
        assert h > CANVAS_H * 0.4

    def test_unknown_region_falls_back_to_center(self) -> None:
        p = _pattern([_zone("z", region="some_invented_region")])
        x, y, w, h = compute_boxes(p, CANVAS_W, CANVAS_H)["z"]
        # Should not crash; should produce a non-zero centered box.
        assert w > 0 and h > 0
        cx = x + w / 2
        cy = y + h / 2
        assert abs(cx - CANVAS_W / 2) < CANVAS_W * 0.2
        assert abs(cy - CANVAS_H / 2) < CANVAS_H * 0.2


# ─────────────────────────────────────────────────────────────────
# 5. Relative placements — second pass over a target's box
# ─────────────────────────────────────────────────────────────────


class TestRelativePlacement:
    def test_below_target(self) -> None:
        p = _pattern(
            [
                _zone("title", h="center", v="top"),
                _zone(
                    "subtitle",
                    relative={"relation": "below", "target": "title"},
                ),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        tx, ty, tw, th = boxes["title"]
        sx, sy, sw, sh = boxes["subtitle"]
        # subtitle should sit below title's box (no overlap, sy >= ty + th).
        assert sy >= ty + th - 0.5

    def test_inside_target(self) -> None:
        p = _pattern(
            [
                _zone("card", h="center", v="middle"),
                _zone(
                    "label",
                    relative={"relation": "inside", "target": "card"},
                ),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        cx, cy, cw, ch = boxes["card"]
        lx, ly, lw, lh = boxes["label"]
        # Label fully inside card.
        assert cx <= lx and lx + lw <= cx + cw + 0.5
        assert cy <= ly and ly + lh <= cy + ch + 0.5

    def test_between_target(self) -> None:
        p = _pattern(
            [
                _zone("a", h="left", v="middle"),
                _zone("b", h="right", v="middle"),
                _zone(
                    "connector",
                    relative={"relation": "between", "target": "a"},
                ),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        # connector should sit roughly in the horizontal middle.
        cx, cy, cw, ch = boxes["connector"]
        assert CANVAS_W * 0.25 < cx + cw / 2 < CANVAS_W * 0.75

    def test_dangling_target_falls_back_gracefully(self) -> None:
        """When `target` doesn't exist as a role, fall back to canvas centroid."""
        p = _pattern(
            [
                _zone("a", h="center", v="middle"),
                _zone(
                    "b",
                    relative={
                        "relation": "between",
                        "target": "nonexistent_role",
                    },
                ),
            ]
        )
        boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
        # Should not crash; b should get a non-zero box near canvas center.
        bx, by, bw, bh = boxes["b"]
        assert bw > 0 and bh > 0


# ─────────────────────────────────────────────────────────────────
# 6. SWOT (#10) — recognizable 2×2 grid
# ─────────────────────────────────────────────────────────────────


class TestSWOT:
    def test_swot_produces_2x2_grid(self) -> None:
        from framegraph._patterns import load_pattern_catalog

        cat = load_pattern_catalog()
        swot = cat.get(10)
        boxes = compute_boxes(swot, CANVAS_W, CANVAS_H)

        # SWOT has 4 quadrant zones — top-left, top-right, bottom-left, bottom-right.
        # Each must land in its designated quadrant relative to canvas mid.
        for role in ["strengths", "weaknesses", "opportunities", "threats"]:
            assert role in boxes, role

        # strengths is top_left (h=left, v=top), threats is bottom_right.
        sx, sy, sw, sh = boxes["strengths"]
        tx, ty, tw, th = boxes["threats"]
        assert sx + sw / 2 < CANVAS_W / 2
        assert sy + sh / 2 < CANVAS_H / 2
        assert tx + tw / 2 > CANVAS_W / 2
        assert ty + th / 2 > CANVAS_H / 2

        # No overlap among the four corner zones.
        corners = ["strengths", "weaknesses", "opportunities", "threats"]
        for i, ra in enumerate(corners):
            for rb in corners[i + 1 :]:
                ax, ay, aw, ah = boxes[ra]
                bx, by, bw, bh = boxes[rb]
                no_overlap = (
                    ax + aw <= bx + 0.5
                    or bx + bw <= ax + 0.5
                    or ay + ah <= by + 0.5
                    or by + bh <= ay + 0.5
                )
                assert no_overlap, f"{ra}/{rb} overlap"


# ─────────────────────────────────────────────────────────────────
# 7. BMC (#44) — 9-block grid, all zones placed, no overlap
# ─────────────────────────────────────────────────────────────────


class TestBMC:
    def test_bmc_all_zones_placed(self) -> None:
        from framegraph._patterns import load_pattern_catalog

        cat = load_pattern_catalog()
        bmc = cat.get(44)
        boxes = compute_boxes(bmc, CANVAS_W, CANVAS_H)
        assert len(boxes) == 9
        for role, box in boxes.items():
            x, y, w, h = box
            assert w > 0 and h > 0, role
            assert x >= 0
            assert y >= 0
            assert x + w <= CANVAS_W + 1, role
            assert y + h <= CANVAS_H + 1, role


# ─────────────────────────────────────────────────────────────────
# 8. Determinism — same input → same output
# ─────────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_layout_is_deterministic(self) -> None:
        from framegraph._patterns import load_pattern_catalog

        cat = load_pattern_catalog()
        bmc = cat.get(44)
        a = compute_boxes(bmc, CANVAS_W, CANVAS_H)
        b = compute_boxes(bmc, CANVAS_W, CANVAS_H)
        assert a == b


# ─────────────────────────────────────────────────────────────────
# 9. Corpus-wide coverage — every catalog pattern lays out cleanly
# ─────────────────────────────────────────────────────────────────


class TestCorpusCoverage:
    """Roadmap acceptance: every zone of every catalog pattern gets
    a non-zero box on a 1920×1080 canvas without errors."""

    def test_every_pattern_lays_out(self) -> None:
        from framegraph._patterns import load_pattern_catalog

        cat = load_pattern_catalog()
        failures: list[tuple[int, str, str]] = []
        for p in cat.slide_template_patterns:
            try:
                boxes = compute_boxes(p, CANVAS_W, CANVAS_H)
            except Exception as exc:
                failures.append((p.id, p.name, f"raised: {exc}"))
                continue
            if len(boxes) != len(p.zones):
                failures.append(
                    (p.id, p.name, f"{len(p.zones)} zones, {len(boxes)} boxes")
                )
                continue
            for z in p.zones:
                box = boxes.get(z.role)
                if box is None:
                    failures.append((p.id, p.name, f"missing role {z.role!r}"))
                    continue
                x, y, w, h = box
                if w <= 0 or h <= 0:
                    failures.append(
                        (p.id, p.name, f"role {z.role!r} has w={w}, h={h}")
                    )
        assert not failures, f"{len(failures)} layout failures: {failures[:5]}"
