"""Unit tests for `framegraph._helpers` — pure functions only."""

from __future__ import annotations

import pytest

from framegraph._helpers import (
    _expand_lorem,
    _lorem,
    attrs,
    box,
    deep_get,
    esc,
    fmt,
    fnum,
    pt,
    pts_attr,
    sid,
)

# ── esc ─────────────────────────────────────────────────────────────


def test_esc_html_special_chars_are_escaped() -> None:
    assert esc("<a>&\"'") == "&lt;a&gt;&amp;&quot;&#x27;"


def test_esc_none_returns_string_none() -> None:
    # html.escape(str(None)) -> "None"
    assert esc(None) == "None"


def test_esc_integer_value_returns_str() -> None:
    assert esc(42) == "42"


# ── fnum ────────────────────────────────────────────────────────────


def test_fnum_valid_int_returns_float() -> None:
    assert fnum(3) == 3.0


def test_fnum_valid_float_string_returns_float() -> None:
    assert fnum("3.14") == 3.14


def test_fnum_none_returns_default() -> None:
    assert fnum(None) == 0.0
    assert fnum(None, default=7.5) == 7.5


def test_fnum_invalid_string_returns_default() -> None:
    assert fnum("not-a-number", default=-1.0) == -1.0


def test_fnum_dict_returns_default() -> None:
    assert fnum({"a": 1}, default=99.0) == 99.0


# ── fmt ─────────────────────────────────────────────────────────────


def test_fmt_integer_value_no_decimal() -> None:
    assert fmt(42) == "42"
    assert fmt(42.0) == "42"


def test_fmt_float_three_decimals_trimmed() -> None:
    # 1.5 → "1.5" (trailing zeros stripped, trailing dot stripped)
    assert fmt(1.5) == "1.5"
    assert fmt(1.234) == "1.234"
    assert fmt(1.2345) == "1.234"  # rounded to 3 decimals then trimmed


def test_fmt_non_numeric_returns_escaped_string() -> None:
    assert fmt("abc") == "abc"
    assert fmt("<x>") == "&lt;x&gt;"


def test_fmt_negative_zero_renders_as_zero() -> None:
    assert fmt(-0.0) == "0"


# ── sid ─────────────────────────────────────────────────────────────


def test_sid_leading_digit_prefixed_with_id() -> None:
    assert sid("123abc").startswith("id_")


def test_sid_special_chars_replaced_with_underscore() -> None:
    result = sid("hello world!")
    assert " " not in result and "!" not in result


def test_sid_empty_string_prefixed_with_id() -> None:
    assert sid("").startswith("id_")


def test_sid_alphanumeric_unchanged() -> None:
    assert sid("foo_bar-baz.1") == "foo_bar-baz.1"


# ── attrs ───────────────────────────────────────────────────────────


def test_attrs_empty_mapping_returns_empty_string() -> None:
    assert attrs({}) == ""


def test_attrs_filters_none_and_false() -> None:
    out = attrs({"x": None, "y": False, "z": 1})
    assert "x=" not in out and "y=" not in out
    assert 'z="1"' in out


def test_attrs_true_serialized_as_quoted_true() -> None:
    assert attrs({"x": True}) == 'x="true"'


def test_attrs_escapes_quotes_in_values() -> None:
    assert "&quot;" in attrs({"k": 'a "b" c'})


def test_attrs_preserves_iteration_order() -> None:
    out = attrs({"a": 1, "b": 2, "c": 3})
    # Ordered by insertion in dict
    assert out.index("a=") < out.index("b=") < out.index("c=")


# ── box ─────────────────────────────────────────────────────────────


def test_box_valid_4_tuple_returns_floats() -> None:
    assert box([1, 2, 3, 4]) == (1.0, 2.0, 3.0, 4.0)


def test_box_wrong_length_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        box([1, 2, 3])
    with pytest.raises(ValueError):
        box([1, 2, 3, 4, 5])


def test_box_string_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        box("1234")


def test_box_bytes_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        box(b"1234")


def test_box_non_sequence_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        box(42)


def test_box_invalid_element_replaced_with_zero_via_fnum() -> None:
    # fnum returns its default (0.0) on invalid input
    assert box(["x", 2, 3, 4]) == (0.0, 2.0, 3.0, 4.0)


# ── pt ──────────────────────────────────────────────────────────────


def test_pt_valid_2_tuple_returns_floats() -> None:
    assert pt([1.5, 2.5]) == (1.5, 2.5)


def test_pt_wrong_length_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        pt([1])
    with pytest.raises(ValueError):
        pt([1, 2, 3])


def test_pt_string_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        pt("12")


# ── deep_get ────────────────────────────────────────────────────────


def test_deep_get_existing_path_returns_value() -> None:
    assert deep_get({"a": {"b": {"c": 1}}}, ["a", "b", "c"]) == 1


def test_deep_get_missing_path_returns_default() -> None:
    assert deep_get({"a": 1}, ["b"], default="X") == "X"


def test_deep_get_intermediate_nonmapping_returns_default() -> None:
    assert deep_get({"a": "string"}, ["a", "b"], default=None) is None


def test_deep_get_empty_path_returns_root() -> None:
    assert deep_get({"a": 1}, []) == {"a": 1}


# ── pts_attr ────────────────────────────────────────────────────────


def test_pts_attr_formats_each_point_comma_separated() -> None:
    assert pts_attr([(1, 2), (3, 4)]) == "1,2 3,4"


def test_pts_attr_empty_returns_empty() -> None:
    assert pts_attr([]) == ""


def test_pts_attr_uses_fmt_for_floats() -> None:
    out = pts_attr([(1.5, 2.0)])
    assert out == "1.5,2"  # 2.0 formats as "2"


# ── _lorem ──────────────────────────────────────────────────────────


def test_lorem_default_returns_30_words() -> None:
    out = _lorem()
    assert len(out.split()) == 30


def test_lorem_zero_or_negative_uses_default_30() -> None:
    assert len(_lorem(0).split()) == 30
    assert len(_lorem(-5).split()) == 30


def test_lorem_capitalizes_first_word_and_ends_with_period() -> None:
    out = _lorem(5)
    assert out[0].isupper()
    assert out.endswith(".")


def test_lorem_n_words_returned() -> None:
    assert len(_lorem(7).split()) == 7


# ── _expand_lorem ───────────────────────────────────────────────────


def test_expand_lorem_lowercase_lorem_returns_30_words() -> None:
    out = _expand_lorem("lorem")
    assert len(out.split()) == 30


def test_expand_lorem_with_count_returns_n_words() -> None:
    out = _expand_lorem("lorem:5")
    assert len(out.split()) == 5


def test_expand_lorem_invalid_count_falls_back_to_30() -> None:
    out = _expand_lorem("lorem:notanumber")
    assert len(out.split()) == 30


def test_expand_lorem_non_lorem_string_returned_unchanged() -> None:
    assert _expand_lorem("hello world") == "hello world"


def test_expand_lorem_uppercase_marker_recognized() -> None:
    # Comparison is on lowercased input
    out = _expand_lorem("LOREM")
    assert len(out.split()) == 30


def test_expand_lorem_strips_whitespace_around_marker() -> None:
    out = _expand_lorem("  lorem  ")
    assert len(out.split()) == 30
