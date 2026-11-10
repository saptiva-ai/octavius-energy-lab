#!/usr/bin/env bash

# Ejecuta la suite de tests de apps/api (unitarios, integración, e2e).

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"

if [[ ! -d "$API_DIR" ]]; then
  echo "❌ No se encontró apps/api en $ROOT_DIR"
  exit 1
fi

pushd "$API_DIR" >/dev/null

if [[ ! -f "pyproject.toml" ]]; then
  echo "❌ Debe ejecutar este script desde la raíz del repo (no se halló pyproject.toml en apps/api)"
  exit 1
fi

if ! command -v pytest >/dev/null 2>&1; then
  echo "❌ pytest no está instalado"
  echo "   Ejecuta: pip install pytest pytest-asyncio"
  exit 1
fi

export PROMPT_REGISTRY_PATH="prompts/registry.yaml"

separator() {
  printf '%s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

run_tests() {
  local name=$1
  local path=$2
  local marker=${3:-}

  separator
  printf '📋 Ejecutando: %s\n\n' "$name"

  if [[ -n "$marker" ]]; then
    pytest "$path" -v -m "$marker" --tb=short
  else
    pytest "$path" -v --tb=short
  fi
}

printf '╔══════════════════════════════════════════════════════════════╗\n'
printf '║         COPILOTOS BRIDGE - API TEST SUITE                    ║\n'
printf '╚══════════════════════════════════════════════════════════════╝\n\n'

run_tests "Tests Unitarios - Prompt Registry" "tests/test_prompt_registry.py"
run_tests "Tests Unitarios - Health Check" "tests/test_health.py"

if [[ -d "tests/integration" ]]; then
  run_tests "Tests de Integración - Database" "tests/integration/test_database.py"
fi

run_tests "Tests E2E - Registry Configuration" "tests/e2e/test_registry_configuration.py"

printf '⚠️  Nota: Tests E2E de chat requieren API corriendo\n\n'
run_tests "Tests E2E - Chat Models" "tests/e2e/test_chat_models.py" || true

separator
printf '\n✅ Tests unitarios completados\n'
printf '✅ Tests de integración completados\n'
printf '✅ Tests E2E de configuración completados\n'
printf '⚠️  Tests E2E de chat requieren API en ejecución\n\n'
printf 'Comandos útiles:\n'
printf '  pytest tests/test_prompt_registry.py -v\n'
printf '  pytest tests/e2e/ -v\n'
printf '  pytest --cov=src --cov-report=html\n'

popd >/dev/null
