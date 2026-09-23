"""Synthetic demo data. No real patient information is used anywhere."""

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import Base
from app.models import Appointment, Doctor, ExamResult, Patient, Payment, Slot
from app.rag.retriever import index_directory

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"

PATIENTS = [
    ("Ana Souza", "+5562991110001", "ana.souza@example.com", date(1990, 4, 12)),
    ("Bruno Lima", "+5562991110002", "bruno.lima@example.com", date(1978, 11, 3)),
    ("Carla Mendes", "+5562991110003", None, date(1995, 7, 25)),
]
DOCTORS = [
    ("Dr. Rafael Costa", "Cardiology"),
    ("Dr. Helena Prado", "Dermatology"),
    ("Dr. Marcos Vieira", "General Practice"),
    ("Dr. Juliana Rocha", "General Practice"),
    ("Dr. Patrícia Alves", "Gynecology"),
]
HOURS = (8, 9, 10, 14, 15, 16)


def reset(db: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def seed(db: Session, now: datetime | None = None) -> None:
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    reset(db)

    patients = [Patient(full_name=n, phone=p, email=e, birth_date=b, tags=[]) for n, p, e, b in PATIENTS]
    doctors = [Doctor(name=n, specialty=s) for n, s in DOCTORS]
    db.add_all(patients + doctors)
    db.flush()

    slots: dict[tuple[int, int, int], Slot] = {}
    for day_offset in range(0, 8):
        day = (now + timedelta(days=day_offset)).date()
        if day.weekday() == 6:  # closed on Sundays
            continue
        for d in doctors:
            for hour in HOURS:
                starts = datetime.combine(day, datetime.min.time()).replace(hour=hour)
                if starts > now:
                    slot = Slot(doctor_id=d.id, starts_at=starts)
                    slots[(day_offset, d.id, hour)] = slot
                    db.add(slot)
    db.flush()

    ana, bruno, carla = patients
    by_specialty = {d.specialty: d for d in doctors}

    def first_slot(doctor: Doctor, min_offset: int) -> Slot:
        return min(
            (s for (off, did, _), s in slots.items() if did == doctor.id and off >= min_offset and not s.is_booked),
            key=lambda s: s.starts_at,
        )

    # Bruno: cardiology in ~2 days, booked but not paid yet
    s = first_slot(by_specialty["Cardiology"], 2)
    s.is_booked = True
    db.add(Appointment(patient=bruno, slot=s, status="scheduled"))

    # Carla: dermatology tomorrow, already paid (reminder candidate)
    s = first_slot(by_specialty["Dermatology"], 1)
    s.is_booked = True
    appt = Appointment(patient=carla, slot=s, status="confirmed")
    db.add(appt)
    db.flush()
    db.add(
        Payment(
            appointment_id=appt.id,
            amount_cents=25000,
            currency="brl",
            status="paid",
            provider_session_id="cs_demo_seed_paid",
            paid_at=now - timedelta(days=1),
        )
    )

    db.add_all(
        [
            ExamResult(
                patient=ana,
                code="57698-3",
                name="Lipid panel",
                status="final",
                conclusion="Total cholesterol 182 mg/dL and triglycerides 110 mg/dL, within reference ranges.",
                collected_at=now - timedelta(days=3),
                released_at=now - timedelta(hours=5),
            ),
            ExamResult(
                patient=ana,
                code="58410-2",
                name="Complete blood count (CBC)",
                status="preliminary",
                collected_at=now - timedelta(days=1),
            ),
            ExamResult(
                patient=bruno,
                code="2345-7",
                name="Fasting glucose",
                status="preliminary",
                collected_at=now - timedelta(days=1),
            ),
        ]
    )
    db.commit()
    index_directory(db, KNOWLEDGE_DIR)
