---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "GPT-5 via Codex"
  date: "2026-05-07"
---

# PURPOSE.md

## Why This Project Exists

FrameGraph exists to make high-quality diagram and presentation graphics
programmable without requiring a browser runtime, a GUI editor, or a heavyweight
graphics stack. The project treats slide and diagram layout as source code:
versionable, reviewable, testable, and reproducible.

## What It Is

FrameGraph is a YAML-first DSL and pure-Python renderer that turns structured
scene descriptions into SVG. It is aimed at people who want precise control over
visual output while keeping authoring close to plain text and source control.

## Who It Is For

- Engineers who want reproducible architecture and systems diagrams
- Analysts and consultants who need slide-grade SVG output from versioned source
- Tool builders who want a Python-native rendering core with a small dependency surface

## Core Commitments

- YAML is the authoring surface; human-readable source is the product input
- SVG is the primary output surface
- Pure-Python rendering stays first-class
- Regression testing is a release requirement, not an optional extra
- Backward compatibility for released v1.x YAML is a load-bearing constraint

## Non-Goals

- A WYSIWYG editor
- A browser-only rendering stack
- An interactive presentation runtime
- A general-purpose charting replacement for scientific plotting libraries
- A constraint-solver-based layout engine for every diagram class
