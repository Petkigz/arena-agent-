"""Contacts — a deterministic, browser-free contacts manager.

Everything here is computed in code (no LLM): CRUD, search, dedupe, CSV import/
export, and vCard export. The model only picks the tool and relays the result.

Storage: a single JSON file under DATA_DIR/contacts.json (simple, inspectable).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


class ContactsTool:
    STORE_PATH = settings.DATA_DIR / "contacts.json"

    @classmethod
    def _load(cls) -> List[Dict[str, Any]]:
        if cls.STORE_PATH.exists():
            try:
                return json.loads(cls.STORE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
        return []

    @classmethod
    def _save(cls, contacts: List[Dict[str, Any]]) -> None:
        cls.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.STORE_PATH.write_text(json.dumps(contacts, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def add_contact(
        cls,
        name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        company: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add (or dedupe-merge) a contact. Returns the stored contact."""
        if not name or not name.strip():
            return {"success": False, "error": "A name is required."}
        name = name.strip()

        contacts = cls._load()
        # Dedupe: an existing contact with the same email OR same phone is updated.
        for existing in contacts:
            if (email and existing.get("email") == email) or (phone and existing.get("phone") == phone):
                if email:
                    existing["email"] = email
                if phone:
                    existing["phone"] = phone
                if company:
                    existing["company"] = company
                if notes:
                    existing["notes"] = notes
                cls._save(contacts)
                audit_logger.info(f"Updated existing contact '{name}'")
                return {"success": True, "contact": existing, "merged": True}

        contact = {
            "id": uuid4().hex[:12],
            "name": name,
            "phone": phone or "",
            "email": email or "",
            "company": company or "",
            "notes": notes or "",
        }
        contacts.append(contact)
        cls._save(contacts)
        audit_logger.info(f"Added contact '{name}'")
        return {"success": True, "contact": contact, "merged": False}

    @classmethod
    def list_contacts(cls, query: str = "") -> List[Dict[str, Any]]:
        """List contacts, optionally filtered by a case-insensitive search string."""
        contacts = cls._load()
        q = query.strip().lower()
        if not q:
            return contacts
        return [
            c for c in contacts
            if q in c.get("name", "").lower()
            or q in c.get("email", "").lower()
            or q in c.get("phone", "").lower()
            or q in c.get("company", "").lower()
        ]

    @classmethod
    def get_contact(cls, contact_id: str) -> Dict[str, Any]:
        for c in cls._load():
            if c.get("id") == contact_id:
                return {"success": True, "contact": c}
        return {"success": False, "error": f"Contact '{contact_id}' not found."}

    @classmethod
    def delete_contact(cls, contact_id: str) -> Dict[str, Any]:
        contacts = cls._load()
        before = len(contacts)
        contacts = [c for c in contacts if c.get("id") != contact_id]
        if len(contacts) == before:
            return {"success": False, "error": f"Contact '{contact_id}' not found."}
        cls._save(contacts)
        audit_logger.info(f"Deleted contact '{contact_id}'")
        return {"success": True}

    @classmethod
    def import_csv(cls, csv_path: str) -> Dict[str, Any]:
        """Import contacts from a CSV with columns: name,phone,email,company,notes."""
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                added = 0
                for row in reader:
                    name = (row.get("name") or "").strip()
                    if not name:
                        continue
                    cls.add_contact(
                        name=name,
                        phone=row.get("phone") or None,
                        email=row.get("email") or None,
                        company=row.get("company") or None,
                        notes=row.get("notes") or None,
                    )
                    added += 1
            return {"success": True, "imported": added}
        except Exception as e:
            app_logger.warning(f"Contacts CSV import failed: {e}")
            return {"success": False, "error": f"CSV import failed: {e}"}

    @classmethod
    def export_csv(cls, output_path: str) -> Dict[str, Any]:
        """Export all contacts to a CSV file."""
        contacts = cls._load()
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name", "phone", "email", "company", "notes"])
                writer.writeheader()
                for c in contacts:
                    writer.writerow({k: c.get(k, "") for k in ["id", "name", "phone", "email", "company", "notes"]})
            return {"success": True, "path": output_path, "count": len(contacts)}
        except Exception as e:
            return {"success": False, "error": f"CSV export failed: {e}"}

    @classmethod
    def export_vcard(cls, output_path: str) -> Dict[str, Any]:
        """Export all contacts as a vCard (.vcf) file (stdlib, no deps)."""
        contacts = cls._load()
        lines = []
        for c in contacts:
            lines.append("BEGIN:VCARD")
            lines.append("VERSION:3.0")
            lines.append(f"FN:{c.get('name', '')}")
            if c.get("email"):
                lines.append(f"EMAIL:{c['email']}")
            if c.get("phone"):
                lines.append(f"TEL:{c['phone']}")
            if c.get("company"):
                lines.append(f"ORG:{c['company']}")
            if c.get("notes"):
                lines.append(f"NOTE:{c['notes']}")
            lines.append("END:VCARD")
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            return {"success": True, "path": output_path, "count": len(contacts)}
        except Exception as e:
            return {"success": False, "error": f"vCard export failed: {e}"}
