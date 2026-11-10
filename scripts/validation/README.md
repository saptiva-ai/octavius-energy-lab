# Validación V1 - Sistema de Files

Script automatizado para validar la implementación V1 del sistema unificado de files.

## Uso

### Prerequisitos

- Servicios Docker en ejecución (`docker-compose up -d`)
- API disponible en `http://localhost:8080` (o configurar `API_URL`)
- `curl` instalado
- `jq` instalado (opcional, para análisis JSON)

### Ejecución básica

```bash
cd scripts/validation
./validate_files_v1.sh
```

### Configuración personalizada

```bash
# Cambiar URL del API
export API_URL=http://localhost

# Usar token existente (omitir auto-generación)
export TEST_USER_TOKEN=your_jwt_token_here

./validate_files_v1.sh
```

## Tests incluidos

El script ejecuta los siguientes tests:

### 1. **Redirect 307**
- ✅ Verifica que `/api/documents/upload` redirige a `/api/files/upload`
- ✅ Confirma código HTTP 307 (Temporary Redirect)
- ✅ Valida que el header `Location` es correcto

### 2. **Upload exitoso**
- ✅ Upload a `/api/files/upload` devuelve 201 Created
- ✅ Respuesta contiene: `file_id`, `status`, `bytes`, `mimetype`
- ✅ Status es `READY` al finalizar procesamiento

### 3. **Rate Limiting**
- ✅ Permite 5 uploads por minuto
- ✅ 6º upload devuelve 429 Too Many Requests
- ✅ Usa Redis ZSET con sliding window de 60 segundos

### 4. **Archivo demasiado grande**
- ✅ Archivo >10MB devuelve 413 Request Entity Too Large
- ✅ Error code: `UPLOAD_TOO_LARGE`

### 5. **MIME type no soportado**
- ✅ Archivo `.exe` devuelve 415 Unsupported Media Type
- ✅ Error code: `UNSUPPORTED_MIME`

### 6. **Configuración de entorno**
- ✅ Verifica que variables `FILES_*` están configuradas
- ✅ Documenta compatibilidad con variables legacy `DOCUMENTS_*`

### 7. **Nginx SSE configuration**
- ✅ Verifica que location `/api/files/events/` existe
- ✅ Confirma `proxy_buffering off` para SSE
- ✅ Valida inyección de `Authorization` desde cookie

### 8. **Métricas Prometheus**
- ✅ Endpoint `/api/metrics` disponible
- ✅ Métricas de files presentes:
  - `copilotos_pdf_ingest_seconds{phase}`
  - `copilotos_pdf_ingest_errors_total{code}`
  - `copilotos_tool_invocations_total{tool}`

### 9. **Idempotencia**
- ✅ Mismo `Idempotency-Key` devuelve mismo `file_id`
- ✅ Evita procesamiento duplicado

## Salida esperada

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDACIÓN V1 - SISTEMA DE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[✓] curl instalado
[✓] API disponible en http://localhost:8080
[✓] Token generado exitosamente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Test 1: Redirect 307 (/api/documents/upload → /api/files/upload)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[✓] Redirect 307 devuelto correctamente
[✓] Location header apunta a /api/files/upload

... (más tests)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REPORTE FINAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total de tests ejecutados: 9
Tests exitosos: 9
Tests fallidos: 0

✓ TODOS LOS TESTS PASARON
```

## Troubleshooting

### Error: API no disponible

```bash
# Verificar que los servicios estén corriendo
docker-compose ps

# Iniciar servicios
docker-compose up -d

# Ver logs
docker-compose logs -f copilotos-api
```

### Error: No se pudo obtener token

```bash
# Generar token manualmente y exportarlo
export TEST_USER_TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_user","password":"your_pass"}' | jq -r '.access_token')

./validate_files_v1.sh
```

### Error: Rate limit ya alcanzado

```bash
# Esperar 60 segundos para que se limpie el sliding window
# O limpiar manualmente la key de Redis:
docker-compose exec redis redis-cli DEL "rate_limit:upload:test-user"
```

## Integración en CI/CD

Ejemplo de uso en GitHub Actions:

```yaml
- name: Run Files V1 Validation
  run: |
    export API_URL=http://localhost:8080
    ./scripts/validation/validate_files_v1.sh
  env:
    TEST_USER_TOKEN: ${{ secrets.TEST_USER_TOKEN }}
```

## Próximos pasos

Una vez que todos los tests pasen:

1. ✅ Validación en entorno de desarrollo
2. ⏳ Canary en postproducción (cohort pequeño)
3. ⏳ Monitoreo 24-48h de p95 y errores
4. ⏳ Rollout gradual al 100% de usuarios
5. ⏳ Retiro de endpoints legacy (`add-files`, `document-review`)

## Referencias

- Implementación: `apps/api/src/routers/files.py`
- Servicio de ingestión: `apps/api/src/services/file_ingest.py`
- Storage: `apps/api/src/services/storage.py`
- Configuración: `apps/api/src/core/config.py`
- Nginx: `infra/nginx/nginx.conf`
- Tests E2E: `apps/api/tests/e2e/test_documents.py`
