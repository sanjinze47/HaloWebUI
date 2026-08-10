# HaloWebUI Quality Gates

## Definition of done

A change is complete only when:

- its user scenario and acceptance result are explicit;
- the implementation respects architecture and authorization boundaries;
- normal, failure, unauthorized, and legacy-state behavior are covered where relevant;
- required checks pass;
- user-visible changes appear under `Unreleased`;
- untested areas and residual risk are reported.

An existing failure is not permission to publish another failing release. Do not
weaken, delete, or skip tests to make a change pass.

## Change matrix

| Change class                 | Minimum verification                                                       |
| ---------------------------- | -------------------------------------------------------------------------- |
| Frontend behavior            | focused Vitest, `npm run check`, full frontend tests, build                |
| Backend behavior             | focused pytest, affected backend suite, compileall                         |
| Frontend/backend contract    | both suites, request/response fixture, error path                          |
| Provider adapter             | sanitized contract fixtures, stream/non-stream paths, provider tier policy |
| Authentication/authorization | allowed and denied cases at the backend boundary                           |
| Files/knowledge              | validation, access, cleanup, failure, persisted metadata                   |
| Skills                       | install/manage authorization, invoke authorization, failure and cleanup    |
| Schema/migration             | old SQLite copy upgrade, repeated startup, data preservation               |
| Docker/runtime               | Compose validation, image build, container health and version smoke        |
| Release/workflow             | YAML validation, version/tag/source SHA checks, immutable tag behavior     |

## Core local checks

Frontend:

```bash
npm ci
npm run check
npm run test:frontend
npm run build
```

`npm run check` enforces the accepted legacy ceiling of 5432 errors, 124 warnings,
and 240 affected files. Use `npm run check:raw` to print every diagnostic. A change
must not raise any ceiling; reduce the baseline whenever existing diagnostics are
fixed.

Backend on Bash:

```bash
PYTHONPATH=backend python -m pytest -q backend/open_webui/test/unit
python -m compileall -q backend/open_webui
```

CI applies Black to Python files added or modified by the change. The repository-wide
`black --check backend` result remains tracked as legacy formatting debt; new or
modified Python code is not allowed to add to it.

The unit-suite `conftest.py` assigns a disposable `DATA_DIR` unless the caller already
provided one. Tests must never create, migrate, or reuse the developer's application
database. CI additionally assigns its own runner-temporary `DATA_DIR` explicitly.

Backend on PowerShell:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest -q backend/open_webui/test/unit
python -m compileall -q backend/open_webui
```

Deployment:

```bash
docker compose config
```

Use focused tests while iterating. Run the complete required set before commit and all
release gates before a tag.

## Regression tests

A bug fix should reproduce the failure before the fix and pass after it. Preserve the
smallest sanitized input, state transition, or provider event sequence that caused the
failure. Test behavior rather than private implementation details.

When an automated regression is impractical, document why and record exact manual
verification evidence. Manual evidence does not replace required automated gates.

## Provider tests

- CI tests use sanitized local fixtures and never call production endpoints.
- Tier 1 adapter changes require a local smoke test when the provider is available.
- A real smoke test must record provider name, scenario, HTTP status, content type,
  completion signal, and duration without recording secrets or full sensitive bodies.
- Test streaming and non-streaming separately when both are supported.
- Treat an error encoded inside a successful streaming HTTP response as an error.

## Release gates

Before a stable release:

1. the worktree is clean and the source commit is fixed;
2. required frontend and backend checks pass;
3. Compose and workflow files validate;
4. version, lockfile, changelog, tag, and build metadata agree;
5. the image builds and passes its health check;
6. deployment and rollback impact is documented.
