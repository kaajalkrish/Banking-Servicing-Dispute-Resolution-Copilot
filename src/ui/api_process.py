"""Start (and later stop) the streaming API on this machine, for the UI.

The UI is a thin client of the API (src/ui/client.py). ``streamlit run
src/ui/app.py`` calls :func:`ensure_api` once per Streamlit server, so one command
opens the UI *and* brings the API up. The API needs about a minute to load (tools,
the local embedding model, tracing); the UI does not wait for it, it shows "API
starting" until ``/health`` answers.

An API that is already running is reused and never stopped. Only an API on this
machine (127.0.0.1 or localhost) is ever started.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from src.ui import client

ROOT = Path(__file__).resolve().parents[2]
API_LOG = ROOT / "artifacts_regen" / "ui_api.log"  # gitignored
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
START_API_ENV = "COPILOT_START_API"  # "0" = never start the API (it runs elsewhere)


def api_target(api_url: str) -> tuple[str, int] | None:
    """``(host, port)`` if the URL points at this machine, else None."""
    parts = urlparse(api_url)
    if parts.hostname not in LOCAL_HOSTS:
        return None
    return parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def start_api(host: str, port: int) -> subprocess.Popen:
    API_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "API_HOST": host, "API_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, "-m", "src.api"],
        cwd=ROOT,
        env=env,
        stdout=API_LOG.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def ensure_api(api_url: str) -> subprocess.Popen | None:
    """Start the API in the background if it is not reachable; return the process
    this call started (stopped again at interpreter exit), else None."""
    if os.environ.get(START_API_ENV) == "0" or client.api_health(api_url, timeout=1.0) is not None:
        return None
    target = api_target(api_url)
    if target is None:
        return None
    proc = start_api(*target)
    atexit.register(stop, proc)
    return proc


def log_tail(chars: int = 600) -> str:
    try:
        return API_LOG.read_text(encoding="utf-8", errors="replace")[-chars:]
    except OSError:
        return "(no API log)"
