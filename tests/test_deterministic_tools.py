"""
Deterministic coworker tools: contacts + spreadsheet. No LLM is involved — the
tests assert exact, computed results.
"""

import csv

from app.tools.contacts import ContactsTool
from app.tools.spreadsheet import SpreadsheetTool


# ── Contacts ────────────────────────────────────────────────────────────────
def test_contacts_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(ContactsTool, "STORE_PATH", tmp_path / "contacts.json")

    added = ContactsTool.add_contact("Alice", phone="123", email="a@x.com", company="Acme")
    assert added["success"] is True
    assert added["merged"] is False

    # Dedupe by email.
    again = ContactsTool.add_contact("Alice Updated", email="a@x.com", company="NewCo")
    assert again["merged"] is True
    assert again["contact"]["company"] == "NewCo"

    # Search.
    assert len(ContactsTool.list_contacts("alice")) == 1
    assert len(ContactsTool.list_contacts("nonexistent")) == 0

    # Delete.
    cid = added["contact"]["id"]
    assert ContactsTool.delete_contact(cid)["success"] is True
    assert ContactsTool.delete_contact(cid)["success"] is False


def test_contacts_requires_name(tmp_path, monkeypatch):
    monkeypatch.setattr(ContactsTool, "STORE_PATH", tmp_path / "contacts.json")
    assert ContactsTool.add_contact("  ")["success"] is False


def test_contacts_csv_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ContactsTool, "STORE_PATH", tmp_path / "contacts.json")

    csv_path = tmp_path / "in.csv"
    csv_path.write_text("name,phone,email\nBob,111,b@x.com\nCarol,222,c@x.com\n", encoding="utf-8")
    imported = ContactsTool.import_csv(str(csv_path))
    assert imported["imported"] == 2

    out = tmp_path / "out.csv"
    exp = ContactsTool.export_csv(str(out))
    assert exp["count"] == 2
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {r["name"] for r in rows} == {"Bob", "Carol"}


def test_contacts_vcard_export(tmp_path, monkeypatch):
    monkeypatch.setattr(ContactsTool, "STORE_PATH", tmp_path / "contacts.json")
    ContactsTool.add_contact("Dave", phone="333", email="d@x.com")
    out = tmp_path / "contacts.vcf"
    res = ContactsTool.export_vcard(str(out))
    assert res["success"] is True
    text = out.read_text()
    assert "BEGIN:VCARD" in text
    assert "FN:Dave" in text


# ── Spreadsheet ─────────────────────────────────────────────────────────────
def test_spreadsheet_write_then_read(tmp_path):
    xlsx = tmp_path / "test.xlsx"
    w = SpreadsheetTool.write_rows(str(xlsx), [
        {"name": "alice", "score": 10},
        {"name": "bob", "score": 20},
    ])
    assert w["success"] is True

    r = SpreadsheetTool.read_sheet(str(xlsx))
    assert r["success"] is True
    assert r["count"] == 2
    assert {row["name"] for row in r["rows"]} == {"alice", "bob"}


def test_spreadsheet_aggregate(tmp_path):
    xlsx = tmp_path / "agg.xlsx"
    SpreadsheetTool.write_rows(str(xlsx), [
        {"score": 10}, {"score": 20}, {"score": 30},
    ])

    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "sum")["result"] == 60
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "avg")["result"] == 20
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "min")["result"] == 10
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "max")["result"] == 30
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "count")["result"] == 3


def test_spreadsheet_aggregate_skips_non_numeric(tmp_path):
    xlsx = tmp_path / "mixed.xlsx"
    SpreadsheetTool.write_rows(str(xlsx), [
        {"score": 10}, {"score": "not a number"}, {"score": 20},
    ])
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "sum")["result"] == 30


def test_spreadsheet_rejects_bad_operation(tmp_path):
    xlsx = tmp_path / "x.xlsx"
    SpreadsheetTool.write_rows(str(xlsx), [{"score": 1}])
    assert SpreadsheetTool.aggregate_column(str(xlsx), "score", "median")["success"] is False
