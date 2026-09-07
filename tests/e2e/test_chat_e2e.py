"""
End-to-end test: boot the unified server, load the React SPA in Chromium, and
drive a real WebSocket chat round-trip through the cognitive runtime.

Run explicitly:  PYTHONPATH=. pytest tests/e2e -m e2e
"""

import json
import re

import pytest

pytestmark = pytest.mark.e2e


def test_health_endpoint(server_url):
    import urllib.request
    with urllib.request.urlopen(f"{server_url}/health", timeout=5) as r:
        data = json.loads(r.read())
    assert data["status"] == "healthy"


def test_spa_serves_react_app(page):
    """The root URL must serve the React SPA (title + #root mount point)."""
    assert "Arena" in page.title()
    assert page.locator("#root").count() == 1


def test_chat_input_renders(page):
    """The chat UI renders its message input."""
    page.get_by_role("button", name=re.compile("^New Chat$", re.I)).click()
    from playwright.sync_api import expect
    expect(page.get_by_role("textbox", name="Type your message")).to_be_enabled()


def test_websocket_chat_roundtrip(server_url, live_server):
    """A WebSocket user_message must stream a reply from the cognitive runtime."""
    import asyncio

    import websockets

    async def _run():
        from urllib.parse import urlencode
        ws_url = server_url.replace("http://", "ws://") + "/ws?" + urlencode({"api_key": live_server.key})
        async with websockets.connect(ws_url, origin=server_url) as ws:
            await ws.send(json.dumps({
                "type": "join_conversation",
                "conversation_id": "e2e-conv",
            }))
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({
                "type": "user_message",
                "conversation_id": "e2e-conv",
                "content": "What is 2+2?",
            }))

            tokens = []
            metadata = None
            done = False
            while not done:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
                t = msg.get("type")
                if t == "message_token":
                    tokens.append(msg.get("token", ""))
                    if msg.get("done"):
                        done = True
                elif t == "cognitive_metadata":
                    metadata = msg
                elif t == "error":
                    raise AssertionError(f"server returned error: {msg}")
            return "".join(tokens), metadata

    reply, metadata = asyncio.run(_run())
    assert re.search(r"=\s*4\b", reply)
    assert "Computed locally" in reply
    assert metadata["grounding"]["status"] == "verified"
    import sqlite3
    with sqlite3.connect(live_server.data / "assistant.db") as conn:
        row = conn.execute(
            "SELECT model_used, goal_verified FROM cognitive_traces WHERE trace_id=?",
            (metadata["trace_id"],),
        ).fetchone()
    assert row == ("deterministic_local", 1)
