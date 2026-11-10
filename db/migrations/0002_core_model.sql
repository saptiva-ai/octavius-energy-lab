-- Modelo normalizado por serie (ver docs/architecture/proposed-energy-lab.md).
-- CENACE, Low Carbon London y UCI caben en el mismo modelo: una entidad
-- (región, nodo, zona de carga, hogar) tiene series, y cada serie tiene
-- observaciones con marca de tiempo en UTC.

CREATE TABLE core.dataset_version (
    id           serial PRIMARY KEY,
    source       text        NOT NULL,            -- p. ej. cenace_pml, lcl, uci_eld
    version      text        NOT NULL,            -- etiqueta de la descarga
    license      text        NOT NULL,
    url          text,
    sha256       text,                            -- del archivo original, si aplica
    retrieved_at timestamptz NOT NULL DEFAULT now(),
    notes        text,
    UNIQUE (source, version)
);

CREATE TABLE core.ingest_batch (
    id                 bigserial PRIMARY KEY,
    dataset_version_id integer     NOT NULL REFERENCES core.dataset_version (id),
    profile            text        NOT NULL CHECK (profile IN ('smoke', 'demo', 'full')),
    unit               text        NOT NULL,      -- archivo, partición o rango que cubre el lote
    status             text        NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending', 'running', 'done', 'failed')),
    rows_read          bigint,
    rows_loaded        bigint,
    started_at         timestamptz,
    finished_at        timestamptz,
    error              text,
    UNIQUE (dataset_version_id, unit)             -- reanudable: un lote por unidad
);

CREATE TABLE core.entity (
    id         bigserial PRIMARY KEY,
    source     text  NOT NULL,
    kind       text  NOT NULL CHECK (kind IN (
                   'system', 'region', 'load_zone', 'node', 'household', 'weather_point', 'client'
               )),
    source_key text  NOT NULL,
    name       text,
    attrs      jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, kind, source_key)
);

CREATE TABLE core.cohort (
    id   bigserial PRIMARY KEY,
    kind text NOT NULL,                           -- p. ej. sistema, tarifa, acorn
    name text NOT NULL,
    UNIQUE (kind, name)
);

CREATE TABLE core.entity_cohort (
    entity_id bigint NOT NULL REFERENCES core.entity (id) ON DELETE CASCADE,
    cohort_id bigint NOT NULL REFERENCES core.cohort (id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, cohort_id)
);

CREATE TABLE core.series (
    id         bigserial PRIMARY KEY,
    entity_id  bigint REFERENCES core.entity (id),
    source     text     NOT NULL,
    source_key text     NOT NULL,
    kind       text     NOT NULL,                 -- demand, demand_forecast, pml, consumption, temperature...
    unit       text     NOT NULL,                 -- MW, MXN/MWh, kWh, degC
    freq       interval NOT NULL,
    tz         text     NOT NULL DEFAULT 'UTC',   -- zona de la fuente; ts se guarda en UTC
    attrs      jsonb    NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, source_key, kind)
);
CREATE INDEX series_entity_idx ON core.series (entity_id);

-- Observaciones particionadas por mes. La clave primaria evita duplicados y
-- permite upsert idempotente con ON CONFLICT (series_id, ts).
CREATE TABLE core.observation (
    series_id bigint           NOT NULL REFERENCES core.series (id),
    ts        timestamptz      NOT NULL,
    value     double precision,
    batch_id  bigint,
    PRIMARY KEY (series_id, ts)
) PARTITION BY RANGE (ts);

-- Atrapa filas fuera de las particiones mensuales. Debe quedar vacía; si
-- tiene filas en un mes, hay que moverlas antes de crear esa partición.
CREATE TABLE core.observation_default PARTITION OF core.observation DEFAULT;

-- Para barridos por tiempo que cruzan series (agregados por intervalo).
CREATE INDEX observation_ts_brin ON core.observation USING brin (ts);

-- Crea las particiones mensuales que cubren [p_from, p_to]. Idempotente.
-- Devuelve cuántas creó. SECURITY DEFINER para que lab_ingest no necesite
-- privilegios de DDL sobre core.
CREATE FUNCTION core.ensure_observation_partitions(p_from date, p_to date)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core
AS $$
DECLARE
    month_start date := date_trunc('month', p_from)::date;
    created     integer := 0;
    part_name   text;
BEGIN
    IF p_to < p_from THEN
        RAISE EXCEPTION 'p_to (%) es anterior a p_from (%)', p_to, p_from;
    END IF;
    WHILE month_start <= p_to LOOP
        part_name := format('observation_%s', to_char(month_start, 'YYYY_MM'));
        IF to_regclass(format('core.%I', part_name)) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE core.%I PARTITION OF core.observation FOR VALUES FROM (%L) TO (%L)',
                part_name,
                -- Límites en UTC explícito, sin depender de la zona de la sesión.
                to_char(month_start, 'YYYY-MM-DD') || ' 00:00:00+00',
                to_char((month_start + interval '1 month')::date, 'YYYY-MM-DD') || ' 00:00:00+00'
            );
            created := created + 1;
        END IF;
        month_start := (month_start + interval '1 month')::date;
    END LOOP;
    RETURN created;
END
$$;
REVOKE ALL ON FUNCTION core.ensure_observation_partitions(date, date) FROM PUBLIC;
