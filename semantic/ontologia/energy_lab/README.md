# Ontología de energy_lab: borrador generado

**Estado:** borrador sin certificar. Lo generó un modelo y nadie lo ha revisado ni corregido todavía. No se usa en ninguna respuesta hasta que se certifique.

## Cómo se generó

| Dato | Valor |
|---|---|
| Fecha | 2026-11-10 |
| Herramienta | `saptiva-ai/auto-ontology-agno` (fork de NVIDIA Auto Ontology sobre Agno), commit `06e63f94` |
| Fuente | Las 7 vistas de `agg` (migración 0007), leídas con el rol `lab_ontology` de solo lectura. El filtro de privilegios dejó fuera `core` |
| Datos | Demos del laboratorio: Low Carbon London (4 archivos, 135 hogares), UCI (20 clientes), CENACE (7 zonas, septiembre-octubre de 2025) y catálogo de Nodos P |
| Modelo de lenguaje | `nemotron-3.5-lightning` en InferNode dev (razonamiento y rol ligero) |
| Embeddings | `qwen3-embedding-8b` en InferNode dev, 2,048 dimensiones |
| Reranker | Ninguno (InferNode no ofrece reranking; la compilación lo tolera) |
| Duración | Ingesta tabular 5.8 s; compilación semántica 54.8 s |
| Máquina | EC2 `t3.large` del laboratorio |

## Archivos

| Archivo | Formato | Contenido |
|---|---|---|
| `auto_ontology.yaml` | Nativo de Auto Ontology | Capa de datos (bases, tablas, columnas, perfiles) y capa semántica (términos, atributos de columna, relaciones, atributos SQL) |
| `ossie.yaml` | [Apache Ossie](https://ossie.apache.org/) | El modelo semántico en el estándar abierto |

## Resultado

7 términos, uno por vista. 0 relaciones semánticas, 0 tablas puente y 0 atributos SQL.

| Vista | Término generado | Observación |
|---|---|---|
| `consumo_cliente_cuarto_hora` | Consumo Cliente Cuarto Hora | Dice "consumo **y generación**", lo que el dato no dice. No menciona que son clientes de Portugal |
| `consumo_hogar_diario` | Home Daily Consumption | Correcto, pero en inglés |
| `consumo_hogar_media_hora` | Home Energy Consumption | Correcto, pero en inglés |
| `hogares` | Hogar | Entiende la tarifa Std y ToU |
| `precio_zona_hora` | Precio Zona Hora | El nombre es el de la vista, sin interpretación |
| `tarifa_dinamica` | Tarifa Dinamica | El nombre es el de la vista, sin acento |
| `zonas_carga` | Load Zone | Buena descripción: centros de control, estados y sistema |

## Lo que hay que corregir antes de certificar

1. **Idioma.** Las descripciones salen en inglés aunque las vistas tienen comentarios en español. Los nombres mezclan idiomas (`consumoKwh`, "Precio Zona Hora").
2. **Afirmaciones sin sustento.** "Generación" en el consumo de clientes de Portugal: el modelo agregó algo que los datos no dicen.
3. **Relaciones faltantes.** `hogares.hogar` y `consumo_hogar_*.hogar` son la misma llave, y `zonas_carga.zona_carga` con `precio_zona_hora.zona_carga` también. Las vistas no declaran llaves y la inferencia semántica no las detectó.
4. **Sin atributos SQL.** Se proponen a partir del historial de consultas y no hay ninguno. Medidas como "consumo total por grupo de tarifa" o "precio promedio por centro de control" tendrían que definirse a mano.

Estos puntos son evidencia para la sección 4 de la charla (*The Evaluation Trap*): una capa semántica generada por un modelo también puede introducir errores, y hay que medirla, no suponer que ayuda (experimento E8).
