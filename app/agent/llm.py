"""LLM providers behind one interface, using the Anthropic Messages format
(content blocks with `text`, `tool_use` and `tool_result`).

- `AnthropicLLM` calls Claude with native tool use.
- `ScriptedLLM` is a deterministic policy that speaks the exact same protocol.
  It lets the full agent loop (tool calls, multi-step plans, tool errors) run
  offline in the demo, in CI and in evals, without an API key.
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings
from app.rag.embeddings import normalize, stem, tokenize


@dataclass
class LLMResponse:
    content: list[dict]
    usage: dict

    @property
    def tool_calls(self) -> list[dict]:
        return [b for b in self.content if b["type"] == "tool_use"]

    @property
    def text(self) -> str:
        return "\n".join(b["text"] for b in self.content if b["type"] == "text").strip()


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.name = model

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        resp = self.client.messages.create(
            model=self.model, max_tokens=1024, system=system, messages=messages, tools=tools
        )
        content = [b.model_dump(include={"type", "text", "id", "name", "input"}) for b in resp.content]
        return LLMResponse(
            content=content,
            usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
        )


# --- deterministic scripted policy ------------------------------------------

SPECIALTIES = {
    "Cardiology": ("cardio", "heart", "coracao"),
    "Dermatology": ("derma", "skin", "pele", "acne", "mole"),
    "Gynecology": ("gyn", "gineco", "pap smear"),
    "General Practice": ("general", "gp", "check-up", "checkup", "clinico", "family doctor"),
}
HUMAN = (
    "human",
    "real person",
    "a person",
    "attendant",
    "someone",
    "staff",
    "atendente",
    "humano",
    "complain",
    "terrible",
    "unacceptable",
)
MEDICAL_ADVICE = (
    "should i take",
    "dose",
    "dosage",
    "which medication",
    "what medicine",
    "diagnos",
    "is it serious",
    "what do i have",
    "remedio",
    "prescribe",
)
PREP = ("prepar", "fast", "before", "jejum", "bring")
RESULTS = ("result", "resultado", "laudo")
CANCEL = ("cancel",)
RESCHEDULE = ("reschedul", "move my", "change my appointment", "remarcar", "another time", "another day")
PAY = ("pay", "payment", "pagar", "pagamento", "checkout")
MY_APPTS = ("my appointment", "my booking", "when is my", "upcoming", "minhas consultas", "minha consulta")
BOOK = ("book", "appointment", "schedule", "consultation", "agendar", "marcar", "see a doctor", "consulta")
INFO = (
    "how much",
    "how long",
    "refund",
    "money back",
    "if i cancel",
    "price",
    "cost",
    "accept",
    "insurance",
    "where",
    "address",
    "hours",
    "open",
    "policy",
    "parking",
    "quanto",
    "convenio",
)
GREETING = ("hi", "hello", "hey", "oi", "ola", "good morning", "bom dia")

SLOT_RE = re.compile(r"\b(?:slot|option|horario)\s*#?\s*(\d+)")
APPT_RE = re.compile(r"\bappointment\s*#?\s*(\d+)")


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)


def _specialty(text: str) -> str | None:
    return next((name for name, keys in SPECIALTIES.items() if _has(text, keys)), None)


class ScriptedLLM:
    name = "scripted-policy"

    def __init__(self) -> None:
        self._n = 0

    # protocol helpers
    def _call(self, name: str, **args) -> LLMResponse:
        self._n += 1
        return LLMResponse([{"type": "tool_use", "id": f"toolu_s{self._n}", "name": name, "input": args}], {})

    @staticmethod
    def _say(text: str) -> LLMResponse:
        return LLMResponse([{"type": "text", "text": text}], {})

    @staticmethod
    def _turn(messages: list[dict]) -> tuple[str, list[str], list[tuple[str, dict, dict]]]:
        """Return (current user text, earlier user texts, [(tool, input, result)] this turn)."""
        user_texts = [i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str)]
        start = user_texts[-1]
        calls: dict[str, tuple[str, dict]] = {}
        steps = []
        for m in messages[start + 1 :]:
            for b in m["content"]:
                if b["type"] == "tool_use":
                    calls[b["id"]] = (b["name"], b["input"])
                elif b["type"] == "tool_result":
                    name, args = calls[b["tool_use_id"]]
                    steps.append((name, args, json.loads(b["content"])))
        earlier = [messages[i]["content"] for i in user_texts[:-1]]
        return messages[start]["content"], earlier, steps

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        raw, earlier, steps = self._turn(messages)
        text = normalize(raw)
        done = {name: result for name, _, result in steps}
        last = steps[-1] if steps else None

        if last and "error" in last[2]:
            return self._say(f"Sorry, I couldn't do that: {last[2]['error']}")

        slot = SLOT_RE.search(text) or (re.fullmatch(r"\s*#?(\d+)\s*", text))
        rescheduling = (_has(text, RESCHEDULE) and not _has(text, INFO)) or (
            bool(slot) and earlier and _has(normalize(earlier[-1]), RESCHEDULE)
        )

        if _has(text, HUMAN):
            if "escalate_to_human" not in done:
                return self._call("escalate_to_human", reason=f"Patient asked: {raw[:120]}")
            return self._say(
                f"Of course. I've passed your conversation to our team. {done['escalate_to_human']['eta']}"
            )

        if _has(text, MEDICAL_ADVICE):
            return self._say(
                "I'm not able to give medical advice, diagnoses or medication guidance. "
                "I can book you a consultation with one of our doctors. Which specialty would you like?"
            )

        asking_info = _has(text, INFO)

        if _has(text, RESULTS) and not _has(text, PREP + INFO):
            if "get_exam_results" not in done:
                return self._call("get_exam_results")
            return self._say(self._render_results(done["get_exam_results"]))

        if _has(text, CANCEL) and not asking_info:
            return self._cancel(text, done)

        if rescheduling:
            return self._reschedule(text, slot, done)

        if slot:
            slot_id = int(slot.group(1))
            if "book_appointment" not in done:
                return self._call("book_appointment", slot_id=slot_id)
            booked = done["book_appointment"]
            if "create_payment_link" not in done:
                return self._call("create_payment_link", appointment_id=booked["appointment_id"])
            link = done["create_payment_link"]
            return self._say(
                f"Booked! {booked['specialty']} with {booked['doctor']} on {booked['when']}.\n"
                f"To confirm your spot, please pay {link['amount']} here: {link['checkout_url']}"
            )

        if _has(text, PAY):
            return self._pay(done)

        if _has(text, MY_APPTS):
            if "get_my_appointments" not in done:
                return self._call("get_my_appointments")
            return self._say(self._render_appointments(done["get_my_appointments"]))

        specialty = _specialty(text)
        if (_has(text, BOOK) or specialty) and not _has(text, PREP + INFO):
            if not specialty:
                return self._say(
                    "Happy to help you book! Which specialty? We offer Cardiology, Dermatology, "
                    "General Practice and Gynecology."
                )
            if "list_available_slots" not in done:
                args = {"specialty": specialty}
                if "tomorrow" in text or "amanha" in text:
                    args["day"] = _tomorrow(system)
                return self._call("list_available_slots", **args)
            return self._say(self._render_slots(done["list_available_slots"]))

        if text.strip(" !.?") in GREETING:
            return self._say(
                "Hi! I'm the ClinicFlow assistant. I can book or reschedule appointments, send payment "
                "links, deliver exam results and answer questions about the clinic. How can I help?"
            )

        if "search_knowledge_base" not in done:
            return self._call("search_knowledge_base", query=raw)
        kb = done["search_knowledge_base"]
        if not kb["results"]:
            return self._say(
                "I can only help with questions about our clinic, appointments and exams. "
                "Is there something along those lines I can do for you?"
            )
        top = kb["results"][0]
        return self._say(f"{_extract_answer(top['content'], raw)}\n(source: {top['citation']})")

    # --- multi-step flows ---

    def _cancel(self, text: str, done: dict) -> LLMResponse:
        if "cancel_appointment" in done:
            r = done["cancel_appointment"]
            extra = " Your refund has been initiated." if r["refund_initiated"] else ""
            return self._say(f"Done. Your {r['specialty']} appointment on {r['when']} is cancelled.{extra}")
        explicit = APPT_RE.search(text)
        if explicit:
            return self._call("cancel_appointment", appointment_id=int(explicit.group(1)))
        if "get_my_appointments" not in done:
            return self._call("get_my_appointments")
        appts = done["get_my_appointments"]["appointments"]
        if not appts:
            return self._say("You don't have any upcoming appointments to cancel.")
        if len(appts) > 1:
            return self._say(
                self._render_appointments(done["get_my_appointments"])
                + "\nWhich one should I cancel? Reply e.g. 'cancel appointment 12'."
            )
        return self._call("cancel_appointment", appointment_id=appts[0]["appointment_id"])

    def _reschedule(self, text: str, slot, done: dict) -> LLMResponse:
        if "reschedule_appointment" in done:
            r = done["reschedule_appointment"]
            return self._say(f"All set! Your {r['specialty']} appointment is now on {r['when']} with {r['doctor']}.")
        if "get_my_appointments" not in done:
            return self._call("get_my_appointments")
        appts = done["get_my_appointments"]["appointments"]
        if not appts:
            return self._say("You don't have an upcoming appointment to reschedule. Want to book one?")
        appt = appts[0]
        if slot:
            return self._call(
                "reschedule_appointment", appointment_id=appt["appointment_id"], new_slot_id=int(slot.group(1))
            )
        if "list_available_slots" not in done:
            return self._call("list_available_slots", specialty=appt["specialty"])
        return self._say(
            f"Your current {appt['specialty']} appointment is on {appt['when']}.\n"
            + self._render_slots(done["list_available_slots"], verb="move it")
        )

    def _pay(self, done: dict) -> LLMResponse:
        if "create_payment_link" in done:
            link = done["create_payment_link"]
            if link.get("status") == "already_paid":
                return self._say("Good news: that appointment is already paid.")
            return self._say(f"Here is your secure payment link ({link['amount']}): {link['checkout_url']}")
        if "get_my_appointments" not in done:
            return self._call("get_my_appointments")
        unpaid = [a for a in done["get_my_appointments"]["appointments"] if a["payment"] != "paid"]
        if not unpaid:
            return self._say("You have no appointments waiting for payment.")
        return self._call("create_payment_link", appointment_id=unpaid[0]["appointment_id"])

    # --- renderers ---

    @staticmethod
    def _render_slots(result: dict, verb: str = "book") -> str:
        if not result["slots"]:
            return f"There are no open {result['specialty']} slots for that date. Want me to check other days?"
        lines = [f"• slot {s['slot_id']}: {s['when']} with {s['doctor']}" for s in result["slots"]]
        return (
            f"Next available {result['specialty']} times:\n" + "\n".join(lines) + f"\nReply 'slot <number>' to {verb}."
        )

    @staticmethod
    def _render_appointments(result: dict) -> str:
        if not result["appointments"]:
            return "You have no upcoming appointments."
        return "Your upcoming appointments:\n" + "\n".join(
            f"• #{a['appointment_id']} {a['specialty']}, {a['when']} ({a['status']}, payment: {a['payment']})"
            for a in result["appointments"]
        )

    @staticmethod
    def _render_results(result: dict) -> str:
        if not result["results"]:
            return "I couldn't find any exams on file for you."
        lines = []
        for r in result["results"]:
            if r["status"] == "ready":
                lines.append(f"✅ {r['exam']}: {r['summary']}")
            else:
                lines.append(f"⏳ {r['exam']}: still processing. I'll message you as soon as it's released.")
        return "\n".join(lines) + f"\n{result['disclaimer']}"


def _extract_answer(text: str, query: str, n: int = 2) -> str:
    """Extractive answer: the n sentences sharing the most terms with the query,
    kept in document order."""
    flat = " ".join(line.strip("-• ").strip() for line in text.splitlines() if line.strip())
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    q = {stem(t) for t in tokenize(query)}
    scored = [(len(q & {stem(t) for t in tokenize(s)}), -i) for i, s in enumerate(sentences)]
    keep = sorted(-i for _, i in sorted(scored, reverse=True)[:n])
    return " ".join(sentences[i] for i in keep)


def _tomorrow(system: str) -> str:
    from datetime import date, timedelta

    m = re.search(r"Today is (\d{4}-\d{2}-\d{2})", system)
    today = date.fromisoformat(m.group(1)) if m else date.today()
    return (today + timedelta(days=1)).isoformat()


def get_llm() -> LLM:
    s = get_settings()
    if s.llm_provider == "anthropic":
        if not s.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        return AnthropicLLM(s.anthropic_api_key, s.anthropic_model)
    return ScriptedLLM()
