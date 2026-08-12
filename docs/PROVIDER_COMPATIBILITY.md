# Provider Compatibility Policy

## Support tiers

| Tier | Providers                                        | Maintenance expectation                                                  |
| --- | --- | --- |
| 1    | OpenAI, Sub2API, grok2api, CLIProxyAPI           | Explicit compatibility, regression fixtures, affected-path smoke testing |
| 2    | Existing named providers not in Tier 1 or Tier 3 | Preserve current behavior and test when touched                          |
| 3    | Ollama and unknown OpenAI-compatible gateways    | Best-effort compatibility without unrelated release blocking             |

A tier does not imply that a provider supports every capability.

## Capability matrix

For each provider and compatibility mode, record only verified support for:

- model discovery;
- chat completions;
- streaming chat;
- Responses API;
- file inputs;
- image generation and editing;
- tools and Skills integration;
- native search;
- structured citations.

Capability claims must identify the provider, route or account mode, source version or
upstream commit, and verification date. Distinguish:

1. fields a gateway accepts;
2. fields it forwards;
3. behavior the final upstream actually supports.

## Adapter rules

- Use explicit connection compatibility modes.
- Do not identify a provider by IP address or hard-coded hostname.
- Preserve standard OpenAI semantics in standard mode.
- Normalize upstream output into stable HaloWebUI events and response shapes.
- Deduplicate normalized sources and tool results using stable identifiers.
- Do not invent citations, completion events, or successful fallback results.
- Preserve upstream status and error meaning while returning safe user-facing detail.
- Keep streaming and non-streaming conversion behavior aligned.

## Fallback policy

- Preserve existing fallback behavior in `auto` modes.
- Do not add a new fallback without a product-level behavior decision.
- An explicit mode fails clearly instead of silently switching semantics.
- A fallback may run only when its capability is enabled and authorized.
- Fallbacks must not broaden data access or move a credential into the browser.

## Connection compatibility fields

- `OPENAI_API_CONFIGS[index].chat_completion_token_parameter` accepts `auto`,
  `max_tokens`, or `max_completion_tokens`. Explicit values override endpoint and
  model heuristics. Missing legacy values use `auto`; Responses requests continue to
  use `max_output_tokens`.
- `OPENAI_API_CONFIGS[index].image_edit_compatibility` accepts `standard` or
  `grok2api`. The latter enables grok2api's JSON data-URL image edit protocol;
  standard OpenAI-compatible image edits remain multipart. grok2api edits request URL
  results so the adapter can reject empty successful responses and localize returned
  media. Legacy connections whose configured name contains `grok2api` retain the
  grok2api behavior.
- `OPENAI_API_CONFIGS[index].responses_compatibility` accepts `standard`,
  `sub2api`, or `custom`. Invalid persisted or submitted values are configuration
  errors and never silently become `standard`.
- `GEMINI_API_CONFIGS[index].gemini_compatibility_mode` accepts `strict` or `auto`.
  New connections use `strict`; existing connections without the field retain
  `auto`. Auto mode strips only an optional capability named by a recognized HTTP
  400 unsupported-field error. Explicit tools, search, thinking, and image output
  requests are required capabilities and are never silently removed.

### grok2api video generation

The video adapter targets the public grok2api `v3.1.2` release (verified 2026-08-12)
through an OpenAI-compatible connection explicitly configured with
`video_generation_compatibility: "grok2api"`. The confirmed routes are:

- `POST /v1/videos/generations` for asynchronous text-to-video and image-to-video submission;
- `GET /v1/videos/{request_id}` for status and progress;
- `GET /v1/videos/{request_id}/content` for the generated MP4 stream.

The submitted fields are `model`, optional `prompt`, optional `image.url` Data URL,
`duration`, `aspect_ratio`, and `resolution`. HaloWebUI currently accepts one JPEG,
PNG, or WebP reference image up to 20 MiB, durations from 1 to 15 seconds, ratios
`1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, and `2:3`, and resolutions `480p` and
`720p`. The adapter requires `video/mp4`, an MP4 `ftyp` header, and a maximum output
size of 256 MiB before archiving the result. These claims are based on the upstream
route contract and sanitized fixtures; a live provider smoke test still requires a
local grok2api credential.

Responses streams are successful only after `response.completed`, the supported
`response.done` compatibility event, or an explicit transport `[DONE]`. A raw EOF,
failure event, or incomplete/cancelled response is normalized as an error in both
streaming and non-streaming paths.

## Local verification

Real provider credentials remain in the Windows DPAPI store outside the repository.
Use `scripts/provider-tests/provider-smoke-test.ps1` for selected, redacted smoke tests.
Never place endpoints, model selections, encrypted blobs, or credentials in this
document when they are specific to the local deployment.

CI uses sanitized fixtures. A fixture must remove credentials, user content, internal
hostnames, request identifiers, and other deployment-specific data while retaining the
protocol structure needed for regression coverage.
