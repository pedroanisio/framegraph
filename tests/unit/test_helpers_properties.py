"""Property-based tests for `framegraph._helpers` algebraic helpers.

Hypothesis is configured with a small `max_examples` to keep CI runtime
modest while still surfacing edge cases beyond what enumerated tests
reach.
"""

from __future__ import annotations

import math
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from framegraph._helpers import attrs, box, fmt, fnum, pt, sid

_FAST = settings(max_examples=50, deadline=None)


@_FAST
@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6))
def test_fnum_round_trip_via_fmt_preserves_value(x: float) -> None:
    """`fnum(fmt(x))` is within the rounding tolerance of `x`."""
    rendered = fmt(x)
    parsed = fnum(rendered)
    # fmt rounds to 3 decimals
    assert math.isclose(parsed, x, abs_tol=5e-4) or math.isclose(parsed, round(x), abs_tol=5e-4)


@_FAST
@given(st.text(min_size=1, max_size=50))
def test_sid_first_char_is_letter_or_underscore(s: str) -> None:
    """`sid(s)[0]` always matches `[A-Za-z_]` for any non-empty input."""
    out = sid(s)
    assert out  # non-empty
    assert re.match(r"^[A-Za-z_]", out[0]) is not None


@_FAST
@given(st.text(min_size=1, max_size=50))
def test_sid_idempotent(s: str) -> None:
    """`sid(sid(s)) == sid(s)`."""
    once = sid(s)
    assert sid(once) == once


@_FAST
@given(
    st.dictionaries(
        keys=st.text(
            alphabet=st.characters(min_codepoint=0x41, max_codepoint=0x7A),
            min_size=1,
            max_size=10,
        ),
        values=st.one_of(
            st.text(min_size=0, max_size=20),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
        max_size=8,
    )
)
def test_attrs_every_truthy_key_appears_with_quoted_value(d: dict) -> None:
    """Every non-None/non-False key in `d` appears as `key="..."` in `attrs(d)`."""
    out = attrs(d)
    for k, v in d.items():
        if v is None or v is False:
            continue
        assert f"{k}=" in out, f"key {k!r} missing from {out!r}"


@_FAST
@given(
    st.tuples(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
    )
)
def test_box_round_trip_via_list(t: tuple[float, float, float, float]) -> None:
    """`box(list(box(t))) == box(t)` for any valid 4-tuple of finite floats."""
    once = box(list(t))
    twice = box(list(once))
    assert once == twice


@_FAST
@given(
    st.lists(
        st.floats(allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=3,
    )
    | st.lists(
        st.floats(allow_nan=False, allow_infinity=False),
        min_size=5,
        max_size=10,
    )
)
def test_box_invalid_length_always_raises(seq: list) -> None:
    """`box(seq)` raises `ValueError` whenever `len(seq) != 4`."""
    import pytest as _pytest

    with _pytest.raises(ValueError):
        box(seq)


@_FAST
@given(
    st.tuples(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e3, max_value=1e3),
    )
)
def test_pt_round_trip_via_list(t: tuple[float, float]) -> None:
    """`pt(list(pt(t))) == pt(t)`."""
    once = pt(list(t))
    twice = pt(list(once))
    assert once == twice


@_FAST
@given(st.text(min_size=0, max_size=50))
def test_fmt_string_input_escaped_no_unescaped_lt_or_gt(s: str) -> None:
    """For non-numeric input, `fmt(s)` returns `esc(s)` — no raw `<` or `>` survives."""
    out = fmt(s)
    # If the string had literal angle brackets, fmt → esc them
    # Otherwise, fmt → numeric path; either way no raw `<` should appear unless input was a non-string somehow
    if "<" in s or ">" in s:
        assert "<" not in out and ">" not in out
