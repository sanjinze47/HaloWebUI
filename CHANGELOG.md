# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Made the citation visibility preference hide inline markers, source cards, and the detail drawer together while retaining a compact restore control.
- Refined citation source cards and the responsive detail drawer with clearer hierarchy, lighter overlay treatment, compact link disclosure, and excerpt cards.

### Fixed

- Reverted citation visibility locally when saving the preference fails and filtered numeric placeholder titles and title-only excerpts from source details.
- Retried failed native web-search streams with HaloWebUI search when the upstream returned no completed response.

## [0.2.5] - 2026-08-10

### Changed

- Replaced overlapping citation controls with a compact source strip and a unified responsive detail drawer for links, excerpts, and local documents.

### Fixed

- Applied per-model built-in web search preferences when model metadata loads after a new chat is initialized.

## [0.2.4] - 2026-08-10

### Fixed

- Displayed single generated images at their full aspect ratio in chat instead of clipping wide images inside a fixed portrait card.
- Sent supported grok2api image edits as JSON data URLs, rejected empty successful responses, selected the edit route for reference-image requests, and resolved loopback result URLs through the configured provider origin.

## [0.2.3] - 2026-08-10

### Changed

- Established project-wide product, architecture, provider, data, quality, and release contracts for ongoing fork maintenance.
- Separated test builds (`edge` and `edge-slim`) from explicitly approved stable Docker releases (`latest` and `slim`).
- Made frontend tests non-interactive and added isolated backend unit tests and bytecode compilation to CI.

### Fixed

- Restored actionable archive-upload guidance and aligned message-outline regression tests with rendered token paths.
- Defaulted OpenAI Responses native web search in the backend and connection form to the current `web_search` tool while preserving explicit legacy `web_search_preview` configuration.
- Fixed Socket authentication refresh, per-response chat task recovery, cross-chat failure isolation, queued multi-model completion, and retryable attachment deletion.
- Fixed knowledge editing and indexing order, staged Skill repair, cross-platform migration locking, persistent secret-key resolution, and retryable knowledge, file, upload, and user cleanup.
- Normalized OpenAI Responses terminal errors and stream/non-stream output, added explicit Gemini and token-parameter compatibility modes, and made Ollama response cleanup deterministic.
- Fixed Gemini route startup, local document fallback without request state, orphan upload cleanup, Windows ZIP MIME normalization, Grok mojibake repair, and buffered reasoning duration accounting.

## [0.2.2] - 2026-08-07

### Fixed

- Fixed Sub2API Responses native web search requests by using `web_search` in Sub2API compatibility mode.
- Preserved explicit legacy `web_search_preview` configuration for standard Responses connections.
- Added parsing for direct and nested Responses URL citations, including independent annotation events and final response annotations.
- Added deduplicated OpenAI-style source cards with domain, favicon fallback, citation details, and safe external links.

## [0.2.1] - 2026-08-07

### Fixed

- 修复模型原生联网搜索在 Responses API 流式请求中返回 HTTP 502 的兼容问题。
- 使用 Responses API 通用的 `tool_choice: required` 强制调用原生搜索，兼容 Sub2API。
- 修复原生搜索和原生文件请求错误无法进入重试与诊断流程的问题。

## [0.2.0] - 2026-08-06

### Highlights

- **图片尺寸兼容**: 扩展图片模型的自然语言尺寸解析与校验，兼容常用比例和分辨率。
- **共享图片模型接口模式修复**: 修正共享图片模型的连接上下文与接口路由选择，凭据继续保留在服务端。
- **文件上传模式改进**: 改进原生文件输入与文件处理模式，并完善不支持场景下的回退行为。
- **Sub2API Responses 兼容**: 增加 Sub2API Responses 图片模型响应和流式响应的兼容处理。
- **代码块复制修复**: 修复复制代码块时空白、缩进和换行被破坏的问题。

## [0.1.0] - 2026-08-06

### Highlights

- **独立版本治理**: 为 HaloWebUI fork 建立统一的语义化版本、变更日志和 GitHub Release 流程。
- **可追踪构建**: 前端设置区域、后端配置接口和 Docker 镜像均显示版本号与构建提交。
- **GHCR 部署**: 提供 `ghcr.io/sanjinze47/halowebui` 的 amd64/arm64 镜像和 Compose 部署方式。

### Experience

- **版本信息更清晰**: 管理员可以在 General 设置中查看版本、构建提交并打开发行说明。
- **发布过程更可验证**: Release 工作流会校验 Git 标签与 `package.json` 版本完全一致。

## [0.0.1] - 2026-03-22

### Highlights

- **多模型统一接入**: 支持 OpenAI、Gemini、Anthropic、Grok、Ollama 以及兼容 OpenAI 协议的第三方服务，在一个界面中统一管理模型、密钥与连接。
- **灵活的联网与知识能力**: 内置 HaloWebUI 搜索、模型原生联网、网页加载、文件解析和知识库检索，适合日常问答、资料整理与复杂研究。
- **可控的工具调用体系**: 提供兼容、原生、关闭等工具调用模式，并支持 MCP、内置工具、技能和函数，让用户按场景决定是否启用自动工具能力。
- **本地优先的数据体验**: 用户、配置、聊天历史、文件和向量数据默认保存在本地托管的服务中，便于私有化部署、迁移和备份。
- **轻量部署与扩展**: 兼顾本地开发、Docker 镜像和服务器部署，保留简洁默认体验，同时为高级用户提供更完整的管理与扩展入口。

### Experience

- **面向中文用户优化**: 默认文案、设置项和关键提示更贴近中文使用习惯，减少理解成本。
- **清晰的管理边界**: 管理员配置、用户个人连接、聊天侧开关和运行时工具能力分层呈现，避免误操作。
- **更适合长期使用**: 强调稳定、可迁移、可验证的产品能力，而不是把内部开发记录直接暴露给普通用户。
