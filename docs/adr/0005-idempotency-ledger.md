# 0005. A database idempotency ledger for all provider events

**Status:** Accepted

## Context

Stripe and Meta both deliver webhooks **at least once**, and retries can arrive concurrently at different API replicas. Processing a `checkout.session.completed` twice would send two confirmations; processing a WhatsApp message twice would make the agent answer twice.

## Decision

Before handling an event, insert its provider id into `processed_webhook_events` (primary key `event_id`). A unique-key violation means "already processed": return `duplicate` and do nothing. Outbound operations are idempotent on their own as well: Stripe Checkout creation uses `idempotency_key=checkout-appointment-{id}`, and reminders check `reminder_sent_at`.

## Consequences

- Exactly-once side effects across replicas, backed by the database's uniqueness guarantee rather than in-memory state. Tested by replaying the same signed event three times.
- The ledger grows with traffic; production should prune rows older than the providers' retry windows (days, not months).
- **Stripe:** the ledger insert and the payment update commit in one transaction, so if processing fails the insert rolls back too and Stripe's retry is processed again.
- **WhatsApp:** the message id is committed *before* the agent runs. This deliberately trades a possibly unanswered message (visible in the CRM, recoverable by staff) for never answering a patient twice.
