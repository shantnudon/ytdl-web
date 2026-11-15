.DEFAULT_GOAL := help
PY := .venv/bin/python
PIP := .venv/bin/pip
RUFF := .venv/bin/ruff

.PHONY: help install ui build-ui dev serve test lint format docker clean

help: ## Show available targets
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv, install python + npm dependencies
	python3 -m venv .venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install -e ".[dev]"
	cd frontend && npm install --no-fund --no-audit

ui: ## Run the Vite dev server (proxies /api to :8080)
	cd frontend && npm run dev

build-ui: ## Build the SPA into app/static
	cd frontend && npm run build

dev: build-ui ## Build the UI, then run the API with reload
	$(PY) -m app serve --reload

serve: build-ui ## Production-ish local run
	$(PY) -m app serve

test: ## Run the test suite
	$(PY) -m pytest -q

lint: ## Ruff
	$(RUFF) check .

format: ## Ruff autofix
	$(RUFF) check . --fix

docker: ## Build the container image
	docker build -t ytdlweb:local .

clean: ## Remove build artefacts (keeps data/)
	rm -rf app/static/assets app/static/index.html .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
