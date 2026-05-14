"""Inline-markdown → span list parser.

Converts a single text line containing **bold**, *italic*, and `code`
runs into a list of span dicts compatible with `spans_svg` (rich text)
and the per-line span path in `render_bullet_list`.

Scope is deliberately narrow:
  - `**…**` → {weight: bold}
  - `*…*`   → {italic: True}
  - `` `…` `` → {font: monospace}

Block-level markdown (headers, lists, links, blockquotes) is out of
scope — bullets are already expressed as YAML list items, headings as
typography roles. The parser is line-local and does not cross newlines.

Unbalanced delimiters are passed through as literal text — the loop
falls back to a single plain span if no closing delimiter is found.
This preserves the existing rendering of strings like "5 * 4 = 20" or
"ratio **0.47" that legitimately contain asterisks.
"""

from __future__ import annotations

import re
from typing import Any

# Token order matters: longer delimiters win so `**bold**` is not parsed
# as two adjacent `*…*` italic runs.
_TOKEN_RE = re.compile(
    r"(?P<bold>\*\*(?P<bold_text>[^*\n]+?)\*\*)"
    r"|(?P<italic>\*(?P<italic_text>[^*\n]+?)\*)"
    r"|(?P<code>`(?P<code_text>[^`\n]+?)`)"
)


def has_inline_markdown(text: str) -> bool:
    """Return True if `text` contains at least one *balanced* inline run.

    A bare asterisk that is not part of a `*…*` pair (e.g. `5 * 4 = 20`)
    must not count — otherwise we would route arithmetic strings through
    the spans path unnecessarily.
    """
    if not text or not isinstance(text, str):
        return False
    return _TOKEN_RE.search(text) is not None


def parse_inline_markdown(text: Any) -> list[dict[str, Any]]:
    """Parse `text` into a list of span dicts.

    Returns:
        A list shaped for `spans_svg`. Plain text yields a single
        ``{"text": "..."}`` span; markdown runs yield additional
        attributes (`weight`, `italic`, `font`). An empty / None input
        returns an empty list.
    """
    if text is None:
        return []
    s = str(text)
    if not s:
        return []

    spans: list[dict[str, Any]] = []
    cursor = 0
    for m in _TOKEN_RE.finditer(s):
        start, end = m.span()
        if start > cursor:
            spans.append({"text": s[cursor:start]})
        if m.group("bold") is not None:
            spans.append({"text": m.group("bold_text"), "weight": "bold"})
        elif m.group("italic") is not None:
            spans.append({"text": m.group("italic_text"), "italic": True})
        elif m.group("code") is not None:
            spans.append({"text": m.group("code_text"), "font": "monospace"})
        cursor = end
    if cursor < len(s):
        spans.append({"text": s[cursor:]})

    # If nothing matched, collapse to a single plain span (preserves
    # callers that always expect at least one span).
    if not spans:
        spans = [{"text": s}]
    return spans
