# Contributing to ClinicFlow AI

Thanks for your interest! Issues and pull requests are welcome.

## Development setup

```bash
git clone https://github.com/GustavoPFARIA/clinicflow-ai.git
cd clinicflow-ai
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Before opening a pull request

Run the same checks as CI:

```bash
ruff format .
ruff check .
pytest -q
python -m evals.run_evals --min-pass-rate 0.95
```

## Guidelines

- **One concern per pull request**, with a description of *why* the change is needed.
- **New behavior needs a test.** Agent behavior changes also need an eval case in `evals/dataset.json` (see [Evaluation](docs/evaluation.md#adding-a-case)).
- **Every bug fix adds a regression test or eval case.**
- **No real patient data**, ever: in code, fixtures, issues or screenshots. Use the synthetic patients from `app/seed.py`.
- **Security-sensitive changes** (tools, guardrails, privacy, webhooks) must keep the guarantees in [Security & privacy](docs/security-and-privacy.md). Say explicitly in the PR how they are preserved.
- Significant design changes deserve an [ADR](docs/adr/).

## Commit messages

Use the imperative mood and explain the reason: `Strip PII from retrieval queries` rather than `fix bug`.
