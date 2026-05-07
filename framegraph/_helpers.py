"""framegraph._helpers — Module-level pure helper functions.
Shared by renderer.py and all modules in framegraph/renderers/.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

Box = tuple[float, float, float, float]
Point = tuple[float, float]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def fnum(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if math.isfinite(n) and abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.3f}".rstrip("0").rstrip(".")


def sid(v: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(v))
    if not s or not re.match(r"^[A-Za-z_]", s):
        s = "id_" + s
    return s


def attrs(a: Mapping[str, Any]) -> str:
    out: list[str] = []
    for k, v in a.items():
        if v is None or v is False:
            continue
        if v is True:
            v = "true"
        out.append(f'{k}="{esc(v)}"')
    return " ".join(out)


def box(v: Any) -> Box:
    if not isinstance(v, Sequence) or isinstance(v, (str, bytes)) or len(v) != 4:
        raise ValueError(f"expected box [x,y,w,h], got {v!r}")
    return fnum(v[0]), fnum(v[1]), fnum(v[2]), fnum(v[3])


def pt(v: Any) -> Point:
    if not isinstance(v, Sequence) or isinstance(v, (str, bytes)) or len(v) != 2:
        raise ValueError(f"expected point [x,y], got {v!r}")
    return fnum(v[0]), fnum(v[1])


def deep_get(m: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    cur: Any = m
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def pts_attr(points: Sequence[Point]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


# ---------------------------------------------------------------------------
# Lorem-ipsum placeholder expansion
# ---------------------------------------------------------------------------

_LOREM_WORDS = [
    "Lorem",
    "ipsum",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipiscing",
    "elit",
    "sed",
    "do",
    "eiusmod",
    "tempor",
    "incididunt",
    "ut",
    "labore",
    "et",
    "dolore",
    "magna",
    "aliqua",
    "Ut",
    "enim",
    "ad",
    "minim",
    "veniam",
    "quis",
    "nostrud",
    "exercitation",
    "ullamco",
    "laboris",
    "nisi",
    "ut",
    "aliquip",
    "ex",
    "ea",
    "commodo",
    "consequat",
    "Duis",
    "aute",
    "irure",
    "dolor",
    "in",
    "reprehenderit",
    "in",
    "voluptate",
    "velit",
    "esse",
    "cillum",
    "dolore",
    "eu",
    "fugiat",
    "nulla",
    "pariatur",
    "Excepteur",
    "sint",
    "occaecat",
    "cupidatat",
    "non",
    "proident",
    "sunt",
    "in",
    "culpa",
    "qui",
    "officia",
    "deserunt",
    "mollit",
    "anim",
    "id",
    "est",
    "laborum",
    "Sed",
    "ut",
    "perspiciatis",
    "unde",
    "omnis",
    "iste",
    "natus",
    "error",
    "sit",
    "voluptatem",
    "accusantium",
    "doloremque",
    "laudantium",
    "totam",
    "rem",
    "aperiam",
    "eaque",
    "ipsa",
    "quae",
    "ab",
    "illo",
    "inventore",
    "veritatis",
    "et",
    "quasi",
    "architecto",
    "beatae",
    "vitae",
    "dicta",
    "sunt",
    "explicabo",
    "Nemo",
    "enim",
    "ipsam",
    "voluptatem",
    "quia",
    "voluptas",
    "sit",
    "aspernatur",
    "aut",
    "odit",
    "aut",
    "fugit",
    "sed",
    "quia",
    "consequuntur",
    "magni",
    "dolores",
    "eos",
    "qui",
    "ratione",
    "voluptatem",
    "sequi",
    "nesciunt",
    "neque",
    "porro",
    "quisquam",
    "est",
    "qui",
    "dolorem",
    "ipsum",
    "quia",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipisci",
    "velit",
]


def _lorem(n_words: int = 30) -> str:
    """Return N words of lorem ipsum, cycling through the word bank."""
    if n_words <= 0:
        n_words = 30
    words = []
    for i in range(n_words):
        w = _LOREM_WORDS[i % len(_LOREM_WORDS)]
        words.append(w)
    # Capitalise first word, add a period at the end
    if words:
        words[0] = words[0].capitalize()
        words[-1] = words[-1].rstrip(".") + "."
    return " ".join(words)


def _expand_lorem(text: str) -> str:
    """Expand lorem placeholder strings:
      "lorem"      → 30 words
      "lorem:N"    → N words
    Non-lorem strings are returned unchanged.
    """
    t = str(text).strip()
    tl = t.lower()
    if tl == "lorem":
        return _lorem(30)
    if tl.startswith("lorem:"):
        try:
            n = int(tl[6:].strip())
            return _lorem(n)
        except ValueError:
            return _lorem(30)
    return text
