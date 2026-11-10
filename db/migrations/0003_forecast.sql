-- Pronósticos con contrato explícito: serie, corte, horizonte, modelo,
-- covariables y cuantiles. Un punto de pronóstico nunca puede caer en o
-- antes del corte: lo impide un trigger (frontera temporal en la base).

CREATE TABLE forecast.forecast_run (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id       bigint           NOT NULL REFERENCES core.series (id),
    experiment_id   text,
    cutoff          timestamptz      NOT NULL,     -- última observación disponible
    horizon         interval         NOT NULL CHECK (horizon > interval '0'),
    freq            interval         NOT NULL CHECK (freq > interval '0'),
    model           text             NOT NULL,     -- timesfm-2.5, seasonal_naive, cenace_oficial...
    model_version   text             NOT NULL,
    context_length  integer,
    -- [{"series_id": 1, "kind": "temperature", "origin": "forecast_issued_before_cutoff"}]
    covariates      jsonb            NOT NULL DEFAULT '[]'::jsonb,
    quantile_levels double precision[],
    params          jsonb            NOT NULL DEFAULT '{}'::jsonb,
    duration_ms     integer,
    status          text             NOT NULL DEFAULT 'done'
                                     CHECK (status IN ('running', 'done', 'failed')),
    error           text,
    created_at      timestamptz      NOT NULL DEFAULT now()
);
CREATE INDEX forecast_run_series_cutoff_idx ON forecast.forecast_run (series_id, cutoff);
CREATE INDEX forecast_run_experiment_idx ON forecast.forecast_run (experiment_id);

CREATE TABLE forecast.forecast_point (
    run_id    uuid             NOT NULL REFERENCES forecast.forecast_run (id) ON DELETE CASCADE,
    ts        timestamptz      NOT NULL,
    point     double precision NOT NULL,
    quantiles double precision[],                  -- alineados con forecast_run.quantile_levels
    PRIMARY KEY (run_id, ts)
);

CREATE FUNCTION forecast.check_point_after_cutoff()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, forecast
AS $$
DECLARE
    run_cutoff  timestamptz;
    run_horizon interval;
BEGIN
    SELECT cutoff, horizon INTO run_cutoff, run_horizon
    FROM forecast.forecast_run WHERE id = NEW.run_id;
    IF NEW.ts <= run_cutoff THEN
        RAISE EXCEPTION 'Punto de pronóstico en % no es posterior al corte %', NEW.ts, run_cutoff
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.ts > run_cutoff + run_horizon THEN
        RAISE EXCEPTION 'Punto de pronóstico en % excede el horizonte (corte % + %)',
            NEW.ts, run_cutoff, run_horizon
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER forecast_point_after_cutoff
    BEFORE INSERT OR UPDATE ON forecast.forecast_point
    FOR EACH ROW EXECUTE FUNCTION forecast.check_point_after_cutoff();
