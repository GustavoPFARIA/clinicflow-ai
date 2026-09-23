# n8n workflows

Source: [`n8n/workflows/`](../n8n/workflows) · API side: [`app/api/automations.py`](../app/api/automations.py)

## Division of responsibility

| n8n decides | The API decides |
|---|---|
| **When** to run (schedules) | **What** is due (queries) |
| Fan-out, retries, alerting | Business rules and message content |
| Routing events to other tools (Slack, Sheets, HubSpot) | Idempotency of each action |

Workflows stay thin and replaceable: swapping n8n for another orchestrator means re-creating three small flows, not re-implementing logic.

## Workflows

### 1. 24h appointment reminders (`appointment-reminders.json`)

`Schedule (hourly)` → `GET /automations/reminders/due?within_hours=24` → `Split Out appointments` → `POST /automations/reminders/{id}/send`

The send endpoint sets `reminder_sent_at` and returns `already_sent` on repeats, so retries are safe. Unpaid bookings get a "reply 'pay'" hint.

### 2. Payment follow-up (`payment-follow-up.json`)

`Schedule (every 2h)` → `GET /automations/payments/pending` → `Split Out` → `POST /automations/payments/{id}/nudge`

Reuses the existing Stripe checkout link (idempotent `get_or_create_checkout`).

### 3. Event router (`event-router.json`)

`Webhook POST /webhook/clinicflow-events` → `Switch on body.type`

| Event | Action |
|---|---|
| `exam.released` | `POST /automations/exam-results/{result_id}/notify` |
| `handoff.requested` | Post to Slack (`SLACK_WEBHOOK_URL`) |
| `payment.succeeded` | Placeholder node: swap in Google Sheets or HubSpot to log revenue |

## Domain events

Emitted by [`events.emit`](../app/integrations/events.py) as `POST {N8N_EVENT_WEBHOOK_URL}` with body `{"type": "...", "data": {...}}`:

| Type | Data |
|---|---|
| `appointment.booked` | `appointment_id`, `patient_id` |
| `appointment.cancelled` | `appointment_id`, `refund` |
| `payment.succeeded` | `appointment_id`, `patient_id` |
| `exam.released` | `result_id`, `patient_id` |
| `handoff.requested` | `patient_id`, `reason` |

Delivery is best-effort with a 5 s timeout. `emit` returns whether n8n accepted the event, so callers can fall back to inline handling.

## Authentication

Every `/automations/*` call must send `X-Automation-Token: <AUTOMATION_TOKEN>` (compared in constant time). In Docker, n8n reads it from `CLINICFLOW_AUTOMATION_TOKEN`; the workflows reference it as `{{ $env.CLINICFLOW_AUTOMATION_TOKEN }}` (this requires `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, already set in `docker-compose.yml`).

## Import and activate

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```

Then open <http://localhost:5678> and toggle each workflow to **Active**. All HTTP nodes retry 3 times with 3 s backoff, and failed executions are saved for inspection.
