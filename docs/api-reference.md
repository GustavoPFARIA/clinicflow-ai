# API reference

Interactive docs (Swagger UI) are served at **`/docs`** and the OpenAPI schema at **`/openapi.json`**. All examples assume `http://localhost:8000`.

## Agent

### `POST /api/chat`

Runs one agent turn for a patient, the same way an inbound WhatsApp message does.

```bash
curl -X POST localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"phone": "+5562991110002", "message": "Please cancel my appointment"}'
```

```json
{
  "reply": "Done. Your Cardiology appointment on Fri 25 Sep, 08:00 is cancelled.",
  "trace": [
    {"tool": "get_my_appointments", "args": {}, "result": {"appointments": [{"appointment_id": 1, "...": "..."}]}, "is_error": false},
    {"tool": "cancel_appointment", "args": {"appointment_id": 1}, "result": {"status": "cancelled", "refund_initiated": false}, "is_error": false}
  ],
  "guardrail": null,
  "latency_ms": 24,
  "model": "scripted-policy",
  "usage": {"input_tokens": 0, "output_tokens": 0}
}
```

| Status | When |
|---|---|
| `200` | Turn handled |
| `404` | Phone number not registered |
| `422` | Empty message or longer than 2000 characters |

## CRM

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/patients` | `[{id, name, phone, tags}]` |
| `GET` | `/api/patients/{id}/crm` | 360° view: `patient`, `appointments`, `exams`, `timeline` (latest 30), `conversation`, `outbox` |

## FHIR R4

| Method | Path | Returns |
|---|---|---|
| `GET` | `/fhir/Patient/{id}` | `Patient` resource |
| `GET` | `/fhir/Appointment?patient={id}` | `Bundle` of `Appointment` |
| `GET` | `/fhir/DiagnosticReport?patient={id}` | `Bundle` of `DiagnosticReport` (no `conclusion` for preliminary results) |

## Lab system simulation

### `POST /api/lis/results/{id}/release`

Marks a result `final`, logs `exam.released`, emits the event to n8n (or notifies inline). Returns `{"status": "released"}` or `{"status": "already_released"}`.

## Webhooks

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/webhooks/whatsapp` | `hub.verify_token` | Meta verification handshake; echoes `hub.challenge` |
| `POST` | `/webhooks/whatsapp` | Meta payload | Inbound messages; returns per-message `replied` / `duplicate` / `unknown_sender` |
| `POST` | `/webhooks/stripe` | `Stripe-Signature` | Returns `{"event_id", "outcome": "processed" \| "duplicate" \| "ignored"}`; `400` on a bad signature |

## Automations (called by n8n)

All require the header `X-Automation-Token`. A missing header returns `422`, a wrong token `401`.

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/automations/reminders/due?within_hours=24` | Active appointments in the window without a reminder |
| `POST` | `/automations/reminders/{appointment_id}/send` | Sends the reminder; `already_sent` on repeat |
| `GET` | `/automations/payments/pending` | Future `scheduled` appointments with no or pending payment |
| `POST` | `/automations/payments/{appointment_id}/nudge` | Sends the (reused) checkout link |
| `POST` | `/automations/exam-results/{result_id}/notify` | "Result ready" message; `409` if not released |

```bash
curl localhost:8000/automations/payments/pending -H "X-Automation-Token: dev-automation-token"
```

## Operations and demo

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "llm": "...", "demo_mode": true}` |
| `POST` | `/api/demo/reset` | Wipes and re-seeds synthetic data, re-indexes the knowledge base |
| `GET` | `/demo/checkout/{session_id}` | Test-mode checkout page (demo only) |
