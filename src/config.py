"""Environment-variable configuration (python-dotenv).

Single source of runtime settings. Secrets come only from the environment / a
local, gitignored ``.env`` file (NFR-01); nothing sensitive is hard-coded.
Gemini is the only model provider (ref-doc.md §3.4).

Import ``settings`` for the loaded singleton. Call ``settings.require_api_key()``
right before the first real Gemini call so offline code (tests, data generation,
the MCP server) can import this module without a key present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root if present. override=False so a real shell
# environment variable always wins over the file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# Sentinel left in .env / .env.example; treated as "no key set".
_PLACEHOLDER_KEYS = {"", "PASTE_YOUR_GEMINI_API_KEY_HERE", "your_key_here"}


def _get(name: str, default: str) -> str:
    val = os.environ.get(name)
    return default if val is None or val == "" else val


def _get_bool(name: str, default: bool) -> bool:
    return _get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable view of the process configuration."""

    # --- Gemini (the only provider) ---
    google_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: _get("GEMINI_MODEL", "gemini-3.5-flash"))
    gemini_model_fast: str = field(
        default_factory=lambda: _get("GEMINI_MODEL_FAST", "gemini-3.5-flash-lite")
    )
    gemini_judge_model: str = field(
        default_factory=lambda: _get("GEMINI_JUDGE_MODEL", _get("GEMINI_MODEL", "gemini-3.5-flash"))
    )

    # --- Filesystem locations ---
    log_dir: Path = field(default_factory=lambda: Path(_get("LOG_DIR", "logs")))
    state_dir: Path = field(default_factory=lambda: Path(_get("STATE_DIR", "data/state")))

    # --- Resilience / graph limits (NFR-04) ---
    request_timeout_s: float = field(default_factory=lambda: float(_get("REQUEST_TIMEOUT_S", "30")))
    max_retries: int = field(default_factory=lambda: _get_int("MAX_RETRIES", 3))
    # recursion_limit is LangGraph's own HARD ceiling (raises GraphRecursionError,
    # not caught by our step guard); max_steps is OUR soft guard, checked once per
    # supervisor visit. A real live run hit the hard ceiling before the soft guard
    # fired: each supervisor<->worker cycle our step_count counts as ONE step is
    # actually 2 graph hops, plus load_memory/build_context/save_memory add 3 more
    # one-time hops per turn (P2-12) -- the original 25/12 pairing left too thin a
    # margin (worst case ~2*12+5=29 hops > 25). recursion_limit is now generously
    # larger than max_steps' worst case so our own guard always fires first.
    recursion_limit: int = field(default_factory=lambda: _get_int("RECURSION_LIMIT", 60))
    max_steps: int = field(default_factory=lambda: _get_int("MAX_STEPS", 12))

    # --- Observability (wired in Phase 3; placeholders here) ---
    phoenix_enabled: bool = field(default_factory=lambda: _get_bool("PHOENIX_ENABLED", True))
    phoenix_project: str = field(
        default_factory=lambda: _get("PHOENIX_PROJECT", "bank-copilot")
    )

    # --- Streaming API (Phase 6 bonus, src/api/) ---
    # Binds to loopback by default: the API trusts the customer_id it is given
    # (real authentication is documented, not built: docs/security-approach.md).
    api_host: str = field(default_factory=lambda: _get("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _get_int("API_PORT", 8000))
    api_turn_timeout_s: float = field(default_factory=lambda: _get_float("API_TURN_TIMEOUT_S", 120.0))

    def has_api_key(self) -> bool:
        return self.google_api_key not in _PLACEHOLDER_KEYS

    def require_api_key(self) -> str:
        """Return the key or raise a clear error. Never echoes the key value."""
        if not self.has_api_key():
            raise RuntimeError(
                "GOOGLE_API_KEY is not set (or is still the placeholder). "
                "Add a valid Google AI Studio key (starts with 'AIza') to a local "
                ".env file: GOOGLE_API_KEY=... — see .env.example. "
                "The key is never logged or committed."
            )
        return self.google_api_key

    def ensure_dirs(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience singleton for imports: `from src.config import settings`.
settings = get_settings()
