import json
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crm, seed
from app.agent.agent import Agent
from app.agent.tools import fmt_dt
from app.api import automations
from app.api.webhooks import process_stripe_webhook
from app.config import get_settings
from app.db import get_session
from app.ehr import fhir
from app.integrations import events, payments
from app.models import (
    Appointment,
    ConversationMessage,
    ExamResult,
    OutboundMessage,
    Patient,
    Payment,
    TimelineEvent,
)

router = APIRouter()


# --- chat (same agent as the WhatsApp webhook, JSON in/out for the demo UI) ---


class ChatIn(BaseModel):
    phone: str = Field(examples=["+5562991110001"])
    message: str = Field(min_length=1, max_length=2000)


@router.post("/api/chat", tags=["agent"])
def chat(body: ChatIn, db: Session = Depends(get_session)):
    patient = crm.find_patient_by_phone(db, body.phone)
    if not patient:
        raise HTTPException(404, "unknown phone number")
    result = Agent(db).handle(patient, body.message)
    return asdict(result)


# --- CRM -----------------------------------------------------------------------


@router.get("/api/patients", tags=["crm"])
def list_patients(db: Session = Depends(get_session)):
    return [
        {"id": p.id, "name": p.full_name, "phone": p.phone, "tags": p.tags}
        for p in db.scalars(select(Patient).order_by(Patient.id))
    ]


@router.get("/api/patients/{patient_id}/crm", tags=["crm"])
def patient_360(patient_id: int, db: Session = Depends(get_session)):
    p = db.get(Patient, patient_id) or _404("patient")
    appts = db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.id)).all()
    return {
        "patient": {"id": p.id, "name": p.full_name, "phone": p.phone, "email": p.email, "tags": p.tags},
        "appointments": [
            {
                "id": a.id,
                "specialty": a.slot.doctor.specialty,
                "doctor": a.slot.doctor.name,
                "when": fmt_dt(a.slot.starts_at),
                "status": a.status,
                "payment": a.payment.status if a.payment else None,
                "checkout_url": a.payment.checkout_url if a.payment else None,
            }
            for a in appts
        ],
        "exams": [
            {"id": r.id, "name": r.name, "status": r.status, "delivered": r.delivered_at is not None}
            for r in db.scalars(select(ExamResult).where(ExamResult.patient_id == p.id))
        ],
        "timeline": [
            {"kind": e.kind, "summary": e.summary, "at": e.created_at.isoformat()}
            for e in db.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.patient_id == p.id, TimelineEvent.kind != "conversation.turn")
                .order_by(TimelineEvent.id.desc())
                .limit(30)
            )
        ],
        "conversation": [
            {"role": m.role, "content": m.content, "at": m.created_at.isoformat()}
            for m in db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.patient_id == p.id)
                .order_by(ConversationMessage.id)
            )
        ],
        "outbox": [
            {"id": m.id, "body": m.body, "status": m.provider_status, "at": m.created_at.isoformat()}
            for m in db.scalars(
                select(OutboundMessage).where(OutboundMessage.patient_id == p.id).order_by(OutboundMessage.id)
            )
        ],
    }


# --- FHIR facade over the EHR/LIS ---------------------------------------------


@router.get("/fhir/Patient/{patient_id}", tags=["fhir"])
def fhir_patient(patient_id: int, db: Session = Depends(get_session)):
    return fhir.patient_resource(db.get(Patient, patient_id) or _404("patient"))


@router.get("/fhir/Appointment", tags=["fhir"])
def fhir_appointments(patient: int, db: Session = Depends(get_session)):
    rows = db.scalars(select(Appointment).where(Appointment.patient_id == patient)).all()
    return fhir.bundle([fhir.appointment_resource(a) for a in rows])


@router.get("/fhir/DiagnosticReport", tags=["fhir"])
def fhir_reports(patient: int, db: Session = Depends(get_session)):
    rows = db.scalars(select(ExamResult).where(ExamResult.patient_id == patient)).all()
    return fhir.bundle([fhir.diagnostic_report_resource(r) for r in rows])


# --- simulated lab system (LIS) -----------------------------------------------

DEMO_CONCLUSIONS = {
    "2345-7": "Fasting glucose 92 mg/dL, within the reference range (70-99 mg/dL).",
    "58410-2": "Hemoglobin, white cells and platelets within reference ranges.",
}


@router.post("/api/lis/results/{result_id}/release", tags=["lis"])
def release_result(result_id: int, db: Session = Depends(get_session)):
    """Simulates the lab signing off a result. In production this is an event
    from the LIS; here n8n picks it up and triggers the patient notification."""
    r = db.get(ExamResult, result_id) or _404("exam result")
    if r.status == "final":
        return {"status": "already_released"}
    r.status, r.released_at = "final", datetime.now()
    r.conclusion = r.conclusion or DEMO_CONCLUSIONS.get(r.code, "Within reference ranges.")
    crm.log_event(db, r.patient_id, "exam.released", f"{r.name} released by the lab")
    db.commit()
    if not events.emit("exam.released", result_id=r.id, patient_id=r.patient_id):
        automations.notify_exam_result(r.id, db)  # n8n unavailable: notify inline
    return {"status": "released"}


# --- demo checkout (stands in for Stripe-hosted checkout without keys) ---------


CHECKOUT_TEMPLATE = (Path(__file__).resolve().parent.parent / "static" / "checkout.html").read_text(encoding="utf-8")


@router.get("/demo/checkout/{session_id}", response_class=HTMLResponse, include_in_schema=False)
def demo_checkout_page(session_id: str, db: Session = Depends(get_session)):
    payment = db.scalar(select(Payment).where(Payment.provider_session_id == session_id)) or _404("session")
    appt = payment.appointment
    amount = f"R$ {payment.amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if payment.status == "paid":
        body = f"""<div class="paid"><div class="check">✓</div><h2>Payment received</h2>
<p>{amount} paid. Your appointment is confirmed and a WhatsApp message is on its way.</p></div>
<a class="back" href="/">← Back to the chat</a>"""
    else:
        body = f"""<div class="amount">{amount}</div>
<form method="post" action="/demo/checkout/{escape(session_id)}/pay">
<label for="card">Card information</label>
<input class="field" id="card" value="4242 4242 4242 4242" readonly aria-readonly="true">
<div class="row"><input class="field" value="12 / 34" readonly aria-label="Expiry">
<input class="field" value="123" readonly aria-label="CVC"></div>
<button>Pay {amount}</button></form>"""
    values = {
        "specialty": appt.slot.doctor.specialty,
        "doctor": appt.slot.doctor.name,
        "when": fmt_dt(appt.slot.starts_at),
        "appointment_id": str(appt.id),
    }
    html = CHECKOUT_TEMPLATE.replace("{body}", body)
    for key, value in values.items():
        html = html.replace("{" + key + "}", escape(value))
    return html


@router.post("/demo/checkout/{session_id}/pay", include_in_schema=False)
def demo_checkout_pay(session_id: str, db: Session = Depends(get_session)):
    """Emits a *signed* checkout.session.completed event through the exact same
    verification + idempotency path a real Stripe webhook takes."""
    payment = db.scalar(select(Payment).where(Payment.provider_session_id == session_id)) or _404("session")
    if payment.status != "paid":
        event = payments.build_demo_completed_event(session_id)
        payload = json.dumps(event).encode()
        signature = payments.sign_payload(payload, get_settings().stripe_webhook_secret)
        process_stripe_webhook(db, payload, signature)
    return RedirectResponse(f"/demo/checkout/{session_id}", status_code=303)


@router.post("/api/demo/reset", tags=["demo"])
def demo_reset(db: Session = Depends(get_session)):
    seed.seed(db)
    return {"status": "reset"}


def _404(what: str):
    raise HTTPException(404, f"{what} not found")
