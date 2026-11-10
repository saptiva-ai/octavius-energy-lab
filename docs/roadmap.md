# Roadmap: fases y PRs

Fase 0, 2026-11-10. Cada PR es atómico, trae sus pruebas y no se fusiona sin revisión.

## Fases

| Fase | Entregable | Criterio de salida |
|---|---|---|
| 0. Discovery | Documentos de charla, arquitectura, fuentes y roadmap | Aprobación del diseño |
| 1. Data Foundation | Fork limpio, Postgres `energy_lab`, migraciones, ingesta CENACE/LCL/UCI, perfiles, benchmark E1 | Perfil `smoke` en CI; `demo` cargado local; estimación de `full` |
| 2. Local Agent | Ollama más Qwen3-8B, registro de N plugins MCP, plugin `energy-data`, E3 | El agente responde preguntas de datos con tool calls trazadas |
| 3. Forecasting | Plugin `forecasting`, baselines, backtesting E2 | Forecasts reproducibles con contrato completo |
| 4. Semantic Layer | Catálogo local y evaluación de viabilidad de Auto Ontology (E8) | Flag funcional; informe de viabilidad |
| 5. Harness Variants | `HarnessConfig` y componentes de B | A y B corren los mismos escenarios |
| 6. Evaluation Runner | Escenarios, ground truth, métricas, sesgos, tracking, export | Corrida completa con artefactos reales |
| 7. Dashboard & Demo | `chart_type: forecast`, `/evals`, replay | Demo de 5-8 min reproducible |
| 8. Talk Materials | Deck y notas desde resultados medidos | Cada gráfica con su `experiment_id` |

## Primeros cinco PRs

1. **`chore: snapshot limpio de Octavius como base del laboratorio`**
   - Importar el árbol de la variante interna de Octavius en `b0a8dd6` sin historial, excluyendo todo lo de §14 de `current-state.md`.
   - Retirar las referencias rotas, con tests de backend y web en verde.
   - gitleaks y grep de nombres de cliente en cero.
   - Licencia, NOTICE y README.
2. **`feat(db): base energy_lab con roles, migraciones y particionamiento`**
   - Servicio postgres en el perfil `lab`.
   - Migraciones `0001-000N` (esquemas, roles, `core.observation` particionada, `lab.*`) y su runner.
   - Tests: que `lab_agent` no pueda escribir y que `statement_timeout` aplique.
3. **`feat(ingest): pipeline genérico con perfiles y conector UCI`**
   - Framework de ingesta: descarga con sha256, staging COPY, `ingest_batch` reanudable, upsert idempotente y verificación de conteos.
   - Perfil `smoke` con fixture UCI recortado.
4. **`feat(ingest): conector CENACE PML/PND y demanda`**
   - Cliente SW-PML/SW-PEND con los límites de 7 días y 20 nodos, y reintentos.
   - Normalización de `hora` 1-24 a `timestamptz`.
   - Verificar el desglose y el pronóstico de demanda antes de escribir su conector.
   - Fixtures grabadas, sin red en CI.
5. **`feat(ingest): conector Low Carbon London y benchmark E1`**
   - Ingesta de LCL y tarifas.
   - Agregados en `agg`.
   - Script de benchmark (filas, throughput, tamaños, p50/p95, EXPLAIN) con salida a `lab.*`.

## Requisitos de infraestructura esperados

| Recurso | Smoke | Demo | Full |
|---|---|---|---|
| Disco | < 1 GB | 5-15 GB | 60-100 GB (CENACE nodos MDA+MTR ~25-35 GB, LCL ~20-30 GB con índices; estimación por medir) |
| RAM | 4 GB | 8-10 GB con el LLM | Ingesta por streaming; no carga todo en memoria |
| GPU | No | 16 GB: Qwen3-8B Q4 y TimesFM 2.5 | Igual |
| Tiempo | Minutos | < 1 h | Horas; las 50,000 llamadas de PML por proceso dominan |

El host tiene 140 GB libres, así que el perfil Full cabe pero ajustado. Se pide aprobación antes de correrlo.
