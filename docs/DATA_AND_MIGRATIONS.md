# Data and Migration Contract

## Supported baseline

- SQLite in the persistent Docker volume is the primary supported database.
- Existing PostgreSQL and MySQL paths remain best-effort compatible.
- `/app/backend/data` is the persistent boundary for the default Compose deployment.
- Container replacement, upgrade, and rollback must not remove the persistent volume.

## Durable data

Treat the following as user data rather than rebuildable cache unless the code clearly
defines otherwise:

- accounts, roles, and settings;
- chats and message metadata;
- uploaded and generated files;
- knowledge-base metadata and source documents;
- provider and model configuration;
- Skills and their configuration.

Do not use destructive cleanup commands against the data directory during development,
testing, migration, or deployment.

## Schema changes

- Use the repository's established migration mechanism.
- Do not mutate production schemas from frontend code or ad hoc startup branches.
- Migrations must be safe to run during repeated container startup.
- Additive changes should use compatible defaults for existing rows.
- Removing or reinterpreting persisted fields requires an explicit migration plan.
- Preserve fields needed by older records even if new records use a newer shape.

## Migration verification

For a schema or persisted-format change:

1. create a disposable copy of an existing SQLite database;
2. run the application migration against the copy;
3. verify critical tables and affected records;
4. start the application a second time to test idempotence;
5. exercise the affected user journey;
6. document backup and rollback behavior.

Do not test migrations against the user's only local database.

## Backup and rollback

The supported rollback mechanism is restoring a verified backup or data-volume copy.
Alembic or internal downgrade functions are not assumed safe unless a change explicitly
implements and tests them.

Before releasing a data-changing version, document:

- what data changes;
- whether the previous application version can read the migrated data;
- what must be backed up;
- how to restore service after a failed migration.

## File and knowledge data

- Validate size, type, empty content, ownership, and path safety at the backend.
- Do not leave remote uploads, temporary files, or generated artifacts orphaned after a
  failed operation when cleanup is possible.
- Knowledge and retrieval changes must preserve access control and source attribution.
- Cache invalidation must not silently delete authoritative documents or chat metadata.

## Runtime coordination and secrets

- SQLite runtime migrations use a persistent sidecar lock file. Unix uses `flock`;
  Windows locks a fixed one-byte region with `msvcrt.locking`. PostgreSQL advisory
  locking is unchanged.
- When no non-empty `WEBUI_SECRET_KEY` or legacy `WEBUI_JWT_SECRET_KEY` is supplied,
  the application resolves the shared key from `DATA_DIR/.webui_secret_key`.
- Legacy key files are migrated by copying their value into the data directory and
  are retained for rollback to older images. Conflicting, empty, unreadable, or
  unwritable key files stop startup instead of rotating encrypted data or sessions.
- Key creation is atomic and protected by the same cross-platform file lock so all
  workers and CLI entry points observe one value.

## Recoverable cleanup state

- `File.meta.deletion_pending` hides a file from normal reads while storage, vector,
  knowledge-reference, and row cleanup are retried. DELETE is idempotent, and startup
  performs a best-effort sweep for tombstones left by failed uploads or deletions.
- Removing a file from a knowledge base only removes that membership and the matching
  knowledge vectors. It does not delete the global File row, blob, or standalone file
  collection.
- `Knowledge.meta.vector_cleanup` records `delete` or `reset` work with attempt and
  error details. The marker remains until vectors, model references, and the matching
  metadata operation complete. Explicit retries and the startup sweep use the same
  idempotent flow; a missing vector collection is already clean.
- A knowledge reindex snapshots the previous collection. File replacement prepares
  embeddings before mutation and restores the previous vectors if insertion or File
  metadata persistence fails. A failed multi-file reindex restores the collection
  snapshot instead of leaving mixed generations.
- User deletion cleans external Skill, knowledge, vector, file, and storage resources,
  then checks all remaining user-owned database resources. User and Auth identity rows
  are removed together only after every cleanup step succeeds. Partial failure returns
  `user_cleanup_failed` with retryable resource details.

## Skill asset updates

- Imported Skill archives and extracted sources are written into a versioned staging
  directory and validated before the Skill row points at them. A failed stage is
  removed without changing the previous working Skill.
- Re-importing the same hash repairs missing archive/source assets. Disabled Skills and
  runtimes that are not ready are excluded from matching, prompts, tool construction,
  and execution, including after a session has already started.
