"""Real-font advance-width metrics for accurate text wrapping.

The legacy `RendererContext._str_width` estimates rendered text width from a
fixed per-character-class table calibrated against narrow Helvetica-class
fonts. When the rasterizer (cairosvg → Pango → fontconfig) actually picks a
different installed font (DejaVu Sans on most Linux distros), the per-glyph
advance widths are systematically wider, so wrap points chosen by the layout
engine push past the box at render time.

This module replaces the estimate with the **real** glyph-advance widths read
from the font file fontconfig would resolve for a given CSS font-family. The
result aligns the layout engine's view with what the rasterizer will draw, so
text wraps correctly without per-deck hand-tuning.

Behavior is graceful: if `fontTools` is not installed, or if `fc-match` is
unavailable, or if the resolved font file fails to parse, the public
`measure_text` returns `None` and callers fall back to the legacy estimator.

Public surface
--------------

- :class:`FontMetrics` — a frozen container of per-codepoint em-units advances.
- :func:`measure_text` — convenience wrapper: family → metrics → pixel width.
- :func:`get_font_metrics` — resolve + load + cache; returns ``None`` on failure.
- :func:`clear_cache` — drop cached metrics (test-only helper).

The module-level cache keys on `(font_family, bold)` tuples; each entry
loads exactly one TTF/OTF file. Decks typically declare two families
(sans + mono) × two weights, so the cache is small and lookup is cheap.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

__all__ = ["FontMetrics", "measure_text", "get_font_metrics", "clear_cache"]


class FontMetrics:
    """Cached glyph-advance widths for one (font-file, weight) pair.

    `advance_widths_em` maps Unicode codepoints to advance widths in em
    units (font design units / unitsPerEm). Multiplying by font_size_px
    yields pixel width. Codepoints not present in the font's ``cmap``
    fall back to ``default_em``, which is the average of the present
    advances (a robust proxy for missing-glyph rendering width).
    """

    __slots__ = ("advance_widths_em", "default_em", "source_path")

    def __init__(
        self,
        advance_widths_em: dict[int, float],
        default_em: float,
        source_path: str,
    ):
        self.advance_widths_em = advance_widths_em
        self.default_em = default_em
        self.source_path = source_path

    def width(self, text: str, font_size: float) -> float:
        """Return rendered width of ``text`` at ``font_size`` pixels."""
        widths = self.advance_widths_em
        default = self.default_em
        return sum(widths.get(ord(c), default) for c in text) * font_size


# Module-level cache. Keyed on (font_family_chain, bold) to keep sans-bold
# and sans-regular distinct (they often live in separate font files with
# materially different advance widths).
_CACHE: dict[tuple[str, bool], Optional[FontMetrics]] = {}


def clear_cache() -> None:
    """Reset the metrics cache. Test-only helper."""
    _CACHE.clear()


def _split_family_chain(font_family: str) -> list[str]:
    """Parse a CSS font-family string into ordered, unquoted candidates.

    `"'DejaVu Sans', Helvetica, sans-serif"` →
    `["DejaVu Sans", "Helvetica", "sans-serif"]`.
    """
    out: list[str] = []
    for part in font_family.split(","):
        s = part.strip().strip("'\"").strip()
        if s:
            out.append(s)
    return out


_GENERIC_FAMILIES = {"sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy"}


def _resolve_font_file(font_family: str, bold: bool) -> Optional[str]:
    """Resolve the first concrete name in a CSS font-family chain to a file path.

    Uses ``fc-match`` (fontconfig) so the resolved file matches what the
    rasterizer (cairosvg via Pango) will pick. Returns ``None`` when:

    * the system has no ``fc-match`` binary,
    * the chain contains only generic family names that fontconfig cannot
      meaningfully resolve to a single file,
    * the resolved path does not exist on disk.

    The first concrete (non-generic) name is queried; if all entries are
    generic, the first one is queried so fontconfig returns its system
    default for that family class.
    """
    if shutil.which("fc-match") is None:
        return None
    candidates = _split_family_chain(font_family)
    if not candidates:
        return None
    concrete = [c for c in candidates if c.lower() not in _GENERIC_FAMILIES]
    target = concrete[0] if concrete else candidates[0]
    weight = "bold" if bold else "regular"
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", f"{target}:weight={weight}"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    path = result.stdout.strip()
    if path and os.path.isfile(path):
        return path
    return None


def _load_font_metrics(font_path: str) -> Optional[FontMetrics]:
    """Read advance widths from a TTF/OTF file via ``fontTools``.

    Returns ``None`` when ``fontTools`` is not installed or the file
    fails to parse — callers fall back to the legacy per-class estimator.
    """
    try:
        from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        font = TTFont(font_path, fontNumber=0, lazy=True)
        units_per_em = int(font["head"].unitsPerEm)
        if units_per_em <= 0:
            return None
        cmap = font.getBestCmap()
        hmtx = font["hmtx"].metrics
        advance_widths_em: dict[int, float] = {}
        for codepoint, glyph_name in cmap.items():
            entry = hmtx.get(glyph_name)
            if entry is None:
                continue
            adv = float(entry[0])
            advance_widths_em[codepoint] = adv / units_per_em
    except Exception:
        return None
    if not advance_widths_em:
        return None
    default_em = sum(advance_widths_em.values()) / len(advance_widths_em)
    return FontMetrics(
        advance_widths_em=advance_widths_em,
        default_em=default_em,
        source_path=font_path,
    )


def get_font_metrics(font_family: str, bold: bool) -> Optional[FontMetrics]:
    """Resolve, load, and cache metrics for a CSS font-family chain.

    Returns ``None`` when fontconfig or ``fontTools`` are unavailable, or
    when no entry in the chain resolves to a parseable font file. The
    result (including ``None`` failures) is cached so retries are cheap.
    """
    if not font_family:
        return None
    key = (font_family, bool(bold))
    if key in _CACHE:
        return _CACHE[key]
    path = _resolve_font_file(font_family, bold)
    if not path:
        _CACHE[key] = None
        return None
    metrics = _load_font_metrics(path)
    _CACHE[key] = metrics
    return metrics


def measure_text(text: str, font_family: str, font_size: float, bold: bool) -> Optional[float]:
    """Return rendered text width using real font metrics, or ``None`` on miss.

    Convenience wrapper for callers that don't need to keep the
    :class:`FontMetrics` object around.
    """
    metrics = get_font_metrics(font_family, bold)
    if metrics is None:
        return None
    return metrics.width(text, font_size)
