# Ingesta a energy_lab

Pipeline reproducible para cargar series eléctricas a `core.observation` (ver `db/README.md`). Cada fuente declara sus series y entrega unidades de carga, por ejemplo un mes. El loader:

1. Salta las unidades que ya están en `done` en `core.ingest_batch`, así que la carga es **reanudable e idempotente**.
2. Hace COPY a una tabla temporal, crea las particiones mensuales que falten y hace upsert sobre `(series_id, ts)` en una sola transacción por unidad.
3. **Verifica conteos:** cada fila de la unidad debe existir en `core.observation` con el mismo valor; si no cuadra, revierte la unidad.
4. Registra filas leídas, filas cargadas y un **reporte de calidad** en el lote.

Las selecciones distintas (otros clientes u otras fechas) generan lotes distintos: un demo de 20 clientes no hace que una carga posterior salte meses.

Las series que la fuente no declara de antemano (por ejemplo, los hogares de LCL) se crean al aparecer. Los duplicados (serie, hora) dentro de una unidad se eliminan en la base y se cuentan, distinguiendo los que traen valores distintos.

**Español:** cada serie guarda `attrs.etiqueta` y `attrs.unidad` en español. La CLI imprime el resumen y el reporte de calidad en español (glosario en `energy_lab_ingest/etiquetas.py`). Los identificadores internos (`consumption`, `price`, llaves de calidad) se mantienen como contratos estables.

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

## Low Carbon London

- **Fuente:** https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d (CC BY 4.0, UK Power Networks).
- **Archivos:** se usa `Partitioned LCL Data.zip` (168 CSV de un millón de filas), con sha256 fijado. Se lee **sin extraer** y cada archivo es una unidad de carga. La tarifa dinámica 2013 se carga desde `Tariffs.xlsx` como la serie `tariff_price` (p/kWh).
- **Fixture:** `fixtures/lcl_smoke.csv` es un recorte real: dos hogares Std y uno ToU alrededor del cambio de horario de marzo de 2013, más un día con duplicados.

### Formato y tratamiento

Verificado sobre el archivo real:

| Hecho | Tratamiento | Calidad |
|---|---|---|
| Los días de cambio de horario de Londres traen 48 lecturas, no 46 ni 50 | `DateTime` se toma como UTC | |
| Duplicados exactos (hogar, hora): 688 en el primer archivo, todos con el mismo valor | El loader los elimina | `duplicates_dropped`, `duplicates_conflicting` |
| Una fila final por hogar fuera de la malla (p. ej. `12:37:27`, con `Null`) | Se descarta | `off_grid_timestamps` |
| `Null` | NULL en la base | `null_values` |
| Archivos ordenados por tarifa: Std al inicio, ToU al final | El demo estratifica por tarifa leyendo la primera fila de cada archivo | |

**Sesgo de selección encontrado:** la primera versión del demo repartía archivos por índice. Eligió los archivos 0, 42, 84 y 126, todos Std, y dejó **cero hogares ToU** con el mismo número de archivos. Ahora cada tarifa recibe archivos en proporción a su tamaño y al menos uno. La prueba `test_pick_files_estratifica_por_tarifa` cubre el caso.

**No verificado:** si `DateTime` marca el inicio o el fin de la media hora. La serie lo declara como `ts_label = as_published`.

```bash
make lcl-smoke
make lcl-demo LCL_FILES=4
make lcl-full          # estimación: 168 millones de filas, ~15 GB
```

### Resultados medidos (demo de 4 archivos, antes de estratificar)

| Medida | Valor |
|---|---|
| Filas leídas / cargadas | 4,000,000 / 3,997,103 |
| Tiempo | 70 s (unas 57 mil filas/s) |
| Duplicados eliminados / marcas fuera de malla | 2,764 / 133 |
| Segunda corrida | 4 archivos saltados |

Con el loader actual (series descubiertas y deduplicación en la base), el demo de UCI bajó de unas 59 mil a unas 34 mil filas/s. Ese es el costo de la deduplicación y de resolver series con JOIN.
