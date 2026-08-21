"""RssAggregator tests — deterministic RSS/Atom parsing (fixtures) plus graceful
degradation for network fetches and a mocked summarize step."""

from unittest.mock import MagicMock

from app.tools.rss_aggregator import RssAggregator

RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Post One</title>
      <link>https://example.com/1</link>
      <description>First post</description>
      <pubDate>Tue, 01 Jan 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Post Two</title>
      <link>https://example.com/2</link>
      <description>Second post</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Entry One</title>
    <link href="https://example.com/a"/>
    <summary>Summary one</summary>
    <updated>2026-01-01T00:00:00Z</updated>
  </entry>
</feed>
"""


def test_parse_rss():
    res = RssAggregator.parse_feed(RSS)
    assert res["success"] is True
    assert res["title"] == "Example Feed"
    assert res["count"] == 2
    assert res["items"][0]["title"] == "Post One"
    assert res["items"][0]["link"] == "https://example.com/1"
    assert res["items"][0]["summary"] == "First post"


def test_parse_atom():
    res = RssAggregator.parse_feed(ATOM)
    assert res["success"] is True
    assert res["title"] == "Atom Feed"
    assert res["count"] == 1
    assert res["items"][0]["title"] == "Entry One"
    assert res["items"][0]["link"] == "https://example.com/a"


def test_parse_invalid_xml():
    assert RssAggregator.parse_feed("not xml at all")["success"] is False


def test_parse_unknown_root():
    res = RssAggregator.parse_feed("<html><body>hi</body></html>")
    assert res["success"] is False


def test_parse_respects_limit():
    res = RssAggregator.parse_feed(RSS, limit=1)
    assert res["count"] == 1
    assert res["truncated"] is True


def test_fetch_requires_url():
    assert RssAggregator.fetch_feed("")["success"] is False
    assert RssAggregator.fetch_feed("not-a-url")["success"] is False


def test_fetch_degrades_gracefully():
    # Nothing listens on port 1 → connection refused; must not raise.
    res = RssAggregator.fetch_feed("http://127.0.0.1:1/feed", timeout=2)
    assert isinstance(res, dict)
    assert res["success"] is False


def test_summarize_feed_with_fake_llm(monkeypatch):
    parsed = RssAggregator.parse_feed(RSS, limit=5)

    def fake_fetch(url, limit=20, timeout=15.0):
        return parsed

    monkeypatch.setattr(RssAggregator, "fetch_feed", fake_fetch)

    llm = MagicMock()
    llm.generate_chat_completion.return_value = {"choices": [{"message": {"content": "Two posts today."}}]}
    res = RssAggregator.summarize_feed("https://example.com/feed", limit=5, llm=llm)
    assert res["success"] is True
    assert res["summary"] == "Two posts today."


def test_summarize_feed_falls_back_when_llm_empty(monkeypatch):
    parsed = RssAggregator.parse_feed(RSS, limit=5)

    def fake_fetch(url, limit=20, timeout=15.0):
        return parsed

    monkeypatch.setattr(RssAggregator, "fetch_feed", fake_fetch)

    llm = MagicMock()
    llm.generate_chat_completion.return_value = {"choices": [{"message": {"content": ""}}]}
    res = RssAggregator.summarize_feed("https://example.com/feed", limit=5, llm=llm)
    assert res["success"] is True
    assert "Post One" in res["summary"]
