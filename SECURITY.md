# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report them privately through [GitHub Security Advisories](https://github.com/GustavoPFARIA/clinicflow-ai/security/advisories/new).

Include the affected component, steps to reproduce, and the impact. You will get an acknowledgement within 72 hours.

## Scope

Of particular interest:

- Cross-patient data access through the agent or its tools
- PII reaching the LLM provider despite redaction
- Webhook signature bypass or replay
- Guardrail bypasses leading to medical advice or unsafe output
- Injected or hallucinated links reaching patients

## Important

This repository is a reference implementation with **synthetic data**. It is not certified for production use with real patient data. See [Security & privacy](docs/security-and-privacy.md) for the threat model and the production hardening checklist.
