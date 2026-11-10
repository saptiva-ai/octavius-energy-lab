# Plugins CLAUDE.md

When this applies: working under `plugins/`.

Entrypoints

- File manager: `plugins/public/file-manager/src/main.py`.
- Retail advisor: `plugins/retail-advisor/src/main.py`.

Compose services

- `file-manager`, `retail-advisor` (see `infra/docker-compose.yml`).

Testing

- Use repo-level commands (invoke `test` skill).

Refs

- `.claude/skills/explore/SKILL.md`
- `plugins/retail-advisor/README.md`
