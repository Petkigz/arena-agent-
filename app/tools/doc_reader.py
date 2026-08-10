import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from pypdf import PdfReader
import docx
from app.config import settings
from app.utils.logger import app_logger

class DocumentReader:
    APPROVED_DOCS_DIR = settings.DATA_DIR / "approved_docs"

    @classmethod
    def ensure_docs_dir(cls):
        cls.APPROVED_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def read_document(cls, file_path_str: str) -> Dict[str, Any]:
        """
        Reads local .pdf, .docx, .txt, or .md files and extracts clean text.
        """
        cls.ensure_docs_dir()
        file_path = Path(file_path_str)

        if not file_path.is_absolute():
            file_path = settings.BASE_DIR / file_path

        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: '{file_path}'",
                "file_name": file_path.name,
                "content": ""
            }

        ext = file_path.suffix.lower()
        extracted_text = ""

        try:
            if ext == ".pdf":
                reader = PdfReader(file_path)
                pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
                extracted_text = "\n\n".join(pages_text)

            elif ext == ".docx":
                doc = docx.Document(file_path)
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n\n".join(paragraphs)

            elif ext in [".txt", ".md", ".json", ".py", ".csv", ".log"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted_text = f.read()

            else:
                return {
                    "success": False,
                    "error": f"Unsupported file format: '{ext}'",
                    "file_name": file_path.name,
                    "content": ""
                }

            return {
                "success": True,
                "file_name": file_path.name,
                "file_path": str(file_path),
                "extension": ext,
                "content": extracted_text[:15000],  # Truncate to safe character limit
                "length": len(extracted_text)
            }
        except Exception as e:
            app_logger.error(f"Error reading document '{file_path}': {e}")
            return {
                "success": False,
                "error": f"Error reading document: {str(e)}",
                "file_name": file_path.name,
                "content": ""
            }

    @classmethod
    def list_approved_documents(cls) -> List[Dict[str, Any]]:
        """
        Lists all document files placed in data/approved_docs/ directory.
        """
        cls.ensure_docs_dir()
        docs = []
        for file in cls.APPROVED_DOCS_DIR.iterdir():
            if file.is_file() and file.suffix.lower() in [".pdf", ".docx", ".txt", ".md", ".json", ".py"]:
                docs.append({
                    "file_name": file.name,
                    "file_path": str(file),
                    "size_bytes": file.stat().st_size,
                    "extension": file.suffix.lower()
                })
        return docs
