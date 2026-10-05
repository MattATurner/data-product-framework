.PHONY: help install check gates golden evals test openspec ci

PY      ?= python3
DPF     ?= $(PY) -m dpf
OPENSPEC ?= openspec
PRODUCT ?= --all

help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## install dpf (editable) with test dependencies
	$(PY) -m pip install -e '.[dev]'

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
