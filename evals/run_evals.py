"""Offline eval suite for the agent.

Every case runs against a freshly seeded database and is scored on:
- tool trajectory: the tools called in the final turn match the expected sequence
- grounding: RAG answers cite the expected knowledge-base section
- response checks: required / forbidden phrases, guardrail triggered
- privacy: listed values never appear in anything sent to the LLM

Usage:
    python -m evals.run_evals                     # scripted policy (deterministic, CI)
    LLM_PROVIDER=anthropic python -m evals.run_evals   # real Claude model
    python -m evals.run_evals --min-pass-rate 0.95     # fail the build below threshold
"""

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(Path(tempfile.mkdtemp()) / 'evals.db').as_posix()}")
os.environ.setdefault("N8N_EVENT_WEBHOOK_URL", "")

from sqlalchemy import select  # noqa: E402

from app import seed  # noqa: E402
from app.agent.agent import Agent  # noqa: E402
from app.agent.llm import get_llm  # noqa: E402
from app.crm import find_patient_by_phone  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Slot  # noqa: E402

PHONES = {"ana": "+5562991110001", "bruno": "+5562991110002", "carla": "+5562991110003"}


class SpyLLM:
    """Wraps the real LLM and records every payload sent to it."""

    def __init__(self, inner):
        self.inner, self.name, self.payloads = inner, inner.name, []

    def complete(self, system, messages, tools):
        self.payloads.append(json.dumps([system, messages], ensure_ascii=False))
        return self.inner.complete(system, messages, tools)


def run_case(case: dict) -> dict:
    with SessionLocal() as db:
        seed.seed(db)
        patient = find_patient_by_phone(db, PHONES[case["patient"]])
        spy = SpyLLM(get_llm())
        agent = Agent(db, llm=spy)
        booked = db.scalar(select(Slot).where(Slot.is_booked.is_(True)))
        vars_ = {"booked_slot": booked.id}

        result = None
        for turn in case["turns"]:
            result = agent.handle(patient, turn.format(**vars_))
            slots = [t.result for t in result.trace if t.tool == "list_available_slots" and not t.is_error]
            if slots and slots[-1]["slots"]:
                vars_["slot0"] = slots[-1]["slots"][0]["slot_id"]

    tools = [t.tool for t in result.trace]
    checks: dict[str, bool] = {"tools": tools == case["expect_tools"]}
    if "expect_citation" in case:
        cites = [r["citation"] for t in result.trace if t.tool == "search_knowledge_base" for r in t.result["results"]]
        checks["grounding"] = bool(cites) and cites[0] == case["expect_citation"]
    reply = result.reply.lower()
    checks["must_contain"] = all(s.lower() in reply for s in case.get("must_contain", []))
    checks["must_not_contain"] = not any(s.lower() in reply for s in case.get("must_not_contain", []))
    if "expect_guardrail" in case:
        checks["guardrail"] = result.guardrail == case["expect_guardrail"]
    if "expect_llm_never_sees" in case:
        sent = "".join(spy.payloads)
        checks["privacy"] = not any(v in sent for v in case["expect_llm_never_sees"])

    return {
        "id": case["id"],
        "category": case["category"],
        "passed": all(checks.values()),
        "checks": checks,
        "tools": tools,
        "reply": result.reply,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
    }


def report(results: list[dict], model: str) -> str:
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)

    def rate(rs, key=None):
        vals = [r["passed"] if key is None else r["checks"][key] for r in rs if key is None or key in r["checks"]]
        return f"{sum(vals)}/{len(vals)} ({100 * sum(vals) / len(vals):.0f}%)" if vals else "-"

    lines = [
        f"# Eval results: `{model}`",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| **Overall pass rate** | **{rate(results)}** |",
        f"| Tool-trajectory accuracy | {rate(results, 'tools')} |",
        f"| RAG grounding (top-1 citation) | {rate(results, 'grounding')} |",
        f"| Safety guardrails | {rate(by_cat['safety'])} |",
        f"| PII never sent to LLM | {rate(results, 'privacy')} |",
        "",
        "| Category | Pass rate |",
        "|---|---|",
        *[f"| {cat} | {rate(rs)} |" for cat, rs in sorted(by_cat.items())],
        "",
        "## Cases",
        "",
        "| Case | Result | Tools called |",
        "|---|---|---|",
        *[
            f"| `{r['id']}` | {'✅' if r['passed'] else '❌ ' + ', '.join(k for k, v in r['checks'].items() if not v)} "
            f"| {' → '.join(r['tools']) or '(none)'} |"
            for r in results
        ],
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    parser.add_argument("--only", help="run a single case id")
    args = parser.parse_args()

    init_db()
    cases = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    results = [run_case(c) for c in cases]
    model = get_llm().name

    md = report(results, model)
    (HERE / "results.md").write_text(md, encoding="utf-8")
    (HERE / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    for r in results:
        if not r["passed"]:
            print(f"FAILED {r['id']}: {r['checks']} tools={r['tools']}\n  reply: {r['reply']}\n")

    pass_rate = sum(r["passed"] for r in results) / len(results)
    return 0 if pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
