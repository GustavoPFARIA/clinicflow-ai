# Agent

Source: [`app/agent/`](../app/agent)

## The loop

`Agent.handle(patient, text)` in [`agent.py`](../app/agent/agent.py):

1. Load the last 10 conversation turns for the patient and persist the new message.
2. **Emergency guardrail**: if the message matches an emergency term, reply with SAMU (192) instructions, escalate to staff and **skip the LLM entirely**.
3. **Redact PII** in history and the new message (see [Security & privacy](security-and-privacy.md)).
4. Call the LLM with `system` blocks, messages and tool schemas. Repeat until the model returns text without tool calls, or `AGENT_MAX_STEPS` (default 6) is reached.
5. For each `tool_use` block: restore redacted values in the arguments, run the tool, append a `tool_result` (redacted again) to the conversation.
6. **Output guardrail**: remove any URL that did not appear in a tool result during this turn.
7. Persist the reply, log a `conversation.turn` CRM event, and return an `AgentResult` with the reply, the full tool trace, latency, and token/cache usage.

If the step budget runs out, the agent escalates to a human instead of looping.

## Tools

Defined in [`tools.py`](../app/agent/tools.py). Every tool receives a `ToolContext(db, patient, now)`: the patient is resolved from the sender's phone number and **cannot be changed by the model**.

| Tool | Arguments | Effect |
|---|---|---|
| `search_knowledge_base` | `query` | Hybrid RAG search, returns up to 3 cited chunks |
| `list_available_slots` | `specialty`, `day?` | Up to 5 future open slots |
| `book_appointment` | `slot_id` | Reserves the slot, CRM event, `appointment.booked` event |
| `get_my_appointments` | — | Upcoming active appointments with payment status |
| `reschedule_appointment` | `appointment_id`, `new_slot_id` | Moves the appointment, frees the old slot |
| `cancel_appointment` | `appointment_id` | Cancels; paid → `refund_pending` |
| `create_payment_link` | `appointment_id` | Idempotent Stripe Checkout link |
| `get_exam_results` | — | Final results with summary; preliminary ones only as "processing" |
| `escalate_to_human` | `reason` | Tags `needs_human`, CRM event, `handoff.requested` event |

**Errors are data.** A `ToolError` (slot taken, appointment not found…) is returned to the model as `{"error": ...}` with `is_error: true`, so it can recover (for example by offering other slots) instead of the turn failing.

### Adding a tool

1. Write `def my_tool(ctx: ToolContext, arg: str) -> dict` in `tools.py`. Raise `ToolError` for recoverable problems.
2. Register it in `TOOLS` with a description the model will read, and its JSON-schema properties. Add required args to `REQUIRED`.
3. Add a test in `tests/test_agent.py` and at least one eval case in `evals/dataset.json`.

## LLM providers

[`llm.py`](../app/agent/llm.py) defines one protocol, `complete(system: list[str], messages, tools) -> LLMResponse`, using the Anthropic Messages format.

| `LLM_PROVIDER` | Class | Use |
|---|---|---|
| `anthropic` | `AnthropicLLM` | Claude with native tool use and prompt caching |
| `mock` (default) | `ScriptedLLM` | Deterministic policy for demo, tests and CI |

`ScriptedLLM` is intentionally **not** a toy stub. It emits the same `tool_use` / `tool_result` protocol as Claude, including multi-step plans (for example `get_my_appointments` → `cancel_appointment`), so the agent loop, tools, guardrails and evals are exercised exactly as in production. It does not reason: it maps English phrasings to intents. See [ADR-0001](adr/0001-scripted-policy-for-offline-mode.md).

### Prompt caching

The system prompt is split into two blocks ([`prompts.py`](../app/agent/prompts.py)):

- `SYSTEM_PROMPT`: instructions identical for every patient, marked with `cache_control: ephemeral`. Together with the tool definitions, this is the cached prefix.
- `CONTEXT_PROMPT`: the patient's first name and today's date. Small and uncached.

Keeping per-patient data out of the first block keeps the cache key identical across patients. Cache hits are reported in `AgentResult.usage.cache_read_input_tokens`. A test asserts this structure: [`tests/test_llm_provider.py`](../tests/test_llm_provider.py).

## Guardrails

| Guardrail | Where | Behavior |
|---|---|---|
| Emergency detection | Before the LLM | Fixed SAMU 192 reply, staff escalation, no LLM call |
| Medical advice | System prompt (+ scripted policy) | Refuse diagnoses and dosages, offer a consultation |
| Out of scope | Retriever relevance gate + prompt | "I can only help with questions about our clinic…" |
| Link allow-list | After the LLM | URLs not produced by a tool this turn become `[link removed]` |
| Step budget | Loop | Escalate to a human after `AGENT_MAX_STEPS` |
| Tool authorization | Tools | Every query is filtered by the sender's `patient_id` |
