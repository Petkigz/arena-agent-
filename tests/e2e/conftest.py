"""
Playwright end-to-end fixtures.

These tests boot the real unified server (app.server:app), load the React SPA in
a real Chromium browser, and drive a WebSocket chat round-trip. They require:

  pip install playwright pytest-asyncio websockets
  python -m playwright install chromium

They are marked `e2e` and are NOT collected by the default `pytest tests/` run
(see pytest.ini) — they run explicitly via `pytest tests/e2e` or in CI.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def server_url():
    """Boot the unified Arena server on a free port and yield its base URL."""
    port = _free_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base = f"http://127.0.0.1:{port}"
    # Wait for /health
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            raise RuntimeError(f"server exited early:\n{out}")
        try:
            import urllib.request
            with urllib.request.urlopen(f"{base}/health", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        raise RuntimeError("server did not become healthy in time")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def page(server_url):
    """A Playwright Chromium page loaded on the Arena SPA."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server_url, wait_until="networkidle")
        yield page
        browser.close()
