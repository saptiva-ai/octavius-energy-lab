# Database Scripts

Scripts para gestión de bases de datos, backups, restauraciones y migraciones.

## Scripts Disponibles

### Backups & Restore
- **`backup-mongodb.sh`** - Backup automático de MongoDB
  ```bash
  ./scripts/database/backup-mongodb.sh
  ```
- **`restore-mongodb.sh`** - Restore desde backup
  ```bash
  ./scripts/database/restore-mongodb.sh [backup-file.gz]
  ```
- **`backup-docker-volumes.sh`** - Backup de volúmenes Docker
- **`db-manager.sh`** - CLI de gestión de DB (en root: `scripts/db-manager.sh`)

### Migraciones de Datos
- **`migrate-conversation-timestamps.py`** - Migración de timestamps de conversaciones
- **`migrate-ready-to-active.py`** - Migración de estados ready→active
- **`migrate-prod-to-octavios.sh`** - Migración desde producción antigua
- **`migrate_attached_files_to_documents.py`** - Migración de archivos adjuntos

### Mantenimiento
- **`fix-orphaned-drafts.py`** - Fix drafts huérfanos
- **`cleanup-duplicate-drafts.py`** - Limpiar drafts duplicados
- **`apply-draft-unique-index.py`** - Aplicar índice único para drafts
- **`apply-email-unique-index.py`** - Aplicar índice único para emails

### Seguridad
- **`rotate-mongo-credentials.sh`** - Rotación de credentials MongoDB
- **`rotate-redis-credentials.sh`** - Rotación de credentials Redis
- **`export-passwords.py`** - Exportar passwords encriptados

## Uso Común

```bash
# Backup antes de cambios importantes
./scripts/database/backup-mongodb.sh

# Restaurar desde backup
./scripts/database/restore-mongodb.sh backups/mongodb_20251203.tar.gz

# Migraciones
python scripts/database/migrate-conversation-timestamps.py
```

## Advertencias

⚠️ **Siempre hacer backup antes de:**
- Ejecutar migraciones
- Aplicar índices
- Modificar datos

---
**Ver también:** `../README.md` para más información
