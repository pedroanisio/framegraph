"""`framegraph.patterns` — fill-and-render pipeline (Phase 1).

Public surface for the pattern-fill layer. Higher phases of the
roadmap (`docs/ROADMAP-FILL-RENDER.md`) extend this subpackage with
layout (Phase 3), renderer bridge (Phase 4), and CLI glue (Phase 5).
"""

from framegraph.patterns.fill import (
    MissingContentTypeError,
    PatternFill,
    derive_default_fill_schema,
    load_fill,
)

__all__ = [
    "MissingContentTypeError",
    "PatternFill",
    "derive_default_fill_schema",
    "load_fill",
]
