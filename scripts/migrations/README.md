# Migrations Scripts

Scripts de migraciones de datos y schema de base de datos.

## Scripts Disponibles

- **`add_bank_chart_ttl_indexes.py`** - Agregar índices TTL para gráficos del Bank Advisor

## Uso

```bash
# Ejecutar migración
python scripts/migrations/add_bank_chart_ttl_indexes.py
```

## Buenas Prácticas

1. **Siempre hacer backup antes de migraciones**
   ```bash
   ./scripts/database/backup-mongodb.sh
   ```

2. **Probar primero en desarrollo**
   - Verificar que la migración funciona localmente
   - Revisar logs para errores

3. **Verificar después de migración**
   - Verificar que los datos están correctos
   - Verificar que los índices se crearon

---
**Ver también:** `../README.md` para más información
