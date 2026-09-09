"""KnowledgeIndexer failure-path pins.

An owner-side log showed an UnboundLocalError-style traceback around the
knowledge-indexing path. Static analysis (pyflakes + ruff F821) is clean on
the current module, so these tests pin the honest behavior on every path:
no UnboundLocalError can escape, failures return None (never a fabricated
memory id), and successes return the created memory id.
"""
import os


import pytest

from app.tools.knowledge_indexer import KnowledgeIndexer


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Re-point the SHARED db singleton at a throwaway initialized file (the
    indexer imported the object at module load, so the identity must stay)."""
    import app.database as database_module

    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "test_assistant.db")
    )
    database_module.db._init_db()  # fresh schema in the throwaway file
    return database_module.db


def test_youtube_index_success_returns_memory_id(temp_db):
    mem_id = KnowledgeIndexer.index_youtube_knowledge({
        "success": True,
        "video_id": "abc123",
        "video_url": "https://youtu.be/abc123",
        "ai_summary": "How to replace a GPU",
    })
    assert mem_id is not None


def test_youtube_index_failure_path_returns_none_without_raising(temp_db):
    assert KnowledgeIndexer.index_youtube_knowledge({"success": False}) is None


def test_web_index_success_and_failure_paths(temp_db):
    mem_id = KnowledgeIndexer.index_web_knowledge({
        "success": True,
        "title": "Cool article",
        "url": "https://example.com/a",
        "domain": "example.com",
        "ai_summary": "points",
    })
    assert mem_id is not None
    assert KnowledgeIndexer.index_web_knowledge({"success": False}) is None


def test_doc_index_success_and_failure_paths(temp_db):
    mem_id = KnowledgeIndexer.index_doc_knowledge(
        {"success": True, "file_name": "notes.txt", "file_path": "C:/notes.txt"},
        "summary text",
    )
    assert mem_id is not None
    assert (
        KnowledgeIndexer.index_doc_knowledge({"success": False}, "summary") is None
    )


def test_db_exception_becomes_honest_none_no_unboundlocal(temp_db, monkeypatch):
    """If the DB layer blows up mid-write, the indexer must return None —
    never raise UnboundLocalError from a partially assigned result."""
    def _boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(temp_db, "create_memory", _boom)
    assert (
        KnowledgeIndexer.index_youtube_knowledge({
            "success": True, "video_id": "x", "video_url": "u", "ai_summary": "s",
        })
        is None
    )
    assert (
        KnowledgeIndexer.index_web_knowledge({
            "success": True, "title": "t", "url": "u", "domain": "d", "ai_summary": "s",
        })
        is None
    )
    assert (
        KnowledgeIndexer.index_doc_knowledge(
            {"success": True, "file_name": "f", "file_path": "p"}, "s"
        )
        is None
    )


def test_manifest_index_knowledge_tool_executes_without_unboundlocal():
    """The registered `index_knowledge` tool path (manifest wrapper) runs the
    doc indexer end-to-end without an UnboundLocalError."""
    from app.tools.manifest import build_tool_manifest

    handler = build_tool_manifest()["index_knowledge"]["handler"]
    result = handler({
        "doc_result": {
            "success": True,
            "file_name": "spec.md",
            "file_path": "spec.md",
        },
        "ai_summary": "the spec says hello",
    })
    # The wrapped handler returns the created memory id (or the typed
    # error dict) — either way it must not raise UnboundLocalError.
    assert isinstance(result, (dict, int))
