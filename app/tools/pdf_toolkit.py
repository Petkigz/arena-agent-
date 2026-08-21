"""PDF toolkit — merge, split, extract, read metadata/text, and fill forms.

Deterministic by design (pure pypdf / stdlib, no LLM). Every method returns a
typed `{"success": bool, ...}` dict and never raises — failures degrade to a
clear error string so the thin model can relay the exact outcome.

Safety model (manifest authoritative):
- read operations (metadata, extract_text) → Level 0 (read).
- write operations (merge, split, extract_pages, fill_form) → Level 2
  (reversible: they only create new files, never overwrite the source in place
  unless an identical output path is explicitly given).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.utils.logger import app_logger, audit_logger


class PdfToolkit:
    OUTPUT_DIR = settings.DATA_DIR / "workspace" / "pdf"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _resolve(cls, path_str: str) -> Path:
        p = Path(path_str)
        if not p.is_absolute():
            p = settings.BASE_DIR / p
        return p

    # ── read (Level 0) ──────────────────────────────────────────────────────
    @classmethod
    def get_metadata(cls, file_path: str) -> Dict[str, Any]:
        """Return page count and document metadata (title, author, producer…)."""
        p = cls._resolve(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: '{p}'"}
        if p.suffix.lower() != ".pdf":
            return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
        try:
            reader = PdfReader(str(p))
            meta = reader.metadata or {}
            # pypdf metadata is a dict-like of NameObject; stringify defensively.
            cleaned = {}
            for k, v in meta.items():
                try:
                    cleaned[str(k).lstrip("/")] = str(v) if v is not None else None
                except Exception:
                    cleaned[str(k).lstrip("/")] = repr(v)
            return {
                "success": True,
                "file_name": p.name,
                "page_count": len(reader.pages),
                "metadata": cleaned,
            }
        except Exception as e:
            app_logger.warning(f"PDF metadata read failed: {e}")
            return {"success": False, "error": f"PDF metadata read failed: {e}"}

    @classmethod
    def extract_text(cls, file_path: str, page: Optional[int] = None, max_chars: int = 20000) -> Dict[str, Any]:
        """Extract text from a whole PDF, or a single 1-indexed page."""
        p = cls._resolve(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: '{p}'"}
        if p.suffix.lower() != ".pdf":
            return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
        try:
            reader = PdfReader(str(p))
            n = len(reader.pages)
            if page is not None:
                if page < 1 or page > n:
                    return {"success": False, "error": f"Page {page} out of range (1-{n})."}
                pages = [reader.pages[page - 1]]
            else:
                pages = reader.pages
            texts = []
            total = 0
            for pg in pages:
                t = (pg.extract_text() or "").strip()
                texts.append(t)
                total += len(t)
                if total >= max_chars:
                    break
            joined = "\n\n".join(texts)
            truncated = total >= max_chars
            return {
                "success": True,
                "file_name": p.name,
                "page_count": n,
                "text": joined[:max_chars],
                "truncated": truncated,
            }
        except Exception as e:
            app_logger.warning(f"PDF text extraction failed: {e}")
            return {"success": False, "error": f"PDF text extraction failed: {e}"}

    # ── write (Level 2) ─────────────────────────────────────────────────────
    @classmethod
    def merge_pdfs(cls, input_paths: List[str], output_path: Optional[str] = None) -> Dict[str, Any]:
        """Merge multiple PDFs in order into a single PDF."""
        if not input_paths:
            return {"success": False, "error": "At least one input PDF is required."}
        if len(input_paths) < 2:
            return {"success": False, "error": "Merging requires at least two input PDFs."}

        writer = PdfWriter()
        for ip in input_paths:
            p = cls._resolve(ip)
            if not p.exists():
                return {"success": False, "error": f"File not found: '{p}'"}
            if p.suffix.lower() != ".pdf":
                return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
            try:
                writer.append(p)
            except Exception as e:
                app_logger.warning(f"Could not append {p}: {e}")
                return {"success": False, "error": f"Could not append '{p.name}': {e}"}

        out = cls._resolve(output_path) if output_path else cls.OUTPUT_DIR / "merged.pdf"
        return cls._write(writer, out, "merged")

    @classmethod
    def split_pdf(cls, file_path: str, output_dir: Optional[str] = None, pages_per_split: int = 1) -> Dict[str, Any]:
        """Split a PDF into multiple PDFs of `pages_per_split` pages each."""
        p = cls._resolve(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: '{p}'"}
        if p.suffix.lower() != ".pdf":
            return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
        pages_per_split = max(1, int(pages_per_split))
        try:
            reader = PdfReader(str(p))
            n = len(reader.pages)
            out_dir = cls._resolve(output_dir) if output_dir else cls.OUTPUT_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            parts: List[str] = []
            for start in range(0, n, pages_per_split):
                writer = PdfWriter()
                for page in reader.pages[start:start + pages_per_split]:
                    writer.add_page(page)
                part_path = out_dir / f"{p.stem}_part_{start // pages_per_split + 1}.pdf"
                with open(part_path, "wb") as f:
                    writer.write(f)
                parts.append(str(part_path))
            audit_logger.info(f"Split '{p.name}' into {len(parts)} parts")
            return {"success": True, "input": str(p), "parts": parts, "count": len(parts)}
        except Exception as e:
            app_logger.warning(f"PDF split failed: {e}")
            return {"success": False, "error": f"PDF split failed: {e}"}

    @classmethod
    def extract_pages(cls, file_path: str, pages: List[int], output_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract specific 1-indexed pages into a new PDF."""
        p = cls._resolve(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: '{p}'"}
        if p.suffix.lower() != ".pdf":
            return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
        if not pages:
            return {"success": False, "error": "No pages specified."}
        try:
            pages = [int(x) for x in pages]
        except (TypeError, ValueError):
            return {"success": False, "error": "pages must be a list of integers."}
        try:
            reader = PdfReader(str(p))
            n = len(reader.pages)
            for pg in pages:
                if pg < 1 or pg > n:
                    return {"success": False, "error": f"Page {pg} out of range (1-{n})."}
            writer = PdfWriter()
            for pg in pages:
                writer.add_page(reader.pages[pg - 1])
            out = cls._resolve(output_path) if output_path else cls.OUTPUT_DIR / f"{p.stem}_extracted.pdf"
            return cls._write(writer, out, "extracted")
        except Exception as e:
            app_logger.warning(f"PDF page extraction failed: {e}")
            return {"success": False, "error": f"PDF page extraction failed: {e}"}

    @classmethod
    def fill_form(cls, file_path: str, field_values: Dict[str, str], output_path: Optional[str] = None) -> Dict[str, Any]:
        """Fill AcroForm fields with the given values (best-effort)."""
        p = cls._resolve(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: '{p}'"}
        if p.suffix.lower() != ".pdf":
            return {"success": False, "error": f"Not a PDF file: '{p.name}'"}
        if not isinstance(field_values, dict) or not field_values:
            return {"success": False, "error": "field_values must be a non-empty dict."}
        try:
            reader = PdfReader(str(p))
            fields = reader.get_fields()
            if not fields:
                return {"success": False, "error": "This PDF has no fillable form fields."}
            writer = PdfWriter()
            writer.append(reader)
            # Apply values to every page; unknown field names are ignored.
            for page in writer.pages:
                writer.update_page_form_field_values(page, field_values)
            out = cls._resolve(output_path) if output_path else cls.OUTPUT_DIR / f"{p.stem}_filled.pdf"
            return cls._write(writer, out, "filled")
        except Exception as e:
            app_logger.warning(f"PDF form fill failed: {e}")
            return {"success": False, "error": f"PDF form fill failed: {e}"}

    # ── shared writer ───────────────────────────────────────────────────────
    @classmethod
    def _write(cls, writer: PdfWriter, out: Path, label: str) -> Dict[str, Any]:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                writer.write(f)
            audit_logger.info(f"Wrote {label} PDF to {out}")
            return {"success": True, "output_path": str(out), "output": str(out)}
        except Exception as e:
            app_logger.warning(f"PDF write failed: {e}")
            return {"success": False, "error": f"PDF write failed: {e}"}
