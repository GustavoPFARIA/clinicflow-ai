# ADR-0006: Real models by default, with graceful degradation

**Status:** Accepted

## Context
The project ran on a scripted policy unless a paid key was configured, so the agent's real behavior was never measured, and anyone trying it saw scripted replies. Free model tiers exist but are rate-limited and sometimes overloaded, and a model failure used to surface as an HTTP 500 in the patient's chat.

## Decision
- `LLM_PROVIDER=auto`: use whichever key is configured (Anthropic, OpenAI, Gemini). The scripted policy remains only as the offline test double for tests and CI ([ADR-0001](0001-scripted-policy-for-offline-mode.md)).
- Gemini through its OpenAI-compatible API, so the same adapter serves OpenAI, Gemini and local servers.
- Resilience in the adapter: request spacing, SDK retries, and fallback to lighter models with a cooldown on 503/429.
- Graceful degradation in the agent: if every model fails, roll back the turn, reply politely and hand off to staff.
- Evals graded on behavior (required tools, no unrequested successful writes, facts and intent), so they are valid for any model.

## Consequences
- The real model scores 34/34, and real agent bugs surfaced (reply language, scope).
- Real-model scores vary slightly between runs; the offline baseline remains the CI gate.
- The free tier is only for synthetic data. Production with patient data needs a paid, zero-retention plan.
