#!/bin/bash
# ========================================
# Docker Volumes Backup Script
# ========================================
# Backup Docker volumes for MongoDB and Redis data
#
# Usage: ./scripts/backup-docker-volumes.sh ▸
#
# Options:
#   --backup-dir PATH   Backup directory (default: ~/backups/docker-volumes)
#   --retention-days N  Keep backups for N days (default: 30)
#   --volumes LIST      Comma-separated volume names (default: auto-detect)
#   --help             Show this help message

set -e

# Status symbols
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
NC=""
BACKUP_DIR="${HOME}/backups/docker-volumes"
RETENTION_DAYS=30
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-prod}"
VOLUMES_TO_BACKUP=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --backup-dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="$2"
      shift 2
      ;;
    --volumes)
      VOLUMES_TO_BACKUP="$2"
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

# Auto-detect volumes if not specified
if [ -z "$VOLUMES_TO_BACKUP" ]; then
    VOLUMES_TO_BACKUP="${COMPOSE_PROJECT_NAME}_mongodb_data,${COMPOSE_PROJECT_NAME}_redis_data"
    log_info "Auto-detected volumes: $VOLUMES_TO_BACKUP"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

DATE=$(date +%Y%m%d_%H%M%S)

log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "  Docker Volumes Backup Starting"
log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_info "Date:        $DATE"
log_info "Destination: $BACKUP_DIR"
echo ""

# Backup each volume
IFS=',' read -ra VOLUMES <<< "$VOLUMES_TO_BACKUP"
BACKUP_COUNT=0
TOTAL_SIZE=0

for volume in "${VOLUMES[@]}"; do
    # Trim whitespace
    volume=$(echo "$volume" | xargs)
    
    log_info "Backing up volume: $volume"
    
    # Check if volume exists
    if ! docker volume inspect "$volume" &>/dev/null; then
        log_warning "Volume '$volume' not found, skipping..."
        continue
    fi
    
    # Get volume mount point info
    VOLUME_SIZE=$(docker run --rm -v "$volume:/data" alpine du -sh /data 2>/dev/null | awk '{print $1}' || echo "unknown")
    log_info "Volume size: $VOLUME_SIZE"
    
    # Create backup using alpine container
    BACKUP_FILE="${volume}_${DATE}.tar.gz"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"
    
    log_info "Creating tar archive..."
    if docker run --rm \
        -v "$volume:/data:ro" \
        -v "$BACKUP_DIR:/backup" \
        alpine \
        tar czf "/backup/$BACKUP_FILE" -C /data . 2>&1; then
        
        BACKUP_SIZE=$(ls -lh "$BACKUP_PATH" | awk '{print $5}')
        log_success "Backup created: $BACKUP_FILE ($BACKUP_SIZE)"
        
        BACKUP_COUNT=$((BACKUP_COUNT + 1))
        
        # Log success
        echo "$(date '+%Y-%m-%d %H:%M:%S') | SUCCESS | $BACKUP_FILE | $BACKUP_SIZE | Volume: $volume" >> "$BACKUP_DIR/backup.log"
    else
        log_error "Failed to backup volume: $volume"
    fi
    
    echo ""
done

# Clean up old backups
log_info "Applying retention policy (keeping last $RETENTION_DAYS days)..."
DELETED_COUNT=0

find "$BACKUP_DIR" -name "*.tar.gz" -type f -mtime +${RETENTION_DAYS} | while read -r old_backup; do
    if rm "$old_backup"; then
        DELETED_COUNT=$((DELETED_COUNT + 1))
        log_info "Deleted old backup: $(basename "$old_backup")"
    fi
done

if [ "$DELETED_COUNT" -eq 0 ]; then
    log_info "No old backups to delete"
fi

# Summary
echo ""
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "  Docker Volumes Backup Completed"
log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_info "Summary:"
echo "  ▸ Volumes backed up: $BACKUP_COUNT"
echo "  ▸ Location:         $BACKUP_DIR"
echo "  ◆ Log:              $BACKUP_DIR/backup.log"
echo ""
log_info "Recent backups:"
ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -5 | awk '{print "  " $9 " (" $5 ", " $6 " " $7 " " $8 ")"}'
echo ""
