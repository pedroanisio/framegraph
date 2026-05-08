#!/usr/bin/env python3
"""Generate sidecars for the 11 comparison-table-family patterns.

The 17-member comparison-table family shares a structural skeleton
(left-axis row labels + 3-5 right-side data columns). Each pattern
specializes the shape with domain-specific role names. Sidecars
here add representative ``example_fill`` content per pattern so
LLM agents see what good content looks like; the default schemas
already validate the payload shape correctly.

Generated sidecars contain ``zones: {}`` (no schema overrides) plus
a hand-written ``example_fill`` per pattern.

Run from the repo root:

    python3 scripts/generate_comparison_table_sidecars.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from framegraph._patterns import load_pattern_catalog  # noqa: E402

FILLS_DIR = REPO_ROOT / "static" / "refs" / "fills"


# Hand-curated example fills for 11 comparison-table-family patterns.
# Each entry maps role → realistic sample content.

EXAMPLES: dict[int, tuple[str, dict]] = {
    91: (
        "communications-plan",
        {
            "audiences": [
                "Executive sponsors",
                "Department heads",
                "Frontline employees",
                "External partners",
            ],
            "key_messages": {
                "headers": ["Audience", "Core message"],
                "rows": [
                    ["Execs", "Why we're transforming and what success looks like"],
                    ["Dept heads", "How responsibilities shift in your function"],
                    ["Employees", "What changes for your day-to-day"],
                    ["Partners", "How our integration evolves"],
                ],
            },
            "channels_frequency": {
                "headers": ["Channel", "Frequency"],
                "rows": [
                    ["All-hands", "Monthly"],
                    ["Manager cascade", "Weekly during cutover"],
                    ["Email + intranet", "Bi-weekly"],
                    ["Partner portal", "Per release"],
                ],
            },
            "owner_timing": {
                "headers": ["Owner", "Timing"],
                "rows": [
                    ["CEO + CFO", "Kickoff"],
                    ["Function leads", "Weeks 1-4"],
                    ["HR + Comms", "Ongoing"],
                    ["Partner ops", "Pre/post release"],
                ],
            },
        },
    ),
    111: (
        "diagnostic-summary",
        {
            "dimensions": [
                "Strategy clarity",
                "Operating-model fit",
                "Capability gaps",
                "Performance metrics",
            ],
            "status": {
                "headers": ["Dimension", "Status"],
                "rows": [
                    ["Strategy", "Amber"],
                    ["Op model", "Red"],
                    ["Capability", "Amber"],
                    ["Metrics", "Green"],
                ],
            },
            "findings": {
                "headers": ["Dimension", "Finding"],
                "rows": [
                    ["Strategy", "Vision known but not cascaded"],
                    ["Op model", "Misaligned incentives across BUs"],
                    ["Capability", "Data-engineering shortfall"],
                    ["Metrics", "Solid; under-used in decisions"],
                ],
            },
            "implications": {
                "headers": ["Dimension", "Implication"],
                "rows": [
                    ["Strategy", "Run cascading workshops"],
                    ["Op model", "Redesign incentives within 6 months"],
                    ["Capability", "Hire / upskill 8 FTEs in 90 days"],
                    ["Metrics", "Embed metrics in QBRs"],
                ],
            },
        },
    ),
    122: (
        "best-practice-gap",
        {
            "practice_areas": {
                "title": "Practice areas under review",
                "body": "Sales ops, demand gen, customer onboarding, renewals.",
            },
            "current_practice": {
                "headers": ["Area", "Today"],
                "rows": [
                    ["Sales ops", "Manual CRM hygiene"],
                    ["Demand gen", "Single-channel attribution"],
                    ["Onboarding", "Self-serve only"],
                    ["Renewals", "Reactive, last-30-days"],
                ],
            },
            "leading_practice": {
                "headers": ["Area", "Leading practice"],
                "rows": [
                    ["Sales ops", "Automated data quality + alerts"],
                    ["Demand gen", "Multi-touch + ML attribution"],
                    ["Onboarding", "High-touch for top tier"],
                    ["Renewals", "90-day proactive program"],
                ],
            },
            "required_change": {
                "headers": ["Area", "Required change"],
                "rows": [
                    ["Sales ops", "Adopt CRM-automation tool"],
                    ["Demand gen", "Stand up attribution model"],
                    ["Onboarding", "Hire 2 CSMs for top tier"],
                    ["Renewals", "Build proactive playbook"],
                ],
            },
        },
    ),
    145: (
        "skills-gap-matrix",
        {
            "skills": {
                "title": "Skills under review",
                "body": "Data engineering, ML/AI, product analytics, change management.",
            },
            "current_level": {
                "headers": ["Skill", "Current"],
                "rows": [
                    ["Data eng.", "Beginner"],
                    ["ML/AI", "None"],
                    ["Product analytics", "Intermediate"],
                    ["Change mgmt.", "Beginner"],
                ],
            },
            "target_level": {
                "headers": ["Skill", "Target"],
                "rows": [
                    ["Data eng.", "Advanced"],
                    ["ML/AI", "Intermediate"],
                    ["Product analytics", "Advanced"],
                    ["Change mgmt.", "Intermediate"],
                ],
            },
            "gap_closure_plan": {
                "headers": ["Skill", "Plan"],
                "rows": [
                    ["Data eng.", "Hire 3 + bootcamp 5"],
                    ["ML/AI", "Hire 2 + partner with vendor"],
                    ["Product analytics", "Internal academy"],
                    ["Change mgmt.", "Coaching for 12 leads"],
                ],
            },
        },
    ),
    183: (
        "data-operating-model",
        {
            "data_domains": [
                "Customer",
                "Product",
                "Finance",
                "Operations",
            ],
            "domain_owners": {
                "headers": ["Domain", "Owner"],
                "rows": [
                    ["Customer", "VP Marketing"],
                    ["Product", "VP Product"],
                    ["Finance", "Controller"],
                    ["Operations", "VP Ops"],
                ],
            },
            "governance_forums": {
                "headers": ["Domain", "Forum"],
                "rows": [
                    ["Customer", "Marketing council"],
                    ["Product", "Product council"],
                    ["Finance", "Finance steering"],
                    ["Operations", "Ops review"],
                ],
            },
            "platform_capabilities": {
                "headers": ["Domain", "Platform"],
                "rows": [
                    ["Customer", "CDP + analytics warehouse"],
                    ["Product", "Event pipeline + feature store"],
                    ["Finance", "ERP + planning"],
                    ["Operations", "Workflow + IoT"],
                ],
            },
            "priority_use_cases": {
                "headers": ["Domain", "Use case"],
                "rows": [
                    ["Customer", "360° customer view"],
                    ["Product", "Real-time experimentation"],
                    ["Finance", "Cash-flow forecasting"],
                    ["Operations", "Predictive maintenance"],
                ],
            },
        },
    ),
    198: (
        "regulatory-compliance-matrix",
        {
            "requirements": [
                "Article 32 — security of processing",
                "Article 33 — breach notification",
                "Article 35 — DPIA",
                "Article 44 — international transfers",
            ],
            "controls": {
                "headers": ["Requirement", "Control"],
                "rows": [
                    ["Art. 32", "Encryption + access reviews"],
                    ["Art. 33", "72-hr notification runbook"],
                    ["Art. 35", "DPIA template + sign-off"],
                    ["Art. 44", "SCCs + transfer impact assessments"],
                ],
            },
            "owners": {
                "headers": ["Requirement", "Owner"],
                "rows": [
                    ["Art. 32", "CISO"],
                    ["Art. 33", "Legal + security"],
                    ["Art. 35", "Privacy office"],
                    ["Art. 44", "Privacy office"],
                ],
            },
            "evidence_status": {
                "headers": ["Requirement", "Evidence"],
                "rows": [
                    ["Art. 32", "ISO 27001 audit"],
                    ["Art. 33", "Tabletop exercise log"],
                    ["Art. 35", "5 DPIAs completed"],
                    ["Art. 44", "SCCs signed for all vendors"],
                ],
            },
            "gaps": {
                "headers": ["Requirement", "Gap"],
                "rows": [
                    ["Art. 32", "Need annual penetration test"],
                    ["Art. 33", "Notification automation in progress"],
                    ["Art. 35", "Backlog of 3 DPIAs"],
                    ["Art. 44", "TIAs pending for 2 vendors"],
                ],
            },
        },
    ),
    219: (
        "decision-log",
        {
            "decision_items": [
                "Adopt cloud-first architecture",
                "Consolidate 3 BUs into 2",
                "Sunset legacy product line",
                "Open EU operations",
            ],
            "decision_owner": {
                "headers": ["Decision", "Owner"],
                "rows": [
                    ["Cloud-first", "CIO"],
                    ["BU consolidation", "COO"],
                    ["Sunset legacy", "VP Product"],
                    ["EU expansion", "CEO"],
                ],
            },
            "decision_date": {
                "headers": ["Decision", "Date"],
                "rows": [
                    ["Cloud-first", "2026-03-04"],
                    ["BU consolidation", "2026-03-18"],
                    ["Sunset legacy", "2026-04-02"],
                    ["EU expansion", "2026-04-22"],
                ],
            },
            "implications": {
                "headers": ["Decision", "Implication"],
                "rows": [
                    ["Cloud-first", "$4M migration spend"],
                    ["BU consolidation", "180 roles affected"],
                    ["Sunset legacy", "$8M revenue exit"],
                    ["EU expansion", "$12M opening cost"],
                ],
            },
            "follow_up_actions": {
                "headers": ["Decision", "Follow-up"],
                "rows": [
                    ["Cloud-first", "RFP issued"],
                    ["BU consolidation", "Comms plan in build"],
                    ["Sunset legacy", "Customer-migration playbook"],
                    ["EU expansion", "Legal entity setup"],
                ],
            },
        },
    ),
    246: (
        "product-market-fit-assessment",
        {
            "fit_dimensions": [
                "Market demand",
                "Usage / engagement",
                "Retention",
                "Monetization",
                "Differentiation",
            ],
            "evidence": {
                "headers": ["Dimension", "Evidence"],
                "rows": [
                    ["Demand", "120% MoM signup growth"],
                    ["Usage", "DAU/MAU = 0.42"],
                    ["Retention", "Cohort retention 65% at M3"],
                    ["Monetization", "ARPU $46/mo"],
                    ["Differentiation", "5 of 7 reviewers cite UX edge"],
                ],
            },
            "score": {
                "headers": ["Dimension", "Score"],
                "rows": [
                    ["Demand", "9/10"],
                    ["Usage", "8/10"],
                    ["Retention", "7/10"],
                    ["Monetization", "6/10"],
                    ["Differentiation", "8/10"],
                ],
            },
            "gaps": {
                "headers": ["Dimension", "Gap"],
                "rows": [
                    ["Demand", "Channel attribution unclear"],
                    ["Usage", "Activation drop-off in step 3"],
                    ["Retention", "Churn driver unknown"],
                    ["Monetization", "No price test yet"],
                    ["Differentiation", "Need third-party validation"],
                ],
            },
            "next_experiments": {
                "headers": ["Dimension", "Experiment"],
                "rows": [
                    ["Demand", "Multi-touch attribution"],
                    ["Usage", "Onboarding redesign A/B"],
                    ["Retention", "Churn-driver interviews"],
                    ["Monetization", "Tiered-pricing test"],
                    ["Differentiation", "Independent benchmark"],
                ],
            },
        },
    ),
    267: (
        "risk-appetite-framework",
        {
            "risk_categories": [
                "Strategic",
                "Operational",
                "Financial",
                "Reputational",
                "Compliance",
            ],
            "appetite_statement": {
                "headers": ["Category", "Appetite"],
                "rows": [
                    ["Strategic", "High — pursue bold growth bets"],
                    ["Operational", "Low — minimize disruption"],
                    ["Financial", "Moderate — preserve liquidity"],
                    ["Reputational", "Very low"],
                    ["Compliance", "Zero tolerance"],
                ],
            },
            "tolerance_thresholds": {
                "headers": ["Category", "Threshold"],
                "rows": [
                    ["Strategic", "Up to 20% of capital"],
                    ["Operational", "<2 hr SLA breach / month"],
                    ["Financial", ">90 days runway always"],
                    ["Reputational", "No regrettable incidents"],
                    ["Compliance", "Zero material findings"],
                ],
            },
            "monitoring_metrics": {
                "headers": ["Category", "Metric"],
                "rows": [
                    ["Strategic", "Bet portfolio mix"],
                    ["Operational", "SLA breach count"],
                    ["Financial", "Cash runway months"],
                    ["Reputational", "Brand sentiment"],
                    ["Compliance", "Audit finding rate"],
                ],
            },
            "escalation_actions": {
                "headers": ["Category", "Escalation"],
                "rows": [
                    ["Strategic", "Board within 30 days"],
                    ["Operational", "COO same day"],
                    ["Financial", "CFO weekly review"],
                    ["Reputational", "Crisis playbook"],
                    ["Compliance", "Audit committee"],
                ],
            },
        },
    ),
    297: (
        "early-warning-indicators",
        {
            "indicators": {
                "title": "Off-track signals",
                "body": "Indicators chosen to detect drift before consequences hit.",
            },
            "thresholds": {
                "headers": ["Indicator", "Threshold"],
                "rows": [
                    ["Velocity", "<80% of plan for 2 sprints"],
                    ["Adoption", "<50% of pilot users by week 4"],
                    ["Cost run-rate", ">110% of monthly budget"],
                    ["NPS", "Drop >10 points QoQ"],
                ],
            },
            "current_signal": {
                "headers": ["Indicator", "Current"],
                "rows": [
                    ["Velocity", "85%"],
                    ["Adoption", "42% (red)"],
                    ["Cost run-rate", "104%"],
                    ["NPS", "+38 (stable)"],
                ],
            },
            "response_action": {
                "headers": ["Indicator", "Action"],
                "rows": [
                    ["Velocity", "Watch one more sprint"],
                    ["Adoption", "Re-run onboarding"],
                    ["Cost run-rate", "Cap discretionary"],
                    ["NPS", "Continue"],
                ],
            },
        },
    ),
    311: (
        "decision-quality-scorecard",
        {
            "quality_dimensions": [
                "Frame clarity",
                "Evidence completeness",
                "Options breadth",
                "Trade-off analysis",
                "Stakeholder alignment",
                "Reversibility",
            ],
            "score": {
                "headers": ["Dimension", "Score"],
                "rows": [
                    ["Frame clarity", "8/10"],
                    ["Evidence", "6/10"],
                    ["Options", "5/10"],
                    ["Trade-offs", "7/10"],
                    ["Alignment", "8/10"],
                    ["Reversibility", "9/10"],
                ],
            },
            "evidence": {
                "headers": ["Dimension", "Evidence"],
                "rows": [
                    ["Frame clarity", "One-page brief"],
                    ["Evidence", "Two interviews; no benchmarks"],
                    ["Options", "Two options surfaced"],
                    ["Trade-offs", "Cost-benefit captured"],
                    ["Alignment", "Cross-functional sign-off"],
                    ["Reversibility", "Pilot scope only"],
                ],
            },
            "improvement_action": {
                "headers": ["Dimension", "Action"],
                "rows": [
                    ["Frame clarity", "Done"],
                    ["Evidence", "Run benchmark study"],
                    ["Options", "Generate two more options"],
                    ["Trade-offs", "Done"],
                    ["Alignment", "Done"],
                    ["Reversibility", "Done"],
                ],
            },
        },
    ),
    320: (
        "governance-by-risk-tier",
        {
            "risk_tiers": [
                "Tier 1 — strategic / regulated",
                "Tier 2 — operational / material",
                "Tier 3 — routine / immaterial",
            ],
            "required_controls": {
                "headers": ["Tier", "Controls"],
                "rows": [
                    ["Tier 1", "Full review + audit trail"],
                    ["Tier 2", "Peer review + log"],
                    ["Tier 3", "Self-serve + post-hoc audit"],
                ],
            },
            "approval_level": {
                "headers": ["Tier", "Approver"],
                "rows": [
                    ["Tier 1", "Exec committee"],
                    ["Tier 2", "Function head"],
                    ["Tier 3", "Manager"],
                ],
            },
            "monitoring_frequency": {
                "headers": ["Tier", "Cadence"],
                "rows": [
                    ["Tier 1", "Weekly"],
                    ["Tier 2", "Monthly"],
                    ["Tier 3", "Quarterly sample"],
                ],
            },
            "escalation_rule": {
                "headers": ["Tier", "Escalation"],
                "rows": [
                    ["Tier 1", "Board within 24h on issue"],
                    ["Tier 2", "Function head + risk officer"],
                    ["Tier 3", "Manager + ops"],
                ],
            },
        },
    ),
}


HEADER = """\
# Sidecar fill schema for pattern #{pid} — {name}.
#
# Member of the comparison-table family ({fam_size} patterns share
# this structural skeleton: row labels + N data columns). The
# default content_type-derived schema validates the payload shape
# correctly; this sidecar exists to ship a representative
# example_fill so agents see what good content looks like.
"""


def main() -> int:
    catalog = load_pattern_catalog()
    fam_size = 17  # see Phase 5 dry-run output

    for pid, (slug, example) in EXAMPLES.items():
        pattern = catalog.get(pid)
        path = FILLS_DIR / f"{pid:03d}-{slug}.yml"
        body = HEADER.format(pid=pid, name=pattern.name, fam_size=fam_size)
        body += "\n"
        body += yaml.safe_dump(
            {
                "pattern_id": pid,
                "zones": {},
                "example_fill": example,
            },
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
        path.write_text(body, encoding="utf-8")
        print(f"wrote {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
