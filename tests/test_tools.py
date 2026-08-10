import pytest
from pathlib import Path
import tempfile
from app.tools.youtube_learner import YouTubeLearner
from app.tools.web_research import WebResearcher
from app.tools.doc_reader import DocumentReader
from app.tools.knowledge_indexer import KnowledgeIndexer

def test_youtube_video_id_extractor():
    assert YouTubeLearner.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeLearner.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeLearner.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeLearner.extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeLearner.extract_video_id("invalid_string_too_long_or_short") is None

def test_document_reader_txt():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_doc.txt"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Line 1: Vocal EQ Settings\nLine 2: High pass filter at 80Hz.")

        res = DocumentReader.read_document(str(test_file))
        assert res["success"] is True
        assert res["file_name"] == "test_doc.txt"
        assert "High pass filter at 80Hz" in res["content"]

def test_knowledge_indexer_simulated():
    # Test YouTube Indexer
    yt_summary = {
        "success": True,
        "video_id": "test_v_123",
        "video_url": "https://www.youtube.com/watch?v=test_v_123",
        "ai_summary": "1. Cut low end. 2. Boost air frequencies."
    }
    mem_id = KnowledgeIndexer.index_youtube_knowledge(yt_summary)
    assert mem_id is not None

    # Test Web Indexer
    web_summary = {
        "success": True,
        "title": "Solana Rust Smart Contracts Tutorial",
        "url": "https://example.com/solana-tutorial",
        "domain": "example.com",
        "ai_summary": "1. Install Anchor framework. 2. Initialize program."
    }
    web_mem_id = KnowledgeIndexer.index_web_knowledge(web_summary)
    assert web_mem_id is not None
