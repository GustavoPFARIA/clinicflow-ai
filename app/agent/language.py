"""Tiny deterministic language detector for the reply-language hint.

LLMs sometimes answer in the language they associate with the clinic (Brazil)
or the patient's name instead of the language the patient wrote in. Detecting
it in code and stating it in the per-turn context makes the choice explicit.
Only the two languages the clinic serves are needed; anything unclear returns
None and the model keeps the conversation's language.
"""

import re

from app.rag.embeddings import normalize

PT = {
    "a",
    "o",
    "os",
    "as",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "um",
    "uma",
    "e",
    "que",
    "nao",
    "sim",
    "meu",
    "minha",
    "voce",
    "eu",
    "para",
    "por",
    "com",
    "quero",
    "quando",
    "qual",
    "como",
    "posso",
    "estou",
    "consulta",
    "exame",
    "exames",
    "obrigado",
    "obrigada",
    "ola",
    "oi",
    "bom",
    "dia",
    "tarde",
    "noite",
    "isso",
    "esta",
    "tem",
    "ate",
    "agendar",
    "marcar",
    "cancelar",
    "remarcar",
    "pagar",
    "resultado",
    "resultados",
}
EN = {
    "the",
    "a",
    "an",
    "i",
    "my",
    "me",
    "you",
    "your",
    "is",
    "are",
    "was",
    "be",
    "to",
    "of",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "can",
    "could",
    "would",
    "please",
    "want",
    "need",
    "when",
    "what",
    "which",
    "how",
    "do",
    "does",
    "this",
    "that",
    "it",
    "have",
    "has",
    "been",
    "appointment",
    "book",
    "cancel",
    "results",
    "hi",
    "hello",
    "thanks",
}


def detect_language(text: str) -> str | None:
    words = re.findall(r"[a-z]+", normalize(text))
    pt = sum(w in PT for w in words)
    en = sum(w in EN for w in words)
    if pt == en:
        return None
    return "Portuguese" if pt > en else "English"
