# Troubleshooting

## The demo does not understand my message

Demo mode (`LLM_PROVIDER=mock`) uses a scripted policy that recognises English phrasings close to the suggestion chips, such as *book a cardiology appointment*, *slot 12*, *cancel my appointment* or *are my results ready?*. For free-form conversation in any language, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

## `slot N` says the slot is not available

Slot ids come from the latest list the agent showed. Past slots and booked slots are rejected. Ask for the list again (*book a dermatology appointment*) and use one of the ids shown.

## The demo data looks wrong or old

Click **Reset demo**, or run:

```bash
curl -X POST localhost:8000/api/demo/reset
```

Slots are generated relative to the current date, so a database seeded days ago will have few future slots.

## The first request with `EMBEDDING_PROVIDER=fastembed` is slow

The model (~130 MB) downloads on first use. The Docker image pre-downloads it at build time. Locally, it is cached after the first run.

## Stripe webhook returns `400 invalid signature`

- `STRIPE_WEBHOOK_SECRET` must be the secret for **this** endpoint (the Stripe CLI prints a different one each `stripe listen` session).
- Do not let a proxy re-serialise the body: the signature covers the raw bytes.
- The event timestamp must be within 5 minutes. Check the server clock.

## WhatsApp verification fails in Meta

`WHATSAPP_VERIFY_TOKEN` must match exactly what you typed in the Meta dashboard, and the callback URL must be public HTTPS (use `ngrok http 8000` locally).

## Messages show `demo` status and nothing reaches a phone

`WHATSAPP_TOKEN` or `WHATSAPP_PHONE_NUMBER_ID` is not set, so messages only go to the outbox. That is the intended demo behavior.

## `LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY`

Set the key in `.env` and restart. API credits are billed separately from a Claude.ai subscription.

## n8n workflows run but calls fail with `401`

The workflows send `CLINICFLOW_AUTOMATION_TOKEN`; the API expects `AUTOMATION_TOKEN`. Both must hold the same value. `docker-compose.yml` wires them from one variable.

## n8n shows "access to env vars denied"

Set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` on the n8n container (already set in `docker-compose.yml`).

## Exam notification does not arrive after releasing a result

With `N8N_EVENT_WEBHOOK_URL` set, n8n must have the **Event router** workflow active. If n8n rejects the event, the API falls back to notifying inline. Check the API logs for `n8n event delivery failed`.

## Tests fail with a database error on Postgres

Use the `pgvector/pgvector` image (plain `postgres` lacks the `vector` extension), and point `TEST_DATABASE_URL` at an empty database.
