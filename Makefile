.PHONY: test lint fmt dev validate

export PYTHONPATH := backend
export PYTHONDONTWRITEBYTECODE := 1

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
RUFF := $(if $(wildcard .venv/bin/ruff),.venv/bin/ruff,$(PYTHON) -m ruff)

test:
	$(PYTHON) -m pytest
	node --test tests/frontend/*.mjs

lint:
	$(RUFF) check backend tests
	$(RUFF) format --check backend tests

fmt:
	$(RUFF) check --fix backend tests
	$(RUFF) format backend tests
	terraform fmt -recursive

dev:
	$(PYTHON) -m devserver

validate:
	terraform fmt -check -recursive
	terraform -chdir=infra init -backend=false
	terraform -chdir=infra validate
	terraform -chdir=infra/bootstrap init -backend=false
	terraform -chdir=infra/bootstrap validate
