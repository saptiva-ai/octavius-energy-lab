-- Roles y esquemas de energy_lab.
--
-- Los roles son globales al clúster: se crean solo si no existen. Las
-- contraseñas no viven aquí; el runner las fija desde variables de entorno.
-- Un rol con LOGIN y sin contraseña no puede autenticarse por scram-sha-256.
--
--   lab_ingest    carga datos en raw y core
--   lab_agent     consultas del agente: solo lectura, con timeout
--   lab_forecast  lee core y escribe pronósticos
--   lab_eval      lee todo y escribe resultados de evaluación

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['lab_ingest', 'lab_agent', 'lab_forecast', 'lab_eval'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', r);
        END IF;
    END LOOP;
END
$$;

-- Nadie entra a esta base por omisión; cada rol recibe CONNECT explícito.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO lab_ingest, lab_agent, lab_forecast, lab_eval',
        current_database()
    );
    -- La ingesta usa tablas temporales para COPY y upsert.
    EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO lab_ingest', current_database());

    -- Límites del agente en esta base: solo lectura y consultas acotadas.
    EXECUTE format(
        'ALTER ROLE lab_agent IN DATABASE %I SET default_transaction_read_only = on',
        current_database()
    );
    EXECUTE format('ALTER ROLE lab_agent IN DATABASE %I SET statement_timeout = %L', current_database(), '5s');
    EXECUTE format(
        'ALTER ROLE lab_agent IN DATABASE %I SET idle_in_transaction_session_timeout = %L',
        current_database(), '30s'
    );
    EXECUTE format('ALTER ROLE lab_agent IN DATABASE %I SET work_mem = %L', current_database(), '16MB');
END
$$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS raw;       -- staging de COPY, sin garantías
CREATE SCHEMA IF NOT EXISTS core;      -- series, entidades y observaciones normalizadas
CREATE SCHEMA IF NOT EXISTS agg;       -- agregados que consulta el agente
CREATE SCHEMA IF NOT EXISTS forecast;  -- corridas y puntos de pronóstico
CREATE SCHEMA IF NOT EXISTS lab;       -- experimentos, corridas, trazas y evaluaciones

COMMENT ON SCHEMA raw IS 'Staging de carga. Solo lab_ingest.';
COMMENT ON SCHEMA core IS 'Modelo normalizado por serie, independiente de la fuente.';
COMMENT ON SCHEMA agg IS 'Agregados para consultas del agente.';
COMMENT ON SCHEMA forecast IS 'Pronósticos con corte temporal explícito.';
COMMENT ON SCHEMA lab IS 'Tracking de experimentos y evaluaciones.';
