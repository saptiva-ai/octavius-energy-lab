# Web CLAUDE.md

When this applies: working under `apps/web/`.

Entrypoints

- App layout: `apps/web/src/app/layout.tsx`.
- Components: `apps/web/src/components/`.
- Lib/utilities: `apps/web/src/lib/`.

Testing

- `make test T=web` (corre en el host con bun; el contenedor web no tiene pnpm/node).
- `cd apps/web && bun run test` (directo, equivalente).

Lint/Format

- `cd apps/web && bun run lint`

Dev server (contenedor)

- El hot-reload del bind mount NO es confiable: tras editar código de
  `apps/web/src`, si el cambio no se refleja haz
  `docker restart octavius-energy-lab-web` antes de depurar en
  falso (visto 2 veces el 2026-07-13).

Refs

- `.claude/skills/code/SKILL.md`
- `.claude/skills/test/SKILL.md`
