from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient, TimelineEvent


def log_event(db: Session, patient_id: int, kind: str, summary: str, **data) -> TimelineEvent:
    event = TimelineEvent(patient_id=patient_id, kind=kind, summary=summary, data=data)
    db.add(event)
    return event


def find_patient_by_phone(db: Session, phone: str) -> Patient | None:
    return db.scalar(select(Patient).where(Patient.phone == normalize_phone(phone)))


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"+{digits}"
