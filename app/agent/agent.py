"""The agent loop: guardrails -> PII redaction -> LLM <-> tools -> output checks."""

import json
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crm
from app.agent import guardrails
from app.agent.llm import LLM, get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import ToolContext, run_tool, tool_schemas
from app.config import get_settings
from app.models import ConversationMessage, Patient
from app.privacy import Redactor

HISTORY_TURNS = 10


@dataclass
class ToolTrace:
    tool: str
    args: dict
    result: dict
    is_error: bool


@dataclass
class AgentResult:
    reply: str
    trace: list[ToolTrace] = field(default_factory=list)
    guardrail: str | None = None
    latency_ms: int = 0
    model: str = ""
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


def _restore_args(args: dict, redactor: Redactor) -> dict:
    return {k: redactor.restore(v) if isinstance(v, str) else v for k, v in args.items()}


def _history(db: Session, patient: Patient) -> list[dict]:
    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.patient_id == patient.id)
        .order_by(ConversationMessage.id.desc())
        .limit(HISTORY_TURNS * 2)
    ).all()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


class Agent:
    def __init__(self, db: Session, llm: LLM | None = None):
        self.db = db
        self.llm = llm or get_llm()
        self.settings = get_settings()

    def handle(self, patient: Patient, text: str, ctx: ToolContext | None = None) -> AgentResult:
        started = time.perf_counter()
        ctx = ctx or ToolContext(self.db, patient)
        result = AgentResult(reply="", model=self.llm.name)

        history = _history(self.db, patient)
        self.db.add(ConversationMessage(patient_id=patient.id, role="user", content=text))

        if guardrails.is_emergency(text):
            run_tool(ctx, "escalate_to_human", {"reason": "Possible medical emergency"})
            result.reply, result.guardrail = guardrails.EMERGENCY_REPLY, "emergency"
        else:
            self._loop(ctx, history, text, result)

        self.db.add(ConversationMessage(patient_id=patient.id, role="assistant", content=result.reply))
        crm.log_event(
            self.db,
            patient.id,
            "conversation.turn",
            f"Agent handled message ({len(result.trace)} tool calls)",
            tools=[t.tool for t in result.trace],
        )
        self.db.commit()
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    def _loop(self, ctx: ToolContext, history: list[dict], text: str, result: AgentResult) -> None:
        redactor = Redactor()
        system = SYSTEM_PROMPT.format(
            clinic=self.settings.app_name,
            first_name=ctx.patient.first_name,
            today=ctx.now.strftime("%Y-%m-%d (%A)"),
        )
        messages = [{"role": m["role"], "content": redactor.redact(m["content"])} for m in history]
        messages.append({"role": "user", "content": redactor.redact(text)})
        trusted = ""  # raw tool output this turn, for the link allow-list

        for _ in range(self.settings.agent_max_steps):
            resp = self.llm.complete(system, messages, tool_schemas())
            for k, v in resp.usage.items():
                result.usage[k] = result.usage.get(k, 0) + v
            messages.append({"role": "assistant", "content": resp.content})

            if not resp.tool_calls:
                reply = redactor.restore(resp.text)
                result.reply = guardrails.enforce_link_allowlist(reply, trusted)
                return

            tool_results = []
            for call in resp.tool_calls:
                args = _restore_args(call["input"], redactor)
                out, is_error = run_tool(ctx, call["name"], args)
                result.trace.append(ToolTrace(call["name"], args, out, is_error))
                raw = json.dumps(out, ensure_ascii=False, default=str)
                trusted += raw
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": redactor.redact(raw),
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        # step budget exhausted: fail safe to a human rather than loop forever
        run_tool(ctx, "escalate_to_human", {"reason": "Agent step limit reached"})
        result.reply = "Let me get a member of our team to help you with this. They'll reply here shortly."
        result.guardrail = "step_limit"
