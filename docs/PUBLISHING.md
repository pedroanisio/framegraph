---
disclaimer:
  notice: >-
    No information within this document should be taken for granted.
    Any statement or premise not backed by a real logical definition
    or verifiable reference may be invalid, erroneous, or a hallucination.
  generated_by: "Claude Opus 4.7 via Claude Code"
  date: "2026-05-08"
---

# Publishing FrameGraph to PyPI

## Disclaimer

This work is subject to the methodological caveats and commitments described in [@DISCLAIMER.md](../DISCLAIMER.md).
> No statement or premise not backed by a real logical definition or verifiable reference should be taken for granted.

---

This document covers the operational steps for cutting a release of
the `framegraph` Python package to PyPI. The CI workflow at
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) handles
the build and upload automatically on tag push using **PyPI
Trusted Publishing** (OIDC) — no API tokens are stored in the repo.

---

## One-time setup (already done for this project)

The project's `pyproject.toml` carries everything PyPI needs:

- `name = "framegraph"`, `version`, `description`, `readme`
- SPDX `license = "MIT"` + `license-files = ["LICENSE"]` (PEP 639)
- `[project.urls]` (Homepage, Repository, Documentation, Issues, Changelog)
- `[project.scripts] framegraph = "framegraph.cli:main"`
- `[tool.setuptools.package-data]` — packages in patterns catalog,
  curated sidecars, themes, stylesheets, and `py.typed`
- `Typing :: Typed` classifier (PEP 561)

The CI publish job is gated on `if: startsWith(github.ref, 'refs/tags/v')`
so only signed tag pushes ever trigger a release.

To configure trusted publishing on PyPI **for the first release**:

1. Create a PyPI account if one doesn't exist.
2. Pre-register the project name (`pypi.org/manage/account/publishing/`):
   - Owner: `pedroanisio`
   - Repository: `framegraph`
   - Workflow: `ci.yml`
   - Environment: `pypi`
3. The first publish from CI will then succeed without a token.

---

## Cutting a release

Each release follows the same five-step recipe. The example here
publishes `0.2.0`; substitute your version everywhere.

### 1. Verify the working tree is green

```sh
python -m pytest                       # 1283 tests, 0 failures
python tests/run_tests.py              # golden snapshots
ruff check . && ruff format --check .
mypy framegraph                        # 0 errors under strict mode
```

If any gate fails, do not proceed. CI will block the upload anyway.

### 2. Bump the version

Two places need to change in lockstep:

```sh
# pyproject.toml
sed -i 's/^version *= "[0-9.]*"/version     = "0.2.0"/' pyproject.toml

# framegraph/__init__.py
sed -i 's/^__version__ = "[0-9.]*"/__version__ = "0.2.0"/' framegraph/__init__.py
```

The version string must be [PEP 440](https://peps.python.org/pep-0440/)
compliant. Plain three-part `MAJOR.MINOR.PATCH` is the simplest path.
The project follows [Semantic Versioning 2.0](https://semver.org/)
under the contract documented in `CHANGELOG.md`:

- **MAJOR** — schema break: a v1.x YAML no longer renders correctly
  within the tolerance defined in `tests/tolerance.cfg`.
- **MINOR** — new YAML surface or features, fully backward-compatible
  with all prior MINOR versions in the same MAJOR series.
- **PATCH** — bug fixes only; no new YAML surface; all existing
  golden snapshots must pass.

### 3. Update the changelog

```sh
# Open CHANGELOG.md and add a new section at the top above [Unreleased]:
#
# ## [0.2.0] — YYYY-MM-DD
#
# ### Added
# - …
#
# ### Changed
# - …
#
# ### Fixed
# - …
```

Keep entries short and action-oriented. Move every relevant
"Planned" item from `[Unreleased]` into the new section.

### 4. Local build verification

Before tagging, confirm the package builds and validates locally:

```sh
rm -rf dist build framegraph.egg-info
python -m build                        # produces sdist + wheel under dist/
twine check dist/*                     # validates PyPI metadata
```

Both `framegraph-<version>-py3-none-any.whl` and
`framegraph-<version>.tar.gz` should report `PASSED`.

Optional: install the wheel into a clean venv and smoke-test the CLI.

```sh
python -m venv /tmp/fg-test
/tmp/fg-test/bin/pip install dist/framegraph-*.whl
/tmp/fg-test/bin/framegraph patterns list --has-sidecar --json | jq length
# → expect 17 (or whatever the current sidecar count is)
rm -rf /tmp/fg-test
```

### 5. Commit, tag, and push

```sh
git add pyproject.toml framegraph/__init__.py CHANGELOG.md
git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main v0.2.0
```

The `git push` of the tag triggers the CI `publish` job:

1. Re-runs the golden-snapshot suite and the lint/mypy gates
   (the `needs: [golden-snapshots, lint]` constraint).
2. Builds the sdist and wheel via `python -m build`.
3. Uploads to PyPI via `pypa/gh-action-pypi-publish@release/v1`,
   authenticating through OIDC against the `pypi` environment.

PyPI surfaces the new release at https://pypi.org/p/framegraph
within ~30 seconds.

---

## What's in a release wheel

Verify with `unzip -l dist/framegraph-<version>-py3-none-any.whl`:

| Path | Provenance |
|---|---|
| `framegraph/*.py` | Source tree |
| `framegraph/lib/tokens/*.yml` | Seven consulting token packs |
| `framegraph/lib/styles/*.yml` | Bundled stylesheet |
| `framegraph/lib/symbols/**/*.yml` | Shared symbol packs |
| `framegraph/data/patterns/*.yml` | 375-pattern catalog (slides-patter-a → slides-pattern-g) |
| `framegraph/data/fills/*.yml` | 17 curated `example_fill` sidecars |
| `framegraph/data/fills/README.md` | Sidecar authoring index |
| `framegraph/py.typed` | PEP 561 typed-package marker |

Anything not listed above is not in the wheel.

---

## Failure recovery

| Failure | Cause | Fix |
|---|---|---|
| `twine check` reports `unrecognized field 'license-file'` | `packaging` lib too old | `pip install --upgrade packaging` (≥24.2) |
| `python -m build` reports `invalid pyproject.toml config: project.urls.dependencies must be string` | `dependencies` key placed inside `[project.urls]` table | Move `[project.urls]` after every other `[project]` key |
| CI publish job fails with `403 Forbidden` | Trusted publishing not configured on PyPI | Re-do the one-time-setup step 2 |
| Wheel installs but catalog is missing at runtime | Pattern data files moved out of `framegraph/data/` | Restore the file or update `[tool.setuptools.package-data]` |
| Tagged version doesn't match `__version__` | Forgot to sync `framegraph/__init__.py` | Delete the tag (`git tag -d vX.Y.Z; git push origin :refs/tags/vX.Y.Z`), fix, re-commit, re-tag |

---

## See also

- [`pyproject.toml`](../pyproject.toml) — single source of truth for package metadata.
- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) — CI / publish workflow.
- [`CHANGELOG.md`](../CHANGELOG.md) — per-release notes.
- [`README.md`](../README.md) — package-level overview consumed as the PyPI long description.
