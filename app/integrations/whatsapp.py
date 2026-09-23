"""WhatsApp Cloud API adapter. Without credentials, messages are written to the
outbox table only, which the demo UI renders as the patient's phone."""

import logging

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OutboundMessage, Patient

log = logging.getLogger(__name__)
GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"


def send_text(db: Session, patient: Patient, body: str) -> OutboundMessage:
    settings = get_settings()
    msg = OutboundMessage(patient_id=patient.id, body=body)
    db.add(msg)

    if not (settings.whatsapp_token and settings.whatsapp_phone_number_id):
        msg.provider_status = "demo"
        return msg

    try:
        resp = httpx.post(
            GRAPH_URL.format(phone_id=settings.whatsapp_phone_number_id),
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": patient.phone.lstrip("+"),
                "type": "text",
                "text": {"body": body},
            },
            timeout=10,
        )
        resp.raise_for_status()
        msg.provider_status = "sent"
    except httpx.HTTPError:
        log.exception("WhatsApp send failed for patient %s", patient.id)
        msg.provider_status = "failed"
    return msg


def parse_inbound(payload: dict) -> list[tuple[str, str, str]]:
    """Extract (message_id, from_phone, text) from a Cloud API webhook payload."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []):
                if m.get("type") == "text":
                    out.append((m["id"], m["from"], m["text"]["body"]))
    return out
