# Octavius Energy Lab

Laboratorio open source para evaluar *agent harnesses* sobre Octavius, la plataforma de chat agéntico de Saptiva AI, con datos eléctricos públicos (CENACE y Low Carbon London), un LLM local (Qwen3-8B) y forecasting con TimesFM.

Acompaña la charla **Beyond the Model: The Art of Evaluating Agent Harnesses** (Cloud Community).

> Do not optimize the benchmark to make the harness look good. Design the benchmark to reveal where the harness actually fails.

## Estado

Este árbol es el punto de partida: el núcleo de Octavius sin código, datos ni documentos de clientes. Todavía no contiene el dominio de energía; las fases siguientes lo agregan como plugins MCP, sin duplicar la plataforma. El diseño y el roadmap están en `docs/`.

## Componentes

| Componente | Tecnología | Ruta |
|---|---|---|
| Web | Next.js 15, React 19, Plotly | `apps/web` |
| Backend | FastAPI, Python 3.11, orquestador de tool calling | `apps/backend` |
| Plugins | Servicios independientes: MCP sobre HTTP o gRPC | `plugins/` |
| Datos de la app | MongoDB, Redis, MinIO, Weaviate | `infra/docker-compose.yml` |
| Datos analíticos | PostgreSQL 15 (perfil `local`) | `infra/docker-compose.yml` |
| Observabilidad | OpenTelemetry, Prometheus, Grafana, Loki | `infra/observability`, `infra/monitoring` |

## Uso

```bash
make help        # comandos disponibles
make env         # crea envs/.env desde el ejemplo
make dev         # levanta el stack de desarrollo
make test T=api  # pruebas unitarias del backend (uv)
make test T=web  # tipos, lint y pruebas de la web (bun)
```

Requisitos: Docker con Compose, `uv` y `bun`.

## Licencia

Apache-2.0 (ver `LICENSE`). Los datasets y modelos que se integren en fases posteriores tienen licencias propias, documentadas en `docs/data/sources.md`; en particular, los datos crudos de CENACE no se redistribuyen y los pesos de TimesFM 3.0 son de uso no comercial.
