# Octavius Energy Lab: comandos de desarrollo
#
# Uso: make help

SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV_FILE ?= $(if $(wildcard envs/.env.local),envs/.env.local,envs/.env)
COMPOSE_BASE := infra/docker-compose.yml
COMPOSE_DEV := infra/docker-compose.dev.yml
COMPOSE = docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) --env-file $(ENV_FILE)

BACKEND_DIR := apps/backend
T ?= api

.PHONY: help env dev up down logs ps test test-api test-web test-db test-ingest lint lint-api lint-web lint-db lint-ingest db-up db-migrate db-status ingest-smoke ingest-demo ingest-full cenace-smoke cenace-demo cenace-full lcl-smoke lcl-demo lcl-full bench-e1 test-bench lint-bench

help: ## Lista los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

env: ## Crea envs/.env a partir del ejemplo si no existe
	@[ -f envs/.env ] || cp envs/.env.example envs/.env
	@echo "Usando $(ENV_FILE)"

dev: env ## Levanta el stack de desarrollo
	$(COMPOSE) up -d --build

up: dev ## Alias de dev

down: ## Detiene el stack
	$(COMPOSE) down

logs: ## Sigue los logs (S=servicio opcional)
	$(COMPOSE) logs -f $(S)

ps: ## Estado de los servicios
	$(COMPOSE) ps

test: ## Corre pruebas: T=api|web|db|ingest|bench
	@$(MAKE) --no-print-directory test-$(T)

test-api: ## Pruebas unitarias del backend en el host (uv)
	cd $(BACKEND_DIR) && TEST_MODE=true uv run --python 3.11 --with-requirements requirements.txt \
		--with pytest --with pytest-asyncio --with mongomock_motor \
		pytest tests/unit -q --tb=short

test-web: ## Pruebas, tipos y lint de la web (bun)
	bun run bun:typecheck:web
	bun run bun:lint:web
	bun run bun:test:web

lint: lint-api lint-web lint-db lint-ingest lint-bench ## Lint de backend, web, db, ingesta y bench

lint-api: ## Ruff sobre el backend
	cd $(BACKEND_DIR) && uvx ruff==0.16.5 check src/ && uvx ruff==0.16.5 format --check src/

lint-web: ## Lint de la web
	bun run bun:lint:web

# ---------------------------------------------------------------------------
# Base energy_lab (db/)
# ---------------------------------------------------------------------------
DB_DIR := db
DB_RUN = cd $(DB_DIR) && set -a && . ../$(ENV_FILE) && set +a && uv run --python 3.11 --with-editable .

db-up: env ## Levanta solo PostgreSQL (perfil lab)
	docker compose -f $(COMPOSE_BASE) --env-file $(ENV_FILE) --profile lab up -d postgres

db-migrate: ## Aplica las migraciones de energy_lab
	$(DB_RUN) python -m energy_lab_db migrate

db-status: ## Muestra migraciones aplicadas y pendientes
	$(DB_RUN) python -m energy_lab_db status

test-db: ## Pruebas de db/ (requiere ENERGY_LAB_TEST_ADMIN_DSN)
	cd $(DB_DIR) && uv run --python 3.11 --with-editable . --with pytest pytest -q

lint-db: ## Ruff sobre db/
	cd $(DB_DIR) && uvx ruff==0.16.5 check . && uvx ruff==0.16.5 format --check .

# ---------------------------------------------------------------------------
# Ingesta (ingest/)
# ---------------------------------------------------------------------------
INGEST_DIR := ingest
INGEST_RUN = cd $(INGEST_DIR) && set -a && . ../$(ENV_FILE) && set +a && uv run --python 3.11 --with-editable .
DEMO_CLIENTS ?= 20
DEMO_START ?= 2013-01-01
DEMO_END ?= 2015-01-01

ingest-smoke: ## Carga el fixture smoke de UCI (sin red)
	$(INGEST_RUN) python -m energy_lab_ingest uci --profile smoke

ingest-demo: ## Descarga UCI y carga DEMO_CLIENTS clientes entre DEMO_START y DEMO_END
	$(INGEST_RUN) python -m energy_lab_ingest uci --profile demo --clients $(DEMO_CLIENTS) --start $(DEMO_START) --end $(DEMO_END)

ingest-full: ## Muestra la estimación del perfil full; agrega YES=1 para cargar
	$(INGEST_RUN) python -m energy_lab_ingest uci --profile full $(if $(filter 1,$(YES)),--yes,)

test-ingest: ## Pruebas de ingest/ (las de carga requieren ENERGY_LAB_TEST_ADMIN_DSN)
	cd $(INGEST_DIR) && uv run --python 3.11 --with-editable . --with-editable ../db --with pytest pytest -q

lint-ingest: ## Ruff sobre ingest/
	cd $(INGEST_DIR) && uvx ruff==0.16.5 check . && uvx ruff==0.16.5 format --check .

CENACE_PER_CCR ?= 2
CENACE_START ?= 2025-01-01
CENACE_END ?= 2025-12-31

cenace-smoke: ## Carga el fixture de CENACE (estructura real, valores sintéticos; sin red)
	$(INGEST_RUN) python -m energy_lab_ingest cenace --profile smoke

cenace-demo: ## Precios por zona: CENACE_PER_CCR zonas por centro de control entre CENACE_START y CENACE_END
	$(INGEST_RUN) python -m energy_lab_ingest cenace --profile demo --per-ccr $(CENACE_PER_CCR) --start $(CENACE_START) --end $(CENACE_END)

cenace-full: ## Estimación de todas las zonas del SIN desde 2016; YES=1 para cargar
	$(INGEST_RUN) python -m energy_lab_ingest cenace --profile full $(if $(filter 1,$(YES)),--yes,)

LCL_FILES ?= 4

lcl-smoke: ## Carga el fixture de Low Carbon London (sin red)
	$(INGEST_RUN) python -m energy_lab_ingest lcl --profile smoke

lcl-demo: ## Descarga LCL y carga LCL_FILES archivos estratificados por tarifa, más la tarifa dinámica
	$(INGEST_RUN) python -m energy_lab_ingest lcl --profile demo --files $(LCL_FILES)

lcl-full: ## Estimación de LCL completo (168 archivos); YES=1 para cargar
	$(INGEST_RUN) python -m energy_lab_ingest lcl --profile full $(if $(filter 1,$(YES)),--yes,)

# ---------------------------------------------------------------------------
# Benchmarks (bench/)
# ---------------------------------------------------------------------------
BENCH_DIR := bench
E1_FECHA ?= $(shell date +%Y-%m-%d)

bench-e1: ## E1: volumen, ingesta, latencia y poda; JSON y resumen en español en results/e1/
	cd $(BENCH_DIR) && set -a && . ../$(ENV_FILE) && set +a && uv run --python 3.11 --with-editable . \
		python -m energy_lab_bench e1 --source lcl --out ../results/e1/$(E1_FECHA).json --resumen ../results/e1/$(E1_FECHA).md

test-bench: ## Pruebas de bench/ (requiere ENERGY_LAB_TEST_ADMIN_DSN)
	cd $(BENCH_DIR) && uv run --python 3.11 --with-editable . --with-editable ../ingest --with-editable ../db --with pytest pytest -q

lint-bench: ## Ruff sobre bench/
	cd $(BENCH_DIR) && uvx ruff==0.16.5 check . && uvx ruff==0.16.5 format --check .
