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
| `correcciones.yaml` | Propio del plugin `semantic-adapter` | Correcciones humanas con llave física: nombres, descripciones, relaciones y medidas |

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

## Correcciones propuestas

Los tres huecos de la compilación se atienden en `correcciones.yaml`, que el plugin aplica encima de la exportación:

1. **Nombres.** "Load Zone" pasa a "Zona de carga" y "Tarifa Dinamica" a "Tarifa dinámica"; los nombres del modelo quedan como sinónimos. También se corrigen columnas sin comentario que el modelo describió mal: `tarifa_dinamica.banda` ("frequency band… signal strength") y `consumo_hogar_diario.lecturas` ("raw meter reading values", cuando es un conteo).
2. **Relaciones.** `consumo_hogar_*.hogar` con `hogares.hogar` y `precio_zona_hora.zona_carga` con `zonas_carga.zona_carga`. Se verificaron en la base: 0 filas sin pareja.
3. **Medidas.** Consumo total, consumo diario promedio por hogar (solo días completos), energía de clientes de Portugal, precio promedio y horas con precio negativo. Las cinco se ejecutaron en la base de desarrollo.

Es una propuesta escrita a partir de la migración 0007: nadie la ha revisado, así que `certificada` sigue en `false`.

Estos puntos son evidencia para la sección 4 de la charla (*The Evaluation Trap*): una capa semántica generada por un modelo también puede introducir errores, y hay que medirla, no suponer que ayuda (experimento E8).
