"""Domain events fanned out to n8n. Delivery is best-effort: an automation
outage must never break a patient-facing request."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def emit(event_type: str, **payload) -> bool:
    """Returns True when n8n accepted the event, so callers can fall back to
    handling it inline."""
    url = get_settings().n8n_event_webhook_url
    log.info("event %s %s", event_type, payload)
    if not url:
        return False
    try:
        httpx.post(url, json={"type": event_type, "data": payload}, timeout=5).raise_for_status()
        return True
    except httpx.HTTPError:
        log.warning("n8n event delivery failed: %s", event_type)
        return False
