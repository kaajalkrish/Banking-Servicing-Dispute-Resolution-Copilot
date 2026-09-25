"""``python -m src.api``: serve the streaming bonus endpoint with uvicorn."""

from __future__ import annotations

import uvicorn

from src.api.app import create_app
from src.config import settings


def main() -> None:
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
