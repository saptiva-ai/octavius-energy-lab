#!/bin/bash
# ============================================================================
# Migración Segura de Producción: copilotos → octavios
# ============================================================================
# Este script migra los contenedores de producción preservando TODOS los datos
# Estrategia: Recrear contenedores app, mantener volúmenes de datos intactos
#
# PREREQUISITOS:
# - Backups completados (MongoDB, Redis, archivos)
# - Código actualizado (git pull)
# - Ejecutar como usuario con permisos Docker
#
# USO:
#   ./scripts/migrate-prod-to-octavios.sh
#
# ROLLBACK (si algo falla):
#   docker compose -f infra/docker-compose.yml --env-file envs/.env.prod down
#   docker start copilotos-prod-web copilotos-prod-api copilotos-prod-redis copilotos-prod-mongodb
# ============================================================================

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/envs/.env.prod"
COMPOSE_FILE="$PROJECT_ROOT/infra/docker-compose.yml"
BACKUP_DIR="$HOME/backups/migration-$(date +%Y%m%d-%H%M%S)"

# Funciones de utilidad
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_prerequisites() {
    log_info "Verificando prerrequisitos..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker no está instalado"
        exit 1
    fi

    # Check docker compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose v2 no está disponible"
        exit 1
    fi

    # Check env file
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "Archivo .env.prod no encontrado: $ENV_FILE"
        exit 1
    fi

    # Check compose file
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Archivo docker-compose.yml no encontrado: $COMPOSE_FILE"
        exit 1
    fi

    # Check running containers
    if ! docker ps --format '{{.Names}}' | grep -q "copilotos-prod"; then
        log_warning "No se encontraron contenedores 'copilotos-prod' corriendo"
        read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    log_success "Prerrequisitos verificados"
}

verify_backups() {
    log_info "Verificando backups existentes..."

    # Check for recent backups
    if ! ls ~/backups/*mongodb*.tar.gz 2>/dev/null | tail -1 &> /dev/null; then
        log_error "No se encontró backup de MongoDB reciente"
        log_error "Ejecuta el Paso 1 del plan de migración primero"
        exit 1
    fi

    LATEST_BACKUP=$(ls -t ~/backups/*mongodb*.tar.gz 2>/dev/null | head -1)
    BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 60 ))

    if [[ $BACKUP_AGE -gt 30 ]]; then
        log_warning "El backup más reciente tiene $BACKUP_AGE minutos"
        read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_success "Backup reciente encontrado (${BACKUP_AGE}m ago)"
    fi
}

show_current_state() {
    log_info "Estado actual de contenedores:"
    echo ""
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAME|copilotos"
    echo ""
}

confirm_migration() {
    echo ""
    log_warning "============================================"
    log_warning "  MIGRACIÓN DE PRODUCCIÓN: copilotos → octavios"
    log_warning "============================================"
    echo ""
    log_info "Este script realizará:"
    echo "  1. Detener contenedores actuales (copilotos-prod-*)"
    echo "  2. Recrear con nuevos nombres (octavios-prod-*)"
    echo "  3. Mantener TODOS los datos intactos (volúmenes no se tocan)"
    echo "  4. Downtime estimado: 2-3 minutos"
    echo ""
    log_warning "IMPORTANTE:"
    echo "  - Los backups deben estar completos"
    echo "  - El código debe estar actualizado (git pull)"
    echo "  - Usuarios no podrán acceder durante 2-3 minutos"
    echo ""

    read -p "¿Proceder con la migración? (yes/no): " -r
    echo
    if [[ ! $REPLY =~ ^yes$ ]]; then
        log_info "Migración cancelada por el usuario"
        exit 0
    fi
}

stop_old_containers() {
    log_info "Paso 1/4: Deteniendo contenedores antiguos..."

    # Stop pero NO remove (permite rollback rápido)
    docker stop copilotos-prod-web copilotos-prod-api 2>/dev/null || true

    # Dar tiempo para conexiones activas
    sleep 2

    # Stop databases (serán reutilizados por nombres de volumen)
    docker stop copilotos-prod-mongodb copilotos-prod-redis 2>/dev/null || true

    log_success "Contenedores antiguos detenidos (no eliminados, rollback posible)"
}

verify_volumes_exist() {
    log_info "Paso 2/4: Verificando volúmenes de datos..."

    # Listar volúmenes actuales
    local volumes=$(docker volume ls --format '{{.Name}}' | grep -E "mongodb|redis")

    if [[ -z "$volumes" ]]; then
        log_error "No se encontraron volúmenes de datos"
        exit 1
    fi

    echo "Volúmenes encontrados:"
    echo "$volumes" | sed 's/^/  - /'
    log_success "Volúmenes de datos verificados"
}

start_new_containers() {
    log_info "Paso 3/4: Iniciando contenedores con nuevos nombres..."

    cd "$PROJECT_ROOT/infra"

    # Usar docker compose con nombres nuevos
    docker compose -f docker-compose.yml \
        --env-file ../envs/.env.prod \
        up -d mongodb redis

    log_info "Esperando a que databases estén healthy..."
    sleep 10

    # Start application containers
    docker compose -f docker-compose.yml \
        --env-file ../envs/.env.prod \
        up -d api web

    log_success "Contenedores nuevos iniciados"
}

verify_new_containers() {
    log_info "Paso 4/4: Verificando servicios nuevos..."

    # Wait for health checks
    log_info "Esperando health checks (60s max)..."
    local max_wait=60
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        local healthy=$(docker ps --format '{{.Names}}\t{{.Status}}' | grep octavios | grep -c "healthy" || true)

        if [[ $healthy -ge 4 ]]; then
            log_success "Todos los servicios están healthy"
            break
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo ""

    # Show final state
    log_info "Estado final de contenedores:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAME|octavios"
}

test_application() {
    log_info "Probando acceso a aplicación..."

    # Test API health
    if curl -f -s http://localhost:8001/api/health > /dev/null; then
        log_success "API responde correctamente"
    else
        log_error "API no responde en http://localhost:8001/api/health"
        log_warning "Verifica logs: docker logs octavios-prod-api"
    fi

    # Test Web
    if curl -f -s http://localhost:3000 > /dev/null; then
        log_success "Web responde correctamente"
    else
        log_error "Web no responde en http://localhost:3000"
        log_warning "Verifica logs: docker logs octavios-prod-web"
    fi
}

show_rollback_instructions() {
    echo ""
    log_warning "============================================"
    log_warning "  INSTRUCCIONES DE ROLLBACK"
    log_warning "============================================"
    echo ""
    echo "Si algo salió mal, ejecuta:"
    echo ""
    echo "  # Detener contenedores nuevos"
    echo "  docker compose -f infra/docker-compose.yml --env-file envs/.env.prod down"
    echo ""
    echo "  # Reiniciar contenedores antiguos"
    echo "  docker start copilotos-prod-mongodb"
    echo "  docker start copilotos-prod-redis"
    echo "  docker start copilotos-prod-api"
    echo "  docker start copilotos-prod-web"
    echo ""
    log_info "Los contenedores antiguos NO fueron eliminados para permitir rollback"
}

cleanup_old_containers() {
    echo ""
    read -p "¿Eliminar contenedores antiguos (copilotos-prod-*)? (y/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Eliminando contenedores antiguos..."
        docker rm -f copilotos-prod-web copilotos-prod-api \
                     copilotos-prod-mongodb copilotos-prod-redis 2>/dev/null || true
        log_success "Contenedores antiguos eliminados"
    else
        log_info "Contenedores antiguos conservados para rollback"
        log_info "Para eliminarlos más tarde:"
        echo "  docker rm -f copilotos-prod-web copilotos-prod-api copilotos-prod-mongodb copilotos-prod-redis"
    fi
}

main() {
    echo ""
    log_info "============================================"
    log_info "  Migración Segura: copilotos → octavios"
    log_info "============================================"
    echo ""

    # Verificaciones pre-migración
    check_prerequisites
    verify_backups
    show_current_state
    confirm_migration

    # Migración
    stop_old_containers
    verify_volumes_exist
    start_new_containers
    verify_new_containers

    # Post-migración
    test_application
    show_rollback_instructions

    echo ""
    log_success "============================================"
    log_success "  MIGRACIÓN COMPLETADA EXITOSAMENTE"
    log_success "============================================"
    echo ""
    log_info "Próximos pasos:"
    echo "  1. Verificar aplicación: http://$(hostname -I | awk '{print $1}'):3000"
    echo "  2. Verificar logs: make logs-prod"
    echo "  3. Probar funcionalidad completa"
    echo "  4. Después de 24h sin problemas, ejecutar cleanup"
    echo ""

    cleanup_old_containers
}

# Trap errors
trap 'log_error "Script falló en línea $LINENO. Revisa los logs."; show_rollback_instructions' ERR

# Run
main "$@"
