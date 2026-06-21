"""Canonical canvas-size normalization helpers.

Canvas dimensions enter FrameGraph through several surfaces: YAML
``canvas.size`` blocks, FrameSet targets, CLI pattern options, SVG roots,
and source-image fallbacks. This module keeps those conversions in one
typed place so later preset support can build on a single value model.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

CanvasUnits = Literal["px", "pt"]
"""Canvas units accepted by the schema."""


@dataclass(frozen=True)
class CanvasSize:
    """Renderer-ready canvas dimensions.

    Attributes:
        width: Canvas width as a finite float.
        height: Canvas height as a finite float.
        units: Canvas units. Rendering currently treats ``px`` as SVG
            user units; ``pt`` is retained for schema-level print sizes.
    """

    width: float
    height: float
    units: CanvasUnits = "px"

    def __post_init__(self) -> None:
        """Validate that dimensions are finite numeric values."""
        width = float(self.width)
        height = float(self.height)
        if not math.isfinite(width) or not math.isfinite(height):
            raise ValueError("canvas dimensions must be finite")
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)

    @property
    def size(self) -> tuple[float, float]:
        """Return ``(width, height)`` for renderer call sites."""
        return (self.width, self.height)

    def as_list(self) -> list[float]:
        """Return ``[width, height]`` for schema/deck dictionaries."""
        return [self.width, self.height]


DEFAULT_SVG_CANVAS = CanvasSize(960.0, 540.0)
"""Fallback for SVG roots without width/height or viewBox."""

DEFAULT_RENDERER_CANVAS = CanvasSize(1000.0, 600.0)
"""Fallback used by the low-level renderer when no scene canvas exists."""

DEFAULT_FRAMESET_CANVAS = CanvasSize(1280.0, 720.0)
"""Fallback used when legacy documents are lifted into a FrameSet."""

DEFAULT_DECK_CANVAS = CanvasSize(960.0, 540.0)
"""Fallback used by deck rendering when deck-level canvas is absent."""

DEFAULT_PATTERN_CANVAS = CanvasSize(1920.0, 1080.0)
"""Default canvas used by pattern CLI rendering."""


def canvas_size_list(canvas: CanvasSize) -> list[float]:
    """Return a mutable ``[width, height]`` pair for existing schema surfaces."""
    return canvas.as_list()


def parse_canvas_size(
    value: object,
    *,
    fallback: CanvasSize | None = None,
    units: CanvasUnits = "px",
) -> CanvasSize:
    """Coerce a two-item size sequence into ``CanvasSize``.

    Args:
        value: Candidate size value, usually a YAML ``[width, height]``.
        fallback: Optional fallback returned for malformed values.
        units: Units to attach to the resulting canvas.

    Returns:
        A normalized canvas size. When ``fallback`` is provided and the
        input is malformed, the exact fallback object is returned.

    Raises:
        ValueError: If ``fallback`` is absent and ``value`` is malformed.
    """
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        if fallback is not None:
            return fallback
        raise ValueError("canvas size must be a two-item sequence")
    if len(value) != 2:
        if fallback is not None:
            return fallback
        raise ValueError("canvas size must contain exactly two values")
    try:
        return CanvasSize(float(value[0]), float(value[1]), units=units)
    except (TypeError, ValueError) as exc:
        if fallback is not None:
            return fallback
        raise ValueError("canvas size values must be numeric") from exc


def canvas_from_mapping(
    canvas: Mapping[str, Any] | None,
    *,
    fallback: CanvasSize | None = None,
) -> CanvasSize:
    """Extract ``CanvasSize`` from a ``canvas`` mapping.

    Args:
        canvas: Mapping with a ``size`` field and optional ``units``.
        fallback: Optional fallback returned for absent or malformed input.

    Returns:
        Normalized canvas dimensions.

    Raises:
        ValueError: If no fallback is provided and the mapping is malformed.
    """
    if not isinstance(canvas, Mapping):
        if fallback is not None:
            return fallback
        raise ValueError("canvas must be a mapping")
    raw_units = canvas.get("units", "px")
    units: CanvasUnits = raw_units if raw_units in ("px", "pt") else "px"
    return parse_canvas_size(canvas.get("size"), fallback=fallback, units=units)


def canvas_from_scene(
    scene: Mapping[str, Any] | None,
    *,
    fallback: CanvasSize,
    use_source_image: bool = False,
) -> CanvasSize:
    """Resolve canvas dimensions from a scene mapping.

    Args:
        scene: Scene mapping that may contain ``canvas`` or
            ``source_image`` dimensions.
        fallback: Fallback returned when the scene has no usable size.
        use_source_image: Whether ``scene.source_image`` dimensions should
            be considered after ``scene.canvas``.

    Returns:
        A normalized canvas size.
    """
    if not isinstance(scene, Mapping):
        return fallback
    try:
        return canvas_from_mapping(scene.get("canvas"))
    except ValueError:
        pass
    if use_source_image:
        source_image = scene.get("source_image")
        if isinstance(source_image, Mapping):
            try:
                return parse_canvas_size([source_image.get("width"), source_image.get("height")])
            except ValueError:
                pass
    return fallback


def svg_canvas_size(svg: str, *, fallback: CanvasSize = DEFAULT_SVG_CANVAS) -> CanvasSize:
    """Extract canvas dimensions from an SVG string.

    The root ``width`` and ``height`` attributes win. If either is absent,
    the third and fourth ``viewBox`` values are used. Malformed or absent
    values return ``fallback``.
    """
    m_w = re.search(r'<svg\b[^>]*\bwidth="([0-9.]+)(?:px)?"', svg)
    m_h = re.search(r'<svg\b[^>]*\bheight="([0-9.]+)(?:px)?"', svg)
    if m_w and m_h:
        return parse_canvas_size([m_w.group(1), m_h.group(1)], fallback=fallback)
    m_vb = re.search(r'<svg\b[^>]*\bviewBox="([^"]+)"', svg)
    if m_vb:
        parts = m_vb.group(1).split()
        if len(parts) >= 4:
            return parse_canvas_size([parts[2], parts[3]], fallback=fallback)
    return fallback
