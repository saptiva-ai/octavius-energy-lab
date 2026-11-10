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

.PHONY: help env dev up down logs ps test test-api test-web lint lint-api lint-web

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

test: ## Corre pruebas: T=api|web
	@$(MAKE) --no-print-directory test-$(T)

test-api: ## Pruebas unitarias del backend en el host (uv)
	cd $(BACKEND_DIR) && TEST_MODE=true uv run --python 3.11 --with-requirements requirements.txt \
		--with pytest --with pytest-asyncio --with mongomock_motor \
		pytest tests/unit -q --tb=short

test-web: ## Pruebas, tipos y lint de la web (bun)
	bun run bun:typecheck:web
	bun run bun:lint:web
	bun run bun:test:web

lint: lint-api lint-web ## Lint de backend y web

lint-api: ## Ruff sobre el backend
	cd $(BACKEND_DIR) && uvx ruff==0.16.5 check src/ && uvx ruff==0.16.5 format --check src/

lint-web: ## Lint de la web
	bun run bun:lint:web
