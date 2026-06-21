"""Documentation-portal toolchain for framegraph.

This internal package turns the deterministic API catalog
(`framegraph.docs.build_catalog`) plus the bundled examples into the
source Markdown for a MkDocs-Material site. It is the *generator* half
of the docs pipeline; the *extraction* half lives in `framegraph.docs`.

Single source of truth
----------------------
The catalog JSON is the only intermediate representation. Every page
this package emits is a pure function of that catalog (or of files on
disk for the gallery) — there is no second docstring parser, so the
portal cannot drift from the catalog that CI already drift-checks.

⚠ ARCHITECTURAL CONTRACT (PALS's LAW) — every stage that consumes
generated content treats it as untrusted: the coverage gate
(`framegraph._docsite.coverage`) fails the build when any public symbol
lacks a docstring, and the gallery validates each example document
against the Pydantic schema before embedding it.

Public surface
--------------
- `coverage` — docstring-coverage gate over the source tree.
- `generate` — catalog → Markdown reference pages (Phase 3).
- `gallery` — examples → rendered SVG + source pages (Phase 4).
"""

__all__: list[str] = []
