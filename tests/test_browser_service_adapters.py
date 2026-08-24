"""Service-specific browser receipts and owner-configured delete adapters.

Uploads against a configured service extract the service's own receipt ID from
the observed page; when the owner's adapter defines a delete flow, the upload's
rollback becomes a concrete browser_delete_upload compensation (still requiring
separate Level-3 authorization). Deletion runs only the configured flow and is
verified by the confirmation selector — nothing stronger is claimed.
"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.cognition.browser_adapters import BrowserAdapterStore
from app.cognition.browser_grounding import BrowserGroundingStore
from app.cognition.execution_control import ExecutionControlRegistry
from app.tools.browser_automation import BrowserAutomation

ADAPTER = {
    "service_id": "example-drive",
    "url_pattern": r"https://drive\.example\.com/.*",
    "receipt_selector": ".receipt-id",
    "receipt_attribute": "text",
    "delete_url_template": "https://drive.example.com/delete/{receipt_id}",
    "confirm_selector": ".deleted",
    "note": "owner-declared",
}


# ── adapter store ────────────────────────────────────────────────────────────

def test_adapter_upsert_match_and_validation(tmp_path):
    store = BrowserAdapterStore(tmp_path / "a.db")
    adapter = store.upsert(ADAPTER)
    assert adapter.delete_supported is True
    assert store.match("https://drive.example.com/upload").service_id == "example-drive"
    assert store.match("https://other.example.net/x") is None

    # Upsert by service_id keeps identity, updates fields.
    changed = store.upsert({**ADAPTER, "receipt_attribute": "data-id"})
    assert changed.adapter_id == adapter.adapter_id
    assert store.get_by_service("example-drive").receipt_attribute == "data-id"

    for bad in (
        {"service_id": "", "url_pattern": "x"},                                # missing fields
        {"service_id": "s", "url_pattern": "(unclosed"},                        # invalid regex
        {**ADAPTER, "delete_url_template": "https://x/delete/42"},              # no {receipt_id}
        {**ADAPTER, "delete_url_template": "https://x/del/{receipt_id}", "confirm_selector": ""},  # no confirm
    ):
        with pytest.raises(ValueError):
            store.upsert(bad)


def test_adapter_removal(tmp_path):
    store = BrowserAdapterStore(tmp_path / "a.db")
    store.upsert({k: v for k, v in ADAPTER.items() if k not in ("delete_url_template", "confirm_selector")})
    assert store.remove("example-drive") is True
    assert store.remove("example-drive") is False
    assert store.list() == []


# ── upload receipt extraction ────────────────────────────────────────────────

class ReceiptElement:
    def inner_text(self):
        return "  RCP-8842  "

    def get_attribute(self, name):
        return f"attr:{name}"


class UploadPage:
    url = "https://drive.example.com/upload"

    def __init__(self):
        self.submitted = False

    def goto(self, *a, **k): pass
    def title(self): return "Upload"

    def is_visible(self, selector):
        # The success selector must be invisible before submission so the
        # absent-before/visible-after transition can verify this upload.
        return selector != ".done" or self.submitted

    def set_input_files(self, *a, **k): pass

    def click(self, selector):
        if selector == "#submit":
            self.submitted = True

    def wait_for_selector(self, *a, **k): pass

    def query_selector(self, selector):
        assert selector == ".receipt-id"
        return ReceiptElement()


class UploadBrowser:
    def new_page(self):
        return UploadPage()

    def close(self): pass


class FakeChromium:
    def __init__(self, browser):
        self.launch = lambda **k: browser


class FakeSyncPlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


class FakeContext:
    def __init__(self, browser):
        self._pw = FakeSyncPlaywright(browser)

    def __enter__(self):
        return self._pw

    def __exit__(self, *a):
        return False


def patch_upload_browser(monkeypatch, tmp_path):
    ctx = FakeContext(UploadBrowser())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: ctx))
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "b.db"))
    source = tmp_path / "f.txt"
    source.write_text("payload")
    return source


def test_upload_extracts_receipt_and_reports_delete_compensation(tmp_path, monkeypatch):
    store = BrowserAdapterStore(tmp_path / "a.db")
    store.upsert(ADAPTER)
    monkeypatch.setattr(BrowserAutomation, "ADAPTERS", store)
    source = patch_upload_browser(monkeypatch, tmp_path)

    result = BrowserAutomation.upload_file(
        "https://drive.example.com/upload", "input[type=file]", str(source), "#submit", ".done"
    )
    assert result["success"] is True
    receipt = result["service_receipt"]
    assert receipt["receipt_id"] == "RCP-8842" and receipt["service_id"] == "example-drive"
    assert result["rollback_supported"] is True
    assert result["rollback_compensation"] == {
        "action": "browser_delete_upload",
        "payload": {"service_id": "example-drive", "receipt_id": "RCP-8842"},
    }
    assert any(ev.startswith("service_receipt:example-drive:RCP-8842") for ev in result["upload_event"]["evidence"])

    # The execution-control rollback receipt becomes a concrete proposal.
    registry = ExecutionControlRegistry(tmp_path / "e.db")
    record = registry.begin("p", "browser_upload")
    receipt_obj = registry.create_rollback_receipt(record.execution_id, "browser_upload", {}, result)
    assert receipt_obj.supported is True
    assert receipt_obj.compensation_action == "browser_delete_upload"
    assert receipt_obj.compensation_payload["receipt_id"] == "RCP-8842"
    assert receipt_obj.requires_approval is True


def test_upload_without_adapter_keeps_honest_unsupported_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(BrowserAutomation, "ADAPTERS", BrowserAdapterStore(tmp_path / "empty.db"))
    source = patch_upload_browser(monkeypatch, tmp_path)
    result = BrowserAutomation.upload_file(
        "https://drive.example.com/upload", "input[type=file]", str(source), "#submit", ".done"
    )
    assert result["success"] is True
    assert result["service_receipt"] is None
    assert result["rollback_supported"] is False
    assert "service-specific delete API" in result["rollback_reason"]
    registry = ExecutionControlRegistry(tmp_path / "e.db")
    record = registry.begin("p", "browser_upload")
    receipt_obj = registry.create_rollback_receipt(record.execution_id, "browser_upload", {}, result)
    assert receipt_obj.supported is False


# ── delete flow ──────────────────────────────────────────────────────────────

class DeletePage:
    url = "https://drive.example.com/delete/RCP-8842"
    visited = []

    def goto(self, url, **k):
        DeletePage.visited.append(url)
        self.url = url

    def title(self): return "Deleted"

    def is_visible(self, selector):
        return selector == ".deleted"

    def wait_for_selector(self, *a, **k): pass


class DeleteBrowser:
    def new_page(self):
        return DeletePage()

    def close(self): pass


def test_delete_runs_only_the_configured_flow(tmp_path, monkeypatch):
    store = BrowserAdapterStore(tmp_path / "a.db")
    store.upsert(ADAPTER)
    monkeypatch.setattr(BrowserAutomation, "ADAPTERS", store)
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "b.db"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: FakeContext(DeleteBrowser())))
    DeletePage.visited = []

    result = BrowserAutomation.delete_uploaded_file("example-drive", "RCP-8842")
    assert result["success"] is True and result["environment_verified"] is True
    assert DeletePage.visited == ["https://drive.example.com/delete/RCP-8842"]
    assert result["delete_event"]["event_type"] == "upload_delete"
    assert result["rollback_supported"] is False  # deletions cannot be undone


def test_delete_receipt_id_is_url_quoted(tmp_path, monkeypatch):
    store = BrowserAdapterStore(tmp_path / "a.db")
    store.upsert(ADAPTER)
    monkeypatch.setattr(BrowserAutomation, "ADAPTERS", store)
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "b.db"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: FakeContext(DeleteBrowser())))
    DeletePage.visited = []

    result = BrowserAutomation.delete_uploaded_file("example-drive", "RCP/8842?x=1")
    assert result["success"] is True
    assert DeletePage.visited == ["https://drive.example.com/delete/RCP%2F8842%3Fx%3D1"]


def test_delete_refuses_without_configuration(tmp_path, monkeypatch):
    store = BrowserAdapterStore(tmp_path / "a.db")
    store.upsert({k: v for k, v in ADAPTER.items() if k not in ("delete_url_template", "confirm_selector")})
    monkeypatch.setattr(BrowserAutomation, "ADAPTERS", store)

    unknown = BrowserAutomation.delete_uploaded_file("not-configured", "RCP-1")
    assert unknown["success"] is False and unknown["side_effects"] is False
    assert "refusing rather than improvising" in unknown["note"]

    no_delete = BrowserAutomation.delete_uploaded_file("example-drive", "RCP-1")
    assert no_delete["success"] is False and "no delete flow" in no_delete["error"]
