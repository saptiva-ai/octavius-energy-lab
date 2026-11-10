## MCP Performance & Load Testing

Documentación completa para tests de performance, carga y stress de las herramientas MCP.

---

## Objetivos

Los tests de performance nos ayudan a:

1. **Medir rendimiento**: Tiempo de respuesta, throughput, latencia
2. **Detectar cuellos de botella**: Identificar componentes lentos
3. **Validar escalabilidad**: Verificar comportamiento bajo carga
4. **Monitorear regresiones**: Comparar con baseline histórico
5. **Optimizar caching**: Medir efectividad del caché
6. **Stress testing**: Encontrar límites del sistema

---

## Estructura

```
tests/performance/
├── __init__.py
├── conftest.py                    # Configuración y fixtures de performance
├── test_mcp_performance.py        # Tests de performance MCP (680 líneas)
└── README_PERFORMANCE.md          # Esta documentación
```

---

## Tipos de Tests

### 1. Response Time Tests (Single Request)

Mide el tiempo de respuesta de invocaciones individuales.

**Tests incluidos**:
- `test_deep_research_response_time` - Medición con 10 rondas
- `test_extract_document_text_response_time_cached` - Con cache hit
- `test_extract_document_text_response_time_extraction` - Con extracción real

**Métricas**:
- ⏱️ Tiempo promedio de respuesta
- 📊 Min/Max latencia
- 🔄 Rounds ejecutados

### 2. Concurrent Load Tests

Prueba el sistema con múltiples peticiones simultáneas.

**Tests incluidos**:
- `test_concurrent_document_extraction_10_users` - 10 usuarios concurrentes
- `test_concurrent_deep_research_5_users` - 5 usuarios concurrentes
- `test_sustained_load_30_requests` - 30 requests secuenciales

**Métricas**:
- 🚀 Throughput (req/s)
- ⏱️ Latencia p50, p95, p99
- ✅ Tasa de éxito
- ⏳ Duración total

### 3. Stress Tests (Heavy Load)

Empuja el sistema a sus límites para identificar puntos de quiebre.

**Tests incluidos** (marker `slow`):
- `test_stress_burst_50_concurrent_requests` - 50 requests simultáneos
- `test_stress_sustained_100_requests_over_time` - 100 requests en batches

**Métricas**:
- 💥 Tasa de fallo
- 🔥 Throughput bajo presión
- 📈 Latencia p99
- 🎯 Umbral de éxito (≥80%)

### 4. Cache Performance Tests

Compara rendimiento con y sin caché.

**Tests incluidos**:
- `test_cache_hit_vs_miss_performance` - Speedup del caché

**Métricas**:
- 💾 Tiempo cache hit vs miss
- ⚡ Speedup factor (ej: 3.5x)
- 📊 Efectividad del caché

---

## Ejecución de Tests

### Comandos Makefile (Recomendado)

```bash
# Ejecutar todos los tests de performance (excluye stress tests)
make test-mcp-performance

# Ejecutar con benchmarks detallados
make test-mcp-performance-benchmark

# Ejecutar stress tests (lentos)
make test-mcp-stress

# Guardar baseline de performance
make test-mcp-performance-save-baseline

# Comparar contra baseline
make test-mcp-performance-compare
```

### Pytest Directo

```bash
# Todos los tests de performance
pytest tests/performance/test_mcp_performance.py -v -m performance

# Solo benchmarks (sin stress tests)
pytest tests/performance/test_mcp_performance.py -m "performance and not slow"

# Solo stress tests
pytest tests/performance/test_mcp_performance.py -m "performance and slow"

# Con output detallado
pytest tests/performance/test_mcp_performance.py -v -s -m performance

# Specific test class
pytest tests/performance/test_mcp_performance.py::TestMCPToolsResponseTime -v

# Specific test
pytest tests/performance/test_mcp_performance.py::TestMCPToolsResponseTime::test_deep_research_response_time -v
```

---

## Interpretar Resultados

### Output Example

```
📊 Concurrent Load (10 users):
  Total Duration: 2.45s
  Throughput: 4.08 req/s
  Avg Latency: 0.245s

📊 Sustained Load (30 requests):
  Total Duration: 5.12s
  Throughput: 5.86 req/s
  Success Rate: 100.0%
  Latency p50: 0.165s
  Latency p95: 0.298s
  Latency p99: 0.312s

🔥 Stress Test (50 concurrent):
  Total Duration: 8.34s
  Throughput: 5.99 req/s
  Successful: 48/50 (96.0%)
  Failed: 2/50
  Latency p50: 1.234s
  Latency p95: 2.567s
  Latency p99: 3.012s

💾 Cache Performance:
  Cache Hit (avg): 0.123s
  Cache Miss (avg): 0.456s
  Speedup: 3.7x
```

### Métricas Clave

| Métrica | Bueno | Aceptable | Malo |
|---------|-------|-----------|------|
| **p50 Latency** | < 0.2s | < 0.5s | > 1s |
| **p95 Latency** | < 0.5s | < 1s | > 2s |
| **p99 Latency** | < 1s | < 2s | > 5s |
| **Throughput** | > 10 req/s | > 5 req/s | < 2 req/s |
| **Success Rate** | 100% | > 95% | < 90% |
| **Cache Speedup** | > 3x | > 2x | < 1.5x |

### Interpretación

**✅ Performance Óptimo**:
- p95 < 500ms
- Throughput > 10 req/s
- Success rate 100%
- Cache speedup > 3x

**⚠️ Performance Aceptable**:
- p95 < 1s
- Throughput > 5 req/s
- Success rate > 95%
- Cache speedup > 2x

**❌ Performance Problemático**:
- p95 > 2s
- Throughput < 2 req/s
- Success rate < 90%
- Cache speedup < 1.5x

---

## Configuración

### pytest-benchmark

Tests usan `pytest-benchmark` para mediciones precisas:

```python
async def test_performance(self, benchmark):
    async def make_request():
        # código a medir
        ...

    result = await benchmark.pedantic(
        make_request,
        rounds=10,        # 10 rondas de medición
        iterations=1      # 1 iteración por ronda
    )
```

### Configuración en conftest.py

```python
benchmark_config = {
    "min_rounds": 5,
    "min_time": 0.1,
    "max_time": 5.0,
    "warmup": True,
    "warmup_iterations": 2,
}
```

### Resource Monitoring

Tests incluyen monitoreo de recursos:

```python
def test_with_monitoring(self, resource_monitor):
    # código del test
    ...

    # Automáticamente imprime al final:
    # 📊 Resource Usage:
    #   Memory: 245.3 MB (+12.5 MB)
    #   CPU: 45.2%
```

---

## Benchmark Management

### Guardar Baseline

```bash
# Primera vez: establecer baseline
make test-mcp-performance-save-baseline
```

Esto crea `.benchmarks/baseline.json` con métricas actuales.

### Comparar con Baseline

```bash
# Después de cambios: comparar performance
make test-mcp-performance-compare
```

**Falla si**:
- Mean performance regresa > 10%
- Cualquier métrica empeora significativamente

### Ver Historial

```bash
# Listar todos los benchmarks guardados
ls -la apps/api/.benchmarks/

# Ver benchmark específico
cat apps/api/.benchmarks/baseline.json
```

---

## Assertions en Tests

### Response Time Tests

```python
# Benchmark automático (no assertions manuales)
result = await benchmark.pedantic(make_request, rounds=10, iterations=1)
```

### Concurrent Load Tests

```python
assert successful == 10, f"Only {successful}/10 requests succeeded"
assert duration < 5.0, f"10 concurrent requests took {duration:.2f}s (should be < 5s)"
assert throughput > 2.0, f"Throughput {throughput:.2f} req/s is too low"
```

### Stress Tests

```python
assert successful >= 40, f"Only {successful}/50 requests succeeded (< 80%)"
assert p95 < 5.0, f"p95 latency {p95:.3f}s is extremely high"
```

### Cache Tests

```python
assert speedup > 1.2, f"Cache only provides {speedup:.1f}x speedup (should be > 1.2x)"
```

---

## Troubleshooting

### Tests muy lentos

**Problema**: Tests tardan demasiado

**Solución**:
```bash
# Excluir stress tests (marker slow)
pytest tests/performance -m "performance and not slow"

# Reducir rounds en benchmark
# Editar conftest.py: min_rounds = 3
```

### Variabilidad alta en métricas

**Problema**: Resultados inconsistentes entre runs

**Causas**:
- Otros procesos en el sistema
- Docker compartiendo recursos
- Conexión de red inestable

**Solución**:
```bash
# Cerrar aplicaciones innecesarias
# Ejecutar múltiples veces y promediar
for i in {1..5}; do
  make test-mcp-performance
done

# Aumentar warmup iterations
# En conftest.py: warmup_iterations = 5
```

### Benchmarks fallan al comparar

**Problema**: `--benchmark-compare` falla

**Solución**:
```bash
# Verificar que baseline existe
ls -la apps/api/.benchmarks/baseline.json

# Recrear baseline si es necesario
make test-mcp-performance-save-baseline

# Ajustar umbral de falla
pytest ... --benchmark-compare-fail=mean:20%  # 20% en lugar de 10%
```

### Memory leaks

**Problema**: Uso de memoria crece durante tests

**Diagnóstico**:
```python
def test_with_monitoring(self, resource_monitor):
    # El fixture imprime memory delta al final
    ...

# Output:
# Resource Usage:
#   Memory: 456.7 MB (+125.3 MB)  # ⚠️ +125MB es mucho
```

**Solución**:
- Revisar fixtures que no limpian recursos
- Verificar conexiones de DB/Redis cerradas
- Usar `gc.collect()` explícito si es necesario

---

## Agregar Nuevos Tests

### 1. Test de Response Time

```python
@pytest.mark.performance
@pytest.mark.asyncio
class TestNewToolResponseTime:
    async def test_new_tool_response_time(
        self,
        client: AsyncClient,
        perf_user_with_token,
        benchmark
    ):
        """Measure new_tool response time."""
        access_token, user_id = perf_user_with_token

        payload = {
            "tool": "new_tool",
            "payload": {"param": "value"}
        }

        async def make_request():
            response = await client.post(
                "/api/mcp/tools/invoke",
                json=payload,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response

        result = await benchmark.pedantic(
            make_request,
            rounds=10,
            iterations=1
        )

        assert result.status_code == 200
```

### 2. Test de Carga Concurrente

```python
async def test_concurrent_new_tool_20_users(
    self,
    client: AsyncClient,
    perf_user_with_token
):
    """Test 20 concurrent requests."""
    access_token, user_id = perf_user_with_token

    payload = {"tool": "new_tool", "payload": {}}

    async def make_request():
        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        return response.status_code, time.time()

    start_time = time.time()
    tasks = [make_request() for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start_time

    successful = sum(1 for r in results if not isinstance(r, Exception) and r[0] == 200)
    throughput = 20 / duration

    print(f"\n📊 New Tool Concurrent (20 users):")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Throughput: {throughput:.2f} req/s")
    print(f"  Success: {successful}/20")

    assert successful == 20
    assert throughput > 3.0
```

### 3. Test de Stress

```python
@pytest.mark.slow
async def test_stress_new_tool_100_requests(
    self,
    client: AsyncClient,
    perf_user_with_token
):
    """Stress test with 100 concurrent requests."""
    # Similar a concurrent pero con 100 requests
    # Assertions más permisivas (success >= 80%)
```

---

## Best Practices

### DO

1. **Usar fixtures de performance**: `perf_user_with_token`, `perf_document_pdf`
2. **Mock servicios externos**: Aletheia, MinIO, etc
3. **Medir métricas relevantes**: p50, p95, p99, throughput
4. **Documentar thresholds**: Assertions con mensajes claros
5. **Imprimir resultados**: `print(f"\n📊 Metrics: ...")` para debugging
6. **Usar markers**: `@pytest.mark.performance`, `@pytest.mark.slow`
7. **Cleanup**: Asegurar que fixtures limpian recursos

### DON'T

1. **No hardcodear valores**: Usar variables para thresholds
2. **No ignorar variabilidad**: Ejecutar múltiples rounds
3. **No testear solo happy path**: Incluir escenarios de error
4. **No olvidar stress tests**: Identificar límites del sistema
5. **No mockear todo**: Performance tests necesitan componentes reales
6. **No commitear benchmarks grandes**: `.benchmarks/` en `.gitignore`

---

## Métricas Monitoreadas

### Latencia (Response Time)

- **p50** (mediana): 50% de requests más rápidos
- **p95**: 95% de requests más rápidos (outliers excluidos)
- **p99**: 99% de requests más rápidos (peor caso típico)
- **Max**: Peor caso absoluto

### Throughput

- **req/s**: Requests procesados por segundo
- **Duration**: Tiempo total para N requests
- **Concurrency**: Número de requests simultáneos

### Reliability

- **Success Rate**: % de requests exitosos (200 OK)
- **Error Rate**: % de requests fallidos (≠ 200)
- **Timeout Rate**: % de requests que timeout

### Resources

- **Memory**: Uso de RAM durante test
- **Memory Delta**: Incremento desde inicio
- **CPU**: % de CPU utilizado

---

## Objetivos de Performance

### Tier 1: Operaciones Rápidas (cached)
- **Target**: p95 < 200ms
- **Examples**: document_extraction (cached), tools_list

### Tier 2: Operaciones Normales
- **Target**: p95 < 1s
- **Examples**: document_extraction (pypdf), excel_analyzer

### Tier 3: Operaciones Pesadas
- **Target**: p95 < 5s
- **Examples**: deep_research, OCR extraction

### Tier 4: Operaciones Muy Pesadas
- **Target**: p95 < 30s
- **Examples**: deep_research (deep mode), full validation

---

## Referencias

- [pytest-benchmark docs](https://pytest-benchmark.readthedocs.io/)
- [Locust (load testing)](https://locust.io/)
- [Performance Testing Guide](https://martinfowler.com/articles/practical-test-pyramid.html#PerformanceTests)
- [MCP Architecture](../../../../docs/MCP_ARCHITECTURE.md)
- [Integration Tests](../integration/README_MCP_TESTS.md)
