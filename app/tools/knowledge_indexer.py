from typing import Dict, Any, Optional
from app.database import db
from app.utils.logger import app_logger, audit_logger

class KnowledgeIndexer:
    @staticmethod
    def index_youtube_knowledge(
        summary_result: Dict[str, Any],
        category: str = "learned_skill",
        confidence: float = 0.95
    ) -> Optional[int]:
        """
        Indexes a YouTube tutorial summary into permanent SQLite memory with source URL citation.
        """
        if not summary_result.get("success"):
            return None

        content = (
            f"📹 [YOUTUBE LEARNING :: {summary_result.get('video_id')}]\n"
            f"Source URL: {summary_result.get('video_url')}\n\n"
            f"{summary_result.get('ai_summary')}"
        )

        try:
            mem_id = db.create_memory({
                "content": content,
                "category": category,
                "source": summary_result.get("video_url"),
                "confidence": confidence
            })
            db.create_audit_log("index_youtube_knowledge", "success", f"Indexed video {summary_result.get('video_id')} into SQLite memory.", level=0)
            return mem_id
        except Exception as e:
            app_logger.error(f"Error indexing YouTube knowledge: {e}")
            return None

    @staticmethod
    def index_web_knowledge(
        summary_result: Dict[str, Any],
        category: str = "web_research",
        confidence: float = 0.90
    ) -> Optional[int]:
        """
        Indexes a web article summary into permanent SQLite memory with source URL citation.
        """
        if not summary_result.get("success"):
            return None

        content = (
            f"🌐 [WEB RESEARCH :: {summary_result.get('title')}]\n"
            f"Source URL: {summary_result.get('url')} ({summary_result.get('domain')})\n\n"
            f"{summary_result.get('ai_summary')}"
        )

        try:
            mem_id = db.create_memory({
                "content": content,
                "category": category,
                "source": summary_result.get("url"),
                "confidence": confidence
            })
            db.create_audit_log("index_web_knowledge", "success", f"Indexed web page '{summary_result.get('title')}' into SQLite memory.", level=0)
            return mem_id
        except Exception as e:
            app_logger.error(f"Error indexing web knowledge: {e}")
            return None

    @staticmethod
    def index_doc_knowledge(
        doc_result: Dict[str, Any],
        ai_summary: str,
        category: str = "document_knowledge",
        confidence: float = 0.95
    ) -> Optional[int]:
        """
        Indexes a local document into permanent SQLite memory with file path citation.
        """
        if not doc_result.get("success"):
            return None

        content = (
            f"📄 [DOCUMENT KNOWLEDGE :: {doc_result.get('file_name')}]\n"
            f"File Path: {doc_result.get('file_path')}\n\n"
            f"{ai_summary}"
        )

        try:
            mem_id = db.create_memory({
                "content": content,
                "category": category,
                "source": doc_result.get("file_name"),
                "confidence": confidence
            })
            db.create_audit_log("index_doc_knowledge", "success", f"Indexed document '{doc_result.get('file_name')}' into SQLite memory.", level=0)
            return mem_id
        except Exception as e:
            app_logger.error(f"Error indexing document knowledge: {e}")
            return None
