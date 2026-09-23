"""FHIR R4 mapping for the synthetic EHR/LIS. Internal models stay simple; the
integration boundary speaks FHIR so a real EHR (HL7 FHIR API) can be plugged in
without touching the agent."""

from datetime import datetime, timedelta

from app.models import Appointment, ExamResult, Patient

SLOT_MINUTES = 30

APPOINTMENT_STATUS = {
    "scheduled": "booked",
    "confirmed": "booked",
    "completed": "fulfilled",
    "cancelled": "cancelled",
}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def patient_resource(p: Patient) -> dict:
    given, *family = p.full_name.split()
    return {
        "resourceType": "Patient",
        "id": str(p.id),
        "name": [{"use": "official", "given": [given], "family": " ".join(family)}],
        "telecom": [{"system": "phone", "value": p.phone, "use": "mobile"}]
        + ([{"system": "email", "value": p.email}] if p.email else []),
        "birthDate": p.birth_date.isoformat(),
    }


def appointment_resource(a: Appointment) -> dict:
    start = a.slot.starts_at
    return {
        "resourceType": "Appointment",
        "id": str(a.id),
        "status": APPOINTMENT_STATUS[a.status],
        "serviceType": [{"text": a.slot.doctor.specialty}],
        "start": _iso(start),
        "end": _iso(start + timedelta(minutes=SLOT_MINUTES)),
        "participant": [
            {"actor": {"reference": f"Patient/{a.patient_id}"}, "status": "accepted"},
            {"actor": {"display": a.slot.doctor.name}, "status": "accepted"},
        ],
    }


def diagnostic_report_resource(r: ExamResult) -> dict:
    return {
        "resourceType": "DiagnosticReport",
        "id": str(r.id),
        "status": r.status,
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "LAB"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": r.code, "display": r.name}], "text": r.name},
        "subject": {"reference": f"Patient/{r.patient_id}"},
        "effectiveDateTime": _iso(r.collected_at),
        "issued": _iso(r.released_at),
        "conclusion": r.conclusion if r.status == "final" else None,
    }


def bundle(resources: list[dict]) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resources),
        "entry": [{"resource": r} for r in resources],
    }
