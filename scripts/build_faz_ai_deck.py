"""Generate a complete FrameGraph deck from `faz-ai-spec.json`.

The script reads the formal-specification JSON workbook, inspects the
9 sections + their contained primitives, and emits a presentation
deck (`output/faz-ai-deck.yml`) plus per-slide SVGs (`output/`) by
running the deck through `FrameGraphDeckRenderer`.

Run from repo root:

    .venv/bin/python scripts/build_faz_ai_deck.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO / "faz-ai-spec.json"
OUTPUT_DIR = REPO / "output" / "faz-ai-deck"
DECK_YML = REPO / "output" / "faz-ai-deck.yml"


# ── Spec loader ───────────────────────────────────────────────────────


def load_spec() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return `(workbook, primitives, contains)` from the JSON spec."""
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    primitives: dict[str, Any] = spec["primitives"]
    relations: dict[str, Any] = spec["relations"]

    contains: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for rel in relations.values():
        if rel["type_id"] == "fs:ContainedIn":
            order = rel.get("field_values", {}).get("order", 999)
            contains[rel["target_id"]].append((order, rel["source_id"]))
    for parent in contains:
        contains[parent].sort()

    return spec["workbook"], primitives, contains


def section_children(
    section_id: str,
    primitives: dict[str, Any],
    contains: dict[str, list[tuple[int, str]]],
    type_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return the contained primitives for a section in declared order."""
    out: list[dict[str, Any]] = []
    for _order, child_id in contains.get(section_id, []):
        child = primitives.get(child_id)
        if child is None:
            continue
        if type_filter and child["type_id"] != type_filter:
            continue
        out.append(child)
    return out


# ── Deck-level chrome (header + footer + page number) ───────────────────


CANVAS_W = 960
CANVAS_H = 540
LEFT = 56
RIGHT = CANVAS_W - 56
TOP_RULE_Y = 48
FOOTER_Y = CANVAS_H - 28


def chrome_objects(
    *,
    slide_num: str,
    eyebrow: str,
    title: str,
) -> list[dict[str, Any]]:
    """Return the standard chrome layer (top rule, eyebrow, title, footer)."""
    return [
        # background
        {
            "type": "rect",
            "id": "bg",
            "decorative": True,
            "box": [0, 0, CANVAS_W, CANVAS_H],
            "fill": "slide_bg",
        },
        # top accent rule
        {
            "type": "rect",
            "id": "top_rule",
            "decorative": True,
            "box": [0, 0, CANVAS_W, 4],
            "fill": "accent",
        },
        # eyebrow
        {
            "type": "text",
            "id": "eyebrow",
            "decorative": True,
            "box": [LEFT, 14, RIGHT - LEFT, 16],
            "text": eyebrow,
            "style": "eyebrow",
        },
        # title
        {
            "type": "text",
            "id": "title",
            "decorative": True,
            "box": [LEFT, 32, RIGHT - LEFT, 30],
            "text": title,
            "style": "slide_title",
        },
        # title rule
        {
            "type": "line",
            "id": "title_rule",
            "decorative": True,
            "from": [LEFT, 70],
            "to": [RIGHT, 70],
            "stroke": {"color": "chrome_line", "width": 0.5},
        },
        # footer rule
        {
            "type": "line",
            "id": "footer_rule",
            "decorative": True,
            "from": [LEFT, FOOTER_Y - 4],
            "to": [RIGHT, FOOTER_Y - 4],
            "stroke": {"color": "chrome_line", "width": 0.5},
        },
        # brand
        {
            "type": "text",
            "id": "brand",
            "decorative": True,
            "box": [LEFT, FOOTER_Y, 200, 14],
            "text": "faz.ai · Manifesto v0.2",
            "style": "chrome_brand",
        },
        # page num
        {
            "type": "text",
            "id": "pgnum",
            "decorative": True,
            "box": [RIGHT - 80, FOOTER_Y, 80, 14],
            "text": slide_num,
            "style": "chrome_num",
        },
    ]


# ── Slide builders ────────────────────────────────────────────────────


def slide_cover(workbook: dict[str, Any]) -> dict[str, Any]:
    """Slide 1 — cover."""
    objs = [
        {
            "type": "rect",
            "id": "bg",
            "decorative": True,
            "box": [0, 0, CANVAS_W, CANVAS_H],
            "fill": "primary",
        },
        {
            "type": "rect",
            "id": "accent_band",
            "decorative": True,
            "box": [0, 0, CANVAS_W, 6],
            "fill": "accent",
        },
        {
            "type": "text",
            "id": "eyebrow",
            "decorative": True,
            "box": [LEFT, 124, RIGHT - LEFT, 18],
            "text": "Formal Specification",
            "style": "cover_eyebrow",
        },
        {
            "type": "text",
            "id": "title",
            "decorative": True,
            "box": [LEFT, 162, RIGHT - LEFT, 92],
            "text": workbook.get("name", "faz.ai Core"),
            "style": "cover_title",
        },
        {
            "type": "line",
            "id": "div",
            "decorative": True,
            "from": [LEFT, 282],
            "to": [LEFT + 80, 282],
            "stroke": {"color": "accent", "width": 3},
        },
        {
            "type": "text",
            "id": "subtitle",
            "decorative": True,
            "box": [LEFT, 304, RIGHT - LEFT, 80],
            "text": (workbook.get("description") or "")[:280],
            "style": "cover_subtitle",
        },
        {
            "type": "text",
            "id": "footer",
            "decorative": True,
            "box": [LEFT, FOOTER_Y, RIGHT - LEFT, 14],
            "text": (
                f"Profile {workbook.get('profile_id', '?')} · "
                f"Revision {workbook.get('revision', '?')} · "
                f"{workbook.get('created_at', '')[:10]}"
            ),
            "style": "cover_footer",
        },
    ]
    return {
        "slide": 1,
        "id": "s01_cover",
        "title": workbook.get("name", "faz.ai Core"),
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_toc(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Slide 2 — table of contents."""
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="02 / 12",
        eyebrow="Table of Contents",
        title="Nine Sections, One Commitment",
    )
    # 9 entries in 3 columns × 3 rows
    col_w = (RIGHT - LEFT - 32) // 3
    row_h = 110
    grid_top = 100
    for i, sec in enumerate(sections):
        col = i % 3
        row = i // 3
        x = LEFT + col * (col_w + 16)
        y = grid_top + row * (row_h + 16)
        num = sec["field_values"].get("number", i + 1)
        title = sec["field_values"].get("title", "")
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"toc_card_{i}_bg",
                    "box": [x, y, col_w, row_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                    "radius": 4,
                },
                {
                    "type": "text",
                    "id": f"toc_card_{i}_num",
                    "box": [x + 12, y + 10, 36, 28],
                    "text": f"{num:02d}",
                    "style": "toc_num",
                },
                {
                    "type": "text",
                    "id": f"toc_card_{i}_title",
                    "box": [x + 12, y + 44, col_w - 24, 56],
                    "text": title,
                    "style": "toc_title",
                },
            ]
        )
    return {
        "slide": 2,
        "id": "s02_toc",
        "title": "Contents",
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_diagnostic(section: dict[str, Any]) -> dict[str, Any]:
    """Slide 3 — section 1: three measured findings as stat cards."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="03 / 12",
        eyebrow=f"§{fv['number']} · Diagnostic",
        title=fv["title"],
    )
    # Description as a lede
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 32],
            "text": "Three measured findings establish the world the Core refuses to accept.",
            "style": "lede",
        }
    )
    # Three stat cards
    findings = [
        ("47s", "Average focused attention", "before context switch", "Mark, UC Irvine 2023"),
        ("95%", "Of enterprise AI pilots", "without measurable ROI", "MIT NANDA 2025"),
        ("19%", "Developer slowdown with AI", "while believing they were 20% faster", "METR 2025"),
    ]
    card_w = (RIGHT - LEFT - 32) // 3
    card_y = 142
    card_h = 280
    for i, (stat, label, sub, source) in enumerate(findings):
        x = LEFT + i * (card_w + 16)
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"card_{i}_bg",
                    "box": [x, card_y, card_w, card_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                    "radius": 4,
                },
                {
                    "type": "rect",
                    "id": f"card_{i}_accent",
                    "box": [x, card_y, card_w, 4],
                    "fill": "accent_warm",
                },
                {
                    "type": "text",
                    "id": f"card_{i}_stat",
                    "box": [x + 16, card_y + 28, card_w - 32, 84],
                    "text": stat,
                    "style": "stat_huge",
                },
                {
                    "type": "text",
                    "id": f"card_{i}_label",
                    "box": [x + 16, card_y + 122, card_w - 32, 32],
                    "text": label,
                    "style": "stat_label",
                },
                {
                    "type": "text",
                    "id": f"card_{i}_sub",
                    "box": [x + 16, card_y + 158, card_w - 32, 56],
                    "text": sub,
                    "style": "stat_sub",
                },
                {
                    "type": "text",
                    "id": f"card_{i}_source",
                    "box": [x + 16, card_y + card_h - 36, card_w - 32, 14],
                    "text": source,
                    "style": "stat_source",
                },
            ]
        )
    # Synthesis bar
    objs.extend(
        [
            {
                "type": "rect",
                "id": "synth_bg",
                "box": [LEFT, card_y + card_h + 12, RIGHT - LEFT, 38],
                "fill": "primary",
            },
            {
                "type": "text",
                "id": "synth_text",
                "box": [LEFT + 16, card_y + card_h + 22, RIGHT - LEFT - 32, 22],
                "text": "Synthesis: fragmented attention is now the default state of knowledge work.",
                "style": "synth",
            },
        ]
    )
    return {
        "slide": 3,
        "id": "s03_diagnostic",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def _principle_card(
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    idx: int,
    statement: str,
    name: str,
) -> list[dict[str, Any]]:
    """Pill-style principle card."""
    return [
        {
            "type": "rect",
            "id": f"p{idx}_bg",
            "box": [x, y, w, h],
            "fill": "panel_bg",
            "stroke": {"color": "chrome_line", "width": 0.5},
            "radius": 6,
        },
        {"type": "rect", "id": f"p{idx}_band", "box": [x, y, 4, h], "fill": "accent_warm"},
        {
            "type": "text",
            "id": f"p{idx}_name",
            "box": [x + 18, y + 14, w - 36, 18],
            "text": name,
            "style": "principle_name",
        },
        {
            "type": "text",
            "id": f"p{idx}_statement",
            "box": [x + 18, y + 38, w - 36, h - 56],
            "text": statement,
            "style": "principle_body",
        },
    ]


def slide_rejection(
    section: dict[str, Any],
    primitives: dict[str, Any],
    contains: dict[str, list[tuple[int, str]]],
) -> dict[str, Any]:
    """Slide 4 — section 2: three principle cards."""
    fv = section["field_values"]
    principles = section_children(section["id"], primitives, contains, type_filter="fs:Principle")
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="04 / 12",
        eyebrow=f"§{fv['number']} · Rejection",
        title=fv["title"],
    )
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 36],
            "text": (
                "Three explicit refusals. Each is structurally incompatible with "
                "the business models of foundation-model providers."
            ),
            "style": "lede",
        }
    )
    card_w = (RIGHT - LEFT - 32) // 3
    card_y = 138
    card_h = 320
    for i, p in enumerate(principles[:3]):
        x = LEFT + i * (card_w + 16)
        objs.extend(
            _principle_card(
                x=x,
                y=card_y,
                w=card_w,
                h=card_h,
                idx=i,
                name=p["field_values"]["name"],
                statement=p["field_values"].get("statement", ""),
            )
        )
    return {
        "slide": 4,
        "id": "s04_rejection",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_reframe(section: dict[str, Any]) -> dict[str, Any]:
    """Slide 5 — section 3: workforce-vs-achievement reframe."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="05 / 12",
        eyebrow=f"§{fv['number']} · Reframe",
        title=fv["title"],
    )
    # Two columns side by side
    col_w = (RIGHT - LEFT - 24) // 2
    col_y = 100
    col_h = 360
    # Left — what most products do
    objs.extend(
        [
            {
                "type": "rect",
                "id": "before_bg",
                "box": [LEFT, col_y, col_w, col_h],
                "fill": "panel_bg",
                "stroke": {"color": "chrome_line", "width": 0.5},
                "radius": 4,
            },
            {
                "type": "text",
                "id": "before_label",
                "box": [LEFT + 16, col_y + 14, col_w - 32, 16],
                "text": "MOST AI PRODUCTS",
                "style": "compare_label_dim",
            },
            {
                "type": "text",
                "id": "before_headline",
                "box": [LEFT + 16, col_y + 36, col_w - 32, 48],
                "text": "Workforce is the product.",
                "style": "compare_headline_dim",
            },
            {
                "type": "text",
                "id": "before_body",
                "box": [LEFT + 16, col_y + 96, col_w - 32, col_h - 116],
                "text": (
                    "Hire AI to do tasks. Success = throughput captured. "
                    "More usage is the goal.\n\n"
                    "DAU, time-spent, sessions per day — these are the KPIs. "
                    "The product is selling more of itself."
                ),
                "style": "compare_body_dim",
            },
        ]
    )
    # Right — the Core's inversion
    x2 = LEFT + col_w + 24
    objs.extend(
        [
            {"type": "rect", "id": "after_bg", "box": [x2, col_y, col_w, col_h], "fill": "primary"},
            {"type": "rect", "id": "after_band", "box": [x2, col_y, 4, col_h], "fill": "accent"},
            {
                "type": "text",
                "id": "after_label",
                "box": [x2 + 16, col_y + 14, col_w - 32, 16],
                "text": "THE CORE INVERTS THIS",
                "style": "compare_label",
            },
            {
                "type": "text",
                "id": "after_headline",
                "box": [x2 + 16, col_y + 36, col_w - 32, 48],
                "text": "Achievement is the product.",
                "style": "compare_headline",
            },
            {
                "type": "text",
                "id": "after_body",
                "box": [x2 + 16, col_y + 96, col_w - 32, col_h - 116],
                "text": (
                    "Workforce is a tier mechanic: Solo · Operator · Team · Portfolio.\n\n"
                    "Success measured in cognition offloaded, not throughput captured. "
                    "The product disappears into outcomes."
                ),
                "style": "compare_body",
            },
        ]
    )
    return {
        "slide": 5,
        "id": "s05_reframe",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_commitments(
    section: dict[str, Any],
    primitives: dict[str, Any],
    contains: dict[str, list[tuple[int, str]]],
) -> dict[str, Any]:
    """Slide 6 — section 4: 4 constitutional commitments grid."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="06 / 12",
        eyebrow=f"§{fv['number']} · Constitutional",
        title=fv["title"],
    )
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 32],
            "text": "The four commitments only the Core can make.",
            "style": "lede",
        }
    )
    commitments = [
        (
            "01",
            "End-to-End Encryption",
            "No training without consent. The user's life is not training data.",
        ),
        (
            "02",
            "Anti-Engagement UX",
            "UI_RESTING and UI_DEPLETED ship as flagship states. The product permits stopping.",
        ),
        (
            "03",
            "Work-Life Merge",
            "One cognitive space. Not two apps, not two voices. One Core that knows the whole life.",
        ),
        ("04", "Refusal as Feature", "AI says No. No is No. The cascade does not relent."),
    ]
    card_w = (RIGHT - LEFT - 16) // 2
    card_h = 158
    grid_y = 138
    for i, (num, label, body) in enumerate(commitments):
        col = i % 2
        row = i // 2
        x = LEFT + col * (card_w + 16)
        y = grid_y + row * (card_h + 16)
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"c{i}_bg",
                    "box": [x, y, card_w, card_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                    "radius": 4,
                },
                {
                    "type": "text",
                    "id": f"c{i}_num",
                    "box": [x + 16, y + 14, 32, 24],
                    "text": num,
                    "style": "commit_num",
                },
                {
                    "type": "line",
                    "id": f"c{i}_div",
                    "from": [x + 56, y + 18],
                    "to": [x + 56, y + 38],
                    "stroke": {"color": "accent_warm", "width": 2},
                },
                {
                    "type": "text",
                    "id": f"c{i}_label",
                    "box": [x + 64, y + 14, card_w - 80, 24],
                    "text": label,
                    "style": "commit_label",
                },
                {
                    "type": "text",
                    "id": f"c{i}_body",
                    "box": [x + 16, y + 50, card_w - 32, card_h - 64],
                    "text": body,
                    "style": "commit_body",
                },
            ]
        )
    return {
        "slide": 6,
        "id": "s06_commitments",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_relationship(
    section: dict[str, Any],
    primitives: dict[str, Any],
) -> dict[str, Any]:
    """Slide 7 — section 5: User / Core / Workers three-layer diagram."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="07 / 12",
        eyebrow=f"§{fv['number']} · Structure",
        title=fv["title"],
    )
    user = primitives.get("def:User", {}).get("field_values", {})
    core = primitives.get("def:Core", {}).get("field_values", {})
    worker = primitives.get("def:Worker", {}).get("field_values", {})
    layers = [
        (
            "Layer 1",
            "User",
            user.get("formal", ""),
            "Holds agency. Can fire any Worker, can cancel the relationship.\nCannot fire the Core, by design.",
            "agentive",
        ),
        (
            "Layer 2",
            "Core",
            core.get("formal", ""),
            "Constitutional. Non-fireable. Composed of Observer, Advisor, Coordinator.\nCommitments fixed; not configurable per user.",
            "constitutional",
        ),
        (
            "Layer 3",
            "Worker",
            worker.get("formal", ""),
            "Replaceable. Each has identity, voice, memory, and ethical limits.\nFired and replaced when judgment doesn't fit.",
            "replaceable",
        ),
    ]
    band_h = 116
    band_gap = 8
    band_y_start = 96
    fills = ["primary", "accent_warm", "panel_dark"]
    for i, (layer_label, name, _formal, body, kind_label) in enumerate(layers):
        y = band_y_start + i * (band_h + band_gap)
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"l{i}_bg",
                    "box": [LEFT, y, RIGHT - LEFT, band_h],
                    "fill": fills[i],
                },
                {
                    "type": "text",
                    "id": f"l{i}_layer",
                    "box": [LEFT + 18, y + 14, 90, 16],
                    "text": layer_label,
                    "style": "layer_label",
                },
                {
                    "type": "text",
                    "id": f"l{i}_name",
                    "box": [LEFT + 18, y + 36, 200, 36],
                    "text": name,
                    "style": "layer_name",
                },
                {
                    "type": "text",
                    "id": f"l{i}_kind",
                    "box": [LEFT + 18, y + 80, 220, 18],
                    "text": kind_label.upper(),
                    "style": "layer_kind",
                },
                {
                    "type": "text",
                    "id": f"l{i}_body",
                    "box": [LEFT + 240, y + 18, RIGHT - LEFT - 256, band_h - 32],
                    "text": body,
                    "style": "layer_body",
                },
            ]
        )
    return {
        "slide": 7,
        "id": "s07_structure",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_cascade(
    section: dict[str, Any],
    primitives: dict[str, Any],
) -> dict[str, Any]:
    """Slide 8 — section 6: refusal cascade × tiers matrix."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="08 / 12",
        eyebrow=f"§{fv['number']} · Cascade",
        title=fv["title"],
    )
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 32],
            "text": "Four cascade layers · three refusal tiers. The system does not soften, does not relent.",
            "style": "lede",
        }
    )
    # 4 cascade layers as rows
    layers = [
        ("def:CascadeLayer1", "1", "No to a request"),
        ("def:CascadeLayer2", "2", "No to a pattern"),
        ("def:CascadeLayer3", "3", "No to a decision"),
        ("def:CascadeLayer4", "4", "No to itself"),
    ]
    grid_y = 142
    row_h = 56
    num_w = 40
    label_w = 180
    body_x = LEFT + num_w + label_w + 16
    body_w = RIGHT - body_x
    for i, (def_id, num, short) in enumerate(layers):
        d = primitives.get(def_id, {}).get("field_values", {})
        y = grid_y + i * (row_h + 6)
        # number bubble
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"r{i}_num_bg",
                    "box": [LEFT, y, num_w, row_h],
                    "fill": "primary",
                },
                {
                    "type": "text",
                    "id": f"r{i}_num",
                    "box": [LEFT, y + 14, num_w, 28],
                    "text": num,
                    "style": "cascade_num",
                },
                # short label
                {
                    "type": "rect",
                    "id": f"r{i}_label_bg",
                    "box": [LEFT + num_w, y, label_w, row_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                },
                {
                    "type": "text",
                    "id": f"r{i}_label",
                    "box": [LEFT + num_w + 12, y + 12, label_w - 24, 18],
                    "text": short,
                    "style": "cascade_short",
                },
                {
                    "type": "text",
                    "id": f"r{i}_informal",
                    "box": [LEFT + num_w + 12, y + 32, label_w - 24, 18],
                    "text": d.get("informal", "")[:48],
                    "style": "cascade_informal",
                },
                # body
                {
                    "type": "rect",
                    "id": f"r{i}_body_bg",
                    "box": [body_x, y, body_w, row_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                },
                {
                    "type": "text",
                    "id": f"r{i}_body",
                    "box": [body_x + 12, y + 8, body_w - 24, row_h - 16],
                    "text": d.get("formal", "")[:240],
                    "style": "cascade_body",
                },
            ]
        )
    # 3 tier badges as a strip
    tiers = [
        ("def:Tier1_Soft", "Tier 1", "Soft + Waiver", "panel_bg"),
        ("def:Tier2_Hard", "Tier 2", "Hard + Defer", "accent_warm"),
        ("def:Tier3_Exit", "Tier 3", "Hard + Exit", "primary"),
    ]
    strip_y = grid_y + 4 * (row_h + 6) + 12
    strip_h = 38
    badge_w = (RIGHT - LEFT - 16) // 3
    for i, (_, tnum, tlabel, fill) in enumerate(tiers):
        x = LEFT + i * (badge_w + 8)
        text_color = "primary" if fill == "panel_bg" else "white"
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"t{i}_bg",
                    "box": [x, strip_y, badge_w, strip_h],
                    "fill": fill,
                    "stroke": {"color": "chrome_line", "width": 0.5},
                },
                {
                    "type": "text",
                    "id": f"t{i}_num",
                    "box": [x + 12, strip_y + 6, 60, 14],
                    "text": tnum,
                    "style": f"tier_num_{text_color}",
                },
                {
                    "type": "text",
                    "id": f"t{i}_label",
                    "box": [x + 12, strip_y + 20, badge_w - 24, 14],
                    "text": tlabel,
                    "style": f"tier_label_{text_color}",
                },
            ]
        )
    return {
        "slide": 8,
        "id": "s08_cascade",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_voice(
    section: dict[str, Any],
    primitives: dict[str, Any],
) -> dict[str, Any]:
    """Slide 9 — section 7: 4 UI states with canonical phrasings."""
    fv = section["field_values"]
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="09 / 12",
        eyebrow=f"§{fv['number']} · Voice",
        title=fv["title"],
    )
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 32],
            "text": "Where every other product asks 'How can I help?' — the Core says something else.",
            "style": "lede",
        }
    )
    states = [
        (
            "def:UI_FRAGMENTED_DEFAULT",
            "FRAGMENTED",
            "Three threads in flight. faz is keeping context warm.",
        ),
        ("def:UI_DEPLETED", "DEPLETED", "You've done enough thinking today."),
        ("def:UI_RESTING", "RESTING", "faz is working. You are resting."),
        ("def:UI_OVERLOADED", "OVERLOADED", "Take a breath. faz triaged the rest."),
    ]
    card_w = (RIGHT - LEFT - 16) // 2
    card_h = 156
    grid_y = 138
    for i, (def_id, label, quote) in enumerate(states):
        d = primitives.get(def_id, {}).get("field_values", {})
        col = i % 2
        row = i // 2
        x = LEFT + col * (card_w + 16)
        y = grid_y + row * (card_h + 16)
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"u{i}_bg",
                    "box": [x, y, card_w, card_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                    "radius": 4,
                },
                {
                    "type": "rect",
                    "id": f"u{i}_band",
                    "box": [x, y, 4, card_h],
                    "fill": "accent_warm",
                },
                {
                    "type": "text",
                    "id": f"u{i}_label",
                    "box": [x + 18, y + 14, card_w - 36, 16],
                    "text": f"UI · {label}",
                    "style": "ui_label",
                },
                {
                    "type": "text",
                    "id": f"u{i}_quote",
                    "box": [x + 18, y + 38, card_w - 36, 56],
                    "text": f"“{quote}”",
                    "style": "ui_quote",
                },
                {
                    "type": "text",
                    "id": f"u{i}_gloss",
                    "box": [x + 18, y + 100, card_w - 36, card_h - 112],
                    "text": d.get("informal", "")[:160],
                    "style": "ui_gloss",
                },
            ]
        )
    return {
        "slide": 9,
        "id": "s09_voice",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_taboos(
    section: dict[str, Any],
    primitives: dict[str, Any],
    contains: dict[str, list[tuple[int, str]]],
) -> dict[str, Any]:
    """Slide 10 — section 8: 6 invariants enforced as cultural commitments."""
    fv = section["field_values"]
    invariants = section_children(section["id"], primitives, contains, type_filter="fs:Invariant")
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="10 / 12",
        eyebrow=f"§{fv['number']} · Taboos",
        title=fv["title"],
    )
    objs.append(
        {
            "type": "text",
            "id": "lede",
            "box": [LEFT, 86, RIGHT - LEFT, 32],
            "text": "Six refusals enforced at every quarterly product review. The cultural enforcement IS the work.",
            "style": "lede",
        }
    )
    grid_y = 138
    item_h = 50
    item_gap = 6
    for i, inv in enumerate(invariants[:6]):
        ifv = inv["field_values"]
        y = grid_y + i * (item_h + item_gap)
        name = ifv.get("name", "")
        statement = ifv.get("statement", "")
        objs.extend(
            [
                {
                    "type": "rect",
                    "id": f"inv{i}_bg",
                    "box": [LEFT, y, RIGHT - LEFT, item_h],
                    "fill": "panel_bg",
                    "stroke": {"color": "chrome_line", "width": 0.5},
                },
                {
                    "type": "rect",
                    "id": f"inv{i}_band",
                    "box": [LEFT, y, 6, item_h],
                    "fill": "danger",
                },
                # NO badge
                {
                    "type": "text",
                    "id": f"inv{i}_badge",
                    "box": [LEFT + 18, y + 18, 36, 14],
                    "text": "NO ·",
                    "style": "taboo_badge",
                },
                {
                    "type": "text",
                    "id": f"inv{i}_name",
                    "box": [LEFT + 60, y + 8, 320, 16],
                    "text": name,
                    "style": "taboo_name",
                },
                {
                    "type": "text",
                    "id": f"inv{i}_statement",
                    "box": [LEFT + 60, y + 26, RIGHT - LEFT - 80, item_h - 30],
                    "text": statement[:200],
                    "style": "taboo_statement",
                },
            ]
        )
    return {
        "slide": 10,
        "id": "s10_taboos",
        "title": fv["title"],
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_closing(
    section: dict[str, Any],
    primitives: dict[str, Any],
) -> dict[str, Any]:
    """Slide 11 — section 9: the single-sentence closing commitment."""
    fv = section["field_values"]
    decision = primitives.get("decision:say-no", {}).get("field_values", {})
    sentence = decision.get(
        "decision_text",
        "I will model the AI to say No.",
    )
    objs: list[dict[str, Any]] = [
        {
            "type": "rect",
            "id": "bg",
            "decorative": True,
            "box": [0, 0, CANVAS_W, CANVAS_H],
            "fill": "primary",
        },
        {
            "type": "rect",
            "id": "accent_band",
            "decorative": True,
            "box": [0, 0, CANVAS_W, 6],
            "fill": "accent",
        },
        {
            "type": "text",
            "id": "eyebrow",
            "decorative": True,
            "box": [LEFT, 80, RIGHT - LEFT, 16],
            "text": f"§{fv['number']} · Closing Commitment",
            "style": "closing_eyebrow",
        },
        {
            "type": "text",
            "id": "label",
            "decorative": True,
            "box": [LEFT, 116, RIGHT - LEFT, 18],
            "text": "THE SENTENCE THAT DRIVES EVERY PRODUCT DECISION FOR TEN YEARS",
            "style": "closing_label",
        },
        # The single sentence — large, centered
        {
            "type": "text",
            "id": "the_sentence",
            "decorative": True,
            "box": [LEFT, 188, RIGHT - LEFT, 120],
            "text": f"“{sentence}”",
            "style": "closing_sentence",
        },
        {
            "type": "line",
            "id": "div",
            "decorative": True,
            "from": [CANVAS_W // 2 - 40, 332],
            "to": [CANVAS_W // 2 + 40, 332],
            "stroke": {"color": "accent", "width": 2},
        },
        {
            "type": "text",
            "id": "rule",
            "decorative": True,
            "box": [LEFT, 350, RIGHT - LEFT, 64],
            "text": (
                "Defended at every quarterly review for the next ten years. "
                "If you cannot defend it on a Monday in 2036, do not ship it."
            ),
            "style": "closing_rule",
        },
        {
            "type": "text",
            "id": "footer",
            "decorative": True,
            "box": [LEFT, FOOTER_Y, RIGHT - LEFT, 14],
            "text": "11 / 12 · faz.ai · Manifesto v0.2",
            "style": "closing_footer",
        },
    ]
    return {
        "slide": 11,
        "id": "s11_closing",
        "title": "Closing Commitment",
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


def slide_colophon(workbook: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    """Slide 12 — colophon with provenance + counts."""
    objs: list[dict[str, Any]] = chrome_objects(
        slide_num="12 / 12",
        eyebrow="Colophon",
        title="Provenance",
    )
    rows = [
        ("Workbook", workbook.get("name", "")),
        ("ID", workbook.get("id", "")),
        ("Profile", workbook.get("profile_id", "")),
        ("Revision", str(workbook.get("revision", ""))),
        ("Created", workbook.get("created_at", "")[:19].replace("T", " ")),
        ("Primitives", str(counts.get("primitives", "?"))),
        ("Relations", str(counts.get("relations", "?"))),
        ("Source", "faz-ai-spec.json"),
    ]
    grid_y = 110
    row_h = 38
    label_w = 120
    for i, (label, value) in enumerate(rows):
        y = grid_y + i * row_h
        objs.extend(
            [
                {
                    "type": "text",
                    "id": f"col_{i}_label",
                    "box": [LEFT, y + 8, label_w, 18],
                    "text": label.upper(),
                    "style": "colophon_label",
                },
                {
                    "type": "text",
                    "id": f"col_{i}_value",
                    "box": [LEFT + label_w + 16, y + 8, RIGHT - LEFT - label_w - 16, 18],
                    "text": value,
                    "style": "colophon_value",
                },
                {
                    "type": "line",
                    "id": f"col_{i}_rule",
                    "from": [LEFT, y + row_h],
                    "to": [RIGHT, y + row_h],
                    "stroke": {"color": "chrome_line", "width": 0.5},
                },
            ]
        )
    objs.append(
        {
            "type": "text",
            "id": "tagline",
            "decorative": True,
            "box": [LEFT, FOOTER_Y - 32, RIGHT - LEFT, 16],
            "text": "Generated from the formal specification by FrameGraph.",
            "style": "colophon_tagline",
        }
    )
    return {
        "slide": 12,
        "id": "s12_colophon",
        "title": "Colophon",
        "visual": {"layers": [{"id": "content", "objects": objs}]},
    }


# ── Deck assembly ─────────────────────────────────────────────────────


def text_styles() -> dict[str, dict[str, Any]]:
    """Define all text styles the deck uses."""
    return {
        # chrome
        "eyebrow": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "slide_title": {
            "font": "primary",
            "size": 22,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        "chrome_brand": {
            "font": "primary",
            "size": 9,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        "chrome_num": {
            "font": "primary",
            "size": 9,
            "weight": 400,
            "color": "text_muted",
            "align": "right",
        },
        "lede": {
            "font": "primary",
            "size": 13,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 18,
        },
        # cover
        "cover_eyebrow": {
            "font": "primary",
            "size": 11,
            "weight": 700,
            "color": "accent",
            "align": "left",
        },
        "cover_title": {
            "font": "primary",
            "size": 38,
            "weight": 700,
            "color": "white",
            "align": "left",
            "line_height": 46,
            "wrap": True,
        },
        "cover_subtitle": {
            "font": "primary",
            "size": 13,
            "weight": 400,
            "color": "text_muted_light",
            "align": "left",
            "line_height": 20,
            "wrap": True,
        },
        "cover_footer": {
            "font": "primary",
            "size": 9,
            "weight": 400,
            "color": "text_muted_light",
            "align": "left",
        },
        # toc
        "toc_num": {
            "font": "primary",
            "size": 22,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "toc_title": {
            "font": "primary",
            "size": 12,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 16,
            "wrap": True,
        },
        # diagnostic stat cards
        "stat_huge": {
            "font": "primary",
            "size": 60,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 70,
        },
        "stat_label": {
            "font": "primary",
            "size": 13,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 18,
            "wrap": True,
        },
        "stat_sub": {
            "font": "primary",
            "size": 11,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 16,
            "wrap": True,
        },
        "stat_source": {
            "font": "primary",
            "size": 9,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "italic": True,
        },
        "synth": {
            "font": "primary",
            "size": 12,
            "weight": 700,
            "color": "white",
            "align": "left",
            "line_height": 16,
        },
        # principle cards
        "principle_name": {
            "font": "primary",
            "size": 11,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "principle_body": {
            "font": "primary",
            "size": 13,
            "weight": 400,
            "color": "primary",
            "align": "left",
            "line_height": 19,
            "wrap": True,
        },
        # reframe (compare)
        "compare_label": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "accent",
            "align": "left",
        },
        "compare_label_dim": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "text_muted",
            "align": "left",
        },
        "compare_headline": {
            "font": "primary",
            "size": 26,
            "weight": 700,
            "color": "white",
            "align": "left",
            "line_height": 32,
            "wrap": True,
        },
        "compare_headline_dim": {
            "font": "primary",
            "size": 26,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 32,
            "wrap": True,
        },
        "compare_body": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "text_muted_light",
            "align": "left",
            "line_height": 18,
            "wrap": True,
        },
        "compare_body_dim": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 18,
            "wrap": True,
        },
        # commitments
        "commit_num": {
            "font": "primary",
            "size": 22,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "commit_label": {
            "font": "primary",
            "size": 14,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 20,
            "wrap": True,
        },
        "commit_body": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 17,
            "wrap": True,
        },
        # relationship layers
        "layer_label": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "accent",
            "align": "left",
        },
        "layer_name": {
            "font": "primary",
            "size": 26,
            "weight": 700,
            "color": "white",
            "align": "left",
        },
        "layer_kind": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "text_muted_light",
            "align": "left",
        },
        "layer_body": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "text_muted_light",
            "align": "left",
            "line_height": 17,
            "wrap": True,
        },
        # cascade
        "cascade_num": {
            "font": "primary",
            "size": 22,
            "weight": 700,
            "color": "white",
            "align": "center",
        },
        "cascade_short": {
            "font": "primary",
            "size": 12,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        "cascade_informal": {
            "font": "primary",
            "size": 10,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
        },
        "cascade_body": {
            "font": "primary",
            "size": 10,
            "weight": 400,
            "color": "primary",
            "align": "left",
            "line_height": 14,
            "wrap": True,
        },
        "tier_num_white": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "white",
            "align": "left",
        },
        "tier_label_white": {
            "font": "primary",
            "size": 13,
            "weight": 700,
            "color": "white",
            "align": "left",
        },
        "tier_num_primary": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        "tier_label_primary": {
            "font": "primary",
            "size": 13,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        # voice / UI states
        "ui_label": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "ui_quote": {
            "font": "primary",
            "size": 17,
            "weight": 700,
            "color": "primary",
            "align": "left",
            "line_height": 24,
            "italic": True,
            "wrap": True,
        },
        "ui_gloss": {
            "font": "primary",
            "size": 11,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 16,
            "wrap": True,
        },
        # taboos
        "taboo_badge": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "danger",
            "align": "left",
        },
        "taboo_name": {
            "font": "primary",
            "size": 12,
            "weight": 700,
            "color": "primary",
            "align": "left",
        },
        "taboo_statement": {
            "font": "primary",
            "size": 10,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "line_height": 14,
            "wrap": True,
        },
        # closing
        "closing_eyebrow": {
            "font": "primary",
            "size": 11,
            "weight": 700,
            "color": "accent",
            "align": "left",
        },
        "closing_label": {
            "font": "primary",
            "size": 11,
            "weight": 700,
            "color": "text_muted_light",
            "align": "left",
        },
        "closing_sentence": {
            "font": "primary",
            "size": 44,
            "weight": 700,
            "color": "white",
            "align": "center",
            "line_height": 56,
            "wrap": True,
        },
        "closing_rule": {
            "font": "primary",
            "size": 13,
            "weight": 400,
            "color": "text_muted_light",
            "align": "center",
            "line_height": 19,
            "wrap": True,
        },
        "closing_footer": {
            "font": "primary",
            "size": 9,
            "weight": 400,
            "color": "text_muted_light",
            "align": "left",
        },
        # colophon
        "colophon_label": {
            "font": "primary",
            "size": 10,
            "weight": 700,
            "color": "accent_warm",
            "align": "left",
        },
        "colophon_value": {
            "font": "primary",
            "size": 12,
            "weight": 400,
            "color": "primary",
            "align": "left",
        },
        "colophon_tagline": {
            "font": "primary",
            "size": 10,
            "weight": 400,
            "color": "text_muted",
            "align": "left",
            "italic": True,
        },
    }


def colors() -> dict[str, str]:
    """Deck-level color palette — high-contrast, sober."""
    return {
        "primary": "#0F172A",  # near-black ink
        "accent": "#2563EB",  # blue accent (cover band, dividers)
        "accent_warm": "#DC2626",  # the No red — used sparingly
        "danger": "#B91C1C",  # taboo red
        "panel_bg": "#F8FAFC",  # card surface
        "panel_dark": "#1F2937",  # the third layer band
        "slide_bg": "#FFFFFF",
        "chrome_line": "#CBD5E1",
        "text_muted": "#475569",
        "text_muted_light": "#CBD5E1",
        "white": "#FFFFFF",
    }


def fonts() -> dict[str, str]:
    return {
        "primary": (
            "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
        ),
    }


def build_deck() -> dict[str, Any]:
    workbook, primitives, contains = load_spec()
    spec_full = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    counts = spec_full.get("counts", {})

    # Index sections by id for slide builders.
    sections = sorted(
        (p for p in primitives.values() if p["type_id"] == "fs:Section"),
        key=lambda p: p["field_values"].get("number", 0),
    )
    sec_by_num = {s["field_values"]["number"]: s for s in sections}

    slides = [
        slide_cover(workbook),
        slide_toc(sections),
        slide_diagnostic(sec_by_num[1]),
        slide_rejection(sec_by_num[2], primitives, contains),
        slide_reframe(sec_by_num[3]),
        slide_commitments(sec_by_num[4], primitives, contains),
        slide_relationship(sec_by_num[5], primitives),
        slide_cascade(sec_by_num[6], primitives),
        slide_voice(sec_by_num[7], primitives),
        slide_taboos(sec_by_num[8], primitives, contains),
        slide_closing(sec_by_num[9], primitives),
        slide_colophon(workbook, counts),
    ]

    return {
        "dsl": "FrameGraph",
        "version": "1.2",
        "kind": "presentation-deck",
        "deck": {
            "canvas": {"size": [CANVAS_W, CANVAS_H], "units": "px"},
            "tokens": {
                "colors": colors(),
                "fonts": fonts(),
                "text_styles": text_styles(),
            },
        },
        "slides": slides,
    }


def main() -> int:
    deck = build_deck()
    DECK_YML.parent.mkdir(parents=True, exist_ok=True)
    DECK_YML.write_text(
        yaml.dump(deck, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    print(f"wrote {DECK_YML}  ({DECK_YML.stat().st_size / 1024:.1f} KB)")

    # Render via the deck renderer.
    sys.path.insert(0, str(REPO))
    from framegraph import FrameGraphDeckRenderer, FrameGraphLibrary

    lib = FrameGraphLibrary(REPO / "framegraph" / "lib")
    renderer = FrameGraphDeckRenderer(deck, library=lib)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = renderer.render_all(OUTPUT_DIR)
    print(f"\nrendered {len(paths)} slides → {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
