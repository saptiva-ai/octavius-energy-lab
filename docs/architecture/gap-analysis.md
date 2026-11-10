# Gap Analysis: de Octavius a Octavius Energy Lab

Fase 0, 2026-11-10. Compara `current-state.md` con `proposed-energy-lab.md`.

## Matriz

| Área | Hoy | Necesario | Acción | Fase |
|---|---|---|---|---|
| Base del repo | Fork de cliente con historial que contiene material de clientes | Repo open source limpio | **Snapshot sin historial**, sin contenido de cliente, con gitleaks y grep de nombres | 0-1 |
| UI de chat y canvas | Existe | Igual | **Reutilizar** | – |
| Gráfica de forecast | Solo componentes retail | `chart_type: forecast` con cuantiles y corte | **Extender** el registro del canvas | 7 |
| Dashboard de evals | No existe | Vista A/B con trazas, MEDIDO/REPLAY | **Nuevo**, ruta `/evals` en `apps/web` | 7 |
| Orquestador | decide/tools/narración, `MAX_DECIDE_ROUNDS=2` fijo | Presupuestos y componentes configurables por harness | **Extender** con `HarnessConfig` y hooks de validación | 2, 5 |
| Cliente LLM | OpenAI-compatible hacia Saptiva o InferNode | Ollama local y parámetro de thinking | **Reutilizar**, cambiando la URL base; verificar el passthrough de `chat_template_kwargs` | 2 |
| Inferencia local | No existe; sin GPU en compose | Ollama con GPU | **Nuevo** servicio en el perfil `gpu` | 2 |
| Registro de plugins | Un plugin de dominio cableado (`domain_tools.py:58`) | N servidores MCP configurables | **Extender**: registro por configuración | 2 |
| Plugin de datos | Plugin retail (fuera del fork) | `energy-data` | **Nuevo**, con el mismo patrón FastMCP y `AnalyticsResponse` | 1-2 |
| Guardas de SQL | sqlguard y sandbox dentro del plugin retail | Las mismas guardas para energía | **Extraer** a un paquete compartido y reutilizar | 1 |
| PostgreSQL | 15, perfil `local`, DDL suelto, sin roles verificados | BD `energy_lab`, particionamiento, 5 roles, migraciones numeradas | **Extender** el servicio y agregar el esquema; evaluar la versión 16 o 17 en el benchmark | 1 |
| Ingesta | ETL retail | Conectores CENACE, LCL y UCI con COPY, reanudables y con perfiles | **Nuevo** | 1 |
| Forecasting | No existe | Plugin TimesFM, baselines y backtesting | **Nuevo** | 3 |
| Capa semántica | Catálogo YAML de métricas; ruta `ontologia` del cliente | Catálogo energético y adaptador de Auto Ontology | **Extender** el patrón del catálogo; Auto Ontology opt-in | 4 |
| Telemetría | OTel, Prometheus, Grafana y Loki | Trazas de corrida consultables | **Reutilizar** OTel y agregar las tablas `lab.*` | 6 |
| Runner de evals | Específico de dominio; JSONL | Agnóstico, con ground truth SQL, métricas, sesgos y export | **Generalizar** los patrones; los casos son nuevos | 6 |
| Auth | JWT con rate limit | Igual | **No modificar** | – |
| CI | ruff, pytest, Jest, Trivy, grounding gate | Más tests de plugins y evals smoke | **Extender** | todas |

## No se modifica

- Autenticación y middleware de seguridad.
- El protocolo de streaming SSE hacia la web.
- El contrato `AnalyticsResponse`; solo se le agrega `chart_type` nuevo.
- El cliente MCP remoto.

## Se elimina del fork

- Plugin y ETL retail.
- Casos, personas y evals de cliente.
- Documentos y kanban de cliente.
- Componentes de gráficas retail.
- Roles de negocio y opciones `retail_advisor_*`.
- Restos de bank-advisor.
- Ruta y formulario de ontología del cliente.
- Basura local.

## Riesgos técnicos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Limpiar el fork deja referencias rotas en el backend (imports, config, componentes) | Alto: bloquea todo | PR dedicado con tests verdes antes de agregar energía |
| RAM del host: 14 GB, con unos 3 GB libres mientras corre otro stack | Alto para la demo y el perfil Full | Perfil `lab` mínimo; apagar stacks ajenos; el perfil Full se ingiere por particiones |
| VRAM compartida entre Ollama (~6 GB con KV) y TimesFM | Medio | Medir en la fase 3; TimesFM 2.5 tiene 200M parámetros; fallback a CPU para TimesFM |
| Qwen3-8B Q4 elige mal las tools | Es justo lo que se mide | Es un resultado, no un bug; documentar E3 |
| Demanda de CENACE sin API y desglose sin verificar | Medio | Iniciar con PML/PND (API verificada); demanda vía descarga manual o scraping respetuoso, verificado en su PR |
| Licencia de CENACE poco clara | Medio | No redistribuir crudos; conectores más citación |
| Open-Meteo gratis solo no comercial | Bajo para una POC educativa | Documentar; autoalojar si se reutiliza en producto |
| `timesfm` en pip: versión ambigua para 2.5 | Bajo | Pin por commit del repo oficial |
| vLLM en sm_120 frágil | Bajo (Ollama por defecto) | vLLM como alternativa documentada |
| Auto Ontology requiere NIM, pgvector y tres modelos | Medio | Opt-in; catálogo local por defecto; evaluación de viabilidad escrita |
| Sesgo del evaluador: el juez favorece respuestas largas | Alto para las conclusiones | Verificadores deterministas primero; juez de otro proveedor; medir E5 |
