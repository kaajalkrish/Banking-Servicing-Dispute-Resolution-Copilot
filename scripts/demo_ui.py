"""Demonstrated local run of the Streamlit UI, end to end (ref-doc.md §8.1).

Drives the REAL ``src/ui/app.py`` via Streamlit's own ``AppTest`` framework --
no mocks: starts the real FastAPI server the UI is a thin client of, runs the
actual app script, sets a real ``chat_input``, and captures what actually
rendered (real HTTP call, real graph, real Gemini). ``scripts/demo_api.py``
already demonstrates the API layer directly; this is the one piece that did
not cover -- a turn through the UI's own code path (widget state, the
``src/ui/client.py`` wiring, masking-on-render), not just the API.

The server is started with its LOG_DIR/STATE_DIR pointed at a throwaway
directory (default ``artifacts_regen/ui_demo``, gitignored), so the demo
never touches the committed ``logs/`` evidence or the real checkpoint/memory
stores. Writes a masked, timestamped run log (default ``logs/ui_demo.log``).
Exits non-zero if the app raises, the API could not be reached, or no real
answer was rendered, so a bad run is never committed as evidence by accident.

Live Gemini calls: one turn by default (a couple of model calls). Needs
GOOGLE_API_KEY.

Usage:
    python scripts/demo_ui.py
    python scripts/demo_ui.py --message "I want to dispute a charge" --customer-id C0002
    python scripts/demo_ui.py --no-server --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Windows terminals often default to a non-UTF-8 codepage.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from src.common.masking import mask_text  # noqa: E402

APP_PATH = str(_REPO_ROOT / "src" / "ui" / "app.py")


class DemoLog:
    """Timestamped, masked log lines to a file and to stdout."""

    def __init__(self, path: Path | None) -> None:
        self._fh = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("w", encoding="utf-8")

    def line(self, status: str, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        text = f"{ts} {status:<4} {mask_text(message)}"
        print(text)
        if self._fh:
            self._fh.write(text + "\n")
            self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int, work_dir: Path) -> tuple[subprocess.Popen, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "API_HOST": "127.0.0.1",
        "API_PORT": str(port),
        "LOG_DIR": str(work_dir / "logs"),
        "STATE_DIR": str(work_dir / "state"),
        "PHOENIX_ENABLED": "false",
    }
    server_log = work_dir / "server.log"
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.api"],
        cwd=_REPO_ROOT,
        env=env,
        stdout=server_log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    return proc, server_log


def _wait_healthy(base_url: str, proc: subprocess.Popen | None, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                return False  # server exited during start-up
            try:
                if client.get("/health").status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
    return False


def run_ui_turn(base_url: str, customer_id: str, message: str, log: DemoLog) -> bool:
    """Drive one real turn through src/ui/app.py via AppTest; True only if a
    real answer rendered with no exception and no error element."""
    os.environ["COPILOT_START_API"] = "0"  # we already started (or were given) one
    os.environ["COPILOT_API_URL"] = base_url

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=180).run()
    if at.exception:
        log.line("FAIL", f"first render raised: {at.exception}")
        return False
    ready = [s.value for s in at.sidebar.success]
    log.line("OK", f"first render: title={at.title[0].value!r} sidebar={ready}")
    if "API ready" not in ready:
        log.line("FAIL", "sidebar does not report the API as ready")
        return False

    # .options is the formatted display string ("C0001 (name)"); .value is the
    # raw option value ("C0001") -- comparing .value against a formatted match
    # string always differs, which triggered a spurious (and broken) reselect
    # even when the requested customer was already the default (found live).
    options = list(at.sidebar.selectbox[0].options)
    match = next((o for o in options if o.split(" ")[0] == customer_id), None)
    if match is None:
        log.line("FAIL", f"customer {customer_id!r} not offered; options={options}")
        return False
    if at.sidebar.selectbox[0].value != customer_id:
        at = at.sidebar.selectbox[0].select(match).run()
        log.line("OK", f"selected customer {match!r}")

    log.line("REQ", f"chat_input customer={customer_id} message={message!r}")
    started = time.perf_counter()
    at = at.chat_input[0].set_value(message).run()
    elapsed_ms = (time.perf_counter() - started) * 1000

    if at.exception:
        log.line("FAIL", f"turn raised: {at.exception}")
        return False
    for e in at.error:
        log.line("FAIL", f"error element rendered: {e.value}")
        return False

    names = [m.name for m in at.chat_message]
    log.line("EVT", f"chat_message roles: {names}")
    for md in at.markdown:
        log.line("EVT", f"markdown: {md.value}")
    for c in at.caption:
        log.line("EVT", f"caption: {c.value}")
    for w in at.warning:
        log.line("EVT", f"warning: {w.value}")

    ok = "assistant" in names and len(at.markdown) >= 2  # the echoed question + a real answer
    log.line("OK" if ok else "FAIL", f"turn rendered in {elapsed_ms:.0f} ms")
    return ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--customer-id", default="C0001")
    p.add_argument("--message", default="What is my current balance?")
    p.add_argument("--out", default="logs/ui_demo.log")
    p.add_argument("--work-dir", default="artifacts_regen/ui_demo", help="isolated LOG_DIR/STATE_DIR for the server")
    p.add_argument("--no-server", action="store_true", help="use an already-running server at --base-url")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--startup-timeout", type=float, default=180.0)
    args = p.parse_args(argv)

    log = DemoLog(Path(args.out))
    proc: subprocess.Popen | None = None
    try:
        if args.no_server:
            base_url = args.base_url
            log.line("INFO", f"using existing server at {base_url}")
        else:
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"
            proc, server_log = _start_server(port, Path(args.work_dir))
            log.line("INFO", f"started server pid={proc.pid} on {base_url} (state isolated in {args.work_dir})")
            if not _wait_healthy(base_url, proc, args.startup_timeout):
                tail = server_log.read_text(encoding="utf-8", errors="replace")[-600:]
                log.line("FAIL", f"server did not become healthy within {args.startup_timeout:.0f}s: {tail}")
                return 1
            log.line("OK", "server is healthy")
        return 0 if run_ui_turn(base_url, args.customer_id, args.message, log) else 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
