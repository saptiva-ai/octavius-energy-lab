# Integration Tests

**Objetivo**: Validar flujos completos end-to-end con dependencias reales.

---

## Diferencia: Unit vs Integration

| Aspecto | Unit Tests | Integration Tests |
|---------|-----------|-------------------|
| **Alcance** | Función/clase aislada | Flujo completo |
| **Dependencias** | Todo mockeado | DB/Redis/API reales o realistas |
| **Velocidad** | Rápido (~40ms/test) | Más lento (~200-500ms/test) |
| **Fragilidad** | Baja (sin deps externas) | Media (depende de servicios) |
| **Confianza** | Valida lógica | Valida integración |

---

## Prerequisitos

### Opción A: Servicios con Docker Compose (Recomendado)

```bash
# Desde root del proyecto
docker-compose up -d mongodb redis

# Verificar
docker ps | grep -E "mongo|redis"
```

### Opción B: Servicios locales

```bash
# MongoDB
sudo systemctl start mongod

# Redis
sudo systemctl start redis
```

---

## Ejecutar Integration Tests

```bash
cd apps/api
source .venv/bin/activate

# Todos los integration tests
pytest tests/integration/ -v --tb=short

# Test específico
pytest tests/integration/test_auth_flow.py -v

# Con output detallado
pytest tests/integration/ -v -s

# Solo un test class
pytest tests/integration/test_auth_flow.py::TestCompleteAuthJourney -v
```

---

## Tests Disponibles

### 1. `test_auth_flow.py` (Auth completo)

**Flujos testeados**:
- ✅ Registration → DB persistence
- ✅ Login → JWT generation
- ✅ Token refresh → New tokens
- ✅ Protected endpoint access
- ✅ Logout → Token invalidation
- ✅ Lifecycle completo (register → ... → logout)

**Test Classes**:
- `TestRegistrationFlow` (3 tests)
- `TestLoginFlow` (3 tests)
- `TestTokenRefreshFlow` (2 tests)
- `TestProtectedEndpointAccess` (3 tests)
- `TestLogoutFlow` (1 test)
- `TestCompleteAuthJourney` (1 test)

**Total**: ~13 tests

---

## Configuración de Tests

### Database Isolation

Los tests usan una base de datos separada (`copilotos_test`) que se limpia entre tests:

```python
@pytest.fixture(scope="session")
async def test_db():
    """Uses copilotos_test database"""
    test_db_name = "copilotos_test"
    # ... setup
    yield client[test_db_name]
    # Cleanup: drop database after tests
    await client.drop_database(test_db_name)
```

### Fixtures Disponibles

**`client`**: TestClient síncrono para requests HTTP
```python
def test_example(client: TestClient):
    response = client.post("/api/endpoint", json={...})
```

**`async_client`**: AsyncClient para streams/SSE
```python
async def test_streaming(async_client: AsyncClient):
    async with async_client.stream("GET", "/api/stream") as response:
        async for chunk in response.aiter_text():
            ...
```

**`test_user`**: Usuario de prueba creado automáticamente
```python
async def test_something(test_user):
    # test_user = {"email": "...", "password": "...", "user_id": "..."}
```

**`authenticated_client`**: Client con headers de auth
```python
def test_protected(authenticated_client):
    client, auth_data = authenticated_client
    response = client.get("/api/protected")  # Already authenticated
```

**`clean_db`**: Database limpia antes de cada test
```python
async def test_with_clean_db(clean_db):
    # Database is empty here
```

---

## Troubleshooting

### Error: "Connection refused" (MongoDB)

```bash
# Verificar que MongoDB corre
docker ps | grep mongo
# o
sudo systemctl status mongod

# Ver logs
docker logs mongodb
```

### Error: "Connection refused" (Redis)

```bash
# Verificar que Redis corre
docker ps | grep redis
# o
sudo systemctl status redis

# Reiniciar
docker restart redis
```

### Error: "Database not initialized"

```bash
# Los tests deben inicializar Beanie automáticamente
# Si falla, verificar que conftest.py tiene init_beanie()
```

### Tests pasan localmente pero fallan en CI

- ✅ Usar `docker-compose` en CI para servicios
- ✅ Esperar a que servicios estén listos (healthchecks)
- ✅ Limpiar DB entre test runs

---

## Próximos Integration Tests

1. **`test_chat_flow.py`** (pendiente)
   - Create session → Send message → Receive response
   - Attach document → Chat with context
   - Stream response

2. **`test_document_flow.py`** (pendiente)
   - Upload → OCR → Cache → Retrieve

3. **`test_research_flow.py`** (pendiente)
   - Create task → Progress updates → Completion

---

## Performance Expectations

- **Auth flow completo**: ~2-3 segundos (incluye DB operations)
- **Single login test**: ~200-400ms
- **Suite completa (future)**: ~30-60 segundos

**Nota**: Integration tests son más lentos que unit tests por diseño. Si son muy lentos (>5 min), hay un problema.

---

## CI/CD Integration

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd apps/api
          pip install -r requirements.txt

      - name: Run integration tests
        run: |
          cd apps/api
          pytest tests/integration/ -v
        env:
          MONGODB_URI: mongodb://localhost:27017
          REDIS_URL: redis://localhost:6379
```

---

**Created**: 2025-10-18
**Status**: Auth flow complete, chat/research flows pending
