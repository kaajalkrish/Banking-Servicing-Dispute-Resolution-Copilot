"""Tests for Phoenix instrumentation setup (§7.2, offline-safe).

conftest.py sets PHOENIX_ENABLED=false before any module import (see its
comment for why this must happen at that point, not via monkeypatch), so
init_tracing() here is a fast no-op — these tests verify that no-op path and
the idempotency/reset contract, not the real Phoenix server (that is verified
by a live smoke test, not the default suite, per D-11).
"""

from __future__ import annotations

from src.observability import tracing


def test_tracing_disabled_by_default_in_tests():
    from src.config import settings

    assert settings.phoenix_enabled is False


def test_init_tracing_is_a_noop_when_disabled():
    tracing.reset_for_tests()
    result = tracing.init_tracing("test-project")
    assert result is None
    assert tracing.is_initialized() is True  # still marks itself initialized


def test_init_tracing_is_idempotent():
    tracing.reset_for_tests()
    first = tracing.init_tracing("test-project")
    second = tracing.init_tracing("test-project")
    assert first is second  # second call does no new work, returns the same value


def test_flush_tracing_is_safe_when_never_initialized():
    tracing.reset_for_tests()
    tracing.flush_tracing()  # must not raise
