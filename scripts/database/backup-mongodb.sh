#!/bin/bash
# ========================================
# MongoDB Backup Script
# ========================================
# Automated MongoDB backup with compression and retention
#
# Usage: ./scripts/backup-mongodb.sh ▸
#
# Options:
#   --retention-days N  Keep backups for N days (default: 30)
#   --backup-dir PATH   Backup directory (default: ~/backups/mongodb)
#   --container NAME    Container name (default: auto-detect from COMPOSE_PROJECT_NAME)
#   --env-file PATH     Load environment from file (e.g., envs/.env.prod)
#   --help              Show this help message
#
# Environment Variables:
#   MONGODB_USER       MongoDB username (default: octavios_user)
#   MONGODB_PASSWORD   MongoDB password (required)
#   MONGODB_DATABASE   Database name (default: octavios)
#   COMPOSE_PROJECT_NAME Project name for container detection (default: octavios-prod)
#
# This script is referenced in the post-mortem: docs/POST-MORTEM-DATA-LOSS-2025-10-09.md

set -e  # Exit on error

# Status symbols for output
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""

# Default configuration
BACKUP_DIR="${HOME}/backups/mongodb"
RETENTION_DAYS=30
MONGODB_USER="${MONGODB_USER:-octavios_user}"
MONGODB_PASSWORD="${MONGODB_PASSWORD:-}"
MONGODB_DATABASE="${MONGODB_DATABASE:-octavios}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-prod}"
CONTAINER_NAME=""
ENV_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --retention-days)
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --backup-dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    --container)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --help)
      grep "^#" "$0" | grep -v "^#!/" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

# Load environment file if specified
if [ -n "$ENV_FILE" ]; then
    if [ -f "$ENV_FILE" ]; then
        echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} Loading environment from: $ENV_FILE"
        source "$ENV_FILE"
        # Re-apply defaults after sourcing in case they weren't set
        MONGODB_USER="${MONGODB_USER:-octavios_user}"
        MONGODB_DATABASE="${MONGODB_DATABASE:-octavios}"
        COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-prod}"
    else
        echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} Environment file not found: $ENV_FILE"
        exit 1
    fi
fi

# Functions
log_info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

# Validate requirements
if [ -z "$MONGODB_PASSWORD" ]; then
    log_error "MONGODB_PASSWORD environment variable is required!"
    log_info "Set it with: export MONGODB_PASSWORD='your-password'"
    log_info "Or source from .env.prod: source envs/.env.prod"
    exit 1
fi

# Auto-detect container if not specified
if [ -z "$CONTAINER_NAME" ]; then
    CONTAINER_NAME="${COMPOSE_PROJECT_NAME}-mongodb"
    log_info "Auto-detected container name: $CONTAINER_NAME"
fi

# Verify container exists and is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container '$CONTAINER_NAME' is not running!"
    log_info "Available MongoDB containers:"
    docker ps --filter "ancestor=mongo" --format "  - {{.Names}} ({{.Status}})"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"
if [ ! -w "$BACKUP_DIR" ]; then
    log_error "Backup directory '$BACKUP_DIR' is not writable!"
    exit 1
fi

# Generate backup filename with timestamp
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="octavios_${DATE}.gz"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"

log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "  MongoDB Backup Starting"
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Container:   $CONTAINER_NAME"
log_info "Database:    $MONGODB_DATABASE"
log_info "Backup file: $BACKUP_FILE"
log_info "Destination: $BACKUP_DIR"
echo ""

# Create backup using mongodump
log_info "Running mongodump (this may take several minutes)..."

# Build MongoDB URI
MONGO_URI="mongodb://${MONGODB_USER}:${MONGODB_PASSWORD}@localhost:27017/${MONGODB_DATABASE}?authSource=admin"

# Execute mongodump inside container
if docker exec "$CONTAINER_NAME" mongodump \
    --uri="$MONGO_URI" \
    --gzip \
    --archive="/tmp/backup_${DATE}.gz" 2>&1 | tee /tmp/mongodump.log; then
    log_success "mongodump completed successfully"
else
    log_error "mongodump failed! Check logs at /tmp/mongodump.log"
    exit 1
fi

# Copy backup from container to host
log_info "Copying backup from container to host..."
if docker cp "$CONTAINER_NAME:/tmp/backup_${DATE}.gz" "$BACKUP_PATH"; then
    log_success "Backup copied to $BACKUP_PATH"
else
    log_error "Failed to copy backup from container!"
    exit 1
fi

# Clean up temporary file in container
docker exec "$CONTAINER_NAME" rm -f "/tmp/backup_${DATE}.gz" || log_warning "Could not clean temporary file in container"

# Verify backup file size
BACKUP_SIZE=$(ls -lh "$BACKUP_PATH" | awk '{print $5}')
BACKUP_SIZE_BYTES=$(stat -c%s "$BACKUP_PATH" 2>/dev/null || stat -f%z "$BACKUP_PATH" 2>/dev/null)

if [ "$BACKUP_SIZE_BYTES" -lt 1000 ]; then
    log_error "Backup file is suspiciously small (${BACKUP_SIZE})!"
    log_error "This may indicate a failed backup. Please investigate."
    exit 1
fi

log_success "Backup size: $BACKUP_SIZE"

# Clean up old backups (retention policy)
log_info "Applying retention policy (keeping last $RETENTION_DAYS days)..."
DELETED_COUNT=0

find "$BACKUP_DIR" -name "octavios_*.gz" -type f -mtime +${RETENTION_DAYS} -print | while read -r old_backup; do
    if rm "$old_backup"; then
        DELETED_COUNT=$((DELETED_COUNT + 1))
        log_info "Deleted old backup: $(basename "$old_backup")"
    fi
done

if [ "$DELETED_COUNT" -eq 0 ]; then
    log_info "No old backups to delete"
fi

# Log backup success
LOG_FILE="$BACKUP_DIR/backup.log"
echo "$(date '+%Y-%m-%d %H:%M:%S') | SUCCESS | $BACKUP_FILE | $BACKUP_SIZE | Container: $CONTAINER_NAME" >> "$LOG_FILE"

# Display summary
echo ""
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "  MongoDB Backup Completed Successfully"
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_info "Backup details:"
echo "  ▸ File:      $BACKUP_FILE"
echo "  ▸ Size:      $BACKUP_SIZE"
echo "  ▸ Location:  $BACKUP_DIR"
echo "  ◆ Log:       $LOG_FILE"
echo ""
log_info "Recent backups:"
ls -lht "$BACKUP_DIR"/octavios_*.gz 2>/dev/null | head -5 | awk '{print "  " $9 " (" $5 ", " $6 " " $7 " " $8 ")"}'
echo ""
log_info "To restore this backup, run:"
echo "  ./scripts/restore-mongodb.sh --backup-file $BACKUP_PATH"
echo ""
