# energy_lab: base de datos del laboratorio

PostgreSQL 15, en el mismo servicio `postgres` de Octavius (perfil `lab`), con una base propia `energy_lab`. No comparte tablas con la aplicación.

## Esquemas

| Esquema | Contenido | Quién escribe |
|---|---|---|
| `raw` | Staging de COPY | `lab_ingest` |
| `core` | `dataset_version`, `ingest_batch`, `entity`, `cohort`, `series` y `observation` (particionada por mes) | `lab_ingest` |
| `agg` | Agregados que consulta el agente | `lab_ingest` (refresco) |
| `forecast` | `forecast_run` y `forecast_point` | `lab_forecast` |
| `lab` | `experiment`, `harness_config`, `scenario`, `run`, `run_event`, `evaluation` | `lab_eval` |

## Roles

| Rol | Puede | No puede |
|---|---|---|
| `lab_agent` | Leer `core` y `agg` | Escribir, leer `raw`/`forecast`/`lab`, consultas de más de 5 s (`statement_timeout`); sus transacciones son de solo lectura |
| `lab_ingest` | Escribir en `raw` y `core`, crear particiones con `core.ensure_observation_partitions` | Borrar observaciones, escribir en `lab` |
| `lab_forecast` | Leer `core`, escribir en `forecast` | Modificar observaciones |
| `lab_eval` | Leer `core`, `agg`, `forecast` y `lab`; escribir en `lab` | Escribir datos de origen |

Las contraseñas vienen de variables de entorno (`LAB_*_PASSWORD`) y nunca de los archivos SQL. Un rol sin contraseña no puede iniciar sesión. Si falta una variable, `migrate` no cambia la contraseña de ese rol; como los roles son globales al clúster, puede conservar una anterior.

La imagen oficial de PostgreSQL confía en las conexiones por loopback **dentro** del contenedor (`pg_hba.conf`). Las conexiones que llegan desde la red de compose o desde el host sí exigen contraseña (`scram-sha-256`), y el puerto solo se publica en `127.0.0.1`.

## Garantías en la base

- **Sin duplicados:** `core.observation` tiene clave primaria `(series_id, ts)`, que permite upsert idempotente.
- **Frontera temporal:** un trigger rechaza cualquier punto de pronóstico que caiga en o antes de `cutoff`, o más allá de `cutoff + horizon`.
- **Particiones mensuales:** las consultas por rango de tiempo solo leen los meses necesarios. La partición `observation_default` debe quedar vacía.

## Migraciones

Archivos `migrations/NNNN_nombre.sql`. Cada uno corre en su propia transacción y queda registrado en `public.schema_migrations` con su sha256. Una migración aplicada no se edita: si cambia, el runner se detiene. Los cambios van en una migración nueva.

```bash
make db-up       # PostgreSQL con el perfil lab
make db-migrate  # crea energy_lab si falta, aplica migraciones y fija contraseñas
make db-status   # aplicadas y pendientes
```

Variables (ver `envs/.env.example`): `ENERGY_LAB_ADMIN_DSN`, `ENERGY_LAB_DB`, `LAB_INGEST_PASSWORD`, `LAB_AGENT_PASSWORD`, `LAB_FORECAST_PASSWORD` y `LAB_EVAL_PASSWORD`.

## Pruebas

Corren contra un PostgreSQL real; cada sesión crea y borra una base temporal.

```bash
docker run -d --name energylab-pgtest -e POSTGRES_PASSWORD=pgtest \
  -p 127.0.0.1:55432:5432 postgres:15-alpine
ENERGY_LAB_TEST_ADMIN_DSN=postgresql://postgres:pgtest@127.0.0.1:55432/postgres make test T=db
```

Sin `ENERGY_LAB_TEST_ADMIN_DSN`, las pruebas que necesitan base se saltan.

Usa un PostgreSQL solo para pruebas: los roles `lab_*` son globales al clúster y las pruebas les fijan contraseñas aleatorias. Si el clúster ya tiene la base `energy_lab`, las pruebas se detienen (`ENERGY_LAB_TEST_ALLOW_SHARED=1` lo permite).
