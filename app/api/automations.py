"""Endpoints orchestrated by n8n. The API owns the business rules; n8n owns
scheduling, retries and fan-out. Protected by a shared automation token."""

import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crm
from app.agent.tools import fmt_dt
from app.config import get_settings
from app.db import get_session
from app.integrations import payments, whatsapp
from app.models import Appointment, ExamResult, Payment, Slot


def require_token(x_automation_token: str = Header()) -> None:
    if not hmac.compare_digest(x_automation_token, get_settings().automation_token):
        raise HTTPException(401, "invalid automation token")


router = APIRouter(prefix="/automations", tags=["automations"], dependencies=[Depends(require_token)])


@router.get("/reminders/due")
def reminders_due(within_hours: int = 24, db: Session = Depends(get_session)):
    now = datetime.now()
    rows = db.scalars(
        select(Appointment)
        .join(Slot)
        .where(
            Appointment.status.in_(["scheduled", "confirmed"]),
            Appointment.reminder_sent_at.is_(None),
            Slot.starts_at.between(now, now + timedelta(hours=within_hours)),
        )
    ).all()
    return {"appointments": [{"appointment_id": a.id, "patient_id": a.patient_id} for a in rows]}


@router.post("/reminders/{appointment_id}/send")
def send_reminder(appointment_id: int, db: Session = Depends(get_session)):
    appt = db.get(Appointment, appointment_id) or _404("appointment")
    if appt.reminder_sent_at:  # idempotent: safe for n8n to retry
        return {"status": "already_sent"}
    slot = appt.slot
    body = (
        f"Hi {appt.patient.first_name}! Reminder: {slot.doctor.specialty} with {slot.doctor.name} "
        f"on {fmt_dt(slot.starts_at)}. Reply 'reschedule' or 'cancel' if you can't make it."
    )
    if appt.status == "scheduled":
        body += " Your payment is still pending: reply 'pay' to get the link."
    whatsapp.send_text(db, appt.patient, body)
    appt.reminder_sent_at = datetime.now()
    crm.log_event(db, appt.patient_id, "reminder.sent", f"24h reminder for appointment #{appt.id}")
    db.commit()
    return {"status": "sent"}


@router.get("/payments/pending")
def payments_pending(db: Session = Depends(get_session)):
    rows = db.scalars(
        select(Appointment)
        .outerjoin(Payment)
        .join(Slot)
        .where(
            Appointment.status == "scheduled",
            Slot.starts_at > datetime.now(),
            (Payment.id.is_(None)) | (Payment.status == "pending"),
        )
    ).all()
    return {"appointments": [{"appointment_id": a.id, "patient_id": a.patient_id} for a in rows]}


@router.post("/payments/{appointment_id}/nudge")
def payment_nudge(appointment_id: int, db: Session = Depends(get_session)):
    appt = db.get(Appointment, appointment_id) or _404("appointment")
    payment = payments.get_or_create_checkout(db, appt)
    whatsapp.send_text(
        db,
        appt.patient,
        f"Hi {appt.patient.first_name}, your {appt.slot.doctor.specialty} appointment on "
        f"{fmt_dt(appt.slot.starts_at)} is reserved. Confirm it by paying here: {payment.checkout_url}",
    )
    crm.log_event(db, appt.patient_id, "payment.nudge", f"Payment reminder for appointment #{appt.id}")
    db.commit()
    return {"status": "sent"}


@router.post("/exam-results/{result_id}/notify")
def notify_exam_result(result_id: int, db: Session = Depends(get_session)):
    result = db.get(ExamResult, result_id) or _404("exam result")
    if result.status != "final":
        raise HTTPException(409, "result not released yet")
    # The notification carries no clinical content; the result itself is only
    # shown inside the verified WhatsApp conversation when the patient asks.
    whatsapp.send_text(
        db,
        result.patient,
        f"Hi {result.patient.first_name}, your {result.name} result is ready. Reply 'results' to see it here.",
    )
    crm.log_event(db, result.patient_id, "exam.notified", f"{result.name} ready notification sent")
    db.commit()
    return {"status": "sent"}


def _404(what: str):
    raise HTTPException(404, f"{what} not found")
