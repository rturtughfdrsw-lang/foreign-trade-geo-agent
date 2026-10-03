"""Loopback-only entry point for the deterministic local Demo."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from foreign_trade_geo_agent.web.app import DEFAULT_DEMO_DB_PATH


def main() -> None:
    db_path = Path(DEFAULT_DEMO_DB_PATH).resolve()
    print(f"Demo database: {db_path}")
    print("Demo URL: http://127.0.0.1:8000")
    uvicorn.run(
        "foreign_trade_geo_agent.web.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
