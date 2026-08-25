"""Disk reservations and in-flight cancellation for browser transfers.

Before any download starts, free space is measured and reserved (worst-case
quota when the size is unknown); concurrent reservations accumulate. The save
phase is owner-cancellable in flight, removing partial artifacts and releasing
the reservation. Upload attach and submit are separately cancellable.
"""
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.cognition.disk_reservation import DiskReservationLedger
from app.cognition.execution_control import ExecutionCancelled, ExecutionControlRegistry
from app.tools.browser_automation import BrowserAutomation
from app.cognition.browser_grounding import BrowserGroundingStore


def fake_usage(free):
    return SimpleNamespace(free=free, total=free * 10)


def test_reservation_granted_with_measured_evidence(tmp_path):
    ledger = DiskReservationLedger(tmp_path / "d.db")
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(10_000_000_000)):
        result = ledger.reserve("browser_download", 1_000_000, target_root=tmp_path)
    assert result["success"] is True
    assert result["free_bytes"] == 10_000_000_000
    assert result["already_reserved_bytes"] == 0
    margin = ledger.safety_margin_bytes()
    assert result["available_after_reservation"] == 10_000_000_000 - margin - 1_000_000


def test_reservation_refused_with_typed_numbers(tmp_path):
    ledger = DiskReservationLedger(tmp_path / "d.db")
    free = ledger.safety_margin_bytes() + 500_000
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(free)):
        refused = ledger.reserve("browser_download", 1_000_000, target_root=tmp_path)
    assert refused["success"] is False and refused["refused"] is True
    assert refused["error"] == "insufficient_disk_space"
    assert refused["free_bytes"] == free
    assert refused["safety_margin_bytes"] == ledger.safety_margin_bytes()
    assert refused["available_after_reservation"] == 0


def test_concurrent_reservations_accumulate(tmp_path):
    ledger = DiskReservationLedger(tmp_path / "d.db")
    free = ledger.safety_margin_bytes() + 3_000_000
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(free)):
        first = ledger.reserve("browser_download", 1_000_000, target_root=tmp_path)
        second = ledger.reserve("browser_download", 1_000_000, target_root=tmp_path)
        assert second["already_reserved_bytes"] == 1_000_000
        # Third would leave less than the margin: refused even though each alone fits.
        third = ledger.reserve("browser_download", 1_200_000, target_root=tmp_path)
    assert first["success"] is True and second["success"] is True
    assert third["success"] is False and third["already_reserved_bytes"] == 2_000_000
    ledger.release(first["reservation"]["reservation_id"], reason="test")
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(free)):
        after_release = ledger.reserve("browser_download", 1_200_000, target_root=tmp_path)
    assert after_release["success"] is True and after_release["already_reserved_bytes"] == 1_000_000


def test_consume_records_actual_and_release_is_idempotent(tmp_path):
    ledger = DiskReservationLedger(tmp_path / "d.db")
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(10_000_000_000)):
        granted = ledger.reserve("browser_download", 1_000, target_root=tmp_path)
    rid = granted["reservation"]["reservation_id"]
    consumed = ledger.consume(rid, 640, reason="test")
    assert consumed.status == "consumed" and consumed.actual_bytes == 640
    again = ledger.release(rid, reason="late release must not resurrect")
    assert again.status == "consumed"  # finished reservations stay finished


def test_stale_active_reservations_recovered_on_restart(tmp_path):
    import sqlite3
    db = tmp_path / "d.db"
    ledger = DiskReservationLedger(db, stale_after_seconds=3600)
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(10_000_000_000)):
        granted = ledger.reserve("browser_download", 5_000_000, target_root=tmp_path)
    rid = granted["reservation"]["reservation_id"]
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE disk_reservations SET created_at='2020-01-01T00:00:00+00:00' WHERE reservation_id=?", (rid,))
        conn.commit()
    DiskReservationLedger(db, stale_after_seconds=3600)
    with sqlite3.connect(db) as conn:
        status = conn.execute("SELECT status FROM disk_reservations WHERE reservation_id=?", (rid,)).fetchone()[0]
    assert status == "stale"
    assert DiskReservationLedger(db, stale_after_seconds=3600).active_bytes() == 0


def test_reservation_requires_positive_size(tmp_path):
    ledger = DiskReservationLedger(tmp_path / "d.db")
    assert ledger.reserve("browser_download", 0, target_root=tmp_path)["refused"] is True


# ── download flow wiring ─────────────────────────────────────────────────────

class Download:
    suggested_filename = "../report.txt"
    cancelled = False

    def cancel(self):
        Download.cancelled = True

    def save_as(self, path):
        with open(path, "wb") as fh:
            fh.write(b"exact download")


class Expect:
    value = Download()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Page:
    url = "https://example.test/file"

    def goto(self, *a, **k): pass
    def click(self, *a, **k): pass
    def title(self): return "Files"

    def expect_download(self, **k): return Expect()


class Browser:
    closed = False

    def new_page(self):
        return Page()

    def close(self):
        Browser.closed = True


class Playwright:
    chromium = SimpleNamespace(launch=lambda **k: Browser())


class Context:
    def __enter__(self): return Playwright()

    def __exit__(self, *a): return False


def patch_browser(monkeypatch, tmp_path):
    fake = SimpleNamespace(sync_playwright=lambda: Context())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    monkeypatch.setattr(BrowserAutomation, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(BrowserAutomation, "GROUNDING", BrowserGroundingStore(tmp_path / "browser.db"))
    ledger = DiskReservationLedger(tmp_path / "res.db")
    monkeypatch.setattr(BrowserAutomation, "DISK_LEDGER", ledger)
    # Reset shared fake-browser state so tests stay order-independent.
    Browser.closed = False
    Download.cancelled = False
    Expect.value = Download()
    return ledger


def test_download_consumes_reservation_and_reports_evidence(tmp_path, monkeypatch):
    ledger = patch_browser(monkeypatch, tmp_path)
    result = BrowserAutomation.download_file("https://example.test", "a.download")
    assert result["success"] is True
    evidence = result["disk_reservation"]
    # Unknown size ⇒ worst-case quota reserved; actual size recorded on consume.
    assert evidence["reserved_bytes"] == 1024 * 1024 * 1024
    assert evidence["actual_bytes"] == len(b"exact download")
    assert evidence["status"] == "consumed"
    import sqlite3
    with sqlite3.connect(ledger.db_path) as conn:
        status = conn.execute(
            "SELECT status, actual_bytes FROM disk_reservations WHERE reservation_id=?",
            (evidence["reservation_id"],),
        ).fetchone()
    assert status[0] == "consumed" and status[1] == len(b"exact download")


def test_download_refused_before_browser_launch_when_disk_short(tmp_path, monkeypatch):
    ledger = patch_browser(monkeypatch, tmp_path)
    tiny_free = ledger.safety_margin_bytes() + 1000  # far below the 1GB quota
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(tiny_free)):
        result = BrowserAutomation.download_file("https://example.test", "a.download")
    assert result["success"] is False and result["side_effects"] is False
    assert result["disk_reservation"]["refused"] is True
    assert Browser.closed is False  # no browser was ever launched
    assert ledger.active_bytes() == 0


def test_expected_size_reservation_overrides_worst_case(tmp_path, monkeypatch):
    ledger = patch_browser(monkeypatch, tmp_path)
    tiny_free = ledger.safety_margin_bytes() + 500_000
    with patch("app.cognition.disk_reservation.shutil.disk_usage", return_value=fake_usage(tiny_free)):
        refused = BrowserAutomation.download_file("https://example.test", "a.download")  # quota default
        granted = BrowserAutomation.download_file("https://example.test", "a.download", expected_size_bytes=400_000)
    assert refused["success"] is False
    assert granted["success"] is True
    assert granted["disk_reservation"]["reserved_bytes"] == 400_000


class SlowDownload(Download):
    def save_as(self, path):
        with open(path, "wb") as fh:
            fh.write(b"partial-bytes")
        for _ in range(40):  # ~2s in-flight window
            time.sleep(0.05)
            if Download.cancelled:
                return  # aborted by browser close


def test_inflight_download_cancellation_removes_partial_and_releases(tmp_path, monkeypatch):
    ledger = patch_browser(monkeypatch, tmp_path)
    Expect.value = SlowDownload()
    import app.cognition.execution_control as ec
    registry = ExecutionControlRegistry(tmp_path / "exec.db")
    # The cooperative runner consults the module-level registry singleton.
    monkeypatch.setattr(ec, "execution_control_registry", registry)
    record = registry.begin("proposal", "browser_download")

    def cancel_soon():
        time.sleep(0.15)
        registry.request_cancel(record.execution_id)

    canceller = threading.Thread(target=cancel_soon)
    canceller.start()
    with pytest.raises(ExecutionCancelled):
        with registry.scope(record.execution_id):
            BrowserAutomation.download_file("https://example.test", "a.download")
    canceller.join(timeout=5)

    finished = registry.get(record.execution_id)
    assert finished.cancel_requested is True and finished.cancellation_observed is True
    # Partial artifact removed; reservation released; abort reached the browser.
    leftovers = list((tmp_path / "downloads").glob("*")) if (tmp_path / "downloads").exists() else []
    assert leftovers == []
    assert ledger.active_bytes() == 0
    assert Download.cancelled is True


class UploadPage:
    url = "https://upload.test"
    attached = False
    submitted = False

    def goto(self, *a, **k): pass

    def is_visible(self, selector):
        return self.submitted and selector == ".done"

    def set_input_files(self, selector, path):
        UploadPage.attached = True
        time.sleep(0.3)  # attach window for cancellation

    def click(self, selector):
        UploadPage.submitted = True

    def wait_for_selector(self, *a, **k): pass

    def title(self): return "Upload"

    @property
    def url_property(self):
        return self.url


class UploadBrowser:
    def __init__(self):
        self._page = UploadPage()

    def new_page(self):
        return self._page

    def close(self): pass


def test_upload_attach_phase_is_cancellable_without_submission(tmp_path, monkeypatch):
    patch_browser(monkeypatch, tmp_path)
    source = tmp_path / "file.txt"
    source.write_text("payload")
    UploadPage.attached = False
    UploadPage.submitted = False

    class UploadContext:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **k: UploadBrowser()))

        def __exit__(self, *a):
            return False

    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: UploadContext()))
    import app.cognition.execution_control as ec
    registry = ExecutionControlRegistry(tmp_path / "exec.db")
    monkeypatch.setattr(ec, "execution_control_registry", registry)
    record = registry.begin("proposal", "browser_upload")

    def cancel_soon():
        time.sleep(0.1)
        registry.request_cancel(record.execution_id)

    canceller = threading.Thread(target=cancel_soon)
    canceller.start()
    with pytest.raises(ExecutionCancelled):
        with registry.scope(record.execution_id):
            BrowserAutomation.upload_file(
                "https://upload.test", "input[type=file]", str(source), "#submit", ".done"
            )
    canceller.join(timeout=5)
    assert UploadPage.attached is True
    assert UploadPage.submitted is False  # cancelled before the submit click


def test_disk_status_endpoint_probes_real_downloads_dir(monkeypatch, tmp_path):
    """Regression: the endpoint must use the concrete BrowserAutomation class
    (the lazy proxy cannot resolve the DOWNLOADS_DIR class attribute) and must
    create the probe target when missing."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cognition.disk_reservation import DiskReservationLedger

    probe_dir = tmp_path / "downloads"  # intentionally does not exist yet
    # Patch the concrete class attribute used inside the endpoint's local import.
    from app.tools.browser_automation import BrowserAutomation as Concrete
    monkeypatch.setattr(Concrete, "DOWNLOADS_DIR", probe_dir)
    monkeypatch.setattr("app.cognition.disk_reservation.disk_reservation_ledger", DiskReservationLedger(tmp_path / "res.db"))
    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    client = TestClient(app)
    response = client.get("/automation/browser/disk-status", headers={"X-API-Key": "owner-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["probe"]["free_bytes"] > 0
    assert probe_dir.exists()  # created before probing
