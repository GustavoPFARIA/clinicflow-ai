# Architecture decision records

Short records of the decisions that shape ClinicFlow AI: the context, the choice, and what it costs. Format: [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

| # | Decision | Status |
|---|---|---|
| [0001](0001-scripted-policy-for-offline-mode.md) | A scripted policy speaks the LLM protocol for offline mode, tests and CI | Accepted |
| [0002](0002-tool-authorization-in-code.md) | Tool authorization is enforced in code, never in the prompt | Accepted |
| [0003](0003-hybrid-retrieval-with-relevance-gate.md) | Hybrid retrieval (dense + BM25, RRF) with a calibrated relevance gate | Accepted |
| [0004](0004-api-owns-rules-n8n-owns-time.md) | The API owns business rules; n8n owns scheduling and fan-out | Accepted |
| [0005](0005-idempotency-ledger.md) | A database idempotency ledger for all provider events | Accepted |
