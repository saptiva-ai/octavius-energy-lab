# Ingesta a energy_lab

Pipeline reproducible para cargar series eléctricas a `core.observation` (ver `db/README.md`). Cada fuente declara sus series y entrega unidades de carga, por ejemplo un mes. El loader:

1. Salta las unidades que ya están en `done` en `core.ingest_batch`, así que la carga es **reanudable e idempotente**.
2. Hace COPY a una tabla temporal, crea las particiones mensuales que falten y hace upsert sobre `(series_id, ts)` en una sola transacción por unidad.
3. **Verifica conteos:** cada fila de la unidad debe existir en `core.observation` con el mismo valor; si no cuadra, revierte la unidad.
4. Registra filas leídas, filas cargadas y un **reporte de calidad** en el lote.

Las selecciones distintas (otros clientes u otras fechas) generan lotes distintos: un demo de 20 clientes no hace que una carga posterior salte meses.

## Perfiles

| Perfil | Datos | Red | Uso |
|---|---|---|---|
| `smoke` | Fixture versionado: 3 clientes y dos ventanas de tres días alrededor de los cambios de horario de 2011 | No | Pruebas y CI |
| `demo` | `--clients N` repartidos uniformemente entre los 370 (no los primeros N), entre `--start` y `--end` | Descarga una vez | Desarrollo y charla |
| `full` | Los 370 clientes, 2011-2014 | Descarga una vez | Sin `--yes` solo muestra la estimación |

```bash
make ingest-smoke
make ingest-demo DEMO_CLIENTS=20 DEMO_START=2013-01-01 DEMO_END=2015-01-01
make ingest-full          # estimación
make ingest-full YES=1    # carga completa
```

Variables: `LAB_INGEST_DSN` (rol `lab_ingest`) y, opcionalmente, `ENERGY_LAB_DATA_DIR` (caché de descargas, por omisión `~/.cache/energy-lab`). Los datos crudos nunca se versionan.

## UCI ElectricityLoadDiagrams20112014

- **Fuente:** https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014. Licencia CC BY 4.0.
- **Fixture:** `fixtures/uci_smoke.txt` es un recorte del archivo original (columnas `MT_001`, `MT_124` y `MT_131`).
- **Checksum:** UCI no publica checksums. El sha256 del zip descargado el 2026-11-10 está fijado en el conector y la descarga se rechaza si no coincide.

### Formato y tratamiento

Verificado sobre el archivo real:

| Hecho | Tratamiento | Llave de calidad |
|---|---|---|
| Separador `;`, coma decimal, una columna por cliente | Formato ancho a largo | `rows_read` (celdas) |
| kW promedio por 15 min; la etiqueta marca el final del intervalo | Unidad `kW`, `attrs.ts_label = interval_end` | |
| Etiquetas en hora de Portugal, malla regular sin huecos | Conversión a UTC con `Europe/Lisbon` | |
| En marzo, las etiquetas de la hora inexistente valen cero | Se descartan | `nonexistent_local_time` |
| En octubre, la hora repetida aparece una vez con la suma de ambas | Primera ocurrencia; el valor conserva la suma | `ambiguous_local_time` |
| Clientes dados de alta después del inicio traen ceros previos | No se cargan los ceros previos al primer valor distinto de cero dentro de la selección | `leading_zeros_skipped` |

Limitación: con `--start` posterior al alta de un cliente, sus ceros reales al inicio de la ventana se cuentan como previos al alta.

### Resultados medidos

Perfil `demo`, 20 clientes, 2013-2014, PostgreSQL 15 en Docker local, 2026-11-10:

| Medida | Valor |
|---|---|
| Unidades (meses) | 24 |
| Celdas leídas | 1,401,600 |
| Filas cargadas | 1,266,530 |
| Tiempo | 21.4 s (unas 59 mil filas/s) |
| Tamaño de las particiones, con índices | 115 MB (unos 95 B por fila) |
| Horas inexistentes / ambiguas | 160 / 160 |
| Ceros previos al alta descartados | 134,910 |
| Segunda corrida | 0 unidades cargadas, 24 saltadas |

El perfil `full` estima 51.9 millones de filas y unos 4.9 GB en disco. Ese número todavía no está medido.

## CENACE: precios del Mercado Eléctrico Mayorista

| Servicio | Contenido | Entidad |
|---|---|---|
| SW-PEND (`--service pend`, por omisión) | Precio de nodos distribuidos por zona de carga | `load_zone` |
| SW-PML (`--service pml`) | Precio marginal local por nodo | `node` |

Cada clave genera cuatro series horarias en MXN/MWh: `price` (total), `price_energy`, `price_losses` y `price_congestion`, separadas por sistema (SIN, BCA, BCS) y proceso (MDA, MTR).

**Licencia:** CENACE no publica términos de uso explícitos para estos servicios. Por eso el repositorio **no redistribuye datos crudos**: el conector los descarga en cada instalación. Los fixtures de `fixtures/cenace/` tienen la estructura real de las respuestas con **valores sintéticos**.

### Comportamiento del servicio, verificado el 2026-11-10

| Hecho | Tratamiento |
|---|---|
| Máximo 7 días por consulta; `{"Message": ...}` con HTTP 200 si se excede | Ventanas de 7 días; el mensaje se convierte en error |
| Máximo 20 claves y, en la práctica, unos 100 caracteres en el segmento de claves: 20 zonas con nombres largos dan HTTP 400 | Bloques por cantidad y por longitud |
| Zonas con espacios se piden con guiones (`CENTRO-ORIENTE`), pero la respuesta trae `CENTRO ORIENTE` | Normalización de la clave en ambos sentidos; las 108 zonas del catálogo responden |
| `hora` 1-24 local; los días de cambio de horario traen 23 o 25 horas | `ts` = medianoche local + (hora - 1), en UTC, inicio del intervalo |
| Clave sin datos: `ZERO_RESULTS` o `Valores` vacío dentro de un `OK` | `quality.keys_without_data` |
| Datos MDA desde el 2016-01-29 (SIN); antes, respuesta vacía | Inicio por omisión del perfil full |

Los meses ya cargados se saltan **sin llamar al servicio**. Entre llamadas hay una pausa de 1 s (`--delay`).

### Catálogo de Nodos P

Los perfiles `demo` y `full` descargan el catálogo oficial versionado (v2026-10-23, sha256 fijado) y cargan a `core.entity`:

- 2,611 nodos y 108 zonas.
- Atributos: centro de control, entidades federativas y tensión.
- Cohortes `system` y `ccr`.

El demo elige `--per-ccr` zonas por centro de control, repartidas dentro de cada uno, para no concentrar la muestra en una región.

```bash
make cenace-smoke
make cenace-demo CENACE_PER_CCR=2 CENACE_START=2025-01-01 CENACE_END=2025-12-31
make cenace-full          # estimación: 101 zonas del SIN desde 2016, ~38 millones de filas, ~6,200 llamadas
```

### Resultados medidos

Demo con 1 zona por CCR (7 zonas), septiembre-octubre de 2025, MDA:

| Medida | Valor |
|---|---|
| Filas cargadas | 40,992 (7 zonas × 1,464 horas × 4 componentes, sin huecos) |
| Llamadas | 10, en 39 s |
| Segunda corrida | 0 llamadas, 2 meses saltados |
| Horas con precio total negativo | 5 en septiembre, 17 en octubre |

### Pendiente

La **demanda** (estimación de demanda real por balance o por retiros) no tiene servicio web. Solo existe un formulario ASP.NET con postbacks (`EstimacionDemandaReal.aspx`), así que queda para un PR aparte.
