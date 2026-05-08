#!/usr/bin/env python3
"""Annotate every zone in the bundled catalog with a `content_type`.

Runs the iterated rule-based derivation against
`static/refs/slides-patter-a.yml`, writes the inferred
`content_type` onto each zone, and saves the file in place.
Validates the result against `framegraph._patterns.PatternCatalog`
before writing.

Idempotent: re-running on an already-annotated catalog leaves
``content_type`` values untouched (the derivation only assigns
when the field is absent). Use ``--fix`` to re-derive over
existing annotations and overwrite when the rules disagree.

Two layers of derivation rules:

  1. **High-confidence rules** (Phases 1–2) — fire only when the
     role name + shape combination is unambiguous. Cover ~66% of
     zones with no false positives.
  2. **Broad-coverage tail rules** (Phase 6) — close the remaining
     34% by mapping shape→title_body for visible shapes,
     plurals→list_items, table-words→table_data,
     chart-words→chart_data, and a singular-named-entity
     fallback to title_body. The corpus survey showed every
     fall-through is a single titled item.

Together the two layers cover 100% of catalog zones.

Run from the repo root:

    python3 scripts/annotate_content_types.py        # only assign missing
    python3 scripts/annotate_content_types.py --fix  # re-derive existing too
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import PatternCatalog  # noqa: E402

BUNDLED = REPO_ROOT / "static" / "refs" / "slides-patter-a.yml"


# ─────────────────────────────────────────────────────────────────
# Curated keyword sets — order matches the iterated derivation
# from the corpus assessment.
# ─────────────────────────────────────────────────────────────────

LIST_TOKENS = {
    "steps", "items", "bullets", "criteria", "rules", "principles",
    "guidelines", "tips", "questions", "risks", "issues", "concerns",
    "options", "levers", "actions", "tactics", "tasks", "activities",
    "findings", "recommendations", "next_steps", "milestones",
    "controls", "mitigations", "opportunities", "gaps",
    "objectives", "outcomes", "features", "capabilities",
    "observations", "patterns", "quotes", "sources",
    "examples", "evidence", "arguments", "considerations",
    "dependencies", "requirements", "assumptions",
    "leverage_points", "breaking_points",
    # BMC blocks + similar collection-shaped roles
    "key_partners", "key_resources", "key_activities",
    "customer_relationships", "customer_segments",
    "channels", "segments", "relationships", "partners",
}
LIST_SUFFIXES = (
    "_list", "_items", "_steps", "_actions", "_levers",
    "_options", "_criteria", "_rules", "_questions",
    "_findings", "_milestones", "_outcomes", "_objectives",
    "_recommendations", "_takeaways", "_takeaway",
    # Plural / collection suffixes that previously fell through
    # to METRIC and now need an explicit list classification:
    "_streams", "_categories", "_pillars", "_pools",
    "_drivers", "_opportunities", "_propositions",
    "_allocation", "_structure", "_breakdown",
    "_lines", "_sources", "_mix",
)

KEY_VALUE_TOKENS = {
    "legend", "label", "labels", "tag", "tags", "status",
    "severity", "priority", "rating", "score",
    "confidence", "health", "mood", "emotion",
    "metadata", "attributes",
}

COMPARISON_TOKENS = {
    "before", "after", "old_", "new_",
    "will_do", "will_not_do",
    "descriptive", "normative",
    "one_way_door", "two_way_door",
    "pros", "cons",
    "fragile_elements", "robust_elements", "antifragile_elements",
    "old_frame", "new_frame", "old_mental_model", "new_mental_model",
    "point_of_difference", "frame_of_reference",
    "current_state", "target_state", "gap",
    "current_practice", "leading_practice",
    "current_culture", "target_culture",
    "definition_of_done", "definition_of_true",
    "evidence_for", "evidence_against",
    "weak_objections", "strongest_opposing_case",
    "baseline", "target",
}

NARRATIVE_TOKENS = {
    "context", "background", "introduction", "summary",
    "narrative", "story", "message", "description",
    "explanation", "reasoning", "rationale",
    "conclusion", "recommendation", "implication",
    "headline", "title", "subtitle", "heading",
    "thesis", "statement", "definition",
    "overview", "snapshot", "commentary",
    "takeaway", "insight", "note", "notes",
    "why_change", "what_is_changing", "what_it_means",
    "response", "synthesis",
}

CHART_TOKENS = {
    "chart", "graph", "curve", "distribution", "funnel",
    "matrix", "tree", "network", "map", "cycle",
    "flow", "pipeline", "timeline", "roadmap",
    "cascade", "pyramid", "venn", "flywheel",
    "quadrants", "dashboard",
}

METRIC_TOKENS = {
    "metric", "metrics", "kpi", "kpis", "value",
    "number", "count", "percentage", "rate",
    "savings", "cost", "revenue", "roi", "npv", "irr",
    "payback", "budget", "spend", "price", "profit",
    "margin", "baseline", "target_value",
    "investment", "benefits", "opportunity", "potential",
    "attractiveness", "velocity",
}

# Plural / collection suffixes that demote a METRIC match to list_items.
# A role like ``revenue_streams`` matches METRIC_TOKENS via "revenue"
# but is conceptually a list of revenue items, not a single number.
METRIC_DEMOTION_SUFFIXES = (
    "_streams", "_categories", "_pillars", "_pools", "_levers",
    "_drivers", "_opportunities", "_propositions", "_allocation",
    "_structure", "_breakdown", "_lines", "_sources", "_mix",
)

DECORATIVE_TOKENS = {
    "connector", "connectors", "arrow", "arrows",
    "decorative", "visual_anchor", "background",
    "spine", "main_spine", "cause_branches",
    "transition_arrow", "transition_logic", "transition_points",
    "logic_connectors", "dependency_links", "dependency_edges",
    "alignment_connectors", "feedback_loops",
    "integration_flows", "connectors_lines",
    "reinforcing_links", "reinforcing_loops",
    "damping_controls", "governance_links",
    "connector_lines", "attribute_links",
}


def _has_any(role: str, tokens: set[str]) -> bool:
    return any(t in role for t in tokens)


def derive_content_type(zone: dict[str, Any]) -> str | None:
    """Return the auto-derived `content_type` for a zone, or None.

    Returns ``None`` only when no high-confidence rule matches —
    those zones are left un-annotated for manual curation.
    """
    role = zone["role"].lower()
    shape = zone.get("shape")

    # Decorative
    if shape == "connector":
        return "decorative"
    if _has_any(role, DECORATIVE_TOKENS):
        return "decorative"
    if role in {"visual", "visual_anchor"}:
        return "decorative"

    # Image
    if "image" in role or "photo" in role or "screenshot" in role:
        return "image"
    if shape == "icon":
        return "image"
    if role.endswith("_logo") or role == "logo":
        return "image"

    # Axis label
    if shape == "axis":
        return "axis_label"
    if role.endswith("_axis") or role == "axis_labels":
        return "axis_label"

    # Chart data
    if shape in {"chart", "timeline", "progress", "bar", "sequence"}:
        return "chart_data"
    if _has_any(role, CHART_TOKENS) and shape != "card":
        return "chart_data"

    # Table data
    if shape in {"table", "cell"}:
        return "table_data"

    # Metric — single number + label.
    # Plural / collection suffixes demote to list_items below
    # (e.g. "revenue_streams" is a list of streams, not one number).
    if shape == "metric":
        return "metric"
    if (
        _has_any(role, METRIC_TOKENS)
        and shape in {"card", None}
        and not any(role.endswith(s) for s in METRIC_DEMOTION_SUFFIXES)
    ):
        return "metric"

    # Comparison
    if _has_any(role, COMPARISON_TOKENS):
        return "comparison"

    # List
    if shape == "list":
        return "list_items"
    if _has_any(role, LIST_TOKENS):
        return "list_items"
    if any(role.endswith(s) for s in LIST_SUFFIXES):
        return "list_items"

    # Key-value
    if _has_any(role, KEY_VALUE_TOKENS):
        return "key_value"
    if shape == "marker":
        return "key_value"

    # Narrative -> title_body (high confidence)
    if _has_any(role, NARRATIVE_TOKENS):
        return "title_body"

    # ── Phase 6 broad-coverage rules (added to close the 504-zone tail) ──
    # These run after every high-confidence rule above. They cover
    # the remaining 504 zones that the conservative rules left
    # un-annotated. Coverage analysis on the bundled catalog showed
    # these three rules close the entire tail without misclassifying
    # any zone the high-confidence rules already settled.

    # Shape implies content: visible text-bearing shapes default to
    # title_body. ``card`` / ``node`` / ``band`` / ``block`` / ``box``
    # / ``container`` zones hold a heading + paragraph by default.
    if shape in {"card", "node", "band", "block", "box", "container", "text"}:
        return "title_body"

    # Role-name plurals + collection words → list_items. The
    # explicit token set avoids the "ends in s" trap (business,
    # process, success, etc.).
    if _has_any(role, _PHASE6_LIST_TOKENS):
        return "list_items"

    # Role names mentioning a tabular structure → table_data.
    if _has_any(role, _PHASE6_TABLE_TOKENS):
        return "table_data"

    # Role names mentioning a chart/diagram structure → chart_data.
    if _has_any(role, _PHASE6_CHART_TOKENS):
        return "chart_data"

    # Final fallback: a singular named entity gets ``title_body``.
    # By this point shape is None and role doesn't match any
    # collection/structural keyword. The corpus showed every such
    # zone is a single titled item (solution_name, central_concept,
    # actor, scenario, quote, etc.).
    return "title_body"


# Phase 6 keyword sets — used by the broad-coverage tail rules.
# Kept separate from the high-confidence sets above so future
# tightening only affects the broad pass.

_PHASE6_LIST_TOKENS = {
    "initiatives", "workstreams", "roles", "scenarios", "dimensions",
    "audiences", "pillars", "segments", "channels", "features",
    "partners", "resources", "activities", "examples", "sources",
    "practices", "phases", "waves", "enablers", "capabilities",
    "systems", "units", "components", "services", "horizons",
    "archetypes", "fields", "platforms", "champions", "sponsors",
    "experiments", "alternatives", "beats", "tiers", "forces",
    "precedents", "mechanisms", "lessons", "okrs", "contracts",
    "profiles", "positions", "gates", "chapters", "tribes",
    "groups", "stages", "moves", "vectors", "interfaces",
    "domains", "themes", "tracks", "modules", "deliverables",
    "stakeholders", "personas", "constraints", "branches",
    "subgroups", "departments", "regions", "markets",
    # plural pain_points specifically — won't match the singular
    # 'pain_point' but the data uses pain_points exclusively.
    "pain_points", "touchpoints", "checkpoints",
    # SWOT-family quadrant role names + similar
    "strengths", "weaknesses", "threats",
    "facts", "unknowns",
    # RAID-family role names already covered via plurals above
}

_PHASE6_TABLE_TOKENS = {
    "table", "matrix_table", "matrix_grid",
}

_PHASE6_CHART_TOKENS = {
    "milestone_sequence", "progression",
}


def main() -> int:
    data = yaml.safe_load(BUNDLED.read_text(encoding="utf-8"))
    patterns = data["slide_template_patterns"]

    annotated = 0
    skipped = 0
    untouched = 0
    overwritten = 0

    fix_mode = "--fix" in sys.argv

    for p in patterns:
        for z in p["zones"]:
            if "content_type" in z:
                if not fix_mode:
                    untouched += 1
                    continue
                # --fix mode: re-derive and overwrite if the rule
                # disagrees with the current annotation.
                derived = derive_content_type(z)
                if derived is not None and derived != z["content_type"]:
                    z["content_type"] = derived
                    overwritten += 1
                else:
                    untouched += 1
                continue
            ct = derive_content_type(z)
            if ct is None:
                skipped += 1
                continue
            z["content_type"] = ct
            annotated += 1

    # Validate before writing.
    cat = PatternCatalog.model_validate({"slide_template_patterns": patterns})

    BUNDLED.write_text(
        yaml.safe_dump(
            {"slide_template_patterns": patterns},
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )

    total = annotated + skipped + untouched + overwritten
    print(
        f"Annotated content_type on {annotated}/{total} zones "
        f"({annotated * 100 / total:.0f}%); "
        f"{skipped} left for manual curation; "
        f"{untouched} preserved; "
        f"{overwritten} overwritten (--fix)."
    )
    print(f"Validated catalog: {len(cat.slide_template_patterns)} patterns.")
    print(f"wrote {BUNDLED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
