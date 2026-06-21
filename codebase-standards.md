---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.8 via Claude Code"
  date: "2026-06-21"
---

# codebase-standards

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](./DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

---

Authoritative, consolidated standards for the **framegraph** repository. Every
rule below is enforced by config (`pyproject.toml`, `.pre-commit-config.yaml`,
`Makefile`) or mandated by `CLAUDE.md` / `PURPOSE.md`. Where this file and the
prose in `CLAUDE.md` disagree, the enforced config value wins; such conflicts
are flagged in §17.

Source of truth per topic:

| Topic | Source of truth |
|---|---|
| Toolchain, lint, types, coverage | `pyproject.toml` |
| Commit-time gate | `.pre-commit-config.yaml` |
| Full release gate | `Makefile` (`make check`) |
| CLI contracts | `AGENTS.md` |
| Mission, non-goals | `PURPOSE.md` |
| Process, behavior, enforcement | `CLAUDE.md` |

---

## 1. Language and runtime

- Source language: Python. New code is Python; this overrides the generic
  "TypeScript over JavaScript" default in `CLAUDE.md`, which applies to
  greenfield non-Python work only.
- Minimum runtime: Python 3.10 (`requires-python = ">=3.10"`).
- Supported: 3.10, 3.11, 3.12.
- Lint/type target: `py310`.
- Package is typed: ships `py.typed`; all public API carries type annotations.

## 2. Dependencies

- Runtime deps are minimal and pinned by floor: `PyYAML>=6.0`, `pydantic>=2.7`.
- All other capabilities are optional extras: `test`, `metrics`, `pdf`,
  `pdf-vector`, `dev`, and `docs` (the last is in-flight — see §17).
- No new runtime dependency without justification. Pure-Python rendering is a
  load-bearing commitment (`PURPOSE.md`); do not pull in a browser/GUI/graphics
  stack into the core.
- `requirements`/lock state lives in `uv.lock`. Do not hand-edit it.

## 3. Code style (ruff)

- Formatter and linter: `ruff` (`>=0.4`; pre-commit pins `v0.15.10`).
- Line length: 100.
- Enabled rule families: `E`, `F`, `W`, `I`, `UP`, `B`, `C4`, `SIM`, `RET`, `D`.
- Ignored: `E501` (formatter owns line length), `D203`, `D213`.
- Docstring convention: Google (`D211` + `D212` retained).
- `PL*`/`PLR*`/`PLW*` and `PLC0415` are intentionally NOT enabled. Do not
  re-enable without a documented defect pattern.
- Per-file `D` exemptions (`[tool.ruff.lint.per-file-ignores]`):
  `framegraph/_helpers.py`, `framegraph/library.py`, `tests/**`. The enforced
  value for each is `["D"]` only. (A pyproject comment claims `_helpers.py` is
  also `F401`-exempt for re-exports, but the config does not grant it — see §17.)
- Formatting is mandatory at commit; no formatter diffs may land.
- Autofix: `make fix` (`ruff check --fix . && ruff format .`).

## 4. Type checking (mypy)

- `mypy` strict mode is ON and enforcing (`>=1.10`; pre-commit pins `v1.10.0`).
- `python_version = "3.10"`, `ignore_missing_imports = true`,
  `warn_unused_ignores = true`.
- Plugin: `pydantic.mypy`. Pydantic settings: `init_typed = true`,
  `init_forbid_extra = false`, `warn_required_dynamic_aliases = true`.
- mypy runs over `framegraph/` only.
- Loosening strict mode requires explaining, in writing, what regressed.
- Command: `make typecheck` (`mypy framegraph`).

## 5. Testing

- Framework: `pytest` (`>=8.0`) with `pytest-cov` and `hypothesis>=6.100`.
- Discovered trees: `tests/unit`, `tests/integration`. Files: `test_*.py`.
- Default `addopts`: `-v --tb=short --cov=framegraph --cov-branch
  --cov-report=term-missing --cov-fail-under=90`.
- Tests must be deterministic, isolated, and realistic.
- TDD is required: Red → Green → Refactor → Cleanup. Write the failing test
  first. No code ships without tests.
- Run tests after every change; do not batch validation to the end.
- Command: `make test` (`python -m pytest`).

## 6. Coverage

- Enforced gate: **90% branch coverage**, build fails below
  (`--cov-fail-under=90`; `[tool.coverage.report] fail_under = 90`).
- Branch coverage is on (`--cov-branch`, `branch = true`).
- Measured source: `framegraph`. Omitted: `framegraph/__main__.py`, `tests/*`.
- Exclusion pragmas: `pragma: no cover`, `raise NotImplementedError`,
  `if __name__ == .__main__.:`, `if TYPE_CHECKING:`, `@abstractmethod`, `...`.

## 7. Golden-snapshot regression

- Golden harness is a release requirement, not optional (`PURPOSE.md`).
- Harness: `python tests/run_tests.py` (standalone; NOT pytest-discovered).
- Drift tolerance: `tests/tolerance.cfg`. A change that pushes prior v1.x YAML
  output outside tolerance is a MAJOR (breaking) change.
- Shipped sidecars are contract-validated: `scripts/validate_fills.py` and
  `tests/integration/test_sidecar_fill_contract.py` assert every
  `framegraph/data/fills/` sidecar resolves its `pattern_id`, builds its
  effective schema, and round-trips its `example_fill`.
- Commands: `make goldens`, `make validate-fills`.

## 8. Quality gate

- Full local gate: `make check` =
  `lint + typecheck + test + goldens + validate-fills`.
- CI (`.github/workflows/ci.yml`) does NOT invoke `make check`. It re-implements
  the gate as independent jobs: `golden-snapshots` (`python tests/run_tests.py`),
  `pytest` (`python -m pytest`), `lint` (`ruff check framegraph/` +
  `ruff format --check framegraph/` + `mypy framegraph/`), and `wheel-smoke`. CI
  scopes ruff/mypy to `framegraph/`, whereas `make lint` runs over the whole repo
  (`ruff check .`) — so the local gate is broader than CI (see §17).
- A change is not "done" until `make check` passes.

## 9. Pre-commit and CI

- Install hooks per clone: `pip install pre-commit && pre-commit install`.
- Commit-time hooks: `ruff --fix`, `ruff-format`, `mypy` (over `^framegraph/`,
  with `types-PyYAML` + `pydantic>=2.7` as additional deps).
- Pre-commit mirrors the CI lint job. CI is the source of truth; pre-commit is
  the same gate run earlier.
- Run all hooks manually: `pre-commit run --all-files`.

## 10. Versioning and releases

- Semantic versioning (`major.minor.patch`). Single source of truth for the
  package version: `pyproject.toml` `[project] version`. `framegraph/__init__.py`
  holds NO version literal — it resolves `__version__` at runtime via
  `importlib.metadata.version("framegraph")`, falling back to
  `framegraph/_version.resolve_version()` (which parses `pyproject.toml`) for
  uninstalled source trees. There is no second literal to keep in lockstep;
  enforced by `tests/unit/test_version_consistency.py`
  (`test_init_py_has_no_hardcoded_version_literal`).
- Schema semver policy:
  - **MAJOR** — schema-breaking: prior v1.x YAML no longer renders within
    `tests/tolerance.cfg`.
  - **MINOR** — new YAML keys/object types/renderer features, fully
    backward-compatible within the same MAJOR series.
  - **PATCH** — bug/renderer/doc fixes, no new YAML surface; must pass all
    existing goldens within tolerance.
- Backward compatibility for released v1.x YAML is a load-bearing constraint.
- Release recipe: `make release VERSION=X.Y.Z` → runs full gate, builds
  artifacts, commits, annotated-tags. CI publishes to PyPI on tag push.
- `CHANGELOG.md` is updated every release.

## 11. Commit conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `release:`.
- AI-generated artifacts are labeled with their source model/tool (in metadata,
  frontmatter, or commit trailer).

## 12. Documentation standards

- Default prose format: Markdown (`.md`). DOCX only on explicit request.
- Every Markdown document produced by an AI agent MUST carry the disclaimer
  YAML frontmatter (`disclaimer.notice`, `generated_by`, `date`); `generated_by`
  identifies model + tool, `date` is the generation date (`YYYY-MM-DD`). Only
  exemption: explicit per-file user opt-out.
- Every `README.md` MUST reference `@DISCLAIMER.md` via a relative path matched
  to its depth (root `./`, one level `../`, two levels `../../`), placed after
  the title and before the first content section.
- Every README linking down to sub-directories links back up to the root
  `README.md`.
- Default language is English (EN-US) for code, comments, commits, docs, and
  agent output. PT-BR only when the user requests it, for bilingual
  project-level docs, or for a PT-BR audience; when both appear, English is
  primary.
- No time estimates (hours/days/weeks). Use complexity scale: XS / S / M / L / XL.

## 13. File-level agent metadata (FLAM)

- Before editing any file, check for embedded metadata:
  Python `__file_meta__`; Markdown frontmatter `role`/`rules`; TS/JS
  `export const __file_meta__` or JSDoc `@file_meta`; or a `<file>.meta.json`
  sidecar.
- When present: respect `status` (`frozen` = do not edit; `deprecated` = warn);
  follow `rules` (`error` = hard fail, `warning` = should follow); check
  `forbidden_patterns` against your output; run any referenced `test_ref`.
- Never remove or weaken an existing metadata block.

## 14. Architecture and purpose constraints

- Never propose changes that conflict with `PURPOSE.md`.
- Do not justify decisions primarily by the current state of the code; move
  toward the target state in `PURPOSE.md`.
- Core commitments: YAML is the authoring surface; SVG is the primary output;
  pure-Python rendering stays first-class; regression testing is a release
  requirement; v1.x YAML backward compatibility holds.
- Non-goals (do not build): WYSIWYG editor; browser-only rendering stack;
  interactive presentation runtime; general-purpose scientific charting
  replacement; constraint-solver layout engine for every diagram class.
- Document significant architecture decisions with rationale and trade-offs.
- Fix root causes, not symptoms (5-Whys before patching).
- Production-ready code only: no placeholders, stubs, or `TODO: implement later`.
- Quality regressions are fixed, not attributed to prior sessions.

## 15. LLM output verification (PALS's Law)

- LLMs statistically produce errors: omissions, hallucinations, partial
  completions, schema violations, silent failures.
- Any pipeline/agent/workflow consuming LLM output MUST treat that output as
  untrusted, incomplete, and unverified by default.
- Absence of an explicit verification layer is an architectural defect, not a
  downstream bug — regardless of how correct the output looks.
- Functions calling an LLM carry the PALS's Law contract banner (see
  `CLAUDE.md`).

## 16. Agent behavioral constraints (ranked)

Ranked; higher rank wins on conflict.

1. **Unbiased over flattering** — state flaws directly; no hedging or
   agreeableness padding.
2. **Formalization means research** — concrete, correct math; full provenance;
   verifiable citations (theorem/paper-with-DOI/spec/shown derivation). Never
   fabricate references, theorems, API signatures, or data. "I cannot verify
   this" is always acceptable.
3. **English over Portuguese** (see §12).
4. **Markdown over DOCX; TypeScript over JavaScript** (Python overrides the
   latter in this repo — see §1).
5. **Mandatory disclaimer frontmatter** in all Markdown (see §12).
6. **Feedback is not a source of truth** — evaluate feedback as a claim; accept
   sound parts and explain, refute unsound parts and explain; never silently
   comply with feedback that breaks a standard here.
7. **Skill assertion gate** — if a Claude Code skill matches the request,
   invoke it instead of a freeform response.
8. **Execution discipline** — when a task is clear, execute it. No planning
   theatre, no approval-seeking on obvious subtasks, no N-alternatives when one
   is correct, no "complexity" stalling. **No deferrals**: only the operator may
   authorize postponing a requested task.

## 17. Known config/prose discrepancies

The enforced value governs the body above in every case; each entry names the
stale source for reconciliation.

- **Coverage prose vs gate.** `CLAUDE.md` §Testing states "80% coverage for
  libraries, 60% for CLIs." The enforced gate is **90% branch coverage**
  (`pyproject.toml` `--cov-fail-under=90`, `[tool.coverage.report] fail_under =
  90`). Reconcile the `CLAUDE.md` prose to 90%.
- **CI does not invoke `make check`.** The `Makefile` header comment says CI
  "should invoke `make check` so the gate has one definition," but
  `.github/workflows/ci.yml` re-implements the gate as separate jobs and never
  calls `make`. The two definitions can drift: CI scopes ruff/mypy to
  `framegraph/`, while `make lint` lints the whole repo (`ruff check .`).
  Reconcile by making CI call `make check`, or by documenting two intentional
  definitions.
- **`_helpers.py` F401 exemption is comment-only.** The
  `[tool.ruff.lint.per-file-ignores]` comment in `pyproject.toml` states
  `_helpers.py` is "Also exempt from F401," but the enforced value is `["D"]`
  only. If the exemption is required, add `"F401"` to the list; otherwise delete
  the misleading comment.
- **Makefile version prose vs recipe.** The `make release` help line ("bump
  version in pyproject.toml + `__init__.py`") and the release-section comment
  ("Bumps the two version sites in lockstep") describe a two-site bump, but the
  recipe seds only `pyproject.toml` — correct per §10 (single source). Reconcile
  the Makefile prose to single-source.
- **In-flight documentation portal (aspirational, not a standard yet).**
  `pyproject.toml` adds a `docs` extra and the `Makefile` adds `install-docs`,
  `portal-gen`, `portal`, `portal-serve`, `portal-check`, and `docs-coverage`
  targets backed by `framegraph._docsite`. These are **not gated**:
  `docs-coverage` / `portal-check` are absent from `.github/workflows/ci.yml`
  and `.pre-commit-config.yaml` (despite a Makefile comment claiming CI and
  pre-commit use `docs-coverage`), and `framegraph/_docsite/` is untracked.
  Treat as aspirational. When committed and wired into CI, fold the
  docstring-coverage gate into §6/§7, the portal build into §8, and the targets
  into §9.

---

[↑ Back to root README](./README.md)
