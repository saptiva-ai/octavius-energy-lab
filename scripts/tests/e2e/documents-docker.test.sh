#!/usr/bin/env bash

# Ejecuta los tests de documentos dentro del contenedor octavios-api.

set -euo pipefail
IFS=$'\n\t'

CONTAINER_NAME="octavios-api"

echo "🧪 Ejecutando tests E2E de documentos en contenedor..."
echo ""

if ! docker ps --format '{{.Names}}' | grep -q "$CONTAINER_NAME"; then
  echo "❌ Error: contenedor $CONTAINER_NAME no está corriendo"
  exit 1
fi
echo "✅ Contenedor $CONTAINER_NAME detectado"
echo ""

echo "📦 Verificando pytest en contenedor..."
docker exec "$CONTAINER_NAME" bash -c "pip list | grep -q pytest || pip install pytest pytest-asyncio" >/dev/null 2>&1
echo "✅ pytest disponible en contenedor"
echo ""

echo "🚀 Ejecutando tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker exec "$CONTAINER_NAME" bash -c "cd /app && python -m pytest tests/e2e/test_documents.py -v --tb=short --color=yes"
EXIT_CODE=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ Tests completados exitosamente"
else
  echo "❌ Tests fallaron (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
