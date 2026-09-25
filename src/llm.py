"""Gemini model factory (the only provider — ref-doc.md §3.4).

Returns configured ChatGoogleGenerativeAI instances by role and provides an
async exponential-backoff-with-jitter wrapper for transient 429/5xx errors
(NFR-04). Fails fast with a clear message if the API key is missing, without
ever echoing the key (NFR-01).
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import settings

# Real Gemini request count (every attempt, including ones that fail and
# retry) since the last reset -- used by src.evaluation.harness to report
# how many calls each golden-set case actually took (asked for explicitly
# so a live run's progress/cost is visible while it runs, not just at the
# end). Not used by the graph/CLI itself; a plain module-level counter is
# enough since the harness runs cases sequentially, not concurrently.
_call_count = 0


def reset_call_count() -> None:
    global _call_count
    _call_count = 0


def call_count() -> int:
    return _call_count

_ROLE_MODELS = {
    "default": lambda: settings.gemini_model,
    "fast": lambda: settings.gemini_model_fast,
    "judge": lambda: settings.gemini_judge_model,
}

# Substrings that identify a retryable transient error from the Gemini API.
_TRANSIENT_MARKERS = (
    "429",
    "500",
    "503",
    "resource_exhausted",
    "unavailable",
    "deadline",
    "rate limit",
    "overloaded",
    "timeout",
    "timed out",
)

# Exception type names to treat as transient even when str(exc) is empty --
# a real, observed failure: asyncio/httpx TimeoutError instances frequently
# carry no message at all, so a pure substring check on str(exc) silently
# missed every one of them and let a timeout crash the whole run instead of
# retrying (found live during a 20-case eval run; see harness.py's commit
# history / notes/failures.local.md for the exact incident).
_TRANSIENT_EXCEPTION_TYPES = ("TimeoutError", "ConnectionError", "ConnectTimeout", "ReadTimeout")


def get_llm(
    role: str = "default",
    *,
    temperature: float = 0.0,
    max_output_tokens: int | None = None,
    **kwargs: Any,
) -> ChatGoogleGenerativeAI:
    """Build a Gemini chat model for the given role ('default' | 'fast' | 'judge')."""
    if role not in _ROLE_MODELS:
        raise ValueError(f"unknown role {role!r}; expected one of {sorted(_ROLE_MODELS)}")
    api_key = settings.require_api_key()  # raises clearly if unset; never logs the key
    return ChatGoogleGenerativeAI(
        model=_ROLE_MODELS[role](),
        google_api_key=api_key,
        temperature=temperature,
        timeout=settings.request_timeout_s,
        max_retries=0,  # we manage retries in ainvoke_with_backoff
        max_output_tokens=max_output_tokens,
        **kwargs,
    )


def _is_transient(exc: Exception) -> bool:
    if type(exc).__name__ in _TRANSIENT_EXCEPTION_TYPES:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


async def ainvoke_with_backoff(
    llm: BaseChatModel,
    messages: Any,
    *,
    max_retries: int | None = None,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
) -> Any:
    """Invoke a chat model asynchronously, retrying transient errors with jitter.

    Non-transient errors propagate immediately (e.g. an invalid API key), so real
    configuration problems surface fast rather than being retried in a loop.
    """
    global _call_count
    retries = settings.max_retries if max_retries is None else max_retries
    attempt = 0
    while True:
        try:
            _call_count += 1
            return await llm.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 - re-raised unless transient
            if not _is_transient(exc) or attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt)) * (0.5 + random.random())
            attempt += 1
            await asyncio.sleep(delay)
