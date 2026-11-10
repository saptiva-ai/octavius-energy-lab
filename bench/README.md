# Benchmarks

## E1: PostgreSQL a escala

Mide sobre la base `energy_lab` cargada:

- **Volumen:** filas reales por fuente, tamaño de tablas e índices y bytes por fila.
- **Ingesta:** throughput por fuente, sacado de `core.ingest_batch`.
- **Latencia:** p50 y p95 de consultas canónicas, corridas con el rol del agente (`lab_agent`) después de un calentamiento.
- **Particiones:** cuántas particiones lee cada consulta según `EXPLAIN ANALYZE`.

Conteos y tamaños se leen con `lab_eval`, nunca con un superusuario.

Las consultas marcadas como **antipatrón** dan el mismo resultado que su par, pero un filtro sobre una expresión de `ts` (`date_trunc('day', ts) >= ...`) impide la poda de particiones. Es el tipo de consulta que un agente puede generar si el harness no la valida.

```bash
make bench-e1     # results/e1/AAAA-MM-DD.json y un resumen en español en results/e1/AAAA-MM-DD.md
```

Variables: `LAB_AGENT_DSN` y `LAB_EVAL_DSN` (ver `envs/.env.example`).

El resumen en Markdown interpreta cada medida en español y declara sus límites: una sola máquina y una sola corrida, sin red ni modelo de lenguaje. Los resultados solo se publican si salen de una corrida con todos los bugs conocidos corregidos.
