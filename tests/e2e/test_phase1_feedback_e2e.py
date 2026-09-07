"""Built SPA → real WS/runtime → durable trace → review → real API/report.

No cognition, store, HTTP response, or WebSocket frame is mocked. This is an
isolated contract scenario, not owner-machine/held-out model-quality evidence.
"""

import json
import os
from pathlib import Path
import re
import sqlite3

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_response_feedback_reaches_existing_reports_and_survives_restart(page, live_server):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.get_by_role("button", name=re.compile("^New Chat$", re.I)).click()
    composer = page.get_by_role("textbox", name="Type your message")
    expect(composer).to_be_enabled()
    expect(page.get_by_text("Local backend not running. Start the Arena backend to use AI features.", exact=True)).not_to_be_visible()
    composer.fill("Remind me in 2 turns to check the report")
    page.get_by_role("button", name="Send message", exact=True).click()
    review = page.get_by_role("button", name="Review response", exact=True)
    expect(review).to_have_count(1, timeout=30000)

    # Verify the task did happen in a real durable store, not just in prose.
    calendar = json.loads((live_server.data / "calendar.json").read_text())
    assert any("check the report" in item["title"] for item in calendar["reminders"])
    with sqlite3.connect(live_server.data / "assistant.db") as conn:
        reply = conn.execute(
            "SELECT message_id, trace_id, content FROM conversations WHERE role='assistant' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        trace = conn.execute(
            "SELECT goal_verified, assistant_reply FROM cognitive_traces WHERE trace_id=?", (reply[1],),
        ).fetchone()
    message_id, trace_id, content = reply
    assert message_id and trace_id and trace[0] == 1
    assert trace[1] == content

    review.click()
    page.get_by_label("How useful was this response?").select_option("helpful")
    page.get_by_label("Feedback note (optional)").fill("Contract test: inspected the persisted reminder.")
    page.get_by_role("button", name="Save usefulness", exact=True).click()
    expect(page.get_by_text("Usefulness recorded:")).to_be_visible()

    page.get_by_text("Record a task evaluation", exact=True).click()
    page.get_by_label("Task comparison key").fill("contract-browser-reminder")
    page.get_by_label("Evaluation type").select_option("contract")
    page.get_by_label("Observed task outcome").select_option("success")
    page.get_by_label("Task usefulness", exact=True).select_option("helpful")
    page.get_by_role("button", name="Save task evaluation", exact=True).click()
    expect(page.get_by_text(re.compile("Evaluation already recorded"))).to_be_visible()

    def report(path):
        response = page.request.get(live_server.url + path)
        assert response.ok, response.text()
        return response.json()

    evidence = report("/benchmarks/phase1/evidence")["report"]
    tasks = report(f"/benchmarks/phase1/tasks/evaluations?trace_id={trace_id}&split=contract")
    assert evidence["usefulness_feedback_count"] == 1
    assert tasks["report"]["evaluation_count"] == 1
    assert tasks["evaluations"][0]["trace_id"] == trace_id
    assert tasks["evaluations"][0]["observed_outcome"] == "success"
    assert tasks["evaluations"][0]["strategy_action_type"] == "schedule_turn_reminder"
    assert report("/benchmarks/phase1/tasks/evaluations?split=held_out")["report"]["evaluation_count"] == 0

    # Restart the actual process, discard the browser conversation cache, and
    # rehydrate. Ratings must still bind to the same DB-backed message/trace.
    live_server.restart()
    page.evaluate("localStorage.removeItem('arena-conversations')")
    page.reload(wait_until="domcontentloaded")
    review = page.get_by_role("button", name="Review response", exact=True)
    expect(review).to_have_count(1, timeout=30000)
    review.click()
    expect(page.get_by_text("Usefulness recorded:")).to_be_visible()
    page.get_by_text("Record a task evaluation", exact=True).click()
    expect(page.get_by_text("contract-browser-reminder · contract · single · success")).to_be_visible()
    assert report("/benchmarks/phase1/evidence")["report"]["usefulness_feedback_count"] == 1
    page.get_by_role("button", name="Why this response?", exact=True).click()
    evidence_panel = page.get_by_label("Recorded response evidence")
    expect(evidence_panel).to_be_visible()
    expect(evidence_panel).to_contain_text("durable local reminder record created")
    artifact_dir = os.getenv("ARENA_E2E_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(artifact_dir) / "response-review.png"), full_page=True)

    # The existing Model Settings correction editor, not a second feedback UI.
    page.get_by_role("link", name="Correct this response", exact=True).click()
    expect(page.get_by_label("Correction source prompt")).to_have_value("Remind me in 2 turns to check the report")
    for _ in range(2):
        page.get_by_role("textbox", name="Preferred response", exact=True).fill("I meant the meeting report rather than the financial report.")
        with page.expect_response(lambda response: response.url.endswith("/loras/training-candidates/owner-correction")
                                  and response.request.method == "POST") as saved:
            page.get_by_role("button", name="Add to review queue", exact=True).click()
        result = saved.value.json()
        assert result["success"] is True
        assert result["candidate"]["status"] == "pending"
        assert result["candidate"]["strategy_update"]["correction_count"] == 1
        assert result["candidate"]["strategy_update"]["generalized"] is False
        assert result["correction_measurement"]["trace_id"] == trace_id
        expect(page.get_by_role("textbox", name="Preferred response", exact=True)).to_have_value("")
    with sqlite3.connect(live_server.data / "assistant.db") as conn:
        assert conn.execute("SELECT goal_verified FROM cognitive_traces WHERE trace_id=?", (trace_id,)).fetchone()[0] == 1
    assert errors == []
