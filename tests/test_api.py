from sqlalchemy import select

from app.models import Appointment, ExamResult, OutboundMessage
from tests.conftest import ANA, BRUNO, CARLA

TOKEN = {"X-Automation-Token": "dev-automation-token"}


def wa_payload(msg_id: str, phone: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"id": msg_id, "from": phone.lstrip("+"), "type": "text", "text": {"body": text}}
                            ]
                        }
                    }
                ]
            }
        ],
    }


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_whatsapp_webhook_replies_once_per_message(client, db):
    payload = wa_payload("wamid.1", ANA, "Do you accept Unimed?")
    first = client.post("/webhooks/whatsapp", json=payload).json()["results"][0]
    retry = client.post("/webhooks/whatsapp", json=payload).json()["results"][0]
    assert first["status"] == "replied" and first["tools"] == ["search_knowledge_base"]
    assert retry["status"] == "duplicate"
    assert len(db.scalars(select(OutboundMessage)).all()) == 1


def test_whatsapp_verification_handshake(client):
    ok = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "clinicflow-verify", "hub.challenge": "42"},
    )
    bad = client.get(
        "/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"}
    )
    assert ok.text == "42" and bad.status_code == 403


def test_unknown_sender_is_ignored(client):
    r = client.post("/webhooks/whatsapp", json=wa_payload("wamid.2", "+5511900000000", "hi"))
    assert r.json()["results"][0]["status"] == "unknown_sender"


def test_automations_require_token(client):
    assert client.get("/automations/reminders/due").status_code == 422
    assert client.get("/automations/reminders/due", headers={"X-Automation-Token": "x"}).status_code == 401


def test_reminder_flow_is_idempotent(client):
    due = client.get("/automations/reminders/due", params={"within_hours": 72}, headers=TOKEN).json()
    ids = [a["appointment_id"] for a in due["appointments"]]
    assert ids
    assert client.post(f"/automations/reminders/{ids[0]}/send", headers=TOKEN).json()["status"] == "sent"
    assert client.post(f"/automations/reminders/{ids[0]}/send", headers=TOKEN).json()["status"] == "already_sent"


def test_pending_payment_nudge(client, db):
    pending = client.get("/automations/payments/pending", headers=TOKEN).json()["appointments"]
    assert len(pending) == 1  # Bruno's unpaid cardiology booking
    client.post(f"/automations/payments/{pending[0]['appointment_id']}/nudge", headers=TOKEN)
    msg = db.scalar(select(OutboundMessage).order_by(OutboundMessage.id.desc()))
    assert "/demo/checkout/" in msg.body


def test_lab_release_notifies_patient_without_clinical_content(client, db):
    result = db.scalar(select(ExamResult).where(ExamResult.status == "preliminary", ExamResult.code == "2345-7"))
    assert client.post(f"/api/lis/results/{result.id}/release").json()["status"] == "released"
    msg = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == result.patient_id))
    assert "result is ready" in msg.body
    assert "mg/dL" not in msg.body  # no clinical data in push notifications


def test_fhir_resources(client, db):
    ana_id = client.get("/api/patients").json()[0]["id"]
    patient = client.get(f"/fhir/Patient/{ana_id}").json()
    assert patient["resourceType"] == "Patient" and patient["name"][0]["family"] == "Souza"

    reports = client.get("/fhir/DiagnosticReport", params={"patient": ana_id}).json()
    assert reports["resourceType"] == "Bundle" and reports["total"] == 2
    by_status = {e["resource"]["status"]: e["resource"] for e in reports["entry"]}
    assert by_status["final"]["code"]["coding"][0]["system"] == "http://loinc.org"
    assert "conclusion" not in by_status["preliminary"]  # never leak unreleased results
    assert "null" not in str(reports).lower() and "None" not in str(reports)  # FHIR forbids nulls


def test_chat_endpoint_and_crm_view(client, db):
    r = client.post("/api/chat", json={"phone": CARLA, "message": "when is my appointment?"}).json()
    assert r["trace"][0]["tool"] == "get_my_appointments"
    carla_id = next(p["id"] for p in client.get("/api/patients").json() if p["phone"] == CARLA)
    crm = client.get(f"/api/patients/{carla_id}/crm").json()
    assert crm["appointments"][0]["payment"] == "paid"
    assert [m["role"] for m in crm["conversation"]] == ["user", "assistant"]


def test_unknown_phone_on_chat(client):
    assert client.post("/api/chat", json={"phone": "+1000", "message": "hi"}).status_code == 404


def test_bruno_has_unpaid_booking(db):
    appt = db.scalar(select(Appointment).where(Appointment.status == "scheduled"))
    assert appt.patient.phone == BRUNO and appt.payment is None
