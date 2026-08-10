# HaloWebUI Product Contract

## Purpose

HaloWebUI is a private, browser-first AI workspace for a small internal team. It
provides one interface for model conversations, streaming output, files, knowledge
bases, and administrator-managed Skills while keeping deployment and data under the
team's control.

## Primary users

- Administrators manage users, providers, shared models, knowledge bases, and Skills.
- Regular users use only resources and capabilities granted to them.
- Existing signup, role assignment, and authentication behavior remains the product
  baseline until an explicitly approved change replaces it.

## Critical journeys

The following journeys are release-critical:

1. A user can authenticate and reach the application.
2. A user can create and continue a chat with an allowed model.
3. Streaming output completes, stops, and reports errors coherently.
4. A user can upload an allowed file and receives a clear validation result.
5. An authorized user can add and query knowledge-base content.
6. An authorized user can invoke an enabled Skill without crossing permission or
   secret boundaries.

Any change touching one of these journeys must state its expected behavior and include
focused regression coverage.

## Product priorities

Use this order for product and engineering trade-offs:

```text
Data safety > authorization correctness > backward compatibility > reliability
> user experience > performance > delivery speed
```

## User experience baseline

- Primary support targets are current Chrome and Edge desktop releases.
- Firefox is a secondary target.
- Other desktop and mobile browsers are best-effort unless explicitly promoted.
- Error messages must tell the user what failed and what action is possible without
  exposing credentials, upstream payloads, or internal stack traces.
- Advanced provider and infrastructure details belong in administrator surfaces, not
  ordinary chat flows.
- Existing Chinese-facing product copy must remain clear and consistent when changed.

## Compatibility baseline

- Standard provider behavior must remain standard.
- Compatibility modes are explicit connection properties, not guesses based on host,
  IP address, or a single model name.
- Automatic behavior may preserve an existing fallback in `auto` mode.
- An explicit user selection must fail clearly rather than silently changing meaning.
- Unsupported optional capabilities must not disable authentication or normal chat.

## Out of scope by default

The following require an explicit product decision before implementation:

- public multi-tenant hosting;
- changing registration or default roles;
- Kubernetes or multi-replica guarantees;
- zero-downtime database migration;
- a new telemetry or external data-sharing mechanism;
- promoting a best-effort browser, database, or provider to a supported tier.

## Operating inputs not yet fixed

Do not invent guarantees for the following areas. Preserve current behavior until the
team supplies a concrete requirement and verification method.

| Input | Current rule |
| --- | --- |
| User count, concurrency, and response-time targets | No formal service-level objective; optimize only from measured internal usage |
| Backup frequency, retention, acceptable data loss, and recovery time | Take a verified local backup before data-changing releases; do not claim automated recovery guarantees |
| File size, storage quota, and retention | Preserve existing limits and cleanup behavior |
| Skills process or filesystem isolation | Treat administrator-installed Skills as trusted privileged code; do not claim sandbox isolation |
| Provider model selection | Do not pin a model globally; select an available model explicitly for each local smoke test |

These inputs become release contracts only after they are documented with an owner,
an acceptance threshold, and a test or operational check.
