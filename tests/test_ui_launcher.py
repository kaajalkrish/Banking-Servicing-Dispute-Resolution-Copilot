"""Tests for the one-command UI: the launcher (src/ui/__main__.py) and the API
starter the app uses (src/ui/api_process.py).

Offline: the API process, Streamlit and the health check are all faked, so nothing
real is started and no model is called.
"""

from __future__ import annotations

import subprocess

import pytest

from src.ui import __main__ as launcher
from src.ui import api_process, client


class FakeProc:
    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code
        self.terminated = False

    def poll(self):
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> None:
        return None

    def kill(self) -> None:  # pragma: no cover
        self.terminated = True


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Fake the health check and Popen for api_process; record what was started."""
    state = {"healthy": False, "popen": [], "atexit": [], "proc": FakeProc()}

    monkeypatch.setattr(client, "api_health", lambda _url, **_kw: {"status": "ok"} if state["healthy"] else None)
    monkeypatch.setattr(api_process.subprocess, "Popen", lambda cmd, **kw: state["popen"].append((cmd, kw)) or state["proc"])
    monkeypatch.setattr(api_process.atexit, "register", lambda fn, *a: state["atexit"].append((fn, a)))
    monkeypatch.setattr(api_process, "API_LOG", tmp_path / "ui_api.log")
    monkeypatch.delenv(api_process.START_API_ENV, raising=False)
    return state


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://127.0.0.1:8000", ("127.0.0.1", 8000)),
        ("http://localhost:9000", ("localhost", 9000)),
        ("http://127.0.0.1", ("127.0.0.1", 80)),
        ("http://example.com:8000", None),
        ("http://10.0.0.5:8000", None),
    ],
)
def test_api_target_only_accepts_this_machine(url, expected):
    assert api_process.api_target(url) == expected


def test_ensure_api_starts_the_api_when_unreachable_and_stops_it_at_exit(api):
    proc = api_process.ensure_api("http://127.0.0.1:8000")
    assert proc is api["proc"]
    (cmd, kw), = api["popen"]
    assert cmd[-2:] == ["-m", "src.api"]
    assert kw["env"]["API_HOST"] == "127.0.0.1" and kw["env"]["API_PORT"] == "8000"
    assert api["atexit"] == [(api_process.stop, (proc,))]


def test_ensure_api_reuses_a_running_api_and_never_stops_it(api):
    api["healthy"] = True
    assert api_process.ensure_api("http://127.0.0.1:8000") is None
    assert api["popen"] == [] and api["atexit"] == []


def test_ensure_api_can_be_switched_off(api, monkeypatch):
    monkeypatch.setenv(api_process.START_API_ENV, "0")
    assert api_process.ensure_api("http://127.0.0.1:8000") is None
    assert api["popen"] == []


def test_ensure_api_never_starts_an_api_that_is_not_on_this_machine(api):
    assert api_process.ensure_api("http://example.com:8000") is None
    assert api["popen"] == []


def test_ensure_api_uses_the_port_of_a_custom_url(api):
    api_process.ensure_api("http://127.0.0.1:9100")
    assert api["popen"][0][1]["env"]["API_PORT"] == "9100"


def test_stop_kills_a_process_that_will_not_terminate():
    class Stubborn(FakeProc):
        killed = False

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("x", timeout)

        def kill(self):
            self.killed = True

    proc = Stubborn()
    api_process.stop(proc)
    assert proc.terminated and proc.killed


def test_log_tail_reads_the_end_of_the_api_log_or_says_there_is_none(api):
    assert api_process.log_tail() == "(no API log)"
    api_process.API_LOG.write_text("x" * 1000 + "GOOGLE_API_KEY is not set", encoding="utf-8")
    assert api_process.log_tail().endswith("GOOGLE_API_KEY is not set")


@pytest.fixture
def streamlit_call(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.subprocess, "call", lambda cmd, **kw: calls.append((cmd, kw)) or 0)
    return calls


def test_the_launcher_runs_streamlit_on_loopback_with_the_api_url(streamlit_call):
    assert launcher.main([]) == 0
    (cmd, kw), = streamlit_call
    assert cmd[1:4] == ["-m", "streamlit", "run"] and cmd[4].endswith("app.py")
    assert "--server.address=127.0.0.1" in cmd and "--browser.gatherUsageStats=false" in cmd
    assert kw["env"]["COPILOT_API_URL"] == client.DEFAULT_API_URL
    assert api_process.START_API_ENV not in kw["env"] or kw["env"][api_process.START_API_ENV] != "0"


def test_no_api_flag_tells_the_app_not_to_start_the_api(streamlit_call):
    launcher.main(["--no-api", "--api-url", "http://127.0.0.1:9100"])
    env = streamlit_call[0][1]["env"]
    assert env[api_process.START_API_ENV] == "0" and env["COPILOT_API_URL"] == "http://127.0.0.1:9100"


def test_ctrl_c_in_the_ui_exits_cleanly(monkeypatch):
    def interrupted(cmd, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher.subprocess, "call", interrupted)
    assert launcher.main([]) == 0


def test_the_client_reads_the_api_url_from_the_environment(monkeypatch):
    import importlib

    monkeypatch.setenv("COPILOT_API_URL", "http://127.0.0.1:9100")
    try:
        assert importlib.reload(client).DEFAULT_API_URL == "http://127.0.0.1:9100"
    finally:
        monkeypatch.delenv("COPILOT_API_URL")
        importlib.reload(client)
