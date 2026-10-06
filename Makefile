.PHONY: help install lock check gates golden evals test openspec ci templates

PY      ?= python3
DPF     ?= $(PY) -m dpf
OPENSPEC ?= openspec
PRODUCT ?= --all
UV_COMPILE ?= uv pip compile --universal --python-version 3.10 --generate-hashes --custom-compile-command "make lock"

help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## install dpf (editable) with test dependencies, pinned by requirements/dev.txt (as CI does)
	$(PY) -m pip install --require-hashes -r requirements/dev.txt
	$(PY) -m pip install --no-deps -e .

lock: ## re-pin the hash-locked requirements/*.txt (needs uv); add --upgrade to move versions
	$(UV_COMPILE) pyproject.toml --extra dev -o requirements/dev.txt
	$(UV_COMPILE) requirements/dbt.in -o requirements/dbt.txt
	$(UV_COMPILE) requirements/templates.in -o requirements/templates.txt

check: ## framework validation and lint, then every gate up to G3 for every product
	$(DPF) check $(PRODUCT) --gate G3

gates: ## G4 too (fails until deployed-run evidence exists for the current build)
	$(DPF) check $(PRODUCT) --gate G4

golden: ## regenerate every golden copy, alternative engines included (review the diff!)
	$(DPF) generate --all --update-golden

evals: ## behavioural evals in tests/evals/
	$(DPF) eval

test: ## unit and contract tests
	$(PY) -m pytest

openspec: ## OpenSpec structure, strict
	$(OPENSPEC) validate --all --strict

ci: openspec check evals test ## everything CI runs
	$(DPF) generate --all --check

templates: ## render the Define-stage PDFs and worked examples (needs requirements/templates.txt)
	$(PY) templates/src/render.py
