"""Invoice generator — deterministic PDF invoices/quotes/receipts from line items.

Pure reportlab + stdlib, no LLM. All math (subtotal, tax, total) is computed in
code and embedded in the PDF, so the numbers can never drift from what the tool
reports. Returns a typed `{"success": bool, ...}` with the totals echoed back so
the caller relays exact figures.

Optional dependency: reportlab. Imported lazily so the rest of the system still
works if it isn't installed; a missing install degrades to a clear error.

Safety model (manifest authoritative): Level 1 (draft — creates a new document,
never modifies anything else).
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger


class InvoiceGenerator:
    OUTPUT_DIR = settings.DATA_DIR / "workspace" / "invoices"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate_invoice(
        cls,
        to_name: str,
        line_items: List[Dict[str, Any]],
        from_name: str = "Arena",
        invoice_number: Optional[str] = None,
        date: Optional[str] = None,
        currency: str = "$",
        tax_rate: float = 0.0,
        notes: str = "",
        document_type: str = "invoice",
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a PDF invoice (or quote/receipt) and return the computed totals."""
        # Validate text fields.
        if not to_name or not str(to_name).strip():
            return {"success": False, "error": "to_name is required."}
        if document_type not in ("invoice", "quote", "receipt"):
            return {"success": False, "error": "document_type must be invoice, quote, or receipt."}

        # Validate + normalize line items.
        items = cls._normalize_items(line_items)
        if items is None:
            return {"success": False, "error": "line_items must be a non-empty list of {description, quantity, unit_price}."}

        # Compute totals deterministically.
        for it in items:
            it["amount"] = round(it["quantity"] * it["unit_price"], 2)
        subtotal = round(sum(it["amount"] for it in items), 2)
        try:
            tax_rate = float(tax_rate)
        except (TypeError, ValueError):
            return {"success": False, "error": "tax_rate must be a number."}
        if tax_rate < 0:
            return {"success": False, "error": "tax_rate cannot be negative."}
        tax = round(subtotal * tax_rate / 100.0, 2)
        total = round(subtotal + tax, 2)

        number = invoice_number or cls._next_number()
        doc_date = date or datetime.date.today().isoformat()

        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
        except ImportError:
            return {"success": False, "error": "reportlab is not installed. Run: pip install reportlab"}

        out = Path(output_path) if output_path else cls.OUTPUT_DIR / f"{document_type}_{number}.pdf"
        if not out.is_absolute():
            out = settings.BASE_DIR / out

        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            cls._draw(canvas, A4, out, {
                "document_type": document_type,
                "from_name": from_name,
                "to_name": to_name,
                "number": number,
                "date": doc_date,
                "currency": currency,
                "items": items,
                "subtotal": subtotal,
                "tax_rate": tax_rate,
                "tax": tax,
                "total": total,
                "notes": notes,
            })
            audit_logger.info(f"Generated {document_type} {number} → {out}")
            return {
                "success": True,
                "output_path": str(out),
                "document_type": document_type,
                "invoice_number": number,
                "currency": currency,
                "subtotal": subtotal,
                "tax_rate": tax_rate,
                "tax": tax,
                "total": total,
                "line_items_count": len(items),
            }
        except Exception as e:
            app_logger.warning(f"Invoice generation failed: {e}")
            return {"success": False, "error": f"Invoice generation failed: {e}"}

    # ── helpers ─────────────────────────────────────────────────────────────
    @classmethod
    def _normalize_items(cls, line_items) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(line_items, list) or not line_items:
            return None
        out: List[Dict[str, Any]] = []
        for raw in line_items:
            if not isinstance(raw, dict):
                return None
            description = str(raw.get("description", "")).strip()
            if not description:
                return None
            try:
                quantity = float(raw.get("quantity", 1))
                unit_price = float(raw.get("unit_price"))
            except (TypeError, ValueError):
                return None
            if quantity < 0 or unit_price < 0:
                return None
            out.append({"description": description, "quantity": quantity, "unit_price": unit_price})
        return out

    @staticmethod
    def _next_number() -> str:
        return f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"

    @staticmethod
    def _money(currency: str, v: float) -> str:
        return f"{currency}{v:,.2f}"

    @classmethod
    def _draw(cls, canvas_mod, A4, out: Path, d: Dict[str, Any]) -> None:
        width, height = A4
        c = canvas_mod.Canvas(str(out), pagesize=A4)
        c.setTitle(f"{d['document_type'].title()} {d['number']}")

        cur = d["currency"]
        # Header.
        c.setFont("Helvetica-Bold", 22)
        c.drawString(50, height - 60, d["document_type"].upper())
        c.setFont("Helvetica", 10)
        c.drawString(50, height - 80, f"{d['from_name']}")
        c.setFont("Helvetica", 10)
        c.drawRightString(width - 50, height - 60, f"{d['document_type'].title()} #: {d['number']}")
        c.drawRightString(width - 50, height - 74, f"Date: {d['date']}")

        # Bill to.
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, height - 120, "Bill To:")
        c.setFont("Helvetica", 11)
        c.drawString(50, height - 136, d["to_name"])

        # Table header.
        top = height - 190
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, top, "Description")
        c.drawRightString(370, top, "Qty")
        c.drawRightString(450, top, "Unit Price")
        c.drawRightString(width - 50, top, "Amount")
        c.line(50, top - 4, width - 50, top - 4)

        # Rows.
        y = top - 22
        c.setFont("Helvetica", 10)
        for it in d["items"]:
            c.drawString(50, y, it["description"][:60])
            c.drawRightString(370, y, f"{it['quantity']:g}")
            c.drawRightString(450, y, cls._money(cur, it["unit_price"]))
            c.drawRightString(width - 50, y, cls._money(cur, it["amount"]))
            y -= 18

        # Totals.
        c.line(50, y + 6, width - 50, y + 6)
        y -= 22
        c.drawRightString(width - 50, y, f"Subtotal: {cls._money(cur, d['subtotal'])}")
        y -= 18
        if d["tax_rate"]:
            c.drawRightString(width - 50, y, f"Tax ({d['tax_rate']:g}%): {cls._money(cur, d['tax'])}")
            y -= 18
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(width - 50, y, f"Total: {cls._money(cur, d['total'])}")

        # Notes.
        if d["notes"]:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(50, 80, f"Notes: {d['notes'][:200]}")

        c.showPage()
        c.save()
