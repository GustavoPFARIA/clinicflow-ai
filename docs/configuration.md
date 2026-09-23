# Configuration

Settings are read from environment variables or a `.env` file ([`app/config.py`](../app/config.py)). Copy [`.env.example`](../.env.example) to start. **Every external service is optional**: a missing key switches that component to its local fallback.

## Core

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./clinicflow.db` | SQLAlchemy URL. Use `postgresql+psycopg://...` for pgvector |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used to build checkout and redirect URLs |

## LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` (deterministic scripted policy), `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Any Claude model with tool use |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-5.5` | Any OpenAI model with function calling |
| `AGENT_MAX_STEPS` | `6` | LLM calls per turn before escalating to a human |

## RAG

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `hashing` | `fastembed` (bge-small, local) or `hashing` (deterministic) |
| `FASTEMBED_CACHE_PATH` | fastembed default | Where model weights are cached (set in the Dockerfile) |

## Stripe

| Variable | Default | Description |
|---|---|---|
| `STRIPE_SECRET_KEY` | — | Use a `sk_test_...` key. Unset → local test-mode checkout |
| `STRIPE_WEBHOOK_SECRET` | `whsec_demo_secret` | Signing secret for `/webhooks/stripe`. **Change in production** |
| `CONSULTATION_PRICE_CENTS` | `25000` | Consultation price (R$ 250.00) |
| `CURRENCY` | `brl` | ISO currency code |

## WhatsApp

| Variable | Default | Description |
|---|---|---|
| `WHATSAPP_TOKEN` | — | Cloud API access token. Unset → messages only go to the outbox |
| `WHATSAPP_PHONE_NUMBER_ID` | — | Sender phone number id |
| `WHATSAPP_VERIFY_TOKEN` | `clinicflow-verify` | Must match the token configured in Meta |

## Automations

| Variable | Default | Description |
|---|---|---|
| `AUTOMATION_TOKEN` | `dev-automation-token` | Shared secret for `/automations/*`. **Change in production** |
| `N8N_EVENT_WEBHOOK_URL` | — | Where domain events are posted. Unset → events are only logged |

## n8n container (docker-compose)

| Variable | Description |
|---|---|
| `CLINICFLOW_API_URL` | Base URL the workflows call (`http://api:8000`) |
| `CLINICFLOW_AUTOMATION_TOKEN` | Mirrors `AUTOMATION_TOKEN` |
| `SLACK_WEBHOOK_URL` | Incoming webhook for handoff alerts (optional) |

## MCP server

| Variable | Description |
|---|---|
| `CLINICFLOW_MCP_PHONE` | Phone number of the patient the MCP server acts for (required) |

## Tests

| Variable | Description |
|---|---|
| `TEST_DATABASE_URL` | Run the test suite against this database instead of a temporary SQLite file |
