"""Deterministic guardrails that run outside the model: they cannot be talked
out of by a prompt."""

import re

from app.rag.embeddings import normalize

EMERGENCY_TERMS = (
    "chest pain",
    "can't breathe",
    "cant breathe",
    "cannot breathe",
    "shortness of breath",
    "unconscious",
    "fainted",
    "stroke",
    "seizure",
    "heavy bleeding",
    "suicid",
    "kill myself",
    "overdose",
    "dor no peito",
    "falta de ar",
    "desmaiou",
)

EMERGENCY_REPLY = (
    "This sounds like a medical emergency. Please call SAMU at 192 or go to the nearest "
    "emergency room right now. I've also alerted our staff."
)

URL_RE = re.compile(r"https?://[^\s)>\]]+")


def is_emergency(text: str) -> bool:
    t = normalize(text)
    return any(term in t for term in EMERGENCY_TERMS)


def enforce_link_allowlist(reply: str, trusted_text: str) -> str:
    """Drop any URL the model produced that did not come from a tool result in
    this turn. Stops hallucinated or injected payment links from reaching a patient."""

    def keep(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,")
        return match.group(0) if url in trusted_text else "[link removed]"

    return URL_RE.sub(keep, reply)
