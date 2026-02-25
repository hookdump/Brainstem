"""CLI entrypoint for Brainstem API."""

from __future__ import annotations

import uvicorn

from brainstem.api import create_app

app = create_app()


def run() -> None:
    uvicorn.run(
        "brainstem.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
