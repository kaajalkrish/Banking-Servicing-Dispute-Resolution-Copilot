"""Audit middleware: machine-generated trail of consequential actions (AC-10).

Appends one masked JSON record per consequential action to
``logs/agent_actions.jsonl``: timestamp, run_id, actor, action, tool,
decision, reason_code, a hashed customer reference (never the raw customer
id — this file may be read more widely than tool_calls.jsonl, so we default
to the extra caution of a stable, non-reversible reference), and masked
details. Atomic append (single write under a lock), matching the pattern
already used by ``mcp_server/transcript.py`` and
``src/observability/tool_logging.py``.

"Consequential" actions (per ref-doc.md §7.4): account-data reads, dispute
creation, service requests, guardrail blocks/sanitizes, escalations,
human-review gating, and refusals.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.ids import get_current_run_id
from src.common.masking import mask_obj

_write_lock = threading.Lock()


def hash_customer_ref(customer_id: str) -> str:
    """A stable, non-reversible reference for the audit log — never the raw
    customer id itself, so the file remains safe even under broader review."""
    return "cust-" + hashlib.sha256(customer_id.encode("utf-8")).hexdigest()[:16]


def _path() -> Path:
    d = Path(os.environ.get("LOG_DIR", "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "agent_actions.jsonl"


def record_action(
    *,
    actor: str,
    action: str,
    decision: str,
    tool: str | None = None,
    reason_code: str | None = None,
    customer_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append one audit record. Never raises into the caller."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": get_current_run_id(),
        "actor": actor,
        "action": action,
        "tool": tool,
        "decision": decision,
        "reason_code": reason_code,
        "customer_ref": hash_customer_ref(customer_id) if customer_id else None,
        "details": mask_obj(details or {}),
    }
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _write_lock:
            with _path().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
    except Exception:  # audit logging must never break the caller
        pass
