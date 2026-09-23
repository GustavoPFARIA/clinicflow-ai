# 0004. The API owns business rules; n8n owns scheduling and fan-out

**Status:** Accepted

## Context

n8n is excellent at schedules, retries, and connecting SaaS tools, but logic built inside workflow nodes is hard to test, review and version. Reminders, payment nudges and result notifications all mix both concerns.

## Decision

Workflows only decide **when** and **where to fan out**. They call token-protected `/automations/*` endpoints that decide **what** is due and **what** to send. Every action endpoint is idempotent, so n8n can retry freely. The API emits domain events (`exam.released`, `payment.succeeded`, ...) to a single n8n router webhook.

## Consequences

- All business rules are covered by the pytest suite; workflows stay three to four nodes long.
- The orchestrator is replaceable (Temporal, cron, a queue) without rewriting logic.
- Critical paths cannot depend on n8n being up: `events.emit` reports delivery, and the API falls back to inline handling for exam notifications.
