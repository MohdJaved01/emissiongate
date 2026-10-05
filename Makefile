# EmissionGate — see AGENTS.md for what each target does and which ones a human must run.
SHELL := /bin/bash
PY    := .venv/bin/python
EG    := .venv/bin/emissiongate
SEED  ?= 42
# Defaults come from .env.example (committed); your .env overrides them.
-include .env.example
-include .env
export
TOFU         ?= $(or $(EG_TOFU_BIN),tofu)
PROVIDER_DIR ?= $(or $(EG_TOFU_PLUGIN_DIR),.tofu-providers)

.PHONY: setup providers models estate demo-offline demo demo-live gate score compare bakeoff \
        test lint fmt agent-check codex-review grid-snapshot clean

# ---- one-time, network, human-run -------------------------------------------------------------
setup:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"
	@command -v $(TOFU) >/dev/null || echo "WARN: OpenTofu not found - install it, then run 'make providers'"
	@command -v ollama >/dev/null || echo "WARN: Ollama not found - only 'make demo-offline' will work"
	@test -f .env || cp .env.example .env

providers:
	cd tofu && $(TOFU) providers mirror $(abspath $(PROVIDER_DIR))
	@echo "Provider mirror ready in $(PROVIDER_DIR) - runs now need no network (ADR-0014)."

models:
	@for m in $(sort $(EG_MODEL_SMALL) $(EG_MODEL_LARGE)); do ollama pull $$m; done

# ---- runs ---------------------------------------------------------------------------------------
estate:
	$(EG) estate --seed $(SEED)

demo-offline: estate
	$(EG) run --mode offline --seed $(SEED) --approve

demo: estate
	$(EG) run --mode local --seed $(SEED) --approve

demo-live:
	@test -n "$$GITHUB_TOKEN" || (echo "Export GITHUB_TOKEN in this terminal (not in .env) first." && exit 1)
	@test -n "$(EG_ESTATE_REPO)" || (echo "EG_ESTATE_REPO is not set in .env" && exit 1)
	$(EG) run --mode live --seed $(SEED)

BASE ?= main
gate:
	$(EG) gate --estate-dir $(EG_ESTATE_DIR) --base $(BASE) --head HEAD

score:
	$(EG) score --latest

compare: estate
	$(EG) run --mode offline --seed $(SEED) --approve
	$(EG) run --mode local --seed $(SEED) --approve
	$(EG) score --compare-latest 2

bakeoff:
	$(EG) bakeoff --models "$(EG_BAKEOFF_MODELS)" --cases fixtures/llm_cases --out runs/bakeoff

grid-snapshot:
	$(EG) grid-snapshot --region eu-west-2 --out fixtures/grid/

# ---- quality ------------------------------------------------------------------------------------
test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

fmt:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

agent-check:
	python3 scripts/check_agent_files.py

codex-review:
	codex review - < docs/review/invariant-reviewer.md

clean:
	rm -rf runs/ data/ .estate/ .pytest_cache/ .ruff_cache/
