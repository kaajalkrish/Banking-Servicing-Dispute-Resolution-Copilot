"""Presidio-based PII detection with banking recognizers (AC-06, NFR-05, §8.1).

Wraps Presidio's ``AnalyzerEngine``/``AnonymizerEngine`` with custom
recognizers for our synthetic data shapes: the account-number format
(``AC`` + 10 digits) and the customer-id format (``C`` + 4 digits). Presidio's
built-in ``CreditCardRecognizer`` already Luhn-validates card numbers, which
covers our synthetic PANs on the reserved 400000 BIN without a custom
recognizer — verified against real generated synthetic data, not assumed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine

ACCOUNT_NUMBER_PATTERN = Pattern(name="synthetic_account_number", regex=r"\bAC\d{10}\b", score=0.9)
CUSTOMER_ID_PATTERN = Pattern(name="synthetic_customer_id", regex=r"\bC\d{4}\b", score=0.6)

_ACCOUNT_NUMBER_RECOGNIZER = PatternRecognizer(
    supported_entity="BANK_ACCOUNT_NUMBER",
    name="SyntheticAccountNumberRecognizer",
    patterns=[ACCOUNT_NUMBER_PATTERN],
)
_CUSTOMER_ID_RECOGNIZER = PatternRecognizer(
    supported_entity="CUSTOMER_ID",
    name="SyntheticCustomerIdRecognizer",
    patterns=[CUSTOMER_ID_PATTERN],
)


@lru_cache(maxsize=1)
def get_analyzer() -> AnalyzerEngine:
    engine = AnalyzerEngine()
    engine.registry.add_recognizer(_ACCOUNT_NUMBER_RECOGNIZER)
    engine.registry.add_recognizer(_CUSTOMER_ID_RECOGNIZER)
    return engine


@lru_cache(maxsize=1)
def get_anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def detect_pii(text: str, *, language: str = "en") -> list[dict[str, Any]]:
    """Return Presidio's detections as plain dicts."""
    results = get_analyzer().analyze(text=text, language=language)
    return [
        {"entity_type": r.entity_type, "start": r.start, "end": r.end, "score": r.score}
        for r in results
    ]


def anonymize_text(text: str, *, language: str = "en") -> str:
    """Detect and mask all PII in text, returning the anonymized string."""
    results = get_analyzer().analyze(text=text, language=language)
    anonymized = get_anonymizer().anonymize(text=text, analyzer_results=results)
    return anonymized.text
