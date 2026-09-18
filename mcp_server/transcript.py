"""Append-only transcript of every MCP request/response (logs/mcp_transcript.jsonl).

One masked JSON object per tool call or resource read (NFR-05, NFR-06, §7.1).
The log directory is read from the LOG_DIR env var at call time (default
``logs``) so tests can redirect it to a temp directory. All values pass through
mask_obj so no PAN/account number is ever written in plaintext.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.masking import mask_obj

_write_lock = threading.Lock()


def _path() -> Path:
    d = Path(os.environ.get("LOG_DIR", "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "mcp_transcript.jsonl"


def record(
    method: str,
    name: str,
    args: dict[str, Any],
    result: Any,
    latency_ms: float,
    status: str,
) -> None:
    """Append one masked transcript record. Never raises into the caller."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,          # "tools/call" | "resources/read"
        "name": name,              # tool name or resource uri
        "args": mask_obj(args),
        "result": mask_obj(result),
        "latency_ms": round(latency_ms, 2),
        "status": status,          # "ok" | "error"
    }
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with _write_lock:
            with _path().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
    except Exception:  # transcript must never break the tool call
        pass
