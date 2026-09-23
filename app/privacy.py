"""PII redaction applied to *everything* sent to the LLM provider.

Identifiers are swapped for stable placeholders ([CPF_1], [EMAIL_1]...) and
restored in the model's reply, so the model can still refer to them without the
provider ever seeing the raw values (LGPD / HIPAA minimum-necessary principle).
"""

import re
from dataclasses import dataclass, field

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("PHONE", re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")),
]


def strip_pii(text: str) -> str:
    """Remove identifiers entirely (e.g. from search queries, logs)."""
    for _, pattern in PATTERNS:
        text = pattern.sub(" ", text)
    return text


@dataclass
class Redactor:
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original
    _reverse: dict[str, str] = field(default_factory=dict)

    def redact(self, text: str) -> str:
        for label, pattern in PATTERNS:
            text = pattern.sub(lambda m, label=label: self._placeholder(label, m.group(0)), text)
        return text

    def restore(self, text: str) -> str:
        for placeholder, original in self.mapping.items():
            text = text.replace(placeholder, original)
        return text

    def _placeholder(self, label: str, value: str) -> str:
        if value in self._reverse:
            return self._reverse[value]
        count = sum(1 for p in self.mapping if p.startswith(f"[{label}_")) + 1
        placeholder = f"[{label}_{count}]"
        self.mapping[placeholder] = value
        self._reverse[value] = placeholder
        return placeholder
