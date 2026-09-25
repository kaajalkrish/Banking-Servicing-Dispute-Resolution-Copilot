"""``python -m src.ui``: same as ``streamlit run src/ui/app.py``, on loopback.

Either command opens the UI *and* starts the streaming API if it is not already
running (src/ui/api_process.py); the app does that itself.

    python -m src.ui                       # start the API if needed, then the UI
    python -m src.ui --no-api              # only the UI (API already running elsewhere)
    python -m src.ui --api-url http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from src.ui import api_process, client

APP = Path(__file__).resolve().parent / "app.py"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Open the Streamlit UI (starting the API if needed).")
    p.add_argument("--api-url", default=client.DEFAULT_API_URL)
    p.add_argument("--no-api", action="store_true", help="do not start the API; use one already running")
    args = p.parse_args(argv)

    env = {**os.environ, "COPILOT_API_URL": args.api_url}
    if args.no_api:
        env[api_process.START_API_ENV] = "0"
    try:
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(APP),
                "--server.address=127.0.0.1",
                "--browser.gatherUsageStats=false",
            ],
            env=env,
        )
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
