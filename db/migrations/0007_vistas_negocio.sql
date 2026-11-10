-- Vistas con nombres de negocio en agg, para el agente y para la capa
-- semántica. Traducen el modelo por serie (core) a conceptos que una persona
-- o un modelo reconoce: hogar, tarifa, zona de carga, precio por componente.
--
-- Rol lab_ontology: solo lectura de agg, con un timeout de 1 minuto para que
-- el perfilado de la capa semántica (SELECT DISTINCT sobre millones de filas)
-- no se corte a los 5 s del agente. No ve core, raw, forecast ni lab.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lab_ontology') THEN
        CREATE ROLE lab_ontology LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO lab_ontology', current_database());
    EXECUTE format(
        'ALTER ROLE lab_ontology IN DATABASE %I SET default_transaction_read_only = on',
        current_database()
    );
    EXECUTE format('ALTER ROLE lab_ontology IN DATABASE %I SET statement_timeout = %L', current_database(), '60s');
    EXECUTE format(
        'ALTER ROLE lab_ontology IN DATABASE %I SET idle_in_transaction_session_timeout = %L',
        current_database(), '60s'
    );
END
$$;

-- Hogares de Low Carbon London con su grupo de tarifa.
CREATE VIEW agg.hogares AS
SELECT e.source_key AS hogar,
       c.name       AS grupo_tarifa
FROM core.entity e
LEFT JOIN core.entity_cohort ec ON ec.entity_id = e.id
LEFT JOIN core.cohort c ON c.id = ec.cohort_id AND c.kind = 'tariff'
WHERE e.source = 'lcl' AND e.kind = 'household';
COMMENT ON VIEW agg.hogares IS
    'Hogares de Londres (Low Carbon London, 2011-2014) y su grupo de tarifa: Std (tarifa plana) o ToU (tarifa dinámica por horario en 2013).';
COMMENT ON COLUMN agg.hogares.hogar IS 'Identificador anónimo del hogar (LCLid).';
COMMENT ON COLUMN agg.hogares.grupo_tarifa IS 'Std: tarifa plana. ToU: tarifa dinámica con bandas alta, normal y baja.';

-- Consumo de cada hogar cada media hora.
CREATE VIEW agg.consumo_hogar_media_hora AS
SELECT s.source_key   AS hogar,
       h.grupo_tarifa,
       o.ts           AS momento,
       o.value        AS consumo_kwh
FROM core.observation o
JOIN core.series s ON s.id = o.series_id
LEFT JOIN agg.hogares h ON h.hogar = s.source_key
WHERE s.source = 'lcl' AND s.kind = 'consumption';
COMMENT ON VIEW agg.consumo_hogar_media_hora IS
    'Consumo eléctrico medido de cada hogar de Londres por media hora. Observaciones históricas, no pronósticos.';
COMMENT ON COLUMN agg.consumo_hogar_media_hora.momento IS 'Marca de tiempo en UTC de la lectura de media hora.';
COMMENT ON COLUMN agg.consumo_hogar_media_hora.consumo_kwh IS 'Energía consumida en la media hora, en kWh. Puede ser nula si el medidor no reportó.';

-- Consumo diario por hogar (día en UTC).
CREATE VIEW agg.consumo_hogar_diario AS
SELECT hogar,
       grupo_tarifa,
       (momento AT TIME ZONE 'UTC')::date AS dia,
       sum(consumo_kwh)                   AS consumo_kwh,
       count(consumo_kwh)                 AS lecturas
FROM agg.consumo_hogar_media_hora
GROUP BY 1, 2, 3;
COMMENT ON VIEW agg.consumo_hogar_diario IS
    'Consumo eléctrico total por hogar y día (UTC). lecturas cuenta las medias horas con dato; 48 es un día completo.';
COMMENT ON COLUMN agg.consumo_hogar_diario.consumo_kwh IS 'Suma del consumo del día en kWh.';

-- Potencia de clientes de Portugal cada 15 minutos (UCI).
CREATE VIEW agg.consumo_cliente_cuarto_hora AS
SELECT s.source_key AS cliente,
       o.ts         AS momento,
       o.value      AS potencia_kw
FROM core.observation o
JOIN core.series s ON s.id = o.series_id
WHERE s.source = 'uci_eld' AND s.kind = 'consumption';
COMMENT ON VIEW agg.consumo_cliente_cuarto_hora IS
    'Potencia promedio de clientes eléctricos de Portugal (UCI, 2011-2014) por intervalo de 15 minutos.';
COMMENT ON COLUMN agg.consumo_cliente_cuarto_hora.potencia_kw IS 'Potencia promedio del intervalo en kW (la energía del intervalo es kW / 4 en kWh).';

-- Zonas de carga del Mercado Eléctrico Mayorista de México (CENACE).
CREATE VIEW agg.zonas_carga AS
SELECT e.name                                        AS zona_carga,
       split_part(e.source_key, ':', 1)              AS sistema,
       e.attrs ->> 'ccr'                             AS centro_control,
       array_to_string(
           ARRAY(SELECT jsonb_array_elements_text(e.attrs -> 'states')), ', '
       )                                             AS estados,
       (e.attrs ->> 'nodes')::int                    AS nodos
FROM core.entity e
WHERE e.source = 'cenace_pend' AND e.kind = 'load_zone';
COMMENT ON VIEW agg.zonas_carga IS
    'Zonas de carga del Sistema Eléctrico Nacional de México según el catálogo de Nodos P de CENACE, con su centro de control regional y estados.';
COMMENT ON COLUMN agg.zonas_carga.sistema IS 'SIN (interconectado), BCA (Baja California) o BCS (Baja California Sur).';

-- Precio horario por zona de carga, con sus componentes.
CREATE VIEW agg.precio_zona_hora AS
SELECT e.name                                                        AS zona_carga,
       s.attrs ->> 'system'                                          AS sistema,
       s.attrs ->> 'process'                                         AS proceso,
       e.attrs ->> 'ccr'                                             AS centro_control,
       o.ts                                                          AS momento,
       max(o.value) FILTER (WHERE s.kind = 'price')                  AS precio_total_mxn_mwh,
       max(o.value) FILTER (WHERE s.kind = 'price_energy')           AS componente_energia_mxn_mwh,
       max(o.value) FILTER (WHERE s.kind = 'price_losses')           AS componente_perdidas_mxn_mwh,
       max(o.value) FILTER (WHERE s.kind = 'price_congestion')       AS componente_congestion_mxn_mwh
FROM core.observation o
JOIN core.series s ON s.id = o.series_id
JOIN core.entity e ON e.id = s.entity_id
WHERE s.source = 'cenace_pend'
GROUP BY 1, 2, 3, 4, 5;
COMMENT ON VIEW agg.precio_zona_hora IS
    'Precio de la energía por zona de carga y hora en el Mercado Eléctrico Mayorista de México (CENACE), en pesos por MWh, con sus componentes. MDA: mercado del día en adelanto; MTR: tiempo real. Puede ser negativo.';
COMMENT ON COLUMN agg.precio_zona_hora.momento IS 'Inicio de la hora en UTC.';

-- Tarifa dinámica de Low Carbon London (2013).
CREATE VIEW agg.tarifa_dinamica AS
SELECT o.ts    AS momento,
       CASE o.value WHEN 67.20 THEN 'Alta' WHEN 11.76 THEN 'Normal' WHEN 3.99 THEN 'Baja' END AS banda,
       o.value AS precio_p_kwh
FROM core.observation o
JOIN core.series s ON s.id = o.series_id
WHERE s.source = 'lcl_tariff' AND s.kind = 'tariff_price';
COMMENT ON VIEW agg.tarifa_dinamica IS
    'Precio por media hora de la tarifa dinámica (ToU) de Low Carbon London en 2013, en peniques por kWh. Los hogares Std pagaron una tarifa plana de 14.228 p/kWh.';

GRANT USAGE ON SCHEMA agg TO lab_ontology;
GRANT SELECT ON ALL TABLES IN SCHEMA agg TO lab_ontology, lab_agent, lab_forecast, lab_eval;
ALTER DEFAULT PRIVILEGES IN SCHEMA agg GRANT SELECT ON TABLES TO lab_ontology;
