"""``python -m src.ui``: serve the Streamlit UI on loopback."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "app.py"


def main() -> int:
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
