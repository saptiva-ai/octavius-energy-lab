# Beyond the Model: The Art of Evaluating Agent Harnesses

*Building Reliable AI Systems with Local LLMs, Semantic Layers, and Time-Series Forecasting*

Documento de diseño de la charla para Cloud Community. Se expone en español y los títulos de sección van en inglés.

Estado: borrador de la fase 0, 2026-11-10. Todavía no hay cifras de resultados. Lo marcado **[por medir]** se llenará solo con artefactos de experimentos que tengan su `experiment_id`.

---

## Core thesis

> A good model does not necessarily make a good AI system. The agent harness determines how models, tools, data, context, and decisions interact.

### Cuatro niveles de evaluación

| Nivel | Pregunta | Qué se evalúa | Ejemplo de métrica | Lo que NO dice |
|---|---|---|---|---|
| **Model evaluation** | ¿Qué tan bueno es el modelo por sí solo? | El LLM o el modelo de forecasting, con entrada fija | BFCL (tool calling), MASE de TimesFM en un benchmark | Si el sistema elegirá la herramienta correcta con tus datos |
| **Agent evaluation** | ¿El agente completa la tarea? | La política del agente: prompt y modelo | Task success, tool selection accuracy | Por qué falló |
| **Harness evaluation** | ¿Cambia el resultado si cambia lo que rodea al modelo? | El runtime: herramientas, contratos, validadores, límites y contexto | Diferencia pareada entre A y B con el modelo fijo, y ablaciones | La precisión propia del modelo |
| **End-to-end system evaluation** | ¿El sistema completo es confiable para quien lo usa? | El producto entero: datos, infraestructura, UI, latencia y costo | Grounded answer rate, leakage rate, p95, costo por tarea | A qué componente atribuir cada falla, si no hay ablaciones |

**Qué es el harness en esta charla:** todo lo que no son los pesos de los modelos.

- Prompts de sistema.
- Catálogo y contratos de herramientas, y la política para elegir herramientas.
- Validación de esquemas y de SQL.
- Fronteras temporales.
- Capa semántica.
- Verificación de resultados y manejo de errores.
- Presupuestos de tokens, rondas y tiempo.
- Trazas.

### Hipótesis experimental

**H1:** si se mantienen fijos los siguientes elementos, dos harnesses producen diferencias medibles en task success, temporal leakage y grounded answer rate:

- El LLM: Qwen3-8B, con la misma cuantización y el mismo muestreo.
- El modelo de forecasting: TimesFM 2.5, con el mismo checkpoint.
- Los datos y la fecha de corte.
- Las preguntas.

**H0:** debe poder sostenerse. Si las diferencias no superan la variabilidad entre repeticiones, medida con intervalos bootstrap pareados, se reporta así. Un resultado nulo, o un B que empeora, también es contenido válido para la charla.

**Principio rector:** *design the benchmark to reveal where the harness actually fails*.

### Datos de la charla

| Rol | Dataset | Por qué |
|---|---|---|
| **Principal** | CENACE: demanda horaria por región del Sistema Eléctrico Nacional y precios marginales locales (PML) por nodo | Relevancia para una audiencia mexicana. Volumen real para PostgreSQL. CENACE publica su propio pronóstico, que sirve como baseline independiente. Ofrece un caso natural de leakage: usar la demanda real como si se conociera en la fecha de corte |
| **Secundario** | Low Carbon London (5,567 hogares, cada 30 minutos, 2011 a 2014, CC BY 4.0) | Granularidad por hogar y una tarifa dinámica real (dToU 2013) para preguntas por cohorte |

Las cifras exactas de CENACE (periodo, número de nodos, filas y términos de uso) se documentan en `docs/data/` tras la verificación. **[por verificar]**

---

## Sección 1. Beyond the Model: Why Model Benchmarks Are Not Enough

- **Mensaje principal:** un leaderboard mide un modelo con entradas controladas. En producción el modelo ve lo que el harness le entrega y solo actúa con lo que el harness le permite.
- **Conceptos técnicos:**
  - Los cuatro niveles de evaluación.
  - Capacidad contra confiabilidad.
  - pass@k contra pass^k.
  - Benchmarks contaminados.
- **Evidencia o experimento:** E0. La misma pregunta y el mismo Qwen3-8B en dos harnesses, con dos resultados distintos y sus trazas. El caso se toma de corridas reales.
- **Qué mostrar:**
  - Diagrama de los cuatro niveles.
  - Un par real de respuestas lado a lado, con su traza abreviada.
- **Tiempo:** 5 min.

## Sección 2. Anatomy of an Agent Harness: Models, Tools, Context and Execution

- **Mensaje principal:** el harness está formado por piezas con nombre propio, y cada una puede introducir una falla o prevenirla.
- **Conceptos técnicos:**
  - El loop de decisión. En Octavius hoy es: decide, tools, narración, con `MAX_DECIDE_ROUNDS = 2`.
  - Contratos de herramientas: esquemas tipados y `AnalyticsResponse`.
  - MCP como frontera entre el runtime y los plugins.
  - Guardas de SQL: AST con SQLGlot, allowlist, `statement_timeout` y transacciones de solo lectura.
  - Presupuestos y trazas.
- **Evidencia o experimento:** diagrama derivado del código real (`docs/architecture/`).
- **Qué mostrar:** diagrama de componentes con A y B superpuestos.
- **Tiempo:** 6 min.

## Sección 3. The Energy Challenge: Forecasting at Scale

- **Mensaje principal:** que PostgreSQL guarde cientos de millones de filas no significa que el modelo deba verlas. El harness decide qué ventana, qué agregado y qué corte temporal llegan al LLM y a TimesFM.
- **Conceptos técnicos:**
  - Demanda del Sistema Eléctrico Nacional por región, PML por nodo y su escala.
  - Hogares de Londres y la tarifa dinámica.
  - Particionamiento temporal y agregados materializados.
  - TimesFM 2.5: contexto largo y cuantiles.
  - Rolling-origin backtesting.
  - Por qué no MAPE: hay ceros y PML negativos posibles **[por verificar]**. Usamos MAE, WAPE y MASE.
- **Evidencia o experimento:**
  - E1, benchmark de base de datos.
  - E2, backtest de seasonal naive, del pronóstico oficial de CENACE y de TimesFM 2.5 **[por medir]**.
- **Qué mostrar:**
  - El conteo de filas en vivo.
  - Un plan con partition pruning.
  - Una gráfica histórica con el corte, el horizonte y los cuantiles.
- **Tiempo:** 6 min.

## Sección 4. The Evaluation Trap: How Harnesses Introduce Bias

- **Mensaje principal:** la forma de evaluar también es un harness, y puede sesgar la conclusión.
- **Conceptos técnicos:**
  - Siete sesgos: selection, temporal leakage, metric, evaluation contamination, LLM-as-a-judge, aggregation y tool availability.
  - Ground truth independiente del sistema evaluado.
  - Un juez de otro proveedor que el sistema medido. Octavius ya usa este patrón.
- **Evidencia o experimento:**
  - E4: ¿cambia el ranking según la métrica?
  - E5: juez LLM contra verificador determinista.
  - E6: resultados por región del Sistema Eléctrico Nacional y por grupo de tarifa de Londres, contra el agregado global **[por medir]**.
- **Qué mostrar:**
  - Una tabla donde el ganador cambia según la métrica, o la evidencia de que no cambia.
  - Un caso real de leakage detectado.
- **Tiempo:** 7 min.

## Sección 5. Controlled Experiments: Same Models, Different Harnesses

- **Mensaje principal:** para atribuirle una mejora al harness hay que fijar todo lo demás y quitar una pieza a la vez.
- **Conceptos técnicos:**
  - Diseño pareado con k repeticiones.
  - Ablaciones, cada una activada o desactivada: capa semántica, validación temporal, verificación de la salida y restricciones de herramientas.
  - Variables de confusión: no determinismo del servidor de inferencia, caché, orden de ejecución y temperatura de la GPU.
  - Intervalos bootstrap pareados.
- **Evidencia o experimento:** E7, la matriz de ablaciones con el costo en latencia y tokens **[por medir]**.
- **Qué mostrar:**
  - La contribución de cada componente, con intervalos.
  - Las fallas por categoría.
- **Tiempo:** 8 min.

## Sección 6. Live Demo: Octavius Energy Lab

- **Mensaje principal:** todo corre en una laptop, con un LLM local, PostgreSQL y TimesFM, sobre Octavius extendido con plugins.
- **Evidencia o experimento:**
  - Tres momentos en 5 a 8 minutos: *Ask the Data*, *Predict the Future* y *Same Model, Different Harness*.
  - Los escenarios se eligen a partir de resultados medidos.
  - El modo replay se identifica en pantalla como **REPLAY**.
- **Qué mostrar:** el chat de Octavius, la gráfica de forecast y el dashboard comparativo entre A y B con sus trazas.
- **Tiempo:** 8 min.

## Sección 7. Lessons Learned: Building Reliable Agentic Systems

- **Mensaje principal:** lo que aprendimos al construir y medir, incluido lo que no funcionó.
- **Conceptos técnicos:** se definen con los resultados. Por ahora son temas a validar:
  - El costo de cada validación.
  - Las fallas que ningún validador atrapó.
  - Los desacuerdos entre el juez y el verificador.
- **Evidencia o experimento:** resultados negativos y limitaciones.
- **Qué mostrar:** lecciones, cada una con su evidencia.
- **Tiempo:** 5 min.

**Total:** 45 minutos, más 5 a 10 de preguntas.

---

## Experimentos

| ID | Pregunta | Fase | Sección |
|---|---|---|---|
| E0 | Mismo modelo con dos harnesses: ¿los resultados difieren? | 6 | 1, 6 |
| E1 | Ingesta y consultas a escala | 1 | 3 |
| E2 | Backtest: seasonal naive, pronóstico de CENACE y TimesFM 2.5 (3.0 opcional) | 3 | 3 |
| E3 | Qwen3-8B con thinking y sin thinking | 2 | 2, 5 |
| E4 | Sensibilidad del ranking a la métrica | 6 | 4 |
| E5 | Juez LLM contra verificador determinista | 6 | 4 |
| E6 | Resultados por cohorte contra el agregado global | 6 | 4 |
| E7 | Matriz de ablaciones | 5-6 | 5 |
| E8 | Capa semántica activada o desactivada, si resulta viable | 4 | 5 |

## Reglas para el material final

- Cada gráfica sale de un artefacto con su `experiment_id`.
- No se hacen afirmaciones comerciales de precisión, y los resultados negativos se reportan.
- Las diapositivas se generan después de la fase 6.
