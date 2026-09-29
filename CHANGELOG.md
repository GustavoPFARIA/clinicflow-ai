# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-09-29

### Added
- Google Gemini as a model provider through its OpenAI-compatible API, including the free tier; `LLM_PROVIDER=auto` picks whichever key is configured.
- `OPENAI_BASE_URL` for any OpenAI-compatible server (Ollama, Groq, OpenRouter).
- Automatic model fallback with cooldown on 503/429, request spacing for free tiers, SDK timeouts and retries.
- Gemini 3 thought signatures are round-tripped with tool calls (and stripped before calling Claude).

- **Real-model results: 34/34 evals with Gemini** (`evals/results-gemini-3.8-flash.md`).
- Deterministic language detection per message, stated to the model (it had answered English messages in Portuguese).

### Changed
- Stricter scope rule: off-topic questions are declined instead of answered.
- Evals grade behavior: required tools in order, no unrequested successful state changes, facts or intent instead of exact wording.

### Fixed
- A model outage (invalid key, quota, provider down) returned HTTP 500 in the chat. The patient now gets a polite reply and the conversation is handed to staff.
- Real-model eval runs no longer overwrite the offline CI baseline report.

## [1.2.0] - 2026-09-23

### Added
- MCP server exposing the agent's 9 tools to any Model Context Protocol client (Claude Desktop, Claude Code), bound to one patient.
- OpenAI provider (function calling) behind the same `LLM` interface, with a protocol translation test.
- Four prompt-injection eval cases and a cross-patient isolation check in the eval runner.
- Human-readable FHIR view in the demo UI.

### Fixed
- FHIR resources no longer contain `null` elements, which the FHIR JSON spec forbids.

## [1.1.0] - 2026-09-23

### Added
- Real sentence embeddings (`bge-small-en-v1.5` via fastembed, local ONNX) behind the `Embedder` protocol.
- Per-provider relevance gate calibrated from measured similarity distributions.
- Prompt caching: static instructions and tools cached; per-patient context in a separate block.
- CI job running the full test suite on Postgres + pgvector.
- Test-mode checkout page with a paid state.
- Demo GIF, full documentation in `docs/`, architecture decision records, contributing and security guides.

### Changed
- CI evals run with real embeddings.
- Paying an already-paid demo session is a no-op.

## [1.0.0] - 2026-09-23

### Added
- WhatsApp AI agent with 9 patient-scoped tools and a multi-step agent loop (Claude tool use + deterministic offline policy).
- Hybrid RAG (dense + BM25 with Reciprocal Rank Fusion) with citations.
- Stripe Checkout with idempotency keys; signed, replay-protected, exactly-once webhooks.
- FHIR R4 facade (Patient, Appointment, DiagnosticReport) and lab result delivery flow.
- CRM timeline, n8n workflows (reminders, payment follow-up, event router), PII redaction, guardrails.
- 30-case agent eval suite gating CI; Docker and docker-compose setup.
