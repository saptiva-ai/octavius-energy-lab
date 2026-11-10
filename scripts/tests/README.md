# Shell Testing Guidelines

## Layout

```
scripts/
  test-runner.sh          # unified shell test runner
  tests/
    e2e/                  # end-to-end shell tests (suffix *.test.sh)
    smoke/                # lightweight smoke checks
    utils/                # helpers or wrappers not run automatically
    deprecated/           # staged for removal
  ci/
    audit-tests.sh        # reports deprecated references/endpoints
```

## Conventions

- Files must begin with `#!/usr/bin/env bash`, use `set -euo pipefail` and `IFS=$'\n\t'`.
- Name executable tests `*.test.sh`; helpers go in `utils/`.
- Use `mktemp` + `trap` for temporary files and quote all variables.
- Pass `shellcheck` and `shfmt` (`make lint:sh` / `make fix:sh`).

## Running

- All shell tests: `make test:sh` (invokes `scripts/test-runner.sh`).
- Lint shell: `make lint:sh` (shellcheck).
- Format shell: `make fix:sh` (shfmt).
- Audit deprecated tests: `make audit:tests`.

Add new tests under `scripts/tests/{e2e,smoke}` and ensure they are executable.
