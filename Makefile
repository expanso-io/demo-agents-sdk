# =============================================================================
# demo-agents-sdk — local quality + smoke targets.
# Tests use `uv run` so dev deps install on first invocation.
# =============================================================================

.PHONY: help test test-fast test-smoke lint format validate compose-config build verify clean

help:
	@echo "Targets:"
	@echo "  test           Run all pytest tests except smoke (no Docker required)"
	@echo "  test-smoke     Run the Docker E2E smoke test (builds runner image)"
	@echo "  test-all       test + test-smoke"
	@echo "  lint           ruff check"
	@echo "  format         ruff format"
	@echo "  validate       expanso-cli validate every pipeline YAML"
	@echo "  compose-config validate the one-shot Docker runners"
	@echo "  build          docker compose build runner image"
	@echo "  verify         lint + test + validate + compose-config (no Docker build)"
	@echo "  clean          remove pytest/ruff caches"

test test-fast:
	uv run --group dev pytest -m "not smoke"

test-smoke:
	uv run --group dev pytest -m smoke

test-all:
	uv run --group dev pytest

lint:
	uv run --group dev ruff check gateway/ scripts/ tests/

format:
	uv run --group dev ruff format gateway/ scripts/ tests/

validate:
	@for f in pipelines/*.yaml; do \
		expanso-cli job validate --offline "$$f" >/dev/null 2>&1 \
			&& echo "PASS: $$(basename $$f)" \
			|| { echo "FAIL: $$(basename $$f)"; exit 1; }; \
	done

compose-config:
	@docker compose config --quiet && echo "compose config: OK"

build:
	docker compose build gateway-subprocess

verify: lint test validate compose-config
	@echo "All quality checks passed."

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__
