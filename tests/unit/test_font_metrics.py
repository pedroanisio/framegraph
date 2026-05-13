"""Unit tests for `framegraph._font_metrics`.

The module replaces hand-tuned per-character-class width estimates with
real glyph-advance widths from the font file fontconfig resolves. These
tests exercise the public surface end-to-end where the host has both
``fontTools`` (declared in the ``metrics`` extra) and the system
``fc-match`` binary, and verify graceful degradation otherwise.
"""

from __future__ import annotations

import shutil
from typing import Any
from unittest import mock

import pytest

from framegraph import _font_metrics


# Skip any test that depends on real metrics when fontTools is unavailable
# or the host has no fontconfig — both are required for the resolver to
# return a parseable file path. The legacy renderer path keeps working;
# these tests just have nothing meaningful to assert.
fonttools = pytest.importorskip("fontTools.ttLib")
HAS_FCMATCH = shutil.which("fc-match") is not None
requires_fontconfig = pytest.mark.skipif(
    not HAS_FCMATCH, reason="fc-match not available on this host"
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Clear the module-level cache between tests so order doesn't matter."""
    _font_metrics.clear_cache()


# ─────────────────────────────────────────────────────────────────────
# Resolution + loading
# ─────────────────────────────────────────────────────────────────────


@requires_fontconfig
def test_get_font_metrics_resolves_dejavu_sans() -> None:
    """A DejaVu Sans request resolves to a real font file with non-empty cmap.

    DejaVu Sans is the de-facto fallback on every Linux distribution
    fontconfig ships with. The metrics dict must include the canonical
    Latin space (``0x20``) and at least one wide letter (``M``).
    """
    metrics = _font_metrics.get_font_metrics("DejaVu Sans", bold=False)
    assert metrics is not None, "DejaVu Sans should resolve via fc-match"
    assert metrics.source_path.endswith((".ttf", ".otf", ".ttc", ".TTF", ".OTF"))
    assert ord(" ") in metrics.advance_widths_em
    assert ord("M") in metrics.advance_widths_em
    # M is one of the widest letters; space is one of the narrowest.
    assert metrics.advance_widths_em[ord("M")] > metrics.advance_widths_em[ord(" ")]


@requires_fontconfig
def test_metrics_cache_is_keyed_by_family_and_weight() -> None:
    """Sans-bold and sans-regular are separate cache entries.

    Bold faces typically live in different files with measurably wider
    advance widths; conflating them would bring back the original wrap
    bug for bold text.
    """
    regular = _font_metrics.get_font_metrics("DejaVu Sans", bold=False)
    bold = _font_metrics.get_font_metrics("DejaVu Sans", bold=True)
    assert regular is not None and bold is not None
    # Both keys present in the cache.
    cached_keys = {(family, b) for family, b in _font_metrics._CACHE}
    assert ("DejaVu Sans", False) in cached_keys
    assert ("DejaVu Sans", True) in cached_keys


@requires_fontconfig
def test_measure_text_dejavu_wider_than_legacy_estimate() -> None:
    """Real DejaVu metrics report wider strings than the legacy table.

    Regression marker: the whole reason this module exists is that the
    legacy per-character-class table underestimated DejaVu Sans by a
    few percent, which is how wrap-engine line breaks pushed past the
    rendered box edge. The real-metrics path must produce a strictly
    larger width than the legacy path for representative prose.
    """
    sample = (
        "The Validator is the only node in this architecture capable of "
        "programmatically rejecting GenAI output."
    )
    real = _font_metrics.measure_text(sample, "DejaVu Sans", font_size=16, bold=False)
    assert real is not None

    # Reproduce the legacy estimate locally so the test does not depend
    # on a renderer instance.
    cw_normal = {
        "narrow": 0.34,
        "normal": 0.50,
        "wide": 0.65,
        "space": 0.25,
        "digit": 0.52,
        "punct": 0.30,
    }
    narrow = set("ijlfrт:;!|1()")
    wide = set("ABCDEFGHIJKLMNOPQRSTUVWXYZmw@#%")
    digit = set("0123456789")
    punct = set(",.'\"-–—")

    def _legacy(c: str) -> float:
        if c in (" ", "\t"):
            return cw_normal["space"]
        if c in narrow:
            return cw_normal["narrow"]
        if c in wide:
            return cw_normal["wide"]
        if c in digit:
            return cw_normal["digit"]
        if c in punct:
            return cw_normal["punct"]
        return cw_normal["normal"]

    legacy = sum(_legacy(c) for c in sample) * 16
    assert real > legacy, (
        f"real DejaVu metrics ({real:.1f}px) should exceed legacy estimate "
        f"({legacy:.1f}px); the wider real width is what fixes the wrap "
        "engine's underestimation"
    )


# ─────────────────────────────────────────────────────────────────────
# Graceful degradation
# ─────────────────────────────────────────────────────────────────────


def test_returns_none_when_font_family_is_empty() -> None:
    """An empty family string short-circuits to ``None`` without invoking fc-match."""
    assert _font_metrics.get_font_metrics("", bold=False) is None
    assert _font_metrics.measure_text("hello", "", 14, bold=False) is None


def test_returns_none_when_fcmatch_missing() -> None:
    """No ``fc-match`` binary → resolver returns ``None`` instead of crashing.

    On hosts without fontconfig the legacy estimator is the only path
    available; the public API must not raise.
    """
    with mock.patch("framegraph._font_metrics.shutil.which", return_value=None):
        assert _font_metrics._resolve_font_file("DejaVu Sans", bold=False) is None
        assert _font_metrics.get_font_metrics("DejaVu Sans", bold=False) is None


def test_returns_none_when_resolved_path_does_not_exist() -> None:
    """A fc-match result that points at a missing file → ``None``."""

    def fake_run(*_args: Any, **_kwargs: Any) -> Any:
        return mock.Mock(stdout="/nonexistent/path/to.ttf", returncode=0)

    with (
        mock.patch("framegraph._font_metrics.shutil.which", return_value="/usr/bin/fc-match"),
        mock.patch("framegraph._font_metrics.subprocess.run", side_effect=fake_run),
    ):
        assert _font_metrics._resolve_font_file("WhateverFont", bold=False) is None


# ─────────────────────────────────────────────────────────────────────
# Family-chain parsing
# ─────────────────────────────────────────────────────────────────────


def test_split_family_chain_strips_quotes_and_whitespace() -> None:
    """The CSS chain parser unwraps quoted names and drops empties."""
    parts = _font_metrics._split_family_chain(
        "'DejaVu Sans', \"Liberation Sans\", Helvetica, , sans-serif"
    )
    assert parts == ["DejaVu Sans", "Liberation Sans", "Helvetica", "sans-serif"]


@requires_fontconfig
def test_resolver_skips_generic_family_when_concrete_present() -> None:
    """A chain with a concrete name first should resolve that name, not the generic.

    This is what makes our author-side declaration `'DejaVu Sans', sans-serif`
    pick DejaVu instead of whatever the system maps `sans-serif` to.
    """
    path = _font_metrics._resolve_font_file("DejaVu Sans, sans-serif", bold=False)
    assert path is not None
    # DejaVu's filename contains "DejaVu" on every distro that ships it.
    assert "dejavu" in path.lower(), (
        f"chain led with DejaVu Sans should resolve to a DejaVu file; got {path!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# FontMetrics object
# ─────────────────────────────────────────────────────────────────────


def test_font_metrics_width_falls_back_to_default_em_for_missing_glyphs() -> None:
    """Codepoints absent from ``cmap`` use the average advance, not zero.

    Using zero would silently make exotic glyphs (CJK, emoji) appear
    free in the wrap budget; the mean-advance fallback is a safer
    proxy for missing-glyph rendering width.
    """
    metrics = _font_metrics.FontMetrics(
        advance_widths_em={ord("a"): 0.5, ord("b"): 0.5},
        default_em=0.5,
        source_path="<test>",
    )
    # An unknown glyph must contribute ``default_em``, not 0.
    assert metrics.width("ab一", font_size=10) == pytest.approx(15.0)
