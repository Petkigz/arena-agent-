"""Document generation — markdown → HTML (and, if available, PDF).

Browser-free: uses only the stdlib (markdown → HTML via a tiny built-in
converter) plus optional reportlab for PDF. Always produces HTML; PDF is
best-effort and degrades gracefully.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger


def _md_to_html(markdown: str) -> str:
    """Minimal, dependency-free Markdown → HTML (headings, bold, lists, code)."""
    import re

    html = markdown
    html = re.sub(r"```([^`]+)```", r"<pre><code>\1</code></pre>", html)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.M)
    html = re.sub(r"\n\n", "</p><p>", html)
    return f"<html><body><p>{html}</p></body></html>"


class DocumentGenerator:
    OUTPUT_DIR = settings.DATA_DIR / "workspace" / "generated"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate(cls, title: str, markdown: str, fmt: str = "html") -> Dict[str, Any]:
        """Generate a document (html | pdf) from markdown content."""
        cls.ensure_dir()
        fmt = (fmt or "html").lower()
        base = f"{uuid4().hex[:8]}_{title.lower().replace(' ', '_')}"

        if fmt == "html":
            path = cls.OUTPUT_DIR / f"{base}.html"
            path.write_text(_md_to_html(markdown), encoding="utf-8")
            return {"success": True, "format": "html", "path": str(path), "file": path.name}

        if fmt == "pdf":
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfgen import canvas
            except ImportError:
                return {
                    "success": False,
                    "error": "PDF generation requires 'reportlab' (pip install reportlab).",
                }

            path = cls.OUTPUT_DIR / f"{base}.pdf"
            c = canvas.Canvas(str(path), pagesize=letter)
            width, height = letter
            y = height - 60
            c.setFont("Helvetica-Bold", 18)
            c.drawString(60, y, title)
            y -= 30
            c.setFont("Helvetica", 11)
            for line in markdown.splitlines():
                if y < 60:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 60
                c.drawString(60, y, line[:100])
                y -= 16
            c.save()
            return {"success": True, "format": "pdf", "path": str(path), "file": path.name}

        return {"success": False, "error": f"Unsupported format '{fmt}' (use 'html' or 'pdf')."}
