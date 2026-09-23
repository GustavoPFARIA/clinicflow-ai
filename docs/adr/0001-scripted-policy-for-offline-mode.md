# 0001. A scripted policy speaks the LLM protocol for offline mode, tests and CI

**Status:** Accepted

## Context

The project must be runnable by anyone in about a minute, including reviewers without API keys, and CI must be deterministic and free. Mocking the LLM at the HTTP level would test little: the interesting behavior is the **agent loop** (multi-step tool calls, recoverable tool errors, guardrails, privacy), not the network call.

## Decision

Implement `ScriptedLLM`, a deterministic policy behind the same `LLM` protocol as `AnthropicLLM`. It returns Anthropic-format `tool_use` blocks, reads `tool_result` blocks, and plans multi-step flows (for example `get_my_appointments` → `cancel_appointment`). `LLM_PROVIDER` selects the implementation.

## Consequences

- The agent loop, tools, guardrails and eval harness run identically offline and online.
- CI evals are reproducible, and a failure means the **system** regressed, not model noise.
- Eval scores in CI do **not** measure model reasoning. This is stated in the README and [evaluation docs](../evaluation.md), and the same suite runs against Claude with one environment variable.
- The scripted policy only understands English phrasings close to the demo suggestions. The UI surfaces suggestion chips to keep the demo usable.
