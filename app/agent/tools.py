"""Tools the agent can call. Each tool is scoped to the patient identified by the
inbound phone number, so the model can never read or mutate another patient's
data, no matter what the prompt says (authorization lives in code, not prompts)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crm
from app.integrations import events, payments
from app.models import Appointment, Doctor, ExamResult, Patient, Slot
from app.rag.retriever import HybridRetriever


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    patient: Patient
    now: datetime = field(default_factory=datetime.now)


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%a %d %b, %H:%M")


def _own_appointment(ctx: ToolContext, appointment_id: int) -> Appointment:
    appt = ctx.db.get(Appointment, appointment_id)
    if not appt or appt.patient_id != ctx.patient.id:
        raise ToolError(f"Appointment {appointment_id} not found for this patient.")
    return appt


def _free_slot(ctx: ToolContext, slot_id: int) -> Slot:
    slot = ctx.db.get(Slot, slot_id)
    if not slot or slot.is_booked or slot.starts_at <= ctx.now:
        raise ToolError(f"Slot {slot_id} is not available. List available slots again.")
    return slot


def _appointment_view(a: Appointment) -> dict:
    return {
        "appointment_id": a.id,
        "specialty": a.slot.doctor.specialty,
        "doctor": a.slot.doctor.name,
        "when": fmt_dt(a.slot.starts_at),
        "status": a.status,
        "payment": a.payment.status if a.payment else "not_started",
    }


# --- tool implementations -------------------------------------------------


def search_knowledge_base(ctx: ToolContext, query: str) -> dict:
    hits = HybridRetriever(ctx.db).search(query, k=3)
    return {
        "results": [{"citation": h.citation, "content": h.content} for h in hits],
        "note": None if hits else "No relevant clinic information found.",
    }


def list_available_slots(ctx: ToolContext, specialty: str, day: str | None = None) -> dict:
    specialties = sorted(set(ctx.db.scalars(select(Doctor.specialty))))
    match = next((s for s in specialties if s.lower() == specialty.strip().lower()), None)
    if not match:
        raise ToolError(f"Unknown specialty '{specialty}'. Available: {', '.join(specialties)}.")

    q = (
        select(Slot)
        .join(Doctor)
        .where(Doctor.specialty == match, Slot.is_booked.is_(False), Slot.starts_at > ctx.now)
        .order_by(Slot.starts_at)
    )
    slots = ctx.db.scalars(q).all()
    if day:
        target = date.fromisoformat(day)
        slots = [s for s in slots if s.starts_at.date() == target]
    return {
        "specialty": match,
        "slots": [{"slot_id": s.id, "doctor": s.doctor.name, "when": fmt_dt(s.starts_at)} for s in slots[:5]],
    }


def book_appointment(ctx: ToolContext, slot_id: int) -> dict:
    slot = _free_slot(ctx, slot_id)
    slot.is_booked = True
    appt = Appointment(patient=ctx.patient, slot=slot)
    ctx.db.add(appt)
    ctx.db.flush()
    crm.log_event(
        ctx.db,
        ctx.patient.id,
        "appointment.booked",
        f"Booked {slot.doctor.specialty} with {slot.doctor.name} on {fmt_dt(slot.starts_at)}",
        appointment_id=appt.id,
        channel="whatsapp_agent",
    )
    events.emit("appointment.booked", appointment_id=appt.id, patient_id=ctx.patient.id)
    return {**_appointment_view(appt), "next_step": "Offer the payment link to confirm the booking."}


def get_my_appointments(ctx: ToolContext) -> dict:
    q = (
        select(Appointment)
        .join(Slot)
        .where(
            Appointment.patient_id == ctx.patient.id,
            Appointment.status.in_(["scheduled", "confirmed"]),
            Slot.starts_at > ctx.now,
        )
        .order_by(Slot.starts_at)
    )
    return {"appointments": [_appointment_view(a) for a in ctx.db.scalars(q)]}


def reschedule_appointment(ctx: ToolContext, appointment_id: int, new_slot_id: int) -> dict:
    appt = _own_appointment(ctx, appointment_id)
    if appt.status not in ("scheduled", "confirmed"):
        raise ToolError("Only active appointments can be rescheduled.")
    new_slot = _free_slot(ctx, new_slot_id)
    old = appt.slot
    old.is_booked, new_slot.is_booked = False, True
    appt.slot = new_slot
    crm.log_event(
        ctx.db,
        ctx.patient.id,
        "appointment.rescheduled",
        f"Moved from {fmt_dt(old.starts_at)} to {fmt_dt(new_slot.starts_at)}",
        appointment_id=appt.id,
    )
    return _appointment_view(appt)


def cancel_appointment(ctx: ToolContext, appointment_id: int) -> dict:
    appt = _own_appointment(ctx, appointment_id)
    if appt.status == "cancelled":
        raise ToolError("Appointment is already cancelled.")
    appt.status, appt.slot.is_booked = "cancelled", False
    refund = appt.payment is not None and appt.payment.status == "paid"
    if refund:
        appt.payment.status = "refund_pending"
    crm.log_event(ctx.db, ctx.patient.id, "appointment.cancelled", f"Cancelled appointment #{appt.id}")
    events.emit("appointment.cancelled", appointment_id=appt.id, refund=refund)
    return {**_appointment_view(appt), "refund_initiated": refund}


def create_payment_link(ctx: ToolContext, appointment_id: int) -> dict:
    appt = _own_appointment(ctx, appointment_id)
    if appt.status == "cancelled":
        raise ToolError("Cannot pay for a cancelled appointment.")
    payment = payments.get_or_create_checkout(ctx.db, appt)
    if payment.status == "paid":
        return {"appointment_id": appt.id, "status": "already_paid"}
    return {
        "appointment_id": appt.id,
        "amount": f"{payment.amount_cents / 100:.2f} {payment.currency.upper()}",
        "checkout_url": payment.checkout_url,
    }


def get_exam_results(ctx: ToolContext) -> dict:
    results = ctx.db.scalars(
        select(ExamResult).where(ExamResult.patient_id == ctx.patient.id).order_by(ExamResult.collected_at)
    ).all()
    out = []
    for r in results:
        if r.status == "final":
            if not r.delivered_at:
                r.delivered_at = ctx.now
                crm.log_event(ctx.db, ctx.patient.id, "exam.delivered", f"{r.name} result delivered via WhatsApp")
            out.append({"exam": r.name, "status": "ready", "summary": r.conclusion})
        else:
            out.append({"exam": r.name, "status": "processing"})
    return {"results": out, "disclaimer": "Results must be interpreted by the requesting physician."}


def escalate_to_human(ctx: ToolContext, reason: str) -> dict:
    if "needs_human" not in ctx.patient.tags:
        ctx.patient.tags = [*ctx.patient.tags, "needs_human"]
    crm.log_event(ctx.db, ctx.patient.id, "handoff.requested", f"Human handoff: {reason}")
    events.emit("handoff.requested", patient_id=ctx.patient.id, reason=reason)
    return {"status": "handed_off", "eta": "A team member will reply within business hours."}


# --- registry / schemas ----------------------------------------------------

_ID = {"type": "integer"}

TOOLS: dict[str, tuple[Callable[..., dict], str, dict]] = {
    "search_knowledge_base": (
        search_knowledge_base,
        "Search the clinic knowledge base (hours, location, insurance, prices, exam preparation, "
        "policies). Use for any factual question about the clinic.",
        {"query": {"type": "string"}},
    ),
    "list_available_slots": (
        list_available_slots,
        "List open appointment slots for a specialty, optionally on a given day (YYYY-MM-DD).",
        {"specialty": {"type": "string"}, "day": {"type": "string"}},
    ),
    "book_appointment": (book_appointment, "Book an open slot for the patient.", {"slot_id": _ID}),
    "get_my_appointments": (get_my_appointments, "List the patient's upcoming appointments.", {}),
    "reschedule_appointment": (
        reschedule_appointment,
        "Move one of the patient's appointments to another open slot.",
        {"appointment_id": _ID, "new_slot_id": _ID},
    ),
    "cancel_appointment": (cancel_appointment, "Cancel one of the patient's appointments.", {"appointment_id": _ID}),
    "create_payment_link": (
        create_payment_link,
        "Create (or reuse) a Stripe payment link for an appointment.",
        {"appointment_id": _ID},
    ),
    "get_exam_results": (get_exam_results, "Get the patient's lab exam results and their status.", {}),
    "escalate_to_human": (
        escalate_to_human,
        "Hand the conversation to the clinic staff. Use when the patient asks for a person, "
        "is upset, or the request is outside what the tools can do.",
        {"reason": {"type": "string"}},
    ),
}

REQUIRED = {
    "search_knowledge_base": ["query"],
    "list_available_slots": ["specialty"],
    "book_appointment": ["slot_id"],
    "reschedule_appointment": ["appointment_id", "new_slot_id"],
    "cancel_appointment": ["appointment_id"],
    "create_payment_link": ["appointment_id"],
    "escalate_to_human": ["reason"],
}


def tool_schemas() -> list[dict]:
    return [
        {
            "name": name,
            "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": REQUIRED.get(name, [])},
        }
        for name, (_, desc, props) in TOOLS.items()
    ]


def run_tool(ctx: ToolContext, name: str, args: dict) -> tuple[dict, bool]:
    """Execute a tool. Returns (result, is_error). Errors are returned to the
    model as data so it can recover (e.g. pick another slot)."""
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}"}, True
    fn = TOOLS[name][0]
    try:
        return fn(ctx, **args), False
    except ToolError as exc:
        return {"error": str(exc)}, True
    except (TypeError, ValueError) as exc:
        return {"error": f"Invalid arguments: {exc}"}, True
