#!/bin/bash
set -e

# ========================================
# MongoDB Credential Rotation Script
# ========================================
# Actualiza credenciales de MongoDB SIN borrar volumen
# Uso:
#   ./scripts/rotate-mongo-credentials.sh OLD_PASSWORD NEW_PASSWORD
# ========================================

if [ "$#" -ne 2 ]; then
    echo "✖ Error: Se requieren 2 argumentos"
    echo "Uso: $0 OLD_PASSWORD NEW_PASSWORD"
    echo ""
    echo "Ejemplo:"
    echo "  $0 'secure_password_change_me' 'NewSecurePass2024!'"
    exit 1
fi

OLD_PASSWORD="$1"
NEW_PASSWORD="$2"
MONGO_USER="${MONGODB_USER:-octavios_prod_user}"
MONGO_DATABASE="${MONGODB_DATABASE:-octavios}"
CONTAINER_NAME="${COMPOSE_PROJECT_NAME:-octavios}-mongodb"

echo "▸ Rotación de credenciales MongoDB"
echo "════════════════════════════════════"
echo "Usuario: $MONGO_USER"
echo "Base de datos: $MONGO_DATABASE"
echo ""

# Verificar que el contenedor esté corriendo
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "✖ Error: Contenedor $CONTAINER_NAME no está corriendo"
    echo "Ejecuta: make dev"
    exit 1
fi

echo "✓ Contenedor MongoDB encontrado"

# Conectar con password viejo y cambiar al nuevo
echo "⛨ Actualizando contraseña..."
docker exec -i "$CONTAINER_NAME" mongosh admin \
    --username "$MONGO_USER" \
    --password "$OLD_PASSWORD" \
    --eval "
    db.changeUserPassword('$MONGO_USER', '$NEW_PASSWORD');
    print('✓ Contraseña actualizada exitosamente');
    " 2>&1 | grep -v "Current Mongosh Log ID"

if [ $? -eq 0 ]; then
    echo ""
    echo "✔ Rotación completada!"
    echo ""
    echo "◆ Siguiente paso:"
    echo "  1. Actualiza envs/.env con la nueva contraseña:"
    echo "     MONGODB_PASSWORD=$NEW_PASSWORD"
    echo ""
    echo "  2. Reinicia los servicios (IMPORTANTE: usar down+up, NO restart):"
    echo "     docker compose -f infra/docker-compose.yml down api"
    echo "     docker compose -f infra/docker-compose.yml up -d api"
    echo ""
    echo "  ▲  NOTA: 'docker compose restart' NO funciona porque no recarga .env"
    echo ""
else
    echo "✖ Error: Falló la rotación"
    echo "Verifica que la contraseña vieja sea correcta"
    exit 1
fi
