"""Stripe payments: Checkout Sessions for consultations, signed + idempotent
webhook processing.

Signature verification follows Stripe's documented scheme
(`Stripe-Signature: t=<ts>,v1=<hmac_sha256(secret, f"{t}.{payload}")>`) and is
implemented explicitly so the demo checkout can emit real-shaped, signed events.
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crm
from app.config import get_settings
from app.integrations import events
from app.models import Appointment, Payment, ProcessedWebhookEvent

SIGNATURE_TOLERANCE_SECONDS = 300


class SignatureError(Exception):
    pass


def get_or_create_checkout(db: Session, appointment: Appointment) -> Payment:
    """Idempotent: calling twice for the same appointment returns the same link."""
    if appointment.payment:
        return appointment.payment

    settings = get_settings()
    payment = Payment(
        appointment=appointment,
        amount_cents=settings.consultation_price_cents,
        currency=settings.currency,
    )

    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": settings.currency,
                        "unit_amount": settings.consultation_price_cents,
                        "product_data": {
                            "name": f"{appointment.slot.doctor.specialty} consultation",
                        },
                    },
                }
            ],
            metadata={"appointment_id": str(appointment.id)},
            success_url=f"{settings.public_base_url}/?paid=1",
            cancel_url=f"{settings.public_base_url}/?paid=0",
            idempotency_key=f"checkout-appointment-{appointment.id}",
        )
        payment.provider_session_id, payment.checkout_url = session.id, session.url
    else:
        session_id = f"cs_demo_{appointment.id}_{secrets.token_hex(6)}"
        payment.provider_session_id = session_id
        payment.checkout_url = f"{settings.public_base_url}/demo/checkout/{session_id}"

    db.add(payment)
    crm.log_event(
        db,
        appointment.patient_id,
        "payment.link_created",
        f"Payment link sent for appointment #{appointment.id}",
        amount_cents=payment.amount_cents,
    )
    return payment


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_signature(payload: bytes, header: str, secret: str, now: int | None = None) -> dict:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError) as exc:
        raise SignatureError("malformed signature header") from exc

    if abs((now or int(time.time())) - ts) > SIGNATURE_TOLERANCE_SECONDS:
        raise SignatureError("timestamp outside tolerance (possible replay)")

    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    candidates = [v for k, v in (i.split("=", 1) for i in header.split(",")) if k == "v1"]
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise SignatureError("signature mismatch")
    return json.loads(payload)


def handle_event(db: Session, event: dict) -> tuple[str, Payment | None]:
    """Process a verified Stripe event exactly once. Returns (outcome, payment)."""
    try:
        db.add(ProcessedWebhookEvent(event_id=event["id"], provider="stripe"))
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate", None

    obj = event["data"]["object"]
    outcome, payment = "ignored", None

    if event["type"] == "checkout.session.completed" and obj.get("payment_status") == "paid":
        payment = db.query(Payment).filter_by(provider_session_id=obj["id"]).one_or_none()
        if payment and payment.status != "paid":
            payment.status, payment.paid_at = "paid", datetime.now()
            appt = payment.appointment
            appt.status = "confirmed"
            crm.log_event(
                db,
                appt.patient_id,
                "payment.succeeded",
                f"Paid {payment.amount_cents / 100:.2f} {payment.currency.upper()} - appointment #{appt.id} confirmed",
                stripe_session=obj["id"],
            )
            events.emit("payment.succeeded", appointment_id=appt.id, patient_id=appt.patient_id)
            outcome = "processed"

    elif event["type"] == "charge.refunded":
        session_id = obj.get("metadata", {}).get("checkout_session_id")
        payment = db.query(Payment).filter_by(provider_session_id=session_id).one_or_none()
        if payment:
            payment.status = "refunded"
            crm.log_event(db, payment.appointment.patient_id, "payment.refunded", "Payment refunded")
            outcome = "processed"

    db.commit()
    return outcome, payment


def build_demo_completed_event(session_id: str) -> dict:
    return {
        "id": f"evt_demo_{secrets.token_hex(8)}",
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id, "object": "checkout.session", "payment_status": "paid"}},
    }
