from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crm
from app.agent.agent import Agent
from app.agent.tools import fmt_dt
from app.config import get_settings
from app.db import get_session
from app.integrations import payments, whatsapp
from app.models import ProcessedWebhookEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    if mode == "subscribe" and token == get_settings().whatsapp_verify_token:
        return challenge
    raise HTTPException(403, "verification failed")


@router.post("/whatsapp")
async def whatsapp_inbound(request: Request, db: Session = Depends(get_session)):
    results = []
    for message_id, phone, text in whatsapp.parse_inbound(await request.json()):
        # Meta retries deliveries: dedupe on message id so a patient never gets two replies
        try:
            db.add(ProcessedWebhookEvent(event_id=message_id, provider="whatsapp"))
            db.commit()
        except IntegrityError:
            db.rollback()
            results.append({"message_id": message_id, "status": "duplicate"})
            continue

        patient = crm.find_patient_by_phone(db, phone)
        if not patient:
            results.append({"message_id": message_id, "status": "unknown_sender"})
            continue
        result = Agent(db).handle(patient, text)
        whatsapp.send_text(db, patient, result.reply)
        db.commit()
        results.append({"message_id": message_id, "status": "replied", "tools": [t.tool for t in result.trace]})
    return {"results": results}


def process_stripe_webhook(db: Session, payload: bytes, signature: str) -> dict:
    try:
        event = payments.verify_signature(payload, signature, get_settings().stripe_webhook_secret)
    except payments.SignatureError as exc:
        raise HTTPException(400, f"invalid signature: {exc}") from exc

    outcome, payment = payments.handle_event(db, event)
    if outcome == "processed" and payment and payment.status == "paid":
        appt = payment.appointment
        whatsapp.send_text(
            db,
            appt.patient,
            f"Payment received, thank you! Your {appt.slot.doctor.specialty} appointment on "
            f"{fmt_dt(appt.slot.starts_at)} with {appt.slot.doctor.name} is confirmed.",
        )
        db.commit()
    return {"event_id": event["id"], "outcome": outcome}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    db: Session = Depends(get_session),
):
    return process_stripe_webhook(db, await request.body(), stripe_signature)
