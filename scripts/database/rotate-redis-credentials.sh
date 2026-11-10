#!/bin/bash
set -e

# ========================================
# Redis Credential Rotation Script
# ========================================
# Actualiza contraseña de Redis SIN borrar volumen
# Uso:
#   ./scripts/rotate-redis-credentials.sh NEW_PASSWORD
# ========================================

if [ "$#" -ne 1 ]; then
    echo "✖ Error: Se requiere 1 argumento"
    echo "Uso: $0 NEW_PASSWORD"
    echo ""
    echo "Ejemplo:"
    echo "  $0 'NewRedisPass2024!'"
    exit 1
fi

NEW_PASSWORD="$1"
CONTAINER_NAME="${COMPOSE_PROJECT_NAME:-octavios}-redis"

echo "▸ Rotación de credenciales Redis"
echo "════════════════════════════════════"
echo ""

# Verificar que el contenedor esté corriendo
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "✖ Error: Contenedor $CONTAINER_NAME no está corriendo"
    echo "Ejecuta: make dev"
    exit 1
fi

echo "✓ Contenedor Redis encontrado"

echo "⛨ Actualizando contraseña en runtime..."
OLD_PASSWORD="${REDIS_PASSWORD:-redis_password_change_me}"

# Cambiar password en runtime (no persiste entre reinicios)
docker exec "$CONTAINER_NAME" redis-cli -a "$OLD_PASSWORD" CONFIG SET requirepass "$NEW_PASSWORD" 2>&1 | grep -q "OK" || {
    echo "✖ Error: Falló la actualización de contraseña"
    echo "Verifica que la contraseña vieja en envs/.env sea correcta"
    exit 1
}

echo "✓ Contraseña actualizada en runtime"

echo ""
echo "▲  IMPORTANTE: Esta es una actualización TEMPORAL"
echo ""
echo "◆ Para hacer permanente la rotación:"
echo ""
echo "  1. Actualiza envs/.env:"
echo "     REDIS_PASSWORD=$NEW_PASSWORD"
echo ""
echo "  2. Reinicia Redis y API (IMPORTANTE: usar down+up, NO restart):"
echo "     docker compose -f infra/docker-compose.yml down redis api"
echo "     docker compose -f infra/docker-compose.yml up -d redis api"
echo ""
echo "  ▲  NOTA: 'docker compose restart' NO funciona porque no recarga .env"
echo ""
echo "✔ Rotación temporal completada!"
echo ""
