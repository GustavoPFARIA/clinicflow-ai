# Architecture

## Overview

ClinicFlow AI is a single FastAPI service plus two supporting systems: **Postgres/pgvector** (state, CRM and vector index) and **n8n** (time-based and event-driven automation). Every external provider sits behind a small interface with a local fallback, so the whole system also runs offline.

```mermaid
flowchart TB
    subgraph Channels
        WA[WhatsApp Cloud API]
        UI[Demo UI / API clients]
    end
    subgraph API[FastAPI service]
        WH[Webhooks<br/>/webhooks/*]
        CH[Chat API<br/>/api/chat]
        AG[Agent]
        TL[Tools]
        AU[Automation API<br/>/automations/*]
        FH[FHIR facade<br/>/fhir/*]
    end
    subgraph Data[Postgres + pgvector]
        CRM[(Patients, appointments,<br/>payments, timeline)]
        KB[(Knowledge chunks<br/>+ embeddings)]
        LED[(Idempotency ledger)]
    end
    ST[Stripe]
    MCPC[MCP clients<br/>Claude Desktop, IDEs]
    MCPS[MCP server]
    LLM[Claude / OpenAI]
    N8N[n8n]

    WA --> WH --> AG
    UI --> CH --> AG
    AG <--> LLM
    AG --> TL
    TL --> CRM & KB
    TL --> ST
    ST -->|signed events| WH
    WH --> LED
    API -->|domain events| N8N
    N8N -->|scheduled jobs| AU --> CRM
    FH --> CRM
    MCPC --> MCPS --> TL
```

## Components

| Package | Responsibility |
|---|---|
| `app/agent/` | Agent loop, tool registry, LLM providers, system prompt, guardrails |
| `app/rag/` | Embedding providers, markdown chunking, hybrid retriever |
| `app/integrations/` | Stripe (`payments.py`), WhatsApp (`whatsapp.py`), n8n events (`events.py`) |
| `app/ehr/` | FHIR R4 mapping of internal models |
| `app/api/` | HTTP layer: chat/CRM/FHIR/LIS routes, provider webhooks, n8n automation endpoints |
| `app/mcp_server.py` | MCP server exposing the agent's tools to external AI clients |
| `app/privacy.py` | PII detection, redaction and restoration |
| `app/crm.py` | Timeline events, patient lookup by phone |
| `app/models.py` | SQLAlchemy models (the CRM schema) |
| `app/seed.py` | Synthetic demo data |

## Lifecycle of an inbound WhatsApp message

```mermaid
sequenceDiagram
    participant Meta as WhatsApp Cloud API
    participant WH as POST /webhooks/whatsapp
    participant L as Idempotency ledger
    participant A as Agent
    participant G as Guardrails
    participant M as LLM
    participant T as Tools
    Meta->>WH: message (id, from, text)
    WH->>L: insert message id
    alt already processed
        L-->>WH: conflict → reply "duplicate", stop
    end
    WH->>A: handle(patient, text)
    A->>G: emergency check (before any LLM call)
    A->>A: redact PII, load last 10 turns
    loop up to AGENT_MAX_STEPS
        A->>M: system + history + tools
        M-->>A: tool_use blocks or final text
        A->>T: run tool (scoped to this patient)
        T-->>A: result or recoverable error
    end
    A->>G: link allow-list on final reply
    A-->>WH: reply + trace
    WH->>Meta: send reply
```

## Data model

```mermaid
erDiagram
    PATIENT ||--o{ APPOINTMENT : books
    PATIENT ||--o{ EXAM_RESULT : has
    PATIENT ||--o{ TIMELINE_EVENT : "CRM history"
    PATIENT ||--o{ CONVERSATION_MESSAGE : chats
    PATIENT ||--o{ OUTBOUND_MESSAGE : receives
    DOCTOR ||--o{ SLOT : offers
    SLOT ||--o| APPOINTMENT : "reserved by"
    APPOINTMENT ||--o| PAYMENT : "paid via"
    KNOWLEDGE_CHUNK {
        string source
        string heading
        text content
        vector embedding
    }
    PROCESSED_WEBHOOK_EVENT {
        string event_id PK
        string provider
    }
```

**Appointment states:** `scheduled` (booked, unpaid) → `confirmed` (paid) → `completed`, or `cancelled` at any point. A cancelled paid appointment moves its payment to `refund_pending`.

## Design principles

1. **Business rules live in the API; orchestration lives in n8n.** Workflows only decide *when* to call the API. ([ADR-0004](adr/0004-api-owns-rules-n8n-owns-time.md))
2. **Authorization in code, not prompts.** Tools receive a `ToolContext` bound to the sender's phone number. ([ADR-0002](adr/0002-tool-authorization-in-code.md))
3. **Exactly-once side effects.** Provider event ids go through an idempotency ledger; outbound operations are idempotent. ([ADR-0005](adr/0005-idempotency-ledger.md))
4. **Deterministic by default.** A scripted policy and a hashing embedder keep tests and CI reproducible; real providers plug in via configuration. ([ADR-0001](adr/0001-scripted-policy-for-offline-mode.md))
5. **Fail safe to a human.** Step budget exhausted, emergency, or explicit request → escalate with context.
