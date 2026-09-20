"""Demonstrated local run of the streaming API (ref-doc.md §8.1, §7.7 Bonus).

Starts the FastAPI server (``python -m src.api``) on a free loopback port,
streams a few committed sample conversations to POST /chat/stream with httpx,
and writes a masked, timestamped run log (default ``logs/api_demo.log``):
one line per health check, HTTP status, stream event and result, plus a final
OK/FAIL verdict. The process exits non-zero if any stream is malformed, ends
in an ``error`` frame, or has no ``final`` answer, so a bad run is not
committed as evidence by accident.

The server is started with its LOG_DIR and STATE_DIR pointed at a throwaway
directory (default ``artifacts_regen/api_demo``, gitignored), so the demo does
not append to the committed ``logs/`` evidence or touch the real checkpoint and
memory stores. Phoenix tracing is off unless ``--with-phoenix``.

Live Gemini calls: the default conversations are ``conv-balance`` and
``conv-fee`` (a few calls each) and ``conv-injection`` (blocked by the input
guard before any model call). A real run needs GOOGLE_API_KEY.

Usage:
    python scripts/demo_api.py
    python scripts/demo_api.py --conversations conv-balance,conv-injection
    python scripts/demo_api.py --base-url http://127.0.0.1:8000 --no-server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.common.masking import mask_text  # noqa: E402

DEFAULT_CONVERSATIONS = "conv-balance,conv-fee,conv-injection"
SAMPLE_INPUTS = _REPO_ROOT / "data" / "sample_inputs" / "conversations.jsonl"


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


def load_conversations(path: Path, ids: list[str]) -> list[dict[str, Any]]:
    """The named sample conversations, in the order requested."""
    by_id: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            conv = json.loads(raw)
            by_id[conv["conversation_id"]] = conv
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise SystemExit(f"unknown conversation id(s) {missing}; available: {sorted(by_id)}")
    return [by_id[i] for i in ids]


async def iter_frames(resp: httpx.Response):
    """Yield (event, json) frames as each one arrives on the wire, so the log can
    show real incremental delivery instead of one batch at the end."""
    event, data = None, []
    async for line in resp.aiter_lines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data.append(line[6:])
        elif line == "" and event is not None:
            yield event, (json.loads("\n".join(data)) if data else {})
            event, data = None, []


def parse_sse(lines: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """Group ``event:`` / ``data:`` lines into (event, json) frames."""
    frames: list[tuple[str, dict[str, Any]]] = []
    event, data = None, []
    for line in [*lines, ""]:
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data.append(line[6:])
        elif line == "" and event is not None:
            frames.append((event, json.loads("\n".join(data)) if data else {}))
            event, data = None, []
    return frames


def _check_frames(frames: list[tuple[str, dict[str, Any]]]) -> str | None:
    """Return a problem description, or None if the stream is well-formed."""
    names = [name for name, _ in frames]
    if not names or names[0] != "start":
        return f"stream does not begin with a start frame (got {names[:1]})"
    if names[-1] != "final":
        return f"stream does not end with a final frame (got {names[-1:]})"
    if "error" in names:
        err = next(d for n, d in frames if n == "error")
        return f"stream carried an error frame: {err.get('type')}"
    if not frames[0][1].get("disclosure"):
        return "start frame has no AI disclosure"
    return None


async def run_demo(client: httpx.AsyncClient, conversations: list[dict[str, Any]], log: DemoLog) -> bool:
    """Drive every turn of every conversation; True only if all streams are clean."""
    ok = True
    health = await client.get("/health")
    log.line("OK" if health.status_code == 200 else "FAIL", f"GET /health -> {health.status_code} {health.text}")
    if health.status_code != 200:
        return False

    turns = 0
    for conv in conversations:
        cid, thread = conv["customer_id"], f"demo-{conv['conversation_id']}"
        for text in conv.get("turns", []):
            turns += 1
            started = time.perf_counter()
            log.line("REQ", f"POST /chat/stream customer={cid} thread={thread} message={text!r}")
            frames: list[tuple[str, dict[str, Any]]] = []
            async with client.stream(
                "POST", "/chat/stream", json={"customer_id": cid, "message": text, "thread_id": thread}
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                    log.line("FAIL", f"HTTP {resp.status_code} {body}")
                    ok = False
                    continue
                log.line("OK", "HTTP 200 text/event-stream: events follow as they arrive (+ms since the request)")
                async for name, data in iter_frames(resp):
                    frames.append((name, data))
                    offset_ms = (time.perf_counter() - started) * 1000
                    if name == "final":
                        detail = (
                            f"tier={data.get('risk_tier')} human_review={data.get('requires_human_review')} "
                            f"escalated={data.get('escalated')} answer={data.get('answer')!r}"
                        )
                    else:
                        detail = json.dumps(data, ensure_ascii=False)
                    log.line("EVT", f"{name} +{offset_ms:.0f}ms {detail}")
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.line("OK", f"stream closed: {len(frames)} events in {elapsed_ms:.0f} ms")
            problem = _check_frames(frames)
            if problem:
                log.line("FAIL", problem)
                ok = False

    log.line("OK" if ok else "FAIL", f"{'OK' if ok else 'FAILED'}: {turns} turn(s) over {len(conversations)} conversation(s)")
    return ok


# ------------------------------------------------------------------ server ---


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int, work_dir: Path, *, with_phoenix: bool) -> tuple[subprocess.Popen, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "API_HOST": "127.0.0.1",
        "API_PORT": str(port),
        "LOG_DIR": str(work_dir / "logs"),
        "STATE_DIR": str(work_dir / "state"),
        "PHOENIX_ENABLED": "true" if with_phoenix else "false",
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


async def _wait_healthy(base_url: str, proc: subprocess.Popen | None, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                return False  # server exited during start-up
            try:
                if (await client.get("/health")).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    return False


async def _main_async(args: argparse.Namespace) -> int:
    ids = [i.strip() for i in args.conversations.split(",") if i.strip()]
    conversations = load_conversations(SAMPLE_INPUTS, ids)
    log = DemoLog(Path(args.out))
    proc: subprocess.Popen | None = None
    try:
        if args.no_server:
            base_url = args.base_url
            log.line("INFO", f"using existing server at {base_url}")
        else:
            port = _free_port()
            base_url = f"http://127.0.0.1:{port}"
            proc, server_log = _start_server(port, Path(args.work_dir), with_phoenix=args.with_phoenix)
            log.line("INFO", f"started server pid={proc.pid} on {base_url} (state isolated in {args.work_dir})")
            if not await _wait_healthy(base_url, proc, args.startup_timeout):
                tail = server_log.read_text(encoding="utf-8", errors="replace")[-600:]
                log.line("FAIL", f"server did not become healthy within {args.startup_timeout:.0f}s: {tail}")
                return 1
            log.line("OK", "server is healthy")
        log.line("INFO", f"conversations: {', '.join(ids)}")
        async with httpx.AsyncClient(base_url=base_url, timeout=args.turn_timeout) as client:
            return 0 if await run_demo(client, conversations, log) else 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conversations", default=DEFAULT_CONVERSATIONS, help="comma-separated sample conversation ids")
    p.add_argument("--out", default="logs/api_demo.log")
    p.add_argument("--work-dir", default="artifacts_regen/api_demo", help="isolated LOG_DIR/STATE_DIR for the server")
    p.add_argument("--no-server", action="store_true", help="use an already-running server at --base-url")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--with-phoenix", action="store_true", help="enable Phoenix tracing in the server")
    p.add_argument("--startup-timeout", type=float, default=180.0)
    p.add_argument("--turn-timeout", type=float, default=150.0)
    return asyncio.run(_main_async(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
