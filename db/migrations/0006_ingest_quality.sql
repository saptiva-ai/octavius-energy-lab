-- Reporte de calidad por lote de ingesta: filas leídas, nulos, ceros,
-- negativos y anomalías de hora local (inexistente o ambigua por horario de
-- verano), entre otras. Las llaves dependen de la fuente.

ALTER TABLE core.ingest_batch
    ADD COLUMN quality jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN selection text NOT NULL DEFAULT '';  -- huella de la selección (clientes, fechas)

COMMENT ON COLUMN core.ingest_batch.quality IS 'Conteos de calidad del lote; llaves por fuente.';
COMMENT ON COLUMN core.ingest_batch.selection IS 'Descripción legible de la selección cargada.';
