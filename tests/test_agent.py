import pytest
from sqlalchemy import select

from app.agent.agent import Agent
from app.agent.llm import LLMResponse
from app.agent.tools import ToolContext, run_tool
from app.crm import find_patient_by_phone
from app.models import Appointment, Slot
from tests.conftest import BRUNO


def tools_used(result):
    return [t.tool for t in result.trace]


def test_booking_is_multi_step_and_ends_with_payment_link(db, ana):
    agent = Agent(db)
    listing = agent.handle(ana, "I'd like to book a dermatology appointment")
    assert tools_used(listing) == ["list_available_slots"]
    slot_id = listing.trace[0].result["slots"][0]["slot_id"]

    booked = agent.handle(ana, f"slot {slot_id}")
    assert tools_used(booked) == ["book_appointment", "create_payment_link"]
    assert "/demo/checkout/cs_demo_" in booked.reply
    assert db.get(Slot, slot_id).is_booked


def test_cannot_double_book_a_slot(db, ana):
    taken = db.scalar(select(Slot).where(Slot.is_booked.is_(True)))
    result = Agent(db).handle(ana, f"slot {taken.id}")
    assert result.trace[0].is_error
    assert "not available" in result.reply


def test_tools_cannot_touch_other_patients_appointments(db, ana):
    bruno = find_patient_by_phone(db, BRUNO)
    bruno_appt = db.scalar(select(Appointment).where(Appointment.patient_id == bruno.id))
    out, is_error = run_tool(ToolContext(db, ana), "cancel_appointment", {"appointment_id": bruno_appt.id})
    assert is_error and "not found" in out["error"]
    assert db.get(Appointment, bruno_appt.id).status == "scheduled"


def test_cancel_resolves_the_appointment_first(db):
    bruno = find_patient_by_phone(db, BRUNO)
    result = Agent(db).handle(bruno, "please cancel my appointment")
    assert tools_used(result) == ["get_my_appointments", "cancel_appointment"]
    assert "cancelled" in result.reply


def test_reschedule_across_two_turns(db):
    bruno = find_patient_by_phone(db, BRUNO)
    agent = Agent(db)
    options = agent.handle(bruno, "I need to reschedule")
    assert tools_used(options) == ["get_my_appointments", "list_available_slots"]
    new_slot = options.trace[1].result["slots"][-1]["slot_id"]

    done = agent.handle(bruno, f"slot {new_slot}")
    assert "reschedule_appointment" in tools_used(done)
    appt = db.scalar(select(Appointment).where(Appointment.patient_id == bruno.id))
    assert appt.slot_id == new_slot


def test_rag_answer_is_grounded_and_cited(db, ana):
    result = Agent(db).handle(ana, "Do you accept Unimed?")
    assert tools_used(result) == ["search_knowledge_base"]
    assert "Unimed" in result.reply and "source: clinic#Health insurance" in result.reply


def test_out_of_scope_questions_are_declined(db, ana):
    result = Agent(db).handle(ana, "What is the capital of France?")
    assert "only help with questions about our clinic" in result.reply


def test_emergency_short_circuits_the_llm(db, ana):
    class ExplodingLLM:
        name = "should-not-be-called"

        def complete(self, *a, **k):
            raise AssertionError("LLM called during emergency")

    result = Agent(db, llm=ExplodingLLM()).handle(ana, "my father has chest pain and fainted")
    assert result.guardrail == "emergency"
    assert "192" in result.reply
    assert "needs_human" in ana.tags


def test_medical_advice_is_refused(db, ana):
    result = Agent(db).handle(ana, "Should I take ibuprofen or paracetamol?")
    assert not result.trace
    assert "not able to give medical advice" in result.reply


def test_exam_results_only_final_ones_are_shown(db, ana):
    result = Agent(db).handle(ana, "are my exam results ready?")
    assert "Total cholesterol 182" in result.reply
    assert "still processing" in result.reply


class RecordingLLM:
    """Captures what would be sent to the provider and tries to leak a link."""

    name = "recording"

    def __init__(self):
        self.seen = []

    def complete(self, system, messages, tools):
        self.seen.append(messages)
        return LLMResponse([{"type": "text", "text": "Pay here: https://evil.example/pay and [CPF_1]"}], {})


def test_pii_never_reaches_the_llm_and_is_restored_in_reply(db, ana):
    llm = RecordingLLM()
    result = Agent(db, llm=llm).handle(ana, "my CPF is 123.456.789-09 and email ana@test.com")
    sent = str(llm.seen)
    assert "123.456.789-09" not in sent and "ana@test.com" not in sent
    assert "[CPF_1]" in sent and "[EMAIL_1]" in sent
    assert "123.456.789-09" in result.reply


def test_untrusted_links_are_stripped(db, ana):
    result = Agent(db, llm=RecordingLLM()).handle(ana, "hello")
    assert "evil.example" not in result.reply
    assert "[link removed]" in result.reply


def test_step_limit_fails_safe_to_human(db, ana):
    class LoopingLLM:
        name = "looping"

        def complete(self, *a, **k):
            return LLMResponse([{"type": "tool_use", "id": "t", "name": "get_my_appointments", "input": {}}], {})

    result = Agent(db, llm=LoopingLLM()).handle(ana, "hi")
    assert result.guardrail == "step_limit"
    assert "needs_human" in ana.tags


@pytest.mark.parametrize("text", ["I want to talk to a human", "this is unacceptable, get me a person"])
def test_handoff(db, ana, text):
    result = Agent(db).handle(ana, text)
    assert tools_used(result) == ["escalate_to_human"]
