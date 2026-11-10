# Registro de decisiones

| ID | Fecha | Decisión | Motivo | Quién |
|---|---|---|---|---|
| ADR-0001 | 2026-11-10 | Base: variante interna más reciente de Octavius, sin datos, documentos ni código de cliente; snapshot sin historial | Es la variante más actual de Octavius; el historial contiene material de clientes | Usuario (base), Claude (snapshot) |
| ADR-0002 | 2026-11-10 | Datos: CENACE como principal, Low Carbon London como secundario, UCI para desarrollo | Relevancia local; granularidad por hogar y tarifa dinámica en LCL | Usuario |
| ADR-0003 | 2026-11-10 | Particionamiento nativo de PostgreSQL; TimescaleDB solo si E1 lo justifica | Evitar dependencias por preferencia | Claude, según el prompt |
| ADR-0004 | 2026-11-10 | No redistribuir datos crudos de CENACE; publicar conectores | Términos de uso no verificados | Claude |
| ADR-0005 | 2026-11-10 | Inferencia por defecto con Ollama `qwen3:8b` (Q4_K_M); vLLM como alternativa | Octavius no tiene inferencia local; vLLM es frágil en sm_120; cabe en 16 GB | Claude |
| ADR-0006 | 2026-11-10 | TimesFM 2.5 por defecto; 3.0 opt-in y aislado | Licencia no comercial de los pesos de 3.0 | Claude, según el prompt |
| ADR-0007 | 2026-11-10 | Capa semántica: catálogo local por defecto; Auto Ontology opt-in por MCP | Costo de NIM, pgvector y tres modelos; no bloquear la POC | Claude, según el prompt |
| ADR-0008 | 2026-11-10 | Clima con pronósticos archivados de Open-Meteo como covariable futura; observaciones solo pasadas | Evitar el leakage temporal | Claude |
| ADR-0009 | 2026-11-10 | Excluir el clima Dark Sky de Kaggle | Licencia de redistribución no clara | Claude |
