#!/usr/bin/env python3
"""Annotate every zone in the bundled catalog with a `content_type`.

Runs the iterated rule-based derivation against
`static/refs/slides-patter-a.yml`, writes the inferred
`content_type` onto each zone, and saves the file in place.
Validates the result against `framegraph._patterns.PatternCatalog`
before writing.

Idempotent: re-running on an already-annotated catalog leaves
``content_type`` values untouched (the derivation only assigns
when the field is absent).

Auto-confidence rules cover ~66% of zones; the rest are flagged
``content_type``-less and remain candidates for manual curation.
This is by design — the catalog now declares its known types and
leaves the genuinely ambiguous tail for human review.

Run from the repo root:

    python3 scripts/annotate_content_types.py
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
}
LIST_SUFFIXES = (
    "_list", "_items", "_steps", "_actions", "_levers",
    "_options", "_criteria", "_rules", "_questions",
    "_findings", "_milestones", "_outcomes", "_objectives",
    "_recommendations", "_takeaways", "_takeaway",
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

    # Metric
    if shape == "metric":
        return "metric"
    if _has_any(role, METRIC_TOKENS) and shape in {"card", None}:
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

    # No high-confidence rule — leave un-annotated.
    return None


def main() -> int:
    data = yaml.safe_load(BUNDLED.read_text(encoding="utf-8"))
    patterns = data["slide_template_patterns"]

    annotated = 0
    skipped = 0
    untouched = 0

    for p in patterns:
        for z in p["zones"]:
            if "content_type" in z:
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

    total = annotated + skipped + untouched
    print(
        f"Annotated content_type on {annotated}/{total} zones "
        f"({annotated * 100 / total:.0f}%); "
        f"{skipped} left for manual curation; {untouched} preserved."
    )
    print(f"Validated catalog: {len(cat.slide_template_patterns)} patterns.")
    print(f"wrote {BUNDLED}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
