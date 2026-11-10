# Backend CLAUDE.md

When this applies: working under `apps/backend/`.

Entrypoints

- App entry: `apps/backend/src/main.py`.
- Routers: `apps/backend/src/routers/`.
- Services: `apps/backend/src/services/`.

Testing

- `make test T=api` (logical API maps to compose service `backend`).
- `make test-local FILE="tests/unit/test_x.py"` for local .venv.
- `/dev-up --start` then `make test T=api` for a minimal check.

Config

- Env files live in `envs/.env*` (do not commit secrets).

Refs

- `.claude/skills/code/SKILL.md`
- `.claude/skills/test/SKILL.md`
- `scripts/testing/test-runner.sh`
