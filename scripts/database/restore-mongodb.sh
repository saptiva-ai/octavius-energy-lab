#!/bin/bash
# ========================================
# MongoDB Restore Script
# ========================================
# Restore MongoDB database from backup
#
# Usage: ./scripts/restore-mongodb.sh --backup-file PATH ▸
#
# Options:
#   --backup-file PATH  Path to backup file (required)
#   --container NAME    Container name (default: auto-detect)
#   --drop             Drop existing database before restore
#   --dry-run          Show what would be restored without doing it
#   --help             Show this help message
#
# Environment Variables:
#   MONGODB_USER       MongoDB username (default: octavios_user)
#   MONGODB_PASSWORD   MongoDB password (required)
#   MONGODB_DATABASE   Database name (default: octavios)
#   COMPOSE_PROJECT_NAME Project name for container detection (default: octavios-prod)

set -e

# Status symbols
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""
BACKUP_FILE=""
DROP_DATABASE=false
DRY_RUN=false
MONGODB_USER="${MONGODB_USER:-octavios_user}"
MONGODB_PASSWORD="${MONGODB_PASSWORD:-}"
MONGODB_DATABASE="${MONGODB_DATABASE:-octavios}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-prod}"
CONTAINER_NAME=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --backup-file)
      BACKUP_FILE="$2"
      shift 2
      ;;
    --container)
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --drop)
      DROP_DATABASE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
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
if [ -z "$BACKUP_FILE" ]; then
    log_error "Backup file is required! Use --backup-file PATH"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

if [ -z "$MONGODB_PASSWORD" ]; then
    log_error "MONGODB_PASSWORD environment variable is required!"
    exit 1
fi

# Auto-detect container
if [ -z "$CONTAINER_NAME" ]; then
    CONTAINER_NAME="${COMPOSE_PROJECT_NAME}-mongodb"
fi

# Verify container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container '$CONTAINER_NAME' is not running!"
    exit 1
fi

# Get backup info
BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
BACKUP_DATE=$(ls -l "$BACKUP_FILE" | awk '{print $6, $7, $8}')

log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "  MongoDB Restore"
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Backup file:  $(basename "$BACKUP_FILE")"
log_info "Backup size:  $BACKUP_SIZE"
log_info "Backup date:  $BACKUP_DATE"
log_info "Container:    $CONTAINER_NAME"
log_info "Database:     $MONGODB_DATABASE"
log_info "Drop existing: $DROP_DATABASE"
echo ""

if [ "$DRY_RUN" = true ]; then
    log_warning "DRY RUN MODE - No changes will be made"
    echo ""
    log_info "Would restore backup:"
    echo "  From: $BACKUP_FILE"
    echo "  To:   $CONTAINER_NAME:$MONGODB_DATABASE"
    [ "$DROP_DATABASE" = true ] && echo "  Mode: DROP and restore" || echo "  Mode: Merge with existing"
    exit 0
fi

# Warning for production
log_warning "▲  WARNING: This will restore database from backup!"
if [ "$DROP_DATABASE" = true ]; then
    log_warning "▲  The --drop flag will DELETE ALL EXISTING DATA!"
fi
echo ""
read -p "Type 'yes' to continue: " -r
echo ""
if [[ ! $REPLY =~ ^yes$ ]]; then
    log_info "Restore cancelled"
    exit 0
fi

# Copy backup to container
log_info "Copying backup to container..."
TEMP_BACKUP="/tmp/restore_$(date +%s).gz"
if docker cp "$BACKUP_FILE" "$CONTAINER_NAME:$TEMP_BACKUP"; then
    log_success "Backup copied to container"
else
    log_error "Failed to copy backup to container!"
    exit 1
fi

# Build restore command
MONGO_URI="mongodb://${MONGODB_USER}:${MONGODB_PASSWORD}@localhost:27017/${MONGODB_DATABASE}?authSource=admin"
RESTORE_CMD="mongorestore --uri='$MONGO_URI' --gzip --archive=$TEMP_BACKUP"

if [ "$DROP_DATABASE" = true ]; then
    RESTORE_CMD="$RESTORE_CMD --drop"
    log_warning "Dropping existing database..."
fi

# Execute restore
log_info "Restoring database (this may take several minutes)..."
if docker exec "$CONTAINER_NAME" sh -c "$RESTORE_CMD"; then
    log_success "Database restored successfully!"
else
    log_error "Restore failed!"
    docker exec "$CONTAINER_NAME" rm -f "$TEMP_BACKUP"
    exit 1
fi

# Cleanup
docker exec "$CONTAINER_NAME" rm -f "$TEMP_BACKUP"

# Verify restore
log_info "Verifying restore..."
COLLECTION_COUNT=$(docker exec "$CONTAINER_NAME" mongosh "$MONGO_URI" --quiet --eval "db.getCollectionNames().length")
log_info "Collections restored: $COLLECTION_COUNT"

echo ""
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "  MongoDB Restore Completed Successfully"
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_info "Next steps:"
echo "  1. Verify data: make db-collections"
echo "  2. Test application functionality"
echo "  3. Check logs: docker logs $CONTAINER_NAME"
echo ""
