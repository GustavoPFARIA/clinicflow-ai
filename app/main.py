import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import select

from app import seed
from app.api import automations, routes, webhooks
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import Patient

STATIC = Path(__file__).parent / "static"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Patient).limit(1)) is None:
            seed.seed(db)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI patient-engagement agent: WhatsApp, RAG, Stripe, CRM, FHIR and n8n automations.",
    lifespan=lifespan,
)
app.include_router(routes.router)
app.include_router(webhooks.router)
app.include_router(automations.router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "llm": settings.llm_provider, "demo_mode": settings.demo_mode}
