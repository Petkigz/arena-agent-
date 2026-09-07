"""Real browser/server fixtures with isolated stores and no mocked cognition.

Run explicitly after building the SPA:
  pytest tests/e2e -m e2e

Install Playwright Chromium normally, or set ARENA_E2E_CHROMIUM to a compatible
local executable. The server binds all interfaces for sandbox compatibility but
its powerful routes remain protected by a random, test-only API key. Browser
fixtures inject that authentication only; HTTP responses and WS frames are real.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("arena-real-browser")
    data = workspace / "data"
    data.mkdir()
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        port = sock.getsockname()[1]
    key = secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "ARENA_API_KEY": key,
        "ARENA_ALLOW_INSECURE_LAN": "0",
        "ARENA_LLM_DISABLED": "1",
        "LPA_DATA_DIR": str(data),
        "LPA_DB_PATH": str(data / "assistant.db"),
        "LPA_AUTONOMY_MODE": "off",
    }
    base = f"http://127.0.0.1:{port}"
    process = None
    log = (workspace / "server.log").open("w+")

    def stop():
        nonlocal process
        if process is None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process = None

    def start():
        nonlocal process
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0",
             "--port", str(port), "--no-access-log"],
            cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.flush()
                log.seek(0)
                raise RuntimeError(f"server exited early:\n{log.read()[-6000:]}")
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.1)
        stop()
        raise RuntimeError("server did not become healthy within 40 seconds")

    def restart():
        stop()
        start()

    try:
        start()
        yield SimpleNamespace(url=base, key=key, data=data, restart=restart, workspace=workspace)
    finally:
        stop()
        log.close()


@pytest.fixture(scope="session")
def server_url(live_server):
    return live_server.url


@pytest.fixture
def page(live_server):
    from playwright.sync_api import sync_playwright

    executable = os.getenv("ARENA_E2E_CHROMIUM") or None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1080},
            extra_http_headers={"X-API-Key": live_server.key},
            service_workers="block",
        )
        # Complete onboarding for this test owner, not fake conversation state.
        # The backend credentials stay out of the public SPA bundle. The WS
        # constructor only adds the same query auth the production client uses.
        context.add_init_script("""
            localStorage.setItem('arena-onboarding', JSON.stringify({state: {completed: true}, version: 0}));
            localStorage.setItem('arena-tutorial-completed', 'true');
        """ + f"""
            const NativeWebSocket = window.WebSocket;
            window.WebSocket = class extends NativeWebSocket {{
                constructor(url, protocols) {{
                    const target = new URL(url, window.location.href);
                    target.searchParams.set('api_key', {json.dumps(live_server.key)});
                    super(target.toString(), protocols);
                }}
            }};
        """)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.goto(f"{live_server.url}/chat", wait_until="domcontentloaded")
        yield page
        context.close()
        browser.close()
