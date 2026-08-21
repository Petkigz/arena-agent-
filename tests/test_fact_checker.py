"""FactChecker tests — verdict parsing, source extraction, degradation, and a
mocked search+LLM round trip (no live network/model)."""

from unittest.mock import MagicMock

from app.tools.fact_checker import FactChecker


def test_requires_claim():
    assert FactChecker.fact_check("")["success"] is False


def test_parse_verdict_supported():
    v, j = FactChecker._parse_verdict("VERDICT: SUPPORTED\nJUSTIFICATION: matches [1].")
    assert v == "supported"
    assert "matches" in j


def test_parse_verdict_defaults_to_unverifiable():
    v, j = FactChecker._parse_verdict("garbage output")
    assert v == "unverifiable"


def test_parse_verdict_ignores_unknown():
    v, _ = FactChecker._parse_verdict("VERDICT: MAYBE\nJUSTIFICATION: x")
    assert v == "unverifiable"


def test_extract_sources():
    pages = [
        {"url": "https://a.com", "title": "A", "content": "hello world"},
        {"url": "", "title": "no url"},
        {"url": "https://b.com", "title": None, "domain": "b.com", "content": "x"},
    ]
    out = FactChecker._extract_sources(pages)
    assert len(out) == 2
    assert out[0]["url"] == "https://a.com"
    assert out[1]["title"] == "b.com"  # fell back to domain


def test_no_sources_is_unverifiable(monkeypatch):
    import app.tools.web_research as wr

    monkeypatch.setattr(wr.WebResearcher, "search_and_scrape", classmethod(lambda cls, *a, **k: {"pages": []}))
    res = FactChecker.fact_check("The sky is green.")
    assert res["success"] is True
    assert res["verdict"] == "unverifiable"
    assert res["citations"] == []


def test_mocked_round_trip(monkeypatch):
    import app.tools.web_research as wr

    pages = [{"url": "https://src.example", "title": "Source", "content": "the sky is blue"}]
    monkeypatch.setattr(wr.WebResearcher, "search_and_scrape", classmethod(lambda cls, *a, **k: {"pages": pages}))

    llm = MagicMock()
    llm.generate_chat_completion.return_value = {"choices": [{"message": {"content": "VERDICT: SUPPORTED\nJUSTIFICATION: source [1] confirms it."}}]}
    res = FactChecker.fact_check("The sky is blue.", llm=llm)
    assert res["success"] is True
    assert res["verdict"] == "supported"
    assert res["citations"][0]["url"] == "https://src.example"


def test_search_exception_is_unverifiable(monkeypatch):
    import app.tools.web_research as wr

    def boom(cls, *a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(wr.WebResearcher, "search_and_scrape", classmethod(boom))
    res = FactChecker.fact_check("anything")
    assert res["success"] is True
    assert res["verdict"] == "unverifiable"
    assert res["citations"] == []
