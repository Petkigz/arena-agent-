"""Markdown notes manager — a native secretary tool (browser-free).

Stores notes as markdown files under DATA_DIR/notes, with CRUD + search.
No external dependencies; fully testable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title.strip().lower()).strip("_")
    return slug or "untitled"


class NotesManager:
    NOTES_DIR = settings.DATA_DIR / "notes"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_note(cls, title: str, content: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        cls.ensure_dir()
        note_id = uuid4().hex[:12]
        filename = f"{note_id}_{_safe_filename(title)}.md"
        path = cls.NOTES_DIR / filename

        tags_line = f"tags: {', '.join(tags or [])}\n" if tags else ""
        body = f"# {title}\n\ndate: {_now()}\n{tags_line}\n{content}\n"
        path.write_text(body, encoding="utf-8")
        audit_logger.info(f"Created note '{title}' ({note_id})")
        return {"success": True, "note_id": note_id, "title": title, "file": filename}

    @classmethod
    def list_notes(cls) -> List[Dict[str, Any]]:
        cls.ensure_dir()
        notes = []
        for p in sorted(cls.NOTES_DIR.glob("*.md"), reverse=True):
            text = p.read_text(encoding="utf-8")
            first = next((l for l in text.splitlines() if l.strip()), p.stem)
            title = first.lstrip("# ").strip() or p.stem
            notes.append({"file": p.name, "title": title, "path": str(p)})
        return notes

    @classmethod
    def read_note(cls, note_id_or_file: str) -> Dict[str, Any]:
        cls.ensure_dir()
        target = cls._resolve(note_id_or_file)
        if target is None:
            return {"success": False, "error": f"Note '{note_id_or_file}' not found."}
        return {"success": True, "content": target.read_text(encoding="utf-8"), "file": target.name}

    @classmethod
    def search_notes(cls, query: str) -> List[Dict[str, Any]]:
        cls.ensure_dir()
        q = query.lower()
        results = []
        for p in cls.NOTES_DIR.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            if q in text.lower():
                first = next((l for l in text.splitlines() if l.strip()), p.stem)
                results.append({"file": p.name, "title": first.lstrip("# ").strip(), "path": str(p)})
        return results

    @classmethod
    def delete_note(cls, note_id_or_file: str) -> Dict[str, Any]:
        target = cls._resolve(note_id_or_file)
        if target is None:
            return {"success": False, "error": f"Note '{note_id_or_file}' not found."}
        target.unlink()
        audit_logger.info(f"Deleted note '{target.name}'")
        return {"success": True, "file": target.name}

    @classmethod
    def _resolve(cls, note_id_or_file: str) -> Optional[Path]:
        cls.ensure_dir()
        # Exact file match first, then note_id prefix match.
        for p in cls.NOTES_DIR.glob("*.md"):
            if p.name == note_id_or_file or p.stem.startswith(note_id_or_file):
                return p
        return None
