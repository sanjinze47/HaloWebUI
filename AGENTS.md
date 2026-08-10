# HaloWebUI Agent Guide

This file is the durable project contract for coding agents. Keep incident-specific
details, provider payload examples, and changing compatibility facts in the linked
documents and regression tests rather than adding them here.

## Product baseline

- HaloWebUI is a browser-first, self-hosted AI workspace for a small internal team.
- The critical user journeys are authentication, chat, streaming responses, file
  upload, knowledge bases, and Skills.
- Chrome and Edge are primary browser targets. Firefox is secondary. Other desktop
  and mobile browsers are best-effort unless a task explicitly expands support.
- Docker Compose is the primary deployment target. The backend serves the built
  frontend from the same origin on port `8080`.
- `/app/backend/data` is the persistent Docker data boundary.
- SQLite is the primary database for the supported single-node deployment.
  Preserve existing PostgreSQL and MySQL compatibility on a best-effort basis.
- Python 3.11 and 3.12 and Node.js 22 are the supported development baselines.
- `origin` is `sanjinze47/HaloWebUI`; `upstream` is `ztx888/HaloWebUI`.
  The fork is maintained independently until upstream maintenance resumes.

When trade-offs conflict, use this order:

```text
Data safety > authorization correctness > backward compatibility > reliability
> user experience > performance > delivery speed
```

## Project contracts

Read the relevant contract before changing that area:

- [Product contract](docs/PRODUCT_CONTRACT.md)
- [Architecture boundaries](docs/ARCHITECTURE.md)
- [Quality gates](docs/QUALITY_GATES.md)
- [Provider compatibility](docs/PROVIDER_COMPATIBILITY.md)
- [Data and migrations](docs/DATA_AND_MIGRATIONS.md)
- [Release process](docs/RELEASE.md)

## Non-negotiable behavior

- Preserve the six critical user journeys unless the request explicitly changes one.
- Do not change existing signup, role assignment, session, or authentication behavior
  without explicit authorization and dedicated authorization tests.
- Enforce permissions in the backend. Hiding or disabling frontend controls is not an
  authorization boundary.
- Keep provider credentials and privileged connection configuration on the server.
- Keep standard provider semantics intact. Isolate gateway-specific differences in
  provider adapters or explicit compatibility modes.
- An explicit user mode must not silently change into a semantically different mode.
- Streaming and non-streaming paths must produce equivalent final content, sources,
  tool results, and error meaning where the provider supports both.
- An optional integration failure must not break authentication or ordinary chat.
- Schema changes require a migration and upgrade verification against existing data.
- Frontend, backend, Docker image, changelog, and build metadata must agree on the
  released version and source commit.

## Architecture boundaries

- Svelte components own interaction and rendering, not provider protocol decisions.
- Frontend API modules own request types and transport calls, not server secrets.
- FastAPI routers own authentication, authorization, validation, and HTTP contracts.
- Provider adapters own upstream payload, event, and error normalization.
- Middleware owns cross-module orchestration; do not accumulate unrelated provider
  exceptions there when an adapter or capability policy is the proper owner.
- Models and storage own persistence and must not depend on frontend behavior.
- Prefer explicit capability metadata and connection configuration. Model-name
  heuristics are compatibility fallbacks, not the primary architecture.

## Provider support

- Tier 1: OpenAI, Sub2API, grok2api, and CLIProxyAPI.
- Tier 2: existing named providers not listed in Tier 1 or Tier 3.
- Tier 3: Ollama and unknown OpenAI-compatible gateways.
- A support tier applies only to documented capabilities. Never infer that every
  provider supports chat, files, images, tools, search, or citations.
- A Tier 1 adapter change requires sanitized contract fixtures, streaming and
  non-streaming coverage where applicable, and a local smoke test when the relevant
  provider is available.
- Real endpoints, model selections, and current capability results belong in the
  local provider store or `docs/PROVIDER_COMPATIBILITY.md`, never in this file.

## Skills and security

- Treat Skills as privileged executable capabilities.
- Administrators install, update, remove, and enable shared Skills.
- Regular users may invoke only the Skills they are allowed to use.
- Skill changes must cover authorization, import validation, execution failure,
  cancellation or cleanup, and protection of provider credentials and other users'
  data.
- Never commit secrets, local databases, tokens, encrypted secret blobs, generated
  dependencies, `.env` files, or local provider configuration.

## Change workflow

1. Record the starting commit and inspect `git status` before editing.
2. Define the user scenario, acceptance result, and affected critical journeys.
3. Read the relevant frontend, backend, data, Docker, workflow, and contract code.
4. Identify authorization, persistence, provider, compatibility, and deployment risk.
5. Make the smallest complete change within the correct ownership boundary.
6. Add a regression test for a bug and behavioral tests for new functionality.
7. Test normal, failure, unauthorized, and legacy-state behavior where applicable.
8. Run focused checks, then every quality gate required by the change class.
9. Add user-visible changes to `CHANGELOG.md` under `Unreleased`.
10. Report tests actually run, results, untested areas, and remaining risk.

Do not weaken, delete, or skip an existing test merely to make a change pass. A
pre-existing failure is not permission to publish another failing release.

## Core commands

```bash
npm ci
npm run check
npm run test:frontend
npm run build
PYTHONPATH=backend python -m pytest -q backend/open_webui/test/unit
python -m compileall -q backend/open_webui
docker compose config
```

On PowerShell, set `$env:PYTHONPATH = "backend"` before running backend tests.
Use focused test paths during development, then run the required broader suite before
commit or release. See `docs/QUALITY_GATES.md` for the change matrix.

## Local provider credentials

- Provider test credentials must remain in the local DPAPI store outside the repo.
- Use only `scripts/provider-tests/` to configure or consume local credentials.
- Never add a command that prints, exports, or returns a decrypted credential.
- Real-provider smoke tests run only when relevant and use the selected provider only.
- CI uses sanitized fixtures and must not depend on local or production credentials.
- A credential shown in chat, screenshots, logs, or terminal output is compromised and
  must be revoked instead of added to the local store.

## Version and release contract

- `package.json` is the application version source of truth; keep `package-lock.json`
  synchronized.
- Ordinary development does not change the version. Accumulate user-visible notes in
  the `Unreleased` changelog section.
- Only an explicit release request authorizes a version bump, tag, GitHub Release, or
  stable Docker publication.
- `edge` and `edge-slim` track successful `main` builds for testing.
- `latest` and `slim` track the latest explicitly approved stable release.
- `X.Y.Z` and `X.Y.Z-slim` are immutable release images.
- A release tag must be `vX.Y.Z` and match `package.json.version` exactly.
- `WEBUI_BUILD_HASH` must identify the exact source commit in the frontend, backend,
  and image.
- Never move or overwrite a published version tag. A retry must build the exact tagged
  source commit.
- Push `main` only after checks pass. Push a release tag only after `main` and all
  release gates pass.

GHCR publishing uses the repository `GHCR_TOKEN`; provider testing never uses that
secret. Do not claim an image is deployable until its manifest is readable and the
container smoke check succeeds.

## Git and task isolation

- Do not use force push, destructive reset, or destructive cleanup on shared branches.
- Concurrent tasks must use separate branches and worktrees.
- Do not edit files already modified by another active task.
- Never release from a dirty or shared worktree.
- Before committing, verify every changed file belongs to the current task.
- Keep functional changes, governance changes, and release metadata in reviewable
  commits; do not mix unrelated churn.
- Do not claim a commit, push, tag, Release, or image succeeded without verifying the
  corresponding local or remote result.

## Handoff requirements

Every completed change must state:

- user-visible behavior;
- files and contracts affected;
- tests run and their results;
- migration, deployment, security, and compatibility impact;
- anything not verified.
