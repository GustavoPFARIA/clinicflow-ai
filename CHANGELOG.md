# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

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
