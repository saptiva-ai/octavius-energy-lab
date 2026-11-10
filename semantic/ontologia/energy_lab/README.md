# Ontología de energy_lab: borrador generado

**Estado:** borrador sin certificar. Lo generó un modelo y nadie lo ha revisado ni corregido todavía. No se usa en ninguna respuesta hasta que se certifique.

## Cómo se generó

| Dato | Valor |
|---|---|
| Fecha | 2026-11-10 |
| Herramienta | `saptiva-ai/auto-ontology-agno` (fork de NVIDIA Auto Ontology sobre Agno), commit `f83e83d6` (el conector de Postgres lee `COMMENT ON`) |
| Fuente | Las 7 vistas de `agg` (migración 0007), leídas con el rol `lab_ontology` de solo lectura. El filtro de privilegios dejó fuera `core` |
| Datos | Demos del laboratorio: Low Carbon London (4 archivos, 135 hogares), UCI (20 clientes), CENACE (7 zonas, septiembre-octubre de 2025) y catálogo de Nodos P |
| Modelo de lenguaje | `nemotron-3.5-lightning` en InferNode dev (razonamiento y rol ligero) |
| Embeddings | `qwen3-embedding-8b` en InferNode dev, 2,048 dimensiones |
| Reranker | Ninguno (InferNode no ofrece reranking; la compilación lo tolera) |
| Máquina | EC2 `t3.large` del laboratorio |

## Archivos

| Archivo | Formato | Contenido |
|---|---|---|
| `auto_ontology.yaml` | Nativo de Auto Ontology | Capa de datos (bases, tablas, columnas, perfiles) y capa semántica (términos, atributos de columna, relaciones, atributos SQL) |
| `ossie.yaml` | [Apache Ossie](https://ossie.apache.org/) | El modelo semántico en el estándar abierto |

## Resultado

7 términos, uno por vista. 0 relaciones semánticas, 0 tablas puente y 0 atributos SQL.

Se compiló dos veces sobre las mismas vistas. La primera, con el conector original, que ignoraba los comentarios de la base: todas las descripciones llegaban vacías y el modelo las escribía solo. La segunda, con el conector que lee `COMMENT ON` (la versión de estos archivos).

| Vista | Sin comentarios | Con comentarios |
|---|---|---|
| `consumo_cliente_cuarto_hora` | "consumo **y generación**" de clientes, sin decir dónde | Potencia promedio de clientes de Portugal (UCI, 2011-2014) por 15 minutos |
| `consumo_hogar_diario` | Home Daily Consumption, en inglés | Consumo Hogar Diario, con la regla de 48 lecturas por día completo |
| `consumo_hogar_media_hora` | Home Energy Consumption, en inglés | Consumo Hogar Media Hora: observaciones históricas, no pronósticos |
| `hogares` | Hogar: "A residential household entity" | Hogar: identificador anónimo (LCLid) y grupo de tarifa |
| `precio_zona_hora` | Precio de electricidad por zona, en inglés | Pesos por MWh, componentes, MDA y MTR glosados, puede ser negativo |
| `tarifa_dinamica` | "Dynamic energy pricing record" | Tarifa ToU de 2013 en peniques por kWh |
| `zonas_carga` | Load Zone, en inglés | Load Zone, con la descripción del catálogo de Nodos P |

La afirmación inventada ("generación") desaparece y las descripciones quedan en español. Documentar la base es la forma más barata de mejorar la ontología.

## Lo que hay que corregir antes de certificar

1. **Nombres.** "Load Zone" sigue en inglés y "Tarifa Dinamica" sin acento: el modelo elige el nombre del término y el comentario solo orienta la descripción.
2. **Relaciones faltantes.** `hogares.hogar` y `consumo_hogar_*.hogar` son la misma llave, y `zonas_carga.zona_carga` con `precio_zona_hora.zona_carga` también. Las vistas no declaran llaves y la inferencia semántica no las detectó.
3. **Sin atributos SQL.** Se proponen a partir del historial de consultas y no hay ninguno. Medidas como "consumo total por grupo de tarifa" o "precio promedio por centro de control" tendrían que definirse a mano.

Estos puntos son evidencia para la sección 4 de la charla (*The Evaluation Trap*): una capa semántica generada por un modelo también puede introducir errores, y hay que medirla, no suponer que ayuda (experimento E8).
