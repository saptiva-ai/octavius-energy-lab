-- Tracking de experimentos: cada corrida guarda harness, modelos, dataset,
-- escenario, trazas de herramientas y evaluaciones. Nunca credenciales.

CREATE TABLE lab.experiment (
    id          text PRIMARY KEY,
    name        text        NOT NULL,
    description text,
    config      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lab.harness_config (
    id         text PRIMARY KEY,                    -- p. ej. harness-a@3f2c1a
    name       text        NOT NULL,                -- harness-a, harness-b, ablación...
    config     jsonb       NOT NULL,
    sha256     char(64)    NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lab.scenario (
    id       text PRIMARY KEY,
    version  text NOT NULL,
    category text NOT NULL CHECK (category IN (
                 'data_retrieval', 'forecasting', 'analytical_reasoning',
                 'temporal_integrity', 'unanswerable', 'ambiguous'
             )),
    question text  NOT NULL,
    spec     jsonb NOT NULL DEFAULT '{}'::jsonb     -- ground truth, cortes, herramientas esperadas
);

CREATE TABLE lab.run (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id      text        NOT NULL REFERENCES lab.experiment (id),
    scenario_id        text        REFERENCES lab.scenario (id),
    harness_id         text        REFERENCES lab.harness_config (id),
    dataset_version_id integer     REFERENCES core.dataset_version (id),
    repetition         integer     NOT NULL DEFAULT 0,
    replay             boolean     NOT NULL DEFAULT false,
    llm                jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- modelo, digest, cuantización, muestreo
    forecast_model     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status             text        NOT NULL DEFAULT 'running'
                                   CHECK (status IN ('running', 'done', 'failed', 'timeout')),
    error_category     text,
    answer             text,
    latency_ms         integer,
    tokens_in          integer,
    tokens_out         integer,
    resources          jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- VRAM, RAM, GPU util si se mide
    started_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz
);
CREATE INDEX run_experiment_idx ON lab.run (experiment_id, harness_id, scenario_id);

CREATE TABLE lab.run_event (
    id              bigserial PRIMARY KEY,
    run_id          uuid        NOT NULL REFERENCES lab.run (id) ON DELETE CASCADE,
    seq             integer     NOT NULL,
    ts              timestamptz NOT NULL DEFAULT now(),
    kind            text        NOT NULL CHECK (kind IN (
                        'llm_call', 'tool_call', 'sql_query', 'forecast', 'semantic_lookup',
                        'validation', 'recovery', 'error'
                    )),
    name            text,
    args            jsonb,
    result          jsonb,
    query_id        text,
    forecast_run_id uuid REFERENCES forecast.forecast_run (id),
    latency_ms      integer,
    UNIQUE (run_id, seq)
);

CREATE TABLE lab.evaluation (
    id        bigserial PRIMARY KEY,
    run_id    uuid             NOT NULL REFERENCES lab.run (id) ON DELETE CASCADE,
    metric    text             NOT NULL,           -- task_success, tool_selection, temporal_leakage...
    value     double precision,
    passed    boolean,
    evaluator text             NOT NULL,           -- deterministic, sql_reference, llm_judge:<modelo>
    details   jsonb            NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, metric, evaluator)
);
