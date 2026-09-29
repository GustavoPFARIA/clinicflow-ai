# ClinicFlow AI

[![CI](https://github.com/GustavoPFARIA/clinicflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/GustavoPFARIA/clinicflow-ai/actions)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![Claude](https://img.shields.io/badge/LLM-Claude%20tool%20use-d97757)
![pgvector](https://img.shields.io/badge/RAG-pgvector-336791)
![Stripe](https://img.shields.io/badge/payments-Stripe-635bff)
![n8n](https://img.shields.io/badge/automation-n8n-ea4b71)
![MCP](https://img.shields.io/badge/MCP-server-000000)
![Evals](https://img.shields.io/badge/agent%20evals-34%2F34-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**ClinicFlow AI is a WhatsApp AI agent for healthcare clinics.** Patients write in natural language. The agent books, reschedules and cancels appointments, collects payments through Stripe, answers questions from the clinic's knowledge base with cited sources, delivers lab results from the EHR/LIS, and hands off to a human when needed. Every action lands on a CRM timeline, and n8n runs the reminders and follow-ups.

> It is an open-source reference implementation of the AI patient-engagement platform I built and ran in production at a healthcare clinic in Brazil, where it cut front-desk workload by up to 70% and booking time by 60%. It is rebuilt from scratch with synthetic data. No proprietary code or patient information is included.

![ClinicFlow AI demo: RAG answer, booking, Stripe payment, CRM update and emergency guardrail](docs/demo.gif)

<sub>RAG answer with citation → multi-step booking → Stripe payment → signed webhook confirms → CRM timeline → emergency guardrail. The right panel is the live agent trace.</sub>

---

## Contents

[Features](#features) · [Tech stack](#tech-stack) · [Prerequisites](#prerequisites) · [Quick start](#quick-start) · [Guided tour](#guided-tour-what-to-try-and-what-happens) · [Using Claude or OpenAI](#using-claude-or-openai-instead-of-demo-mode) · [MCP server](#use-it-from-claude-desktop-mcp) · [Full stack with Docker](#full-stack-with-docker-postgres--pgvector--n8n) · [How the agent works](#how-the-agent-works) · [Configuration](#configuration) · [Project structure](#project-structure) · [Testing and evals](#testing-and-evals) · [Troubleshooting](#troubleshooting) · [Documentation](#documentation)

## Features

- **Tool-using LLM agent, provider-agnostic.** Claude (native tool use) or OpenAI (function calling) behind one interface, with 9 tools: search, list slots, book, reschedule, cancel, pay, results, my appointments, human handoff. It plans multiple steps on its own, such as *find the appointment → cancel it*.
- **MCP server.** The same 9 tools are exposed over the **Model Context Protocol**, so Claude Desktop, Claude Code or any MCP client can use the clinic's scheduling, payments and knowledge base. Like the agent, it is bound to one patient.
- **Hybrid RAG with citations.** Real sentence embeddings (`bge-small-en-v1.5`, running locally) in **pgvector** plus BM25, fused with Reciprocal Rank Fusion. A relevance gate calibrated from measurements declines off-topic questions.
- **Stripe payments.** Checkout Sessions with idempotency keys, and **signed webhooks** (HMAC with replay protection) processed **exactly once**.
- **EHR / LIS integration over FHIR R4.** `Patient`, `Appointment` and `DiagnosticReport` with LOINC codes. When the lab releases a result, the patient is notified on WhatsApp.
- **CRM, single source of truth.** Bookings, payments, messages, reminders and handoffs all go onto one 360° timeline per patient.
- **n8n orchestration.** Importable workflows for 24h reminders, payment follow-up and an event router (result released → notify patient, handoff → Slack).
- **Guardrails outside the model.** Emergencies bypass the LLM (SAMU 192), medical advice is refused, URLs the model invents are stripped, and a step budget fails safe to a human.
- **Privacy by design (LGPD / HIPAA).** CPF, phone, e-mail and card numbers are redacted **before** reaching the LLM and restored in the reply. Tool authorization is enforced in code, never in prompts.
- **Tested against prompt injection.** The eval suite attacks the agent with fake admin modes, cross-patient requests, injected payment links and rule-bypass attempts.
- **LLMOps.** A 34-case eval suite gates CI, the prompt is cached, and every turn is traced with latency and token/cache usage.
- **Runs with a real model for free.** Plug in a free Google Gemini key (or Claude / OpenAI). Without any key, an offline test policy drives the same agent loop, so tests and CI never depend on an external API.
- **Never crashes on a patient.** If the model API is down, rate-limited or misconfigured, the patient gets a polite reply and the conversation is handed to staff.

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API | FastAPI, Pydantic, Uvicorn |
| LLM | Anthropic Claude (tool use, prompt caching), OpenAI (function calling); deterministic scripted policy for offline mode |
| Agent interop | Model Context Protocol (MCP) server |
| RAG | pgvector, fastembed (`bge-small-en-v1.5`, ONNX), BM25, Reciprocal Rank Fusion |
| Data | PostgreSQL + pgvector (SQLite for local demo and tests), SQLAlchemy 2.0 |
| Payments | Stripe Checkout + webhooks |
| Messaging | WhatsApp Cloud API |
| Healthcare | FHIR R4, LOINC |
| Automation | n8n |
| Quality | pytest (55 tests), 34 agent evals incl. prompt injection, Ruff |
| Delivery | Docker, docker-compose, GitHub Actions (SQLite + Postgres jobs, image build), Dependabot |

## Prerequisites

- Windows, macOS or Linux
- **Python 3.12+** (enough for the demo)
- **Docker** (only for the full stack with Postgres and n8n)
- *Optional:* an Anthropic API key, a Stripe test key, a WhatsApp Cloud API app

## Quick start

**1. Clone the repository**

```bash
git clone https://github.com/GustavoPFARIA/clinicflow-ai.git
cd clinicflow-ai
```

**2. Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

**3. Install the dependencies**

```bash
pip install -r requirements-dev.txt
```

**4. Start the app**

```bash
uvicorn app.main:app --reload
```

→ On first start, the app creates a local SQLite database, seeds **synthetic** patients, doctors, time slots and lab results, and indexes the clinic knowledge base. You'll see `Application startup complete`.

**5. Open http://localhost:8000**

→ On the left is a WhatsApp-style chat. On the right are three tabs: **Agent trace** (every tool call the AI makes), **CRM · 360° view** and **FHIR**. The header badge shows the model in use (`live · gemini`), or `offline · no model key` if you haven't added one yet. Interactive API docs are at http://localhost:8000/docs.

## Guided tour: what to try and what happens

Pick a patient in the header. Each one starts in a different situation:

| Patient | Starting situation |
|---|---|
| **Ana Souza** | One lab result ready, one still processing |
| **Bruno Lima** | Has a cardiology booking that is **not paid** |
| **Carla Mendes** | Has a dermatology booking tomorrow, **already paid** |

### 1. Ask a question (RAG)

As **Ana**, send `Do I need to fast before a lipid panel?`

→ The agent calls `search_knowledge_base`, answers *"fast for 8 to 12 hours"* and cites its source: `(source: exams#Blood test fasting)`. The trace shows the retrieved chunks.

### 2. Book an appointment (multi-step tools)

Send `Book a cardiology appointment`

→ `list_available_slots` runs and the agent lists 5 times, each with a slot id.

Send `slot <id>` using one of the listed ids.

→ **Two tools run in one turn:** `book_appointment`, then `create_payment_link`. The agent replies with the booking and a payment link.

### 3. Pay (Stripe, signed webhook)

Click the payment link, then **Pay**.

→ A test-mode checkout sends a **signed** `checkout.session.completed` webhook through the same verification path as production. The page shows **Payment received**. Back in the chat, an automated message confirms the appointment, and the **CRM** tab shows it as `confirmed · paid`.

### 4. Get lab results (EHR/LIS + FHIR)

Send `Are my exam results ready?`

→ The finished result is shown (*Lipid panel: total cholesterol 182 mg/dL…*). The one still processing is **not** revealed.

Now open the **CRM** tab and click **Release result** on the pending exam.

→ This simulates the lab signing the result off. The patient receives *"your result is ready, reply 'results'"*. The notification itself carries no clinical data. The **FHIR** tab shows the `DiagnosticReport` changing from `preliminary` to `final`.

### 5. Reschedule and cancel

Switch to **Bruno** and send `Reschedule my appointment`, then `slot <id>`.

→ The agent finds his appointment, offers new times and moves it. The old slot is freed.

Send `Cancel my appointment`.

→ `get_my_appointments` → `cancel_appointment`. The CRM timeline records it.

### 6. Guardrails

| Send | What happens |
|---|---|
| `I have chest pain` | **The LLM is bypassed.** The reply tells the patient to call SAMU (192), staff are alerted, and the patient is tagged `needs_human`. |
| `Should I take ibuprofen?` | Medical advice is refused, and a consultation is offered instead. |
| `What's the capital of France?` | The relevance gate finds nothing relevant, so the agent declines instead of making something up. |
| `My CPF is 123.456.789-09, what are your hours?` | Answered normally, but **the CPF never reaches the LLM**: it is replaced by `[CPF_1]` before the call. |
| `I want to talk to a human` | `escalate_to_human`: the patient is tagged in the CRM and an event goes to n8n (Slack alert). |

Click **Reset demo** at any time to start over.

> **Without a key:** an offline test policy plays the LLM's role using the exact same tool-use protocol. It understands English phrasings close to the suggestion chips. Add a key (next section) for free conversation in any language.

## Connecting a model (free option included)

The app uses whichever key is in `.env` (`LLM_PROVIDER=auto`):

| Provider | Cost | `.env` |
|---|---|---|
| **Google Gemini** | **Free tier, no card.** Key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | `GEMINI_API_KEY=...` |
| Anthropic Claude | Paid (tool use + prompt caching) | `ANTHROPIC_API_KEY=...` |
| OpenAI | Paid | `OPENAI_API_KEY=...` |
| Any OpenAI-compatible server | Varies (Ollama is free and local) | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` |

```bash
cp .env.example .env     # then paste your key, e.g. GEMINI_API_KEY=AIza...
```

Also set `EMBEDDING_PROVIDER=fastembed` for semantic retrieval. Restart the app, and the header badge shows `live · gemini`.

The free Gemini tier is rate-limited and sometimes overloaded, so calls are spaced automatically and the adapter **falls back to lighter models** (`GEMINI_FALLBACK_MODELS`) instead of failing. Free-tier prompts may be used by Google to improve its products: the data here is synthetic, but don't use the free tier with real patient data (use a paid, zero-retention plan for that).

**Optional, for real payments in Stripe test mode:** set `STRIPE_SECRET_KEY=sk_test_...` and forward webhooks with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Copy the `whsec_...` secret it prints into `STRIPE_WEBHOOK_SECRET`. For WhatsApp setup, see [Integrations → WhatsApp](docs/integrations.md#whatsapp-cloud-api).

## Use it from Claude Desktop (MCP)

The agent's tools are also an MCP server. Run it for a demo patient:

```bash
CLINICFLOW_MCP_PHONE=+5562991110001 python -m app.mcp_server
```

→ Any MCP client can now search the clinic knowledge base, list slots, book, pay and read results as that patient. Setup for Claude Desktop and Claude Code: [docs/mcp.md](docs/mcp.md).

## Full stack with Docker (Postgres + pgvector + n8n)

**1.** Create the environment file:

```bash
cp .env.example .env
```

**2.** Build and start everything:

```bash
docker compose up --build
```

→ This starts **Postgres + pgvector**, the **API** (with the embedding model baked into the image) and **n8n**.

**3.** Import the n8n workflows:

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```

**4.** Open http://localhost:5678, create the n8n owner account, and switch the three **ClinicFlow** workflows to **Active**.

→ Reminders now run every hour, payment follow-ups every 2 hours, and lab-result events are routed through n8n.

| Service | URL |
|---|---|
| API + demo UI | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| n8n | http://localhost:5678 |

## How the agent works

```mermaid
flowchart LR
    P([Patient on WhatsApp]) -->|webhook| API
    subgraph API[FastAPI service]
        direction TB
        G[Guardrails<br/>emergency · scope] --> R[PII redaction]
        R --> A[Agent loop<br/>Claude tool use]
        A <--> T[Patient-scoped tools]
        A --> O[Output checks<br/>link allow-list]
    end
    T --> KB[(pgvector<br/>hybrid RAG)]
    T --> CRM[(CRM timeline<br/>Postgres)]
    T --> S[Stripe Checkout]
    T --> EHR[EHR / LIS<br/>FHIR R4]
    S -->|signed webhook| API
    API -->|domain events| N8N[n8n]
    N8N -->|reminders · nudges · notifications| API
    O -->|reply| P
```

1. A message arrives by WhatsApp webhook. The **message id is deduplicated**, because Meta retries deliveries.
2. The patient is identified by **phone number**. From here on, every tool can only touch that patient's data.
3. **Emergency check**: if it matches, the agent replies with emergency instructions and stops. The LLM is never called.
4. **PII is redacted** from the message and the conversation history.
5. The LLM receives the cached instructions, the patient context, the history and the tool definitions.
6. The LLM calls tools, reads their results, and repeats (up to 6 steps) until it has an answer.
7. **Output check**: any link that did not come from a tool is removed. PII is restored in the reply.
8. The reply is sent, and the turn is logged to the CRM with its full trace.

Deeper dives: [Architecture](docs/architecture.md) · [Agent](docs/agent.md) · [RAG](docs/rag.md) · [Integrations](docs/integrations.md) · [Decision records](docs/adr/)

## Configuration

Everything is optional. A missing key switches that component to its local fallback.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto` (first key found: Anthropic, OpenAI, Gemini; offline policy if none), `anthropic`, `openai`, `gemini` or `mock` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | – / `gemini-3.8-flash` | Free tier at aistudio.google.com/apikey |
| `GEMINI_FALLBACK_MODELS` | `["gemini-3.5-flash-lite","gemini-3.1-flash-lite"]` | Tried when the main model is overloaded or rate-limited |
| `OPENAI_BASE_URL` | – | Any OpenAI-compatible server (Ollama, Groq, OpenRouter) |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Claude model |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-5.5` | OpenAI key and model |
| `CLINICFLOW_MCP_PHONE` | — | Patient the MCP server is bound to |
| `EMBEDDING_PROVIDER` | `hashing` | `fastembed` (real model) or `hashing` (fast, deterministic) |
| `DATABASE_URL` | SQLite file | Use `postgresql+psycopg://...` for pgvector |
| `STRIPE_SECRET_KEY` | — | Stripe test key; unset → local test checkout |
| `STRIPE_WEBHOOK_SECRET` | demo value | Webhook signing secret |
| `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` | — | WhatsApp Cloud API; unset → in-app outbox |
| `AUTOMATION_TOKEN` | dev value | Shared secret between n8n and the API |
| `N8N_EVENT_WEBHOOK_URL` | — | Where domain events are sent |

Full list: [docs/configuration.md](docs/configuration.md)

## Project structure

```
.
|-- app/
|   |-- agent/            # Agent loop, 9 tools, LLM providers (Claude/OpenAI), prompts, guardrails
|   |-- rag/              # Embeddings (bge-small / hashing), hybrid retriever
|   |-- integrations/     # Stripe, WhatsApp Cloud API, n8n domain events
|   |-- ehr/              # FHIR R4 mapping
|   |-- api/              # Chat, CRM, FHIR, webhooks, n8n automation endpoints
|   |-- static/           # Demo UI (WhatsApp simulator, agent trace, CRM) and test checkout
|   |-- mcp_server.py     # MCP server exposing the agent's tools
|   |-- privacy.py        # PII redaction
|   |-- models.py         # Database schema (the CRM)
|   `-- seed.py           # Synthetic demo data
|-- data/knowledge/       # Clinic knowledge base (markdown, one topic per ## section)
|-- evals/                # 34-case agent eval suite (incl. prompt injection) and runner
|-- n8n/workflows/        # Importable n8n workflows
|-- tests/                # 55 unit and integration tests
|-- docs/                 # Full documentation and architecture decision records
|-- Dockerfile
`-- docker-compose.yml
```

## Testing and evals

| Command | What it does |
|---|---|
| `pytest -q` | 64 unit and integration tests |
| `ruff check .` | Lint |
| `python -m evals.run_evals` | Runs the 34 agent scenarios and writes `evals/results.md` |
| `EMBEDDING_PROVIDER=fastembed python -m evals.run_evals` | Same scenarios with real embeddings (what CI runs) |
| `python -m evals.run_evals` (with a key in `.env`) | Scores the real model; the report goes to `evals/results-<model>.md` |

CI runs on every push: lint, tests on **SQLite and Postgres + pgvector**, evals with real embeddings (failing below 95%), and the Docker image build.

| Metric | Score |
|---|---|
| **Overall pass rate** | **34/34 (100%)** |
| Tool-trajectory accuracy | 34/34 (100%) |
| RAG grounding (top-1 citation) | 10/10 (100%) |
| Safety guardrails | 4/4 (100%) |
| Prompt-injection resistance | 4/4 (100%) |
| PII never sent to LLM | 1/1 (100%) |

The table above is the **offline baseline** that CI enforces: it validates the system (tool contracts, multi-step flows, retrieval, guardrails, privacy) without depending on an external API.

### With a real model

`gemini-3.8-flash` (free tier), with automatic fallback to `gemini-3.5-flash-lite` when the main model was rate-limited: **34/34 on the final run**, $0.00. Full report: [evals/results-gemini-3.8-flash.md](evals/results-gemini-3.8-flash.md).

| Metric | Score |
|---|---|
| **Overall pass rate** | **34/34 (100%)** |
| Tool-trajectory accuracy | 34/34 (100%) |
| RAG grounding (top-1 citation) | 10/10 (100%) |
| Safety guardrails | 4/4 (100%) |
| Prompt-injection resistance | 4/4 (100%) |
| PII never sent to LLM | 1/1 (100%) |

Real models are not deterministic, so here is the honest picture. The first run scored **16/34**, and the fixes went in step by step: 16 → 19 → 30 → 33 → 32 → **34**. In the last runs, tool use, grounding, safety, PII and injection resistance stayed at 100%. The occasional miss was reply quality from the free *lite* fallback model, such as a malformed message or a reply in the wrong language.

**What the real model exposed:**
1. **It answered English messages in Portuguese**, inferring the language from the clinic's location and the patient's name. A prompt rule alone wasn't reliable, so the language of each message is now **detected in code** and stated to the model.
2. **It answered off-topic trivia** ("Paris"). The scope rule is now explicit.
3. **Evals that matched one model's wording were brittle.** Checks now require the right tools in order, forbid unrequested *successful* state changes (a cross-patient cancel that the tool layer blocks changed nothing), and verify facts or intent (for example "says it's paid **and** sends no checkout link") instead of exact sentences.
4. **A model outage returned HTTP 500 in the chat.** Now the patient gets a polite reply and the conversation is handed to staff.

The suite also caught two real bugs during development: a CPF in the query skewed retrieval, and an off-topic question was "grounded" through one shared word. The suite also caught two real bugs during development: a CPF in the query skewed retrieval, and an off-topic question was "grounded" through one shared word. Details: [docs/evaluation.md](docs/evaluation.md).

## Troubleshooting

**The assistant doesn't understand my message.** Without a model key, the offline policy only recognises phrasings close to the suggestion chips. Add a free Gemini key (see above).

**"Slot is not available".** Use an id from the most recent list. Past and taken slots are rejected.

**Old or odd demo data.** Click **Reset demo**. Slots are generated relative to today's date.

**Stripe webhook returns 400.** `STRIPE_WEBHOOK_SECRET` must be the secret printed by `stripe listen` for the current session.

**First request is slow with `fastembed`.** The model (~130 MB) downloads once and is then cached. The Docker image already includes it.

More: [docs/troubleshooting.md](docs/troubleshooting.md)

## Documentation

| Guide | |
|---|---|
| [Getting started](docs/getting-started.md) | Setup, demo patients, running tests against Postgres |
| [Architecture](docs/architecture.md) | Components, request lifecycle, data model |
| [Agent](docs/agent.md) | Loop, tools, LLM providers, prompt caching, guardrails |
| [MCP server](docs/mcp.md) | Use the tools from Claude Desktop, Claude Code or any MCP client |
| [RAG](docs/rag.md) | Chunking, embeddings, hybrid ranking, relevance gate |
| [Integrations](docs/integrations.md) | Stripe, WhatsApp, EHR/LIS over FHIR, CRM |
| [n8n workflows](docs/n8n.md) | Workflows, domain events, authentication |
| [API reference](docs/api-reference.md) | Every endpoint with examples |
| [Evaluation](docs/evaluation.md) | Metrics, coverage, adding cases |
| [Security & privacy](docs/security-and-privacy.md) | Threat model, PII handling, LGPD/HIPAA |
| [Deployment](docs/deployment.md) | Topology, going-live checklist |
| [Decision records](docs/adr/) | Why the system is built this way |

## Important notes

- **Synthetic data only.** Never put real patient data in this demo. Going to production with real data requires an LGPD/HIPAA assessment and the [hardening checklist](docs/security-and-privacy.md#production-hardening-checklist).
- **The agent does not give medical advice.** It schedules, informs and hands off. Clinical questions go to the doctors.
- **Demo endpoints** (`/api/demo/reset`, `/demo/checkout/*`) exist for demonstration only. Remove or protect them in production.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), and report vulnerabilities privately as described in [SECURITY.md](SECURITY.md). Changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © Gustavo do Prado Faria

---

Built by **Gustavo do Prado Faria** ([@GustavoPFARIA](https://github.com/GustavoPFARIA)), AI Engineer focused on LLM agents, automation and integrations.
