---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 (1M context) via Claude Code"
  date: "2026-05-07"
---

# Proposal — Python Code-Style & Documentation Enhancement

**Scope.** `framegraph/` package (3,029 LOC across 13 files), test harness, CI, and contributor tooling.
**Goal.** Bring style, typing, and docstring hygiene to a level that matches the project's stated maturity (Beta, v2.0.0-dev) and supports the public-API contract advertised in [framegraph/__init__.py](../framegraph/__init__.py) and [pyproject.toml](../pyproject.toml).

---

## 1. Evidence Baseline (verified today, 2026-05-07)

| Signal | Value | Source |
|---|---|---|
| Ruff lint failures | **443** | `ruff check framegraph/ --statistics` (ruff 0.15.10) |
| Auto-fixable | **231 / 443** | same |
| Tracked Python LOC | 3,029 | `wc -l` over `framegraph/**/*.py` |
| Functions | 140 | `grep '^def\|^    def'` |
| Docstrings (`"""`) | 68 occurrences (≈34 docstrings) | `grep '"""'` |
| Mypy job in CI | runs with `continue-on-error: true` | [.github/workflows/ci.yml:75](../.github/workflows/ci.yml#L75) |
| Mypy strict mode | **off** (`strict = false`) | [pyproject.toml:115](../pyproject.toml#L115) |
| Ruff line-length | 100 | [pyproject.toml:105](../pyproject.toml#L105) |
| Target Python | 3.10 | [pyproject.toml:106](../pyproject.toml#L106) |
| Pre-commit config | absent (only declared as dev dep) | `.pre-commit-config.yaml` not present |

### Ruff failures by class (top offenders)

| Code | Count | Meaning |
|---|---:|---|
| `E701` | 104 | Multiple statements on one line (colon) |
| `F401` | 97 | Unused imports |
| `UP006` | 75 | Pre-PEP-585 generics (`Dict`/`List`/`Tuple`) |
| `UP035` | 42 | Deprecated `typing` imports |
| `E702` | 31 | Multiple statements on one line (semicolon) |
| `F811` | 20 | Redefined-while-unused (often duplicate type aliases) |
| `E402` | 16 | Module-import-not-at-top |
| `I001` | 14 | Unsorted imports |
| `UP045` | 11 | Non-PEP-604 `Optional` |
| `E722` | 6 | Bare `except:` |
| `E741` | 6 | Ambiguous variable name |
| `B904` | 1 | `raise … from` missing inside `except` |
| `F821` | 1 | Undefined name (likely real bug) |

Concrete examples worth flagging:

- Bare excepts that swallow type errors silently:
  - `except: return default` at [_helpers.py:32, 37, 156, 161](../framegraph/_helpers.py#L32) and [renderer.py:93](../framegraph/renderer.py#L93)
- Duplicate type aliases (cause of `F811`): `Box`/`Point` defined twice in [_helpers.py:10-11 & 18-19](../framegraph/_helpers.py#L10).
- Untyped first argument across the renderer plug-in API: `def render_rect(r, obj: …)` etc. in [renderers/shapes.py](../framegraph/renderers/shapes.py), [renderers/layout.py:14, 147, 192, 221](../framegraph/renderers/layout.py#L14), [renderers/text_objects.py:9](../framegraph/renderers/text_objects.py#L9). `r` is the renderer instance; this is the public extension surface and should be typed.
- One pure-`def` (no docstring) example surface: [renderers/shapes.py:9](../framegraph/renderers/shapes.py#L9) — both `render_rect` and `render_ellipse` lack module/function docstrings, despite being entry points enumerated in `RENDERERS`.

> ⚠ Note: `F821` (undefined name) is a real correctness signal, not a style issue. It must be triaged before any blanket "auto-fix everything" pass.

---

## 2. Gap Analysis vs. Stated Standards

The project already declares the right tools (ruff, mypy, pre-commit) in [pyproject.toml](../pyproject.toml#L62) but the configuration and enforcement are weaker than CLAUDE.md's "production-ready code only" core principle requires.

| Axis | Current | Target |
|---|---|---|
| Lint enforcement | Advisory in CI for everything except hard ruff failures (and ruff currently has 443 issues) | Zero ruff issues; pre-commit hook prevents regressions |
| Type checking | `strict=false`, advisory in CI | `strict=true` for `framegraph/`; relaxed for `tests/`; CI failure on regression |
| Docstrings | ~24 % of functions | 100 % of public API + every entry in `RENDERERS` registries |
| Public renderer-plugin contract | `r: Any` (untyped) | A `Protocol` (`RendererContext`) with the methods plug-ins call: `fill_value`, `stroke_attrs`, `rect_stroke`, `group_attrs`, `color`, etc. |
| Style of `def` bodies | Many `if cond: return …` and `;`-joined statements (135 single-line E701/E702 hits) | One statement per line — readability per PEP 8 |
| Imports | Unsorted, duplicates, deprecated `typing.{Dict,List,Tuple,Optional,Union}` | PEP 604 unions / PEP 585 generics; `from __future__ import annotations` already present |
| Pre-commit | Not wired | `.pre-commit-config.yaml` runs ruff (lint+format) and mypy in `framegraph/` |
| Line length | 100 | Keep at **100** (project precedent overrides skill default of 120 — diffs are smaller and the codebase already conforms) |

---

## 3. Proposed Plan (incremental, each step independently shippable)

Each step is sized XS / S / M / L per CLAUDE.md (no time estimates).

### Step 1 — Auto-fix the safe 231 — **XS**

```bash
ruff check framegraph/ --fix         # 231 fixes; no semantics
ruff format framegraph/              # whitespace + quotes
python tests/run_tests.py            # all 35 goldens must still pass
```

Expected residue after this step: ~212 issues (the unfixable ones).

### Step 2 — Hand-fix the residual ruff issues — **S**

Triage in this order:

1. `F821` (undefined name) — possible real bug, fix first.
2. `F811` (redefined-while-unused) — collapse the duplicate `Box`/`Point` aliases in `_helpers.py`.
3. `E722` bare excepts — replace with `except (TypeError, ValueError)` in [_helpers.py](../framegraph/_helpers.py) and [renderer.py:93](../framegraph/renderer.py#L93). Bare `except:` also catches `KeyboardInterrupt` and `SystemExit`, which is a real defect in CLI tooling.
4. `B904` — add `raise X from exc`.
5. `E701`/`E702` (135 instances) — split single-line ifs and semicolon chains. Mostly mechanical, large diff but no behavior change. Goldens are the safety net.
6. `E402`, `E741` — case-by-case; `E741` (`l`, `I`, `O` names) likely needs renaming.

### Step 3 — Type the renderer plug-in contract — **M**

Add a `Protocol` to `framegraph/_types.py` describing what every `render_*` function expects from its `r` argument. Then update each function signature in `framegraph/renderers/*.py`:

```python
# framegraph/_types.py
from typing import Any, Mapping, Protocol

class RendererContext(Protocol):
    yaml_source_dir: str
    def fill_value(self, v: Any, default: str = ...) -> str: ...
    def stroke_attrs(self, s: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def rect_stroke(self, obj: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def group_attrs(self, obj: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def color(self, v: Any, default: str = ...) -> str: ...
    # …add the rest as discovered while typing the renderers
```

Then:

```python
def render_rect(r: RendererContext, obj: Mapping[str, Any]) -> str: ...
```

Why this matters: `register(type_name, fn)` is advertised as a v2.0 public API. Without a typed contract, third-party plug-in authors are guessing at what `r` provides — exactly the kind of "untrusted, incomplete by default" surface CLAUDE.md says must be made explicit.

### Step 4 — Docstring sweep on the public API — **M**

Mandatory docstrings (Google style, per CLAUDE.md "Markdown over DOCX; TS over JS" cousin rule for Python prose):

- All three classes in `__init__.py` (`FrameGraphRenderer`, `FrameGraphLibrary`, `FrameGraphDeckRenderer`) — already partial in `__init__.py` module docstring; needs class- and method-level coverage.
- Every function listed in a `RENDERERS` dict (currently 14 object types).
- Every method on `FrameGraphRenderer` that the `RendererContext` Protocol exposes.
- The CLI subcommand handlers in [cli.py](../framegraph/cli.py).

Template (matches Google style):

```python
def render_rect(r: RendererContext, obj: Mapping[str, Any]) -> str:
    """Render a `rect` object to an SVG `<g><rect/></g>` string.

    Args:
        r: Active renderer context — supplies fill/stroke/group attribute
            resolution against the document's token tables.
        obj: The YAML object node. Recognized keys: `box`, `radius`,
            `fill`, `stroke`, `outer_ring`, `id`, `class`.

    Returns:
        SVG fragment. When `outer_ring` is set, two stacked `<rect>`
        elements are emitted; the ring is drawn first so the fill
        covers the interior.
    """
```

Out of scope for this step: private helpers (`_lorem`, `_expand_lorem`) and `_helpers.py` internals — these get one-line docstrings only.

### Step 5 — Tighten config + wire pre-commit + flip CI to enforcing — **S**

**5a. Update [pyproject.toml](../pyproject.toml):**

```toml
[tool.ruff.lint]
select = [
    "E", "F", "W", "I", "B", "C4", "UP", "SIM",
    "RET",   # flake8-return  — catches dead-end branches
    "PT",    # flake8-pytest-style for tests/
    "PL",    # selected pylint rules
    "D",     # pydocstyle — Google style
]
ignore = ["E501", "PLR0913"]      # line length handled by formatter; many-args ok in renderer fns

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D", "PLR2004"]    # docstrings + magic-numbers tolerated in tests
"framegraph/_helpers.py" = ["D"] # internal helpers exempt
"**/__init__.py" = ["F401"]      # explicit re-exports

[tool.mypy]
python_version         = "3.10"
strict                 = true
ignore_missing_imports = true
warn_unused_ignores    = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

**5b. Add `.pre-commit-config.yaml`:**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        files: ^framegraph/
        additional_dependencies: [types-PyYAML]
```

**5c. Flip [.github/workflows/ci.yml](../.github/workflows/ci.yml) lint job to enforcing:**

```yaml
- name: mypy
  run: mypy framegraph/
  # remove: continue-on-error: true
```

This step **must come last**. Flipping CI to enforcing before Steps 1–4 are merged would block the project on its own backlog.

### Step 6 (optional, follow-up) — Test typing & coverage gate — **L**

CLAUDE.md mandates 80 % library coverage. The current suite is **golden-snapshot only** ([tests/run_tests.py](../tests/run_tests.py)) — strong for visual regression, weak for branch coverage of error paths. Add unit tests for `_helpers.py` invariants (`box`, `pt`, `fmt`, `attrs`) and assert coverage in CI via `coverage.py`.

Treat Step 6 as a separate proposal — listed here for completeness, not bundled.

---

## 4. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Mechanical reformat (E701/E702 split) breaks a golden | Run [tests/run_tests.py](../tests/run_tests.py) after every commit; tolerance is 1 % per [tests/tolerance.cfg](../tests/tolerance.cfg) |
| `strict=true` mypy reveals deep dynamic-typing patterns the renderer relies on | Type the `RendererContext` Protocol first (Step 3); allow `Any` in narrow, justified spots with `# type: ignore[reason]` |
| Public-API drift: tightening signatures breaks downstream `register(...)` users | None known yet — v2.0.0-dev is unreleased. Document the typed protocol in CHANGELOG as the v2.0 contract |
| `from __future__ import annotations` already present in most files; the codebase is ready for PEP 604 unions | No mitigation needed — confirms `UP006`/`UP007`/`UP035`/`UP045` auto-fixes are safe |

---

## 5. Acceptance Criteria

- `ruff check framegraph/` exits 0.
- `ruff format --check framegraph/` exits 0.
- `mypy framegraph/` exits 0 under `strict = true`.
- `python tests/run_tests.py` passes — all 35 goldens within 1 % tolerance.
- Every function listed in any `RENDERERS` dict has a Google-style docstring.
- `RendererContext` Protocol is exported and used by every `framegraph/renderers/*.py` function.
- `.pre-commit-config.yaml` exists and `pre-commit run --all-files` passes.
- CI lint job no longer carries `continue-on-error: true`.

---

## 6. What This Proposal Is *Not*

- **Not a refactor of `renderer.py`'s 873 LOC orchestrator.** That's a separate architectural concern; this proposal touches behavior only via the auto-fix pass and the bare-except hardening.
- **Not a coverage push.** That's Step 6, broken out.
- **Not a 120-char line-length migration.** Project precedent is 100; the skill's default is overridden by codebase convention.
- **Not a docstring sweep of every private helper.** Public API and renderer registry only.

---

## 7. Recommended Sequencing

1. Step 1 (auto-fix) — single PR, large diff, no semantics, gated on goldens.
2. Step 2 (hand-fix residue) — single PR, includes `F821` triage.
3. Step 3 (Protocol type) — single PR, typed renderer surface.
4. Step 4 (docstring sweep) — single PR, prose only.
5. Step 5 (config + CI flip) — single PR, lands the enforcement.

Each PR is independently revertable. Each PR keeps the goldens green.

---

## 8. Decision Requested

Approve / reject each step. Default recommendation: **approve Steps 1–5; defer Step 6 to a separate proposal.**
