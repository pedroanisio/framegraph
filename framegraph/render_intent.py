"""Normalize render requests before they reach renderer/export code.

The renderer intentionally consumes simple numeric canvas dimensions.
This module gives higher-level entry points one typed envelope for the
decisions that happen before rendering: input coercion, frame selection,
target resolution, canvas normalization, style references, and export
defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from framegraph._frameset import (
    Frame,
    FrameSetDocument,
    FrameTarget,
    _resolve_target,
    coerce_to_frameset,
    list_frameset_target_union,
)
from framegraph.canvas import CanvasUnits, parse_canvas_size

ExportFormat = Literal["svg", "png", "pdf"]
"""Supported output formats for a normalized render request."""


@dataclass(frozen=True)
class ResolvedCanvas:
    """Canvas resolved to renderer-ready numeric units.

    Attributes:
        size: Width and height in SVG/CSS pixels.
        units: Renderer units. The current renderer treats these as
            SVG user units, equivalent to CSS pixels for export.
        target_name: Name of the FrameSet target that supplied the canvas.
    """

    size: tuple[float, float]
    units: CanvasUnits = "px"
    target_name: str = "default"


@dataclass(frozen=True)
class ExportIntent:
    """Export settings attached to a render request.

    Attributes:
        format: Primary output format. ``svg`` keeps export out of the
            render pass; ``png`` and ``pdf`` are handled after SVG emission.
        raster_dpi: Rasterization DPI for raster exports. Vector PDF output
            ignores this value by design.
        vector: Whether PDF export should use the vector backend.
    """

    format: ExportFormat = "svg"
    raster_dpi: int = 300
    vector: bool = False


@dataclass(frozen=True)
class RenderIntent:
    """One normalized render unit.

    Attributes:
        frameset: Coerced FrameSet document shared by this render pass.
        frame: Frame to render.
        target: Target selected for the frame.
        target_name: Requested or defaulted target name.
        canvas: Canvas normalized from the target.
        theme: Theme id inherited from the FrameSet, when present.
        stylesheet_ref: Stylesheet reference inherited from the FrameSet,
            when present.
        export: Export options that downstream export code should apply.
    """

    frameset: FrameSetDocument
    frame: Frame
    target: FrameTarget
    target_name: str
    canvas: ResolvedCanvas
    theme: str | None = None
    stylesheet_ref: str | None = None
    export: ExportIntent = ExportIntent()


def _resolved_canvas(target: FrameTarget) -> ResolvedCanvas:
    """Return the renderer-facing canvas value for a selected target."""
    canvas = parse_canvas_size(target.canvas)
    return ResolvedCanvas(
        size=canvas.size,
        units=canvas.units,
        target_name=target.name,
    )


def _selected_frames(frameset: FrameSetDocument, frame_ids: list[str] | None) -> list[Frame]:
    """Return frames in document order, optionally filtered by id."""
    if frame_ids is None:
        return list(frameset.frames)
    wanted = set(frame_ids)
    selected = [frame for frame in frameset.frames if frame.id in wanted]
    missing = [
        frame_id for frame_id in frame_ids if frame_id not in {frame.id for frame in selected}
    ]
    if missing:
        raise KeyError(f"unknown frame id(s): {missing}")
    return selected


def collect_render_intents(
    data: dict[str, Any],
    *,
    target_name: str | None = None,
    all_targets: bool = False,
    frame_ids: list[str] | None = None,
    export: ExportIntent | None = None,
) -> list[RenderIntent]:
    """Normalize a FrameGraph payload into concrete render intents.

    Args:
        data: Parsed FrameGraph YAML payload.
        target_name: Optional target to render. When omitted, each frame uses
            the same fallback order as the FrameSet renderer.
        all_targets: When true, build a frame-by-target cross product over the
            FrameSet's declared target union.
        frame_ids: Optional allow-list of frame ids. Render order still follows
            the document's frame order.
        export: Optional export settings. Defaults to SVG output with 300-DPI
            raster settings ready for later PDF/PNG conversion.

    Returns:
        Render intents in deterministic render order. For ``all_targets``, the
        outer loop is target order and the inner loop is frame order, matching
        the existing deck CLI output grouping.

    Raises:
        ValueError: If ``target_name`` and ``all_targets`` are both provided.
        KeyError: If a requested frame or target does not exist.
    """
    if target_name is not None and all_targets:
        raise ValueError("target_name and all_targets are mutually exclusive")

    frameset = coerce_to_frameset(data)
    frames = _selected_frames(frameset, frame_ids)
    target_names = list_frameset_target_union(frameset) if all_targets else [target_name]
    export_intent = export if export is not None else ExportIntent()

    intents: list[RenderIntent] = []
    for name in target_names:
        for frame in frames:
            target = _resolve_target(frame, frameset, name)
            canvas = _resolved_canvas(target)
            intents.append(
                RenderIntent(
                    frameset=frameset,
                    frame=frame,
                    target=target,
                    target_name=target.name,
                    canvas=canvas,
                    theme=frameset.theme,
                    stylesheet_ref=frameset.stylesheet,
                    export=export_intent,
                )
            )
    return intents
