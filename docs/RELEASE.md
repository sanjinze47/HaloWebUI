# HaloWebUI Release Contract

## Authorization

Ordinary fixes and features do not automatically create a release. Only an explicit
user instruction to publish or release authorizes:

- changing the application version;
- creating or pushing a release tag;
- creating a GitHub Release;
- moving stable Docker aliases.

Accumulate user-visible changes under `Unreleased` until that instruction is given.

## Version sources

- `package.json.version` is the source of truth.
- `package-lock.json` must contain the same root package version.
- `CHANGELOG.md` must contain a matching release section.
- The Git tag is `vX.Y.Z` and must point to the released source commit.
- `WEBUI_BUILD_HASH` is the full released source commit SHA.

Published version tags are immutable. Never move, delete, or force-update one to retry a
release. A retry may use an updated workflow definition, but it must checkout and build
the exact original tag commit and report that source SHA. A manual stable-image retry
must set `version_tag` to `X.Y.Z` and `source_ref` to the matching `vX.Y.Z`; the workflow
rejects branch-based stable publication.

## Image channels

| Tag | Meaning | Intended use |
| --- | --- | --- |
| `edge` | Latest successful full `main` build | Internal testing |
| `edge-slim` | Latest successful slim `main` build | Internal testing |
| `latest` | Latest explicitly approved full release | Stable deployment |
| `slim` | Latest explicitly approved slim release | Stable lightweight deployment |
| `X.Y.Z` | Immutable full release | Pinned production deployment |
| `X.Y.Z-slim` | Immutable slim release | Pinned lightweight deployment |
| `git-<sha>` | Source-addressable build | Diagnostics and traceability |

Production documentation should prefer an exact `X.Y.Z` tag. `latest` is a convenient
stable alias; `edge` is not a production recommendation.

## Release sequence

1. Finish functional work and regression tests without changing the version.
2. Run all required quality gates on the intended source commit.
3. Move `Unreleased` notes into the new semantic version section.
4. Update `package.json` and `package-lock.json` together.
5. Re-run version, frontend, backend, Compose, and workflow checks.
6. Commit and push `main`.
7. Create and push the matching annotated `vX.Y.Z` tag.
8. Verify GitHub Release and Docker workflows reach success.
9. Verify the version manifests and anonymous pull path.
10. Start the released image and verify health, version, build hash, and persistent
    volume behavior.

Do not describe a queued workflow as published. Do not describe a readable manifest as
a successfully started deployment.

## Credentials

`GHCR_TOKEN` is a repository Actions secret used only to publish images. It requires
the minimum package scopes documented by the workflow and must never appear in source,
logs, release notes, or local provider configuration.

Provider API credentials remain local and are never copied to GitHub Actions for the
release process.

## Failure and rollback

- A failed quality gate stops the release.
- A failed Release or image workflow may be retried without changing the source tag.
- A code fix after tagging requires a new patch version, not a moved tag.
- Roll back the application by selecting a previous immutable image tag.
- If a release changed persistent data incompatibly, restore the documented backup
  before starting the older image.
