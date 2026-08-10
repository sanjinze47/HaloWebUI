# HaloWebUI Architecture Boundaries

## Runtime shape

The supported production baseline is one Docker Compose service that serves the built
Svelte frontend and FastAPI backend from the same origin. Persistent application state
lives under `/app/backend/data`.

## Ownership boundaries

### Frontend components

Svelte components own rendering, interaction state, accessibility, and responsive
behavior. They may select among capabilities supplied by the backend, but must not
contain provider credentials or become the source of truth for provider protocol
compatibility.

### Frontend API modules

`src/lib/apis` owns typed HTTP requests, streaming transport consumption, and client
error conversion. It must preserve backend contracts and avoid reconstructing
privileged configuration in browser state.

### FastAPI routers

Routers own authentication, authorization, input validation, stable HTTP response
shapes, and status codes. Every privileged action requires backend enforcement even
when the frontend already hides the action.

### Provider adapters

Provider-specific modules own upstream paths, payload fields, streaming events,
citations, tool results, and error normalization. Compatibility behavior must be
selected by explicit connection configuration or capability metadata.

### Middleware and orchestration

Middleware coordinates chat, files, tools, search, images, and persistence. Keep
provider-specific conversions in adapters or dedicated helpers. Shared orchestration
must not become a collection of unrelated gateway exceptions.

### Models, storage, and migrations

Persistence code owns durable state. Schema changes use the established migration
mechanisms and must work against an existing SQLite database. Frontend state is not a
database migration mechanism.

### Skills

Skills are privileged executable resources. Installation and lifecycle management are
administrator operations. Invocation must preserve resource access rules and protect
provider credentials, local files, and other users' data.

## Capability policy

Prefer, in order:

1. explicit connection configuration;
2. upstream capability metadata;
3. a centrally tested compatibility rule;
4. model-name heuristics as a final fallback.

Do not spread the same capability rule across frontend components, routers, and
middleware. Establish one server-side source and expose only the safe result.

## Cross-layer changes

A cross-layer contract change must update all affected consumers in one change:

- backend schema or response;
- frontend types and rendering;
- streaming and non-streaming paths;
- persisted legacy values;
- tests and documentation.

Preserve existing public response fields when adding optional capability metadata.
