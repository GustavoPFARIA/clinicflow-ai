import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["N8N_EVENT_WEBHOOK_URL"] = ""
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("WHATSAPP_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.crm import find_patient_by_phone  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402

init_db()

ANA, BRUNO, CARLA = "+5562991110001", "+5562991110002", "+5562991110003"


@pytest.fixture
def db():
    session = SessionLocal()
    seed.seed(session)
    yield session
    session.close()


@pytest.fixture
def client(db):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def ana(db):
    return find_patient_by_phone(db, ANA)
