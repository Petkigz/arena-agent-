"""Entry point for the native Arena desktop client.

Usage:
    python -m desktop.main                # connect to http://localhost:8000
    python -m desktop.main --url http://192.168.1.5:8000

The backend (app.server:app) must be running, or you can start it separately:
    PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Arena native desktop client")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    from desktop.app import run
    return run(base_url=args.url)


if __name__ == "__main__":
    sys.exit(main())
