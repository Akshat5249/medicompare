SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE := docker compose
TEST_RUN := $(COMPOSE) --profile test run --rm -T backend-test
TOOLS_NET := medicompare_default

.PHONY: help up up-real down seed-demo-users lint types test-backend test-safety test-frontend e2e security perf smoke data-check docs-check verify evaluate backup-test package

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "%-18s %s\n",$$1,$$2}'

up: ## Build and start the full stack, then add local demo accounts
	$(COMPOSE) up -d --build --wait
	$(COMPOSE) exec -T backend python -m app.cli seed-demo-users

up-real: ## Fresh database with real NPPA data only, and no demo data
	$(COMPOSE) down -v
	INCLUDE_DEMO_DATA=false $(COMPOSE) up -d --build --wait

down: ## Stop the stack
	$(COMPOSE) down

lint: ## Ruff, ESLint and Prettier
	$(TEST_RUN) sh -c "ruff check app tests && ruff format --check app tests"
	cd frontend && npx eslint src e2e && npx prettier --check src e2e messages

types: ## mypy and tsc
	$(TEST_RUN) sh -c "mypy"
	cd frontend && npx tsc --noEmit

test-backend: ## pytest with coverage gates (85% overall, 95% on safety, matching and pricing)
	$(TEST_RUN) sh -c "pytest --cov=app --cov-report=json:../verification/coverage-backend.json --cov-report=term --cov-fail-under=85 && python ../scripts/check_core_coverage.py ../verification/coverage-backend.json"

test-safety: ## The safety invariant suite on its own
	$(TEST_RUN) sh -c "pytest -m safety -v --no-header"

test-frontend: ## Vitest with coverage gate
	cd frontend && npx vitest run --coverage

e2e: ## Playwright on desktop and mobile with axe and video, against the running stack
	cd frontend && npx playwright test

security: ## Bandit, pip-audit, npm audit, Trivy, Gitleaks
	bash scripts/security_scan.sh

perf: ## Locust load test against the running stack
	bash scripts/load_test.sh

smoke: ## Smoke tests against the running stack
	bash scripts/smoke.sh

data-check: ## Data-quality checks on the seeded database
	$(COMPOSE) exec -T backend python -m app.cli quality

docs-check: ## Mermaid diagrams, OpenAPI and internal links
	bash scripts/docs_check.sh

evaluate: ## Regenerate the synthetic set, run both OCR engines and score them
	bash scripts/fetch_fonts.sh
	$(TEST_RUN) sh -c "python ../evaluation/generate.py --count 600 --seed 20261105 && python ../evaluation/run_ocr.py --engine tesseract && python ../evaluation/run_ocr.py --engine rapidocr && python ../evaluation/evaluate.py"

backup-test: ## Back up, wipe and restore into a scratch database, and compare
	bash scripts/backup_restore_test.sh

verify: ## Run every gate from Section 10 and write verification/logs
	bash scripts/verify.sh

package: ## Build medicompare.zip and SHA256SUMS
	bash scripts/package.sh
