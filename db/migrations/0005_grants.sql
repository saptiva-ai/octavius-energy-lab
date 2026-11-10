-- Permisos por rol. Las DEFAULT PRIVILEGES cubren tablas futuras que cree
-- el rol que aplica las migraciones.

-- Agente: lee core y agg, nada más.
GRANT USAGE ON SCHEMA core, agg TO lab_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA core, agg TO lab_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, agg GRANT SELECT ON TABLES TO lab_agent;

-- Ingesta: staging en raw, escritura en core sin DELETE sobre observaciones.
GRANT USAGE ON SCHEMA raw, core TO lab_ingest;
GRANT CREATE ON SCHEMA raw TO lab_ingest;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core TO lab_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO lab_ingest;
GRANT EXECUTE ON FUNCTION core.ensure_observation_partitions(date, date) TO lab_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT, INSERT, UPDATE ON TABLES TO lab_ingest;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT USAGE, SELECT ON SEQUENCES TO lab_ingest;
-- Refrescar agregados es parte de la ingesta.
GRANT USAGE ON SCHEMA agg TO lab_ingest;

-- Forecast: lee core, escribe en forecast.
GRANT USAGE ON SCHEMA core, agg, forecast TO lab_forecast;
GRANT SELECT ON ALL TABLES IN SCHEMA core, agg TO lab_forecast;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA forecast TO lab_forecast;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, agg GRANT SELECT ON TABLES TO lab_forecast;
ALTER DEFAULT PRIVILEGES IN SCHEMA forecast GRANT SELECT, INSERT, UPDATE ON TABLES TO lab_forecast;

-- Evaluación: lee todo menos raw, escribe en lab.
GRANT USAGE ON SCHEMA core, agg, forecast, lab TO lab_eval;
GRANT SELECT ON ALL TABLES IN SCHEMA core, agg, forecast, lab TO lab_eval;
GRANT INSERT, UPDATE ON ALL TABLES IN SCHEMA lab TO lab_eval;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lab TO lab_eval;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, agg, forecast, lab GRANT SELECT ON TABLES TO lab_eval;
ALTER DEFAULT PRIVILEGES IN SCHEMA lab GRANT INSERT, UPDATE ON TABLES TO lab_eval;
ALTER DEFAULT PRIVILEGES IN SCHEMA lab GRANT USAGE, SELECT ON SEQUENCES TO lab_eval;
