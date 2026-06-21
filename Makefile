# framegraph — developer task runner
#
# Single source of truth for the local dev gate, example regeneration, and
# release recipe. CI (.github/workflows/ci.yml) should invoke `make check`
# so the gate has one definition. Canonical command incantations come from
# docs/PUBLISHING.md and AGENTS.md.

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

PACKAGE      := framegraph
PYPROJECT    := pyproject.toml

# Examples are versioned `.yml` sources with committed `.svg`/`.pdf` siblings.
EXAMPLE_YMLS := $(wildcard examples/*/*.yml)

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "framegraph — make targets"
	@echo ""
	@echo "  Install"
	@echo "    install         editable install (runtime only)"
	@echo "    install-dev     editable install + [dev] (test, lint, typecheck, metrics)"
	@echo "    install-pdf     editable install + [pdf] (raster PDF backend)"
	@echo "    install-pdf-vector  editable install + [pdf-vector] (selectable-text PDF)"
	@echo ""
	@echo "  Gate (matches docs/PUBLISHING.md release checklist)"
	@echo "    check           lint + typecheck + test + goldens (full release gate)"
	@echo "    test            pytest (unit + integration, coverage-gated)"
	@echo "    goldens         golden-snapshot regression harness"
	@echo "    validate-fills  validate every shipped sidecar against the catalog"
	@echo "    lint            ruff check + ruff format --check"
	@echo "    typecheck       mypy --strict on the package"
	@echo "    format          ruff format (autofix)"
	@echo "    fix             ruff check --fix + ruff format (autofix everything)"
	@echo ""
	@echo "  Artefacts"
	@echo "    examples        re-render every examples/*/*.yml to .svg (+ .pdf when sidecared)"
	@echo "    catalog         dump full Python API catalog to catalog.json"
	@echo "    patterns-list   list catalog patterns with sidecar presence (JSON)"
	@echo ""
	@echo "  Release"
	@echo "    build           build sdist + wheel via python -m build"
	@echo "    release VERSION=X.Y.Z   bump version in pyproject.toml + __init__.py, then tag"
	@echo ""
	@echo "  Housekeeping"
	@echo "    clean           remove build/, dist/, caches, coverage artefacts"

# ── Install ───────────────────────────────────────────────────────────────
.PHONY: install install-dev install-pdf install-pdf-vector
install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

install-pdf:
	$(PIP) install -e ".[pdf]"

install-pdf-vector:
	$(PIP) install -e ".[pdf-vector]"

# ── Gate ──────────────────────────────────────────────────────────────────
.PHONY: check test goldens lint typecheck format fix validate-fills
check: lint typecheck test goldens validate-fills

test:
	$(PYTHON) -m pytest

goldens:
	$(PYTHON) tests/run_tests.py --verbose

# Validate every shipped sidecar (framegraph/data/fills/) against the live
# catalog: pattern_id resolves, effective schema builds, example_fill
# round-trips. The pytest suite already enforces this per-sidecar
# (tests/integration/test_sidecar_fill_contract.py); this target runs the
# same contract as a standalone gate for local pre-push and scripting.
validate-fills:
	$(PYTHON) scripts/validate_fills.py

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy $(PACKAGE)

format:
	ruff format .

fix:
	ruff check --fix .
	ruff format .

# ── Artefacts ─────────────────────────────────────────────────────────────
# `examples` regenerates the committed .svg next to each .yml. PDFs are
# only attempted when the [pdf] extra is installed; the rule tolerates
# their absence so the SVG path still works without cairosvg.
.PHONY: examples catalog patterns-list
examples:
	@for yml in $(EXAMPLE_YMLS); do \
		out="$${yml%.yml}.svg"; \
		echo "  render  $$yml -> $$out"; \
		$(PYTHON) -m $(PACKAGE) render "$$yml" -o "$$out" || exit $$?; \
		pdf_out="$${yml%.yml}.pdf"; \
		if [ -f "$$pdf_out" ]; then \
			echo "  pdf     $$yml -> $$pdf_out"; \
			$(PYTHON) -m $(PACKAGE) render "$$yml" -o "$$pdf_out" --pdf || exit $$?; \
		fi; \
	done

catalog:
	$(PYTHON) -m $(PACKAGE) docs -o catalog.json

patterns-list:
	$(PYTHON) -m $(PACKAGE) patterns list --has-sidecar --json

# ── Release ───────────────────────────────────────────────────────────────
# Bumps the two version sites in lockstep (matches docs/PUBLISHING.md §2),
# runs the full gate, builds artefacts, and creates an annotated tag.
# Push the tag manually after inspection: `git push origin vX.Y.Z`.
.PHONY: build release
build:
	$(PYTHON) -m build

release:
ifndef VERSION
	$(error VERSION is required, e.g. `make release VERSION=0.2.0`)
endif
	@echo "Bumping to $(VERSION) in $(PYPROJECT) (single source of truth)"
	sed -i.bak -E 's/^version( *)= "[0-9]+\.[0-9]+\.[0-9]+"/version\1= "$(VERSION)"/' $(PYPROJECT)
	rm -f $(PYPROJECT).bak
	$(MAKE) check
	$(MAKE) build
	git add $(PYPROJECT)
	git commit -m "release: v$(VERSION)"
	git tag -a "v$(VERSION)" -m "framegraph v$(VERSION)"
	@echo ""
	@echo "Tag v$(VERSION) created locally. Push with:"
	@echo "    git push origin main && git push origin v$(VERSION)"

# ── Housekeeping ──────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf build/ dist/ *.egg-info $(PACKAGE).egg-info
	rm -rf .mypy_cache .ruff_cache .pytest_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
