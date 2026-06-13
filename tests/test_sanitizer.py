from __future__ import annotations

import pytest

from app.services.sanitizer import LLMSanitizer


@pytest.fixture
def sanitizer() -> LLMSanitizer:
    return LLMSanitizer()


def test_sanitizer_normal_text(sanitizer: LLMSanitizer) -> None:
    text = "Transfer to John Doe for lunch expense"
    assert sanitizer.sanitize(text) == text


def test_sanitizer_empty_and_none(sanitizer: LLMSanitizer) -> None:
    assert sanitizer.sanitize("") == ""
    assert sanitizer.sanitize(None) == ""  # type: ignore[arg-type]


def test_sanitizer_credit_card(sanitizer: LLMSanitizer) -> None:
    text = "Paid with card 1234567890123456 at Lulu"
    assert sanitizer.sanitize(text) == "Paid with card [CARD_MASKED] at Lulu"


def test_sanitizer_ssn(sanitizer: LLMSanitizer) -> None:
    text = "Customer SSN is 987-65-4321, verify status"
    assert sanitizer.sanitize(text) == "Customer SSN is [SSN_MASKED], verify status"


def test_sanitizer_iban(sanitizer: LLMSanitizer) -> None:
    # Test lowercase and uppercase IBAN patterns
    text1 = "Send money to AE830280000012345678901 account"
    text2 = "Send money to ae830280000012345678901 account"
    expected = "Send money to [IBAN_MASKED] account"

    assert sanitizer.sanitize(text1) == expected
    assert sanitizer.sanitize(text2) == expected


def test_sanitizer_email(sanitizer: LLMSanitizer) -> None:
    text = "Contact neha.bajaj@example.com for queries"
    assert sanitizer.sanitize(text) == "Contact [EMAIL_MASKED] for queries"


def test_sanitizer_mixed_pii(sanitizer: LLMSanitizer) -> None:
    text = (
        "User neha@example.com has card 1111222233334444 and IBAN AE1234567890123456789"
        "\nSSN: 123-45-6789"
    )
    expected = (
        "User [EMAIL_MASKED] has card [CARD_MASKED] and IBAN [IBAN_MASKED]"
        "\nSSN: [SSN_MASKED]"
    )
    assert sanitizer.sanitize(text) == expected
