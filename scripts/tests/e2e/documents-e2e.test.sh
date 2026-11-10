#!/usr/bin/env bash

# E2E document ingestion test suite runner.

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
API_DIR="$ROOT_DIR/apps/api"
ENV_FILE="$ROOT_DIR/envs/.env"

echo "🧪 Configurando entorno para tests E2E de documentos..."
echo ""

if [[ ! -d "$API_DIR/.venv" ]]; then
  echo "❌ Error: no se encontró .venv en $API_DIR"
  echo "   Ejecuta: python3 -m venv apps/api/.venv && source apps/api/.venv/bin/activate && pip install -r apps/api/requirements.txt"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Error: no se encontró envs/.env en $ROOT_DIR"
  exit 1
fi

source "$API_DIR/.venv/bin/activate"

mapfile -t REQUIRED_KEYS <<'EOF'
MONGODB_USER
MONGODB_PASSWORD
MONGODB_DATABASE
REDIS_PASSWORD
JWT_SECRET_KEY
SECRET_KEY
SAPTIVA_API_KEY
EOF

declare -A ENV_VARS=()
while IFS='=' read -r key value; do
  case "$key" in
    MONGODB_USER|MONGODB_PASSWORD|MONGODB_DATABASE|REDIS_PASSWORD|JWT_SECRET_KEY|SECRET_KEY|SAPTIVA_API_KEY)
      ENV_VARS["$key"]="$value"
      ;;
  esac
done < <(grep -E '^(MONGODB|REDIS|JWT_SECRET_KEY|SECRET_KEY|SAPTIVA_API_KEY)=' "$ENV_FILE" || true)

for required in "${REQUIRED_KEYS[@]}"; do
  if [[ -z "${ENV_VARS[$required]:-}" ]]; then
    echo "❌ Falta la variable $required en $ENV_FILE"
    exit 1
  fi
  export "$required"="${ENV_VARS[$required]}"
done

export MONGODB_URL="mongodb://${MONGODB_USER}:${MONGODB_PASSWORD}@localhost:27018/${MONGODB_DATABASE}?authSource=admin&directConnection=true"
export REDIS_URL="redis://:${REDIS_PASSWORD}@localhost:6380/0"
export REDIS_HOST="localhost"
export REDIS_PORT="6380"
export DEBUG="true"
export LOG_LEVEL="info"
export JWT_ALGORITHM="HS256"
export SAPTIVA_BASE_URL="https://api.saptiva.com"

echo "✅ Variables cargadas desde envs/.env"

echo ""
echo "🐳 Verificando contenedores..."
if ! docker ps --format '{{.Names}}' | grep -q 'octavios-mongodb'; then
  echo "❌ Error: contenedor MongoDB (octavios-mongodb) no está corriendo"
  exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -q 'octavios-redis'; then
  echo "❌ Error: contenedor Redis (octavios-redis) no está corriendo"
  exit 1
fi
echo "✅ MongoDB y Redis detectados"

if ! python -c "import pytest" >/dev/null 2>&1; then
  echo "❌ Error: pytest no está instalado en el entorno virtual"
  echo "   Instalando pytest y pytest-asyncio..."
  pip install pytest pytest-asyncio
fi

echo ""
echo "🚀 Ejecutando tests E2E de documentos..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pushd "$API_DIR" >/dev/null
pytest tests/e2e/test_documents.py -v --tb=short --color=yes
EXIT_CODE=$?
popd >/dev/null

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ Tests completados exitosamente"
else
  echo "❌ Tests fallaron (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
