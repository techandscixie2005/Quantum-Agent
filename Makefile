SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
UV ?= uv
CHECK_JSONSCHEMA_VERSION ?= 0.38.0
MANIFEST ?= content/quantum_course/manifest.toml
GRAPH_SYNC_BATCH_SIZE ?= 100

.PHONY: \
	help doctor require-secrets compose-schema compose-config build up bootstrap \
	down ps logs migrate ingest graph-sync graph-worker graph-worker-stop \
	test test-api test-web test-container lint lint-api lint-web lint-container \
	test-live-infra test-live-model test-live-e2e

help: ## Show available development and operations commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Quantum Agent local stack\n\n"} \
		/^[a-zA-Z0-9_.-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

doctor: ## Check local command prerequisites without starting containers.
	@for command_name in docker $(UV) node npm; do \
		if command -v "$${command_name}" >/dev/null 2>&1; then \
			printf 'ok: %s\n' "$${command_name}"; \
		else \
			printf 'missing: %s\n' "$${command_name}"; \
		fi; \
	done

require-secrets: ## Fail unless all required runtime secrets are present.
	@$(COMPOSE) -f compose.yaml config --quiet >/dev/null

compose-schema: ## Validate compose.yaml against the upstream Compose JSON schema.
	$(UV) tool run --from "check-jsonschema==$(CHECK_JSONSCHEMA_VERSION)" check-jsonschema \
		--schemafile https://raw.githubusercontent.com/compose-spec/compose-spec/main/schema/compose-spec.json \
		compose.yaml

compose-config: require-secrets ## Render Docker Compose configuration and interpolation.
	$(COMPOSE) -f compose.yaml config --quiet

build: require-secrets ## Build the API and web runtime images.
	$(COMPOSE) -f compose.yaml build api web

up: require-secrets ## Start databases, migrate, and launch healthy API/web services.
	$(COMPOSE) -f compose.yaml up --build --detach postgres neo4j redis migrate api web

bootstrap: up ingest ## Start the stack, then ingest the checksum-verified real manifest.

down: ## Stop all stack services while preserving named data volumes.
	$(COMPOSE) -f compose.yaml --profile jobs --profile workers --profile tools down --remove-orphans

ps: ## Show container and health status.
	$(COMPOSE) -f compose.yaml --profile jobs --profile workers ps

logs: ## Follow API, web, migration, and graph-worker logs.
	$(COMPOSE) -f compose.yaml logs --follow --tail=200 api web migrate graph-sync-worker

migrate: require-secrets ## Run the Alembic migration as a one-shot container.
	$(COMPOSE) -f compose.yaml run --rm migrate

ingest: require-secrets ## Verify and ingest the authoritative course manifest once.
	$(COMPOSE) -f compose.yaml --profile jobs run --rm ingest \
		quantum-agent ingest --manifest "/workspace/$(MANIFEST)"

graph-sync: require-secrets ## Drain one bounded batch of approved Neo4j outbox events.
	$(COMPOSE) -f compose.yaml --profile jobs run --rm graph-sync-once \
		quantum-agent sync-graph --limit "$(GRAPH_SYNC_BATCH_SIZE)"

graph-worker: require-secrets ## Start the continuous approved-graph projection worker.
	$(COMPOSE) -f compose.yaml --profile workers up --detach graph-sync-worker

graph-worker-stop: ## Stop the graph projection worker without touching databases.
	$(COMPOSE) -f compose.yaml --profile workers stop graph-sync-worker

test: test-api test-web ## Run Python and existing web test suites locally.

test-api: ## Run the Python knowledge and teaching tests from the locked uv environment.
	cd services/api && $(UV) run --frozen --extra dev pytest -q

test-web: ## Run the existing deterministic web test/build suite.
	npm test

test-container: require-secrets ## Run Python tests in the network-disabled test image.
	$(COMPOSE) -f compose.yaml --profile tools run --rm --build api-test

test-live-infra: require-secrets ## Exercise PostgreSQL/pgvector, Neo4j, Redis, and the live API.
	$(COMPOSE) -f compose.yaml --profile tools run --rm --build api-live-test

test-live-model: require-secrets ## Spend real USTC calls through upload, tutor, HITL, and trace APIs.
	$(COMPOSE) -f compose.yaml --profile tools run --rm --build api-live-model-test

test-live-e2e: require-secrets ## Run the real multimodal browser workflow with ephemeral credentials.
	./scripts/run-live-e2e.sh

lint: lint-api lint-web ## Run Python and web linters locally.

lint-api: ## Run Ruff over the Python backend, tests, and migrations.
	cd services/api && $(UV) run --frozen --extra dev ruff check quantum_agent tests alembic

lint-web: ## Run the existing web lint command.
	npm run lint

lint-container: require-secrets ## Run Ruff in the network-disabled test image.
	$(COMPOSE) -f compose.yaml --profile tools run --rm --build api-lint
