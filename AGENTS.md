# HaloWebUI Agent Guide

This file is the project-specific contract for Codex, GitHub Copilot, and other coding agents.

## Project

- Frontend: Svelte 4, TypeScript, Vite, Tailwind CSS.
- Backend: Python 3.11+, FastAPI, SQLAlchemy, and Alembic under `backend/`.
- Runtime: the backend serves the built frontend from the same origin on port `8080`.
- Persistent data: `/app/backend/data` in Docker.
- Main branch: `main`.
- Fork remote: `origin` points to `sanjinze47/HaloWebUI`.
- Upstream remote: `upstream` points to `ztx888/HaloWebUI`.

## Local commands

```bash
npm ci
npm run check
npm run test:frontend
npm run build
python -m compileall -q backend/open_webui
docker compose config
```

Use `npm run dev` for the frontend and the backend development command documented by the repository when both services are needed. Use `docker compose up -d` for the normal container deployment.

## Version and release contract

- `package.json` is the source of truth for the application version.
- Keep `package-lock.json` in sync with `package.json`.
- Use Semantic Versioning and update `CHANGELOG.md` for every user-visible release.
- The first fork release is `0.1.0`; its Git tag is `v0.1.0`.
- A release tag must exactly match `package.json.version` after removing the leading `v`.
- `WEBUI_BUILD_HASH` identifies the source commit inside the backend and Docker runtime.
- The frontend displays the version, build hash, and release notes from the same contract.

## Change workflow

1. Read the relevant frontend, backend, Docker, and workflow code before editing.
2. Make the smallest change that satisfies the request and preserve existing API compatibility.
3. Never commit secrets, local databases, tokens, generated dependency directories, or `.env` files.
4. Run the focused checks for the changed area, then run the release checks before publishing.
5. Update `CHANGELOG.md` and the version only when the change is a release.
6. Commit with a clear message and push only after checks pass.
7. For a release, push `main` first and then push the matching `vX.Y.Z` tag.

## GitHub and publishing safety

- Never use `git push --force`, `git reset --hard`, or destructive cleanup commands on shared branches.
- Do not claim that a commit, tag, GitHub Release, or Docker image was published unless the command and remote result succeeded.
- If GitHub credentials, package permissions, or required tools are unavailable, stop before publishing and report the exact blocker.
- GHCR image names are lowercase: `ghcr.io/sanjinze47/halowebui`.
- GHCR publishing uses the repository Actions secret `GHCR_TOKEN` with `read:packages` and `write:packages` scopes; never place this token in source files.
- `latest` tracks successful `main` builds; immutable version tags track `vX.Y.Z` releases.

## Pull request expectations

- Explain the user-visible behavior and any migration or deployment impact.
- Include tests run and their results.
- Keep unrelated formatting, dependency, and metadata churn out of the change.
