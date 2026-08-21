"""
Hardening tests: the shared extract_reply helper (never raises) and the deepened
content_creator / business_growth (input validation + safe extraction).
"""

from unittest.mock import patch

from app.llm import extract_reply
from app.tools.content_creator import ContentCreatorTool
from app.tools.business_growth import BusinessGrowthEngine


# ── extract_reply (the root fix) ────────────────────────────────────────────
def test_extract_reply_normal():
    assert extract_reply({"choices": [{"message": {"content": "hi"}}]}) == "hi"


def test_extract_reply_never_raises_on_bad_shapes():
    assert extract_reply(None) == ""
    assert extract_reply({}) == ""
    assert extract_reply({"choices": []}) == ""
    assert extract_reply({"choices": [{}]}) == ""
    assert extract_reply({"choices": [{"message": {}}]}) == ""
    assert extract_reply({"choices": [{"message": {"content": None}}]}) == ""
    assert extract_reply("not a dict") == ""
    assert extract_reply({"choices": [{"message": {"content": 123}}]}, fallback="fb") == "fb"


# ── content_creator ─────────────────────────────────────────────────────────
def test_content_creator_requires_topic():
    assert ContentCreatorTool.generate_content("  ")["success"] is False


def test_content_creator_rejects_bad_type():
    res = ContentCreatorTool.generate_content("x", content_type="not_a_type")
    assert res["success"] is False
    assert "Unsupported content_type" in res["error"]


def test_content_creator_generates_valid_type(monkeypatch):
    fake = {"choices": [{"message": {"content": "Great post"}}]}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)

    res = ContentCreatorTool.generate_content("AI", content_type="twitter_thread", auto_save=False)
    assert res["success"] is True
    assert res["content"] == "Great post"
    assert res["content_type"] == "twitter_thread"


def test_content_creator_backcompat_script(monkeypatch):
    fake = {"choices": [{"message": {"content": "script"}}]}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)

    res = ContentCreatorTool.generate_content_script("AI", platform="youtube", auto_save_workspace=False)
    assert res["success"] is True
    assert res["script_text"] == "script"
    assert res["platform"] == "youtube"
    assert res.get("draft_file") is None  # no file written during tests


# ── business_growth ─────────────────────────────────────────────────────────
def test_business_requires_niche():
    assert BusinessGrowthEngine.discover_opportunities("  ")["success"] is False


def test_business_growth_loop_validates_revenue():
    assert BusinessGrowthEngine.generate_growth_loop("x", "abc")["success"] is False
    assert BusinessGrowthEngine.generate_growth_loop("x", -5)["success"] is False


def test_business_growth_loop_succeeds(monkeypatch):
    fake = {"choices": [{"message": {"content": "plan"}}]}
    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)

    res = BusinessGrowthEngine.generate_growth_loop("Acme", 5000)
    assert res["success"] is True
    assert res["growth_plan"] == "plan"
    assert res["target_monthly_revenue"] == 5000.0


def test_business_opportunities_continues_without_web(monkeypatch):
    fake = {"choices": [{"message": {"content": "opportunities"}}]}

    def web_fails(*a, **kw):
        raise RuntimeError("no network")

    monkeypatch.setattr("app.llm.llm_client.generate_chat_completion", lambda **kw: fake)
    monkeypatch.setattr("app.tools.web_research.WebResearcher.search_and_scrape", web_fails)

    res = BusinessGrowthEngine.discover_opportunities("AI")
    assert res["success"] is True
    assert res["used_web_research"] is False
