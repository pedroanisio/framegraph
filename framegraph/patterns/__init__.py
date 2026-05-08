"""`framegraph.patterns` — fill-and-render pipeline.

Public surface for the pattern-fill layer. Higher phases of the
roadmap (`docs/ROADMAP-FILL-RENDER.md`) extend this subpackage with
layout (Phase 3), renderer bridge (Phase 4), and CLI glue (Phase 5).

Phase 1 introduced the default-schema fill model; Phase 2 adds
sidecar overrides (`framegraph.patterns.sidecar`).
"""

from framegraph.patterns.fill import (
    MissingContentTypeError,
    PatternFill,
    derive_default_fill_schema,
    load_fill,
)
from framegraph.patterns.layout import (
    Box,
    compute_boxes,
)
from framegraph.patterns.render import (
    compose_document,
    render_pattern_svg,
)
from framegraph.patterns.sidecar import (
    BMC_SIDECAR_PATH,
    PatternFillSidecar,
    SidecarFieldSpec,
    SidecarZoneOverride,
    derive_fill_schema_with_sidecar,
    load_sidecar,
)

__all__ = [
    # Phase 1
    "MissingContentTypeError",
    "PatternFill",
    "derive_default_fill_schema",
    "load_fill",
    # Phase 2
    "BMC_SIDECAR_PATH",
    "PatternFillSidecar",
    "SidecarFieldSpec",
    "SidecarZoneOverride",
    "derive_fill_schema_with_sidecar",
    "load_sidecar",
    # Phase 3
    "Box",
    "compute_boxes",
    # Phase 4
    "compose_document",
    "render_pattern_svg",
]
