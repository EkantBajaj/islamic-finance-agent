from __future__ import annotations

import re


class LLMSanitizer:
    """Strips PII (credit cards, SSNs, IBANs, emails) from strings to ensure LLM data hygiene."""

    PII_PATTERNS = [
        (re.compile(r"\b\d{16}\b"), "[CARD_MASKED]"),  # Card numbers
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_MASKED]"),  # SSN-like
        (
            re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b", re.IGNORECASE),
            "[IBAN_MASKED]",
        ),  # IBAN
        (re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b"), "[EMAIL_MASKED]"),  # Email addresses
    ]

    def sanitize(self, text: str) -> str:
        """Replace all detected PII in the given text with placeholder tokens."""
        if not text:
            return ""
        for pattern, replacement in self.PII_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
