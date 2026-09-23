# Security & privacy

> This is a reference implementation using synthetic data. Deploying it with real patient data requires a formal LGPD/HIPAA assessment, a data processing agreement with every provider (LLM, WhatsApp, hosting), and the production hardening in [Deployment](deployment.md).

## Threat model

| Threat | Mitigation | Where |
|---|---|---|
| Model reads or changes another patient's data (prompt injection, confusion) | Tools are bound to the sender's `patient_id`; the model never chooses the patient | `app/agent/tools.py` |
| Hallucinated or injected payment links | Output URLs must come from a tool result in the same turn | `guardrails.enforce_link_allowlist` |
| Personal identifiers sent to the LLM provider | Redaction before every call, restoration after | `app/privacy.py` |
| Forged or replayed payment events | HMAC-SHA256 signature, constant-time compare, 300 s tolerance | `payments.verify_signature` |
| Duplicate side effects from provider retries | Idempotency ledger on event and message ids | `processed_webhook_events` |
| Clinical data exposed in push notifications | Notifications say "ready" only; content is shown inside the verified conversation | `automations.notify_exam_result` |
| Unreleased results leaking | Preliminary reports have no `conclusion`, even via FHIR | `fhir.diagnostic_report_resource` |
| Unauthenticated automation calls | Shared token, constant-time compare | `automations.require_token` |
| Medical harm from model output | Emergency short-circuit, refusal rules, human escalation | `guardrails`, system prompt |
| Runaway agent loops (cost, latency) | Step budget, then escalation | `Agent._loop` |

## PII redaction

Before any content is sent to the LLM, `Redactor` replaces:

| Type | Example | Placeholder |
|---|---|---|
| E-mail | `ana@clinic.com` | `[EMAIL_1]` |
| Card number | `4242 4242 4242 4242` | `[CARD_1]` |
| CPF | `123.456.789-09` | `[CPF_1]` |
| Phone | `(62) 99111-0001` | `[PHONE_1]` |

Placeholders are stable within a turn, so the model can refer to "[CPF_1]" consistently. Tool arguments are restored before execution, and the final reply is restored before sending. Search queries have identifiers stripped entirely (`strip_pii`), since they add no retrieval signal.

This is verified by a test and by the privacy eval case, which spies on every payload sent to the model.

## LGPD / HIPAA mapping

| Principle | Implementation |
|---|---|
| Minimum necessary (HIPAA) / necessity (LGPD Art. 6 III) | Only the first name and redacted text reach the LLM; the system prompt carries no record data |
| Security (LGPD Art. 46) | Signed webhooks, token-protected automations, non-root container |
| Purpose limitation | Tools expose only scheduling, payment and released-result data |
| Transparency and access | Patient timeline records every action taken on their behalf |

## Production hardening checklist

- [ ] Rotate `STRIPE_WEBHOOK_SECRET`, `AUTOMATION_TOKEN` and `WHATSAPP_VERIFY_TOKEN`; keep them in a secrets manager
- [ ] Use an LLM provider configuration with zero data retention, under a signed BAA/DPA
- [ ] Verify the Meta `X-Hub-Signature-256` header on WhatsApp webhooks
- [ ] Encrypt the database at rest; restrict network access to Postgres and n8n
- [ ] Put the API behind TLS and a rate limiter
- [ ] Add patient identity verification (for example date of birth) before showing results
- [ ] Define retention periods for conversations and outbound messages

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
