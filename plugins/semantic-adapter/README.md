# semantic-adapter

Plugin MCP de capa semántica para Octavius. Sigue el mismo patrón que los demás plugins: FastMCP sobre FastAPI, en su propio contenedor. **No sabe nada del dominio:** trabaja con cualquier ontología exportada por Auto Ontology (fork `saptiva-ai/auto-ontology-agno`), sin importar el motor de base de datos de origen.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `search_terms(query, limit)` | Términos y columnas más cercanos a un concepto, con su vista y columna físicas y un puntaje (coseno 0-1) |
| `get_term(name)` | Un término (por nombre o sinónimo) con su descripción, vistas, columnas, relaciones y medidas |
| `check_answerable(question)` | Extrae los conceptos de la pregunta y dice si la ontología los cubre. No responde la pregunta ni escribe SQL |

Cada respuesta incluye la versión de la ontología (sha256 de la exportación más las correcciones), si está **certificada** y el estado de las correcciones (aplicadas, huérfanas, quién revisó). Un borrador generado por un modelo se declara como tal.

## Correcciones humanas

`correcciones.yaml`, junto a la exportación, se aplica encima de lo que generó el modelo: nombres, sinónimos, descripciones de columnas, relaciones y medidas (expresiones SQL de agregación). Sus llaves son nombres físicos (`agg.vista`, `agg.vista.columna`), no los IDs del modelo, así que sobreviven a una recompilación.

- Si una vista o columna desaparece de la base, la corrección queda **huérfana**: se reporta en cada respuesta y la ontología deja de estar certificada.
- La certificación la declara quien revisa (`certificada: true` y `revisado_por`), nunca el modelo.

**Cómo funciona `check_answerable`:**
- Un modelo extrae los conceptos con salida estructurada (Agno sobre InferNode).
- Cada concepto se busca en el índice. Se da por cubierto si su coseno supera `SEMANTIC_THRESHOLD`.
- Las referencias de tiempo ("mañana", "junio de 2025") no cuentan contra la cobertura, pero se devuelven aparte.

## Interruptor

`ENERGY_SEMANTIC_LAYER=off` (valor por omisión) o `local`. Con `off`, las herramientas responden `{"enabled": false}` en lugar de inventar. Es la ablación del experimento E8.

## Configuración

Ver el docstring de `src/semantic_adapter/server.py`:

| Variable | Contenido |
|---|---|
| `SEMANTIC_BASE_URL`, `SEMANTIC_API_KEY` | Endpoint compatible con OpenAI y su llave |
| `SEMANTIC_LLM_MODEL` | Modelo que extrae los conceptos |
| `SEMANTIC_EMBED_MODEL`, `SEMANTIC_EMBED_DIMENSIONS` | Modelo de embeddings y su dimensión |
| `SEMANTIC_ONTOLOGY_PATH` | Ruta del YAML de la ontología |
| `SEMANTIC_CORRECTIONS_PATH` | Capa de correcciones (por omisión, `correcciones.yaml` junto al YAML) |
| `SEMANTIC_THRESHOLD` | Coseno mínimo para dar un concepto por cubierto |
| `SEMANTIC_CACHE_DIR` | Caché del índice |
| `LLM_EXTRA_HEADERS_JSON` | Encabezados extra para el gateway |

El índice se guarda en caché por versión de ontología y modelo: reiniciar el plugin no vuelve a pedir embeddings.

## Pruebas

```bash
uv run --with-editable . --with pytest pytest -q
```

Corren sin red, con un embedder determinista y un extractor fijo, sobre la ontología real exportada (`semantic/ontologia/energy_lab/`).
