# Getting started

## Prerequisites

| Mode | You need |
|---|---|
| Local demo | Python 3.12+ |
| Full stack | Docker with Compose v2 |
| Live providers (optional) | Anthropic API key, Stripe test key, WhatsApp Cloud API app |

## 1. Run locally (demo mode)

```bash
git clone https://github.com/GustavoPFARIA/clinicflow-ai.git
cd clinicflow-ai
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

On first start the app creates a SQLite database (`clinicflow.db`), seeds **synthetic** patients, doctors, slots and lab results, and indexes the knowledge base in `data/knowledge/`.

### Demo patients

| Patient | Phone | State |
|---|---|---|
| Ana Souza | `+5562991110001` | One lab result ready, one still processing |
| Bruno Lima | `+5562991110002` | Cardiology booking, **unpaid**; glucose result processing |
| Carla Mendes | `+5562991110003` | Dermatology booking tomorrow, **paid** |

Use the **Reset demo** button (or `POST /api/demo/reset`) to restore this state at any time.

### A 2-minute tour

1. As **Ana**, click *Book a cardiology appointment*, then type `slot <id>` using an id from the list.
2. Open the payment link and click **Pay**. The chat receives the confirmation and the **CRM** tab shows the appointment as `confirmed / paid`.
3. In the **CRM** tab, click **Release result** on the pending exam. A "result ready" WhatsApp message arrives.
4. Try the guardrails: *I have chest pain*, *Should I take ibuprofen?*, *What's the capital of France?*
5. Open the **Agent trace** tab after each message to see every tool call, its arguments and its result.

> Demo mode uses a deterministic scripted policy instead of an LLM (see [Agent](agent.md#llm-providers)). It understands English phrasings close to the suggestion chips. Set `LLM_PROVIDER=anthropic` for free-form conversation in any language.

## 2. Run the full stack with Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```

| Service | URL | Notes |
|---|---|---|
| API + demo UI | <http://localhost:8000> | Postgres + pgvector, real embeddings (`bge-small-en-v1.5`) |
| n8n | <http://localhost:5678> | Create the owner account, then activate the 3 imported workflows |
| Postgres | `localhost:5432` (internal) | user / password / db: `clinicflow` |

## 3. Tests, lint and evals

```bash
pytest -q                                   # 51 tests, SQLite
ruff check .                                # lint
python -m evals.run_evals                   # 30 agent scenarios, writes evals/results.md
EMBEDDING_PROVIDER=fastembed python -m evals.run_evals   # same, with real embeddings
```

Run the tests against Postgres, as CI does:

```bash
docker run -d --name cf-pg -p 5432:5432 -e POSTGRES_USER=clinicflow \
  -e POSTGRES_PASSWORD=clinicflow -e POSTGRES_DB=clinicflow pgvector/pgvector:pg16
TEST_DATABASE_URL=postgresql+psycopg://clinicflow:clinicflow@localhost:5432/clinicflow pytest -q
```

## 4. Switch to live providers

Edit `.env` (see [Configuration](configuration.md)):

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...        # from `stripe listen` or the dashboard
```

Forward Stripe events locally with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

WhatsApp setup is covered in [Integrations → WhatsApp](integrations.md#whatsapp-cloud-api).
