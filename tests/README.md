# Test Suite — OctaviOS Chat (raíz del repo)

Suites genéricas del host que corren contra el stack VIVO (no en CI; CI corre
las unit de `apps/backend/tests/unit` y las de cada plugin por separado).

> Historia (2026-07-07): las suites del producto bancario (regression,
> charts, conversation, clarification, metrics, fixtures/happy_path) se
> eliminaron; sus equivalentes retail viven en el eval harness del plugin
> (`plugins/retail-advisor/tests/evals/`, corre con `make demo-retail.evals`)
> y en los e2e web (`apps/web/e2e`).

## Estructura

```
tests/
├── integration/      # Servicio a servicio (backend ↔ embedding/filemanager/minio)
├── smoke/            # Smoke de paths críticos (embedding delegation)
├── system/
│   ├── security/     # Seguridad black-box del API (auth tokens, hardening)
│   ├── rag/          # Calidad de RAG (requiere Weaviate)
│   └── embedding/    # Regresión de la arquitectura de embedding delegation
├── unit/             # Unit del host (text sanitizer, …)
├── utils/            # Helpers + validación de output crudo
└── runner/           # Runner paralelo por suites
```

## Cómo correr

```bash
# Prerequisito: stack arriba
make dev

# Listar suites disponibles
python -m tests.runner --list

# Correr suites (paralelo)
python -m tests.runner system_security integration

# Un script directo
python tests/system/security/test_auth_token_manipulation.py
./scripts/testing/run_embedding_tests.sh   # suite completa de embedding
```

Suites: `system_security` · `system_rag` · `system_embedding` · `system_all` ·
`integration` · `smoke` · `unit` · `backend_unit`.

## Convenciones

- Estos scripts corren como procesos independientes contra
  `http://localhost:8000` (backend) y servicios del compose — no usan mocks.
- Exit codes: `0` OK · `1` fallos de test · `2` fallo de infraestructura
  (servicio caído: levanta el stack primero).
- Deps de host: los scripts usan `requests`/`httpx`; instálalas en el venv
  desde el que corras (no van en los requirements de los servicios).
