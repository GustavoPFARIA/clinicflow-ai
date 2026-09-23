import json
import time

import pytest
from sqlalchemy import select

from app.integrations import payments
from app.models import Appointment, OutboundMessage, Payment
from tests.conftest import BRUNO

SECRET = "whsec_demo_secret"


def test_signature_roundtrip():
    payload = b'{"id":"evt_1"}'
    header = payments.sign_payload(payload, SECRET)
    assert payments.verify_signature(payload, header, SECRET) == {"id": "evt_1"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p, h: (p + b" ", h),  # tampered body
        lambda p, h: (p, h.replace("v1=", "v1=0")),  # tampered signature
        lambda p, h: (p, payments.sign_payload(p, "wrong-secret")),
        lambda p, h: (p, payments.sign_payload(p, SECRET, timestamp=int(time.time()) - 3600)),  # replay
        lambda p, h: (p, "garbage"),
    ],
)
def test_signature_rejections(mutate):
    payload = b'{"id":"evt_1"}'
    p, h = mutate(payload, payments.sign_payload(payload, SECRET))
    with pytest.raises(payments.SignatureError):
        payments.verify_signature(p, h, SECRET)


def _bruno_checkout(db):
    appt = db.scalar(select(Appointment).join(Appointment.patient).where(Appointment.status == "scheduled"))
    assert appt.patient.phone == BRUNO
    payment = payments.get_or_create_checkout(db, appt)
    db.commit()
    return appt, payment


def test_checkout_link_is_idempotent(db):
    appt, payment = _bruno_checkout(db)
    assert payments.get_or_create_checkout(db, appt).id == payment.id


def test_webhook_confirms_appointment_exactly_once(client, db):
    appt, payment = _bruno_checkout(db)
    event = payments.build_demo_completed_event(payment.provider_session_id)
    body = json.dumps(event).encode()

    for expected in ("processed", "duplicate", "duplicate"):  # Stripe retries deliveries
        r = client.post(
            "/webhooks/stripe",
            content=body,
            headers={"Stripe-Signature": payments.sign_payload(body, SECRET)},
        )
        assert r.status_code == 200 and r.json()["outcome"] == expected

    db.expire_all()
    assert db.get(Payment, payment.id).status == "paid"
    assert db.get(Appointment, appt.id).status == "confirmed"
    confirmations = db.scalars(select(OutboundMessage).where(OutboundMessage.body.contains("Payment received"))).all()
    assert len(confirmations) == 1


def test_webhook_rejects_bad_signature(client):
    r = client.post("/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "t=1,v1=bad"})
    assert r.status_code == 400
