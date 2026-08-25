import os
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.cognition.browser_grounding import BrowserGroundingStore
from app.cognition.browser_adapters import browser_adapter_store
from app.cognition.disk_reservation import disk_reservation_ledger
from app.cognition.execution_control import (
    ExecutionCancelled,
    cooperative_checkpoint,
    current_execution_id,
    run_cancellable_blocking_call,
)

class BrowserAutomation:
    SCREENSHOTS_DIR = settings.DATA_DIR / "workspace" / "screenshots"
    DOWNLOADS_DIR = settings.DATA_DIR / "workspace" / "downloads"
    GROUNDING = BrowserGroundingStore(settings.DATA_DIR / "browser_grounding.db")
    DISK_LEDGER = disk_reservation_ledger
    ADAPTERS = browser_adapter_store
    # Persistent Chromium profile: survives across runs so owner logins (set
    # once via open_session) carry into later headless navigations. The
    # directory holds session cookies — treat it as sensitive owner data.
    PROFILE_DIR = settings.DATA_DIR / "browser_profile"
    # Live owner session state (one at a time; the process owns the profile).
    _session_browser = None
    _playwright_handle = None
    _session_tab = None

    @classmethod
    def _launch(cls, chromium, *, use_profile: bool = False, headless: bool = True):
        """Launch Chromium, optionally with the persistent owner profile."""
        if not use_profile:
            return chromium.launch(headless=headless)
        cls.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        # One writer at a time: Chromium locks the profile directory, so a
        # busy profile is reported honestly instead of corrupting it.
        lock = cls.PROFILE_DIR / "arena.lock"
        if lock.exists():
            return None
        lock.write_text("in-use", encoding="utf-8")
        context = chromium.launch_persistent_context(
            str(cls.PROFILE_DIR), headless=headless
        )
        # Wrap the context so `.close()` releases our advisory lock too.
        class _ContextWithLock:
            def __init__(self, ctx, lock_path):
                self._ctx = ctx
                self._lock = lock_path

            def new_page(self):
                return self._ctx.new_page()

            def close(self):
                try:
                    self._ctx.close()
                finally:
                    try:
                        self._lock.unlink(missing_ok=True)
                    except Exception:
                        pass

            def __getattr__(self, item):
                return getattr(self._ctx, item)

        return _ContextWithLock(context, lock)

    @classmethod
    def open_session(cls, url: str, headless: bool = False) -> Dict[str, Any]:
        """Open a browser with the persistent profile for the owner to log in.

        Non-blocking: the visible window stays open (owner logs in / solves
        checks at their own pace) until close_session is called. Later headless
        runs with use_profile=true reuse the saved session. This never bypasses
        any wall — the owner solves human checks interactively, the session
        persists.
        """
        if not url or not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        if cls._session_browser is not None:
            return {"success": False, "refused": True,
                    "error": "A profile session is already open; close it with close_session first"}
        try:
            cooperative_checkpoint("before_browser_session")
            from playwright.sync_api import sync_playwright
            cls._playwright_handle = sync_playwright().start()
            browser = cls._launch(cls._playwright_handle.chromium, use_profile=True, headless=headless)
            if browser is None:
                cls._playwright_handle.stop(); cls._playwright_handle = None
                return {"success": False, "refused": True,
                        "error": "Browser profile is already in use (lock file present)"}
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            cls._session_browser = browser
            session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
            tab = cls.GROUNDING.observe_tab(
                session_id=session_id, url=page.url, title=page.title(),
                profile_type="persistent-owner",
                evidence=["owner-opened persistent profile session", "page.url", "page.title"],
            )
            cls._session_tab = tab
            return {"success": True, "browser_session_id": session_id,
                    "tab_grounding": tab.to_dict(),
                    "note": "Window is open: log in, then call close_session to persist it. use_profile=true reuses it later."}
        except ExecutionCancelled:
            raise
        except Exception as exc:
            try:
                if cls._playwright_handle is not None:
                    cls._playwright_handle.stop()
            except Exception:
                pass
            cls._playwright_handle = None; cls._session_browser = None
            return {"success": False, "available": False, "error": str(exc)}

    @classmethod
    def close_session(cls) -> Dict[str, Any]:
        """Close the owner's open profile session, persisting login state."""
        browser = cls._session_browser
        cls._session_browser = None
        handle = cls._playwright_handle
        cls._playwright_handle = None
        tab = cls._session_tab
        cls._session_tab = None
        if browser is None:
            return {"success": False, "error": "No open profile session"}
        try:
            browser.close()
        finally:
            try:
                if handle is not None:
                    handle.stop()
            except Exception:
                pass
        if tab is not None:
            cls.GROUNDING.record_event(tab.tab_id, "session", "closed",
                                       evidence=["owner closed persistent session"])
        return {"success": True, "note": "Session closed; login state persisted in the profile."}

    @staticmethod
    def _hash_file(path: Path) -> str:
        import hashlib
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _download_destination(cls, suggested_filename: str) -> Path:
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(suggested_filename or "download.bin").name
        candidate = cls.DOWNLOADS_DIR / safe_name
        if candidate.exists():
            candidate = cls.DOWNLOADS_DIR / f"{candidate.stem}_{uuid.uuid4().hex[:8]}{candidate.suffix}"
        return candidate

    @classmethod
    def ensure_dir(cls):
        cls.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def download_file(cls, url: str, click_selector: str, expected_size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Download one file through an ephemeral tab and verify the local artifact.

        The transfer is disk-reserved before launch (worst-case quota when the
        size is unknown) and the save phase is owner-cancellable in flight; a
        cancelled save removes its partial artifact and releases the reservation.
        """
        if not url or not click_selector:
            return {"success": False, "error": "URL and click selector are required"}
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        max_bytes = max(1, int(settings.BROWSER_TRANSFER_MAX_MB)) * 1024 * 1024
        # Unknown size ⇒ reserve the worst-case quota, never zero.
        reserve_bytes = max(1, int(expected_size_bytes)) if expected_size_bytes else max_bytes
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # probe target must exist
        reservation = cls.DISK_LEDGER.reserve(
            "browser_download", reserve_bytes,
            target_root=cls.DOWNLOADS_DIR,
            execution_id=current_execution_id(),
        )
        if not reservation.get("success"):
            return {
                "success": False,
                "request_success": False,
                "side_effects": False,
                "error": reservation.get("detail", reservation.get("error", "insufficient_disk_space")),
                "disk_reservation": reservation,
            }
        reservation_id = reservation["reservation"]["reservation_id"]
        browser = None
        destination: Optional[Path] = None
        try:
            cooperative_checkpoint("before_browser_download")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("before_download_click")
                with page.expect_download(timeout=30000) as download_info:
                    page.click(click_selector)
                download = download_info.value
                destination = cls._download_destination(download.suggested_filename)

                def _abort_inflight() -> None:
                    # Closing the browser context aborts an in-flight transfer.
                    for interrupt in (
                        lambda: download.cancel(),
                        lambda: browser.close(),
                    ):
                        try:
                            interrupt()
                        except Exception:
                            pass

                # The remote fetch itself is cancellable: the cooperative runner
                # polls the owner cancel flag and invokes the browser abort.
                run_cancellable_blocking_call(
                    lambda: download.save_as(str(destination)),
                    cancel=_abort_inflight,
                    description="browser download save",
                )
                cooperative_checkpoint("after_download_save")
                if not destination.is_file():
                    cls.DISK_LEDGER.release(reservation_id, reason="download produced no artifact")
                    return {"success": False, "error": "Download completed but file was not observed"}
                size_bytes = destination.stat().st_size
                if size_bytes > max_bytes:
                    destination.unlink(missing_ok=True)
                    cls.DISK_LEDGER.release(reservation_id, reason="oversized artifact removed")
                    return {"success":False,"request_success":True,"error":"Downloaded artifact exceeded owner transfer quota and was removed","size_bytes":size_bytes,"max_bytes":max_bytes,"environment_verified":not destination.exists(),"side_effects":False,"disk_reservation":{"reservation_id":reservation_id,"status":"released"}}
                digest = cls._hash_file(destination)
                # Completed: the artifact now physically occupies the space.
                cls.DISK_LEDGER.consume(reservation_id, size_bytes, reason="verified download completed")
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["Playwright download event", "page.url", "page.title"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "download", "completed",
                    evidence=[f"path:{destination}", f"sha256:{digest}"],
                )
                browser.close(); browser = None
            return {
                "success": True, "environment_verified": True,
                "download_path": str(destination), "download_sha256": digest,
                "size_bytes": size_bytes,
                "browser_session_id": session_id, "tab_grounding": tab.to_dict(),
                "download_event": event, "profile_type": "ephemeral",
                "auth_state": "unknown", "side_effects": True,
                "rollback_path": str(destination), "rollback_sha256": digest,
                "disk_reservation": {
                    "reservation_id": reservation_id,
                    "reserved_bytes": reserve_bytes,
                    "actual_bytes": size_bytes,
                    "status": "consumed",
                },
            }
        except ExecutionCancelled:
            # Never assert the peer aborted cleanly: only local cleanup is known.
            partial_removed = None
            if destination is not None:
                try:
                    destination.unlink(missing_ok=True)
                    partial_removed = not destination.exists()
                except Exception:
                    partial_removed = False
            cls.DISK_LEDGER.release(reservation_id, reason="cancelled in flight")
            raise
        except Exception as exc:
            cls.DISK_LEDGER.release(reservation_id, reason=f"download failed: {exc}"[:120])
            return {"success": False, "available": False, "error": str(exc)}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def upload_file(cls, url: str, input_selector: str, file_path: str,
                    submit_selector: str, success_selector: str) -> Dict[str, Any]:
        """Upload and submit one file; success requires an observed success selector."""
        source = Path(file_path)
        if not source.is_file():
            return {"success": False, "request_success": False, "error": "Upload file not found"}
        if not all((url, input_selector, submit_selector, success_selector)):
            return {"success": False, "request_success": False, "error": "URL, input, submit and success selectors are required"}
        if not url.startswith(("http://", "https://")): url = f"https://{url}"
        browser = None
        try:
            size_bytes=source.stat().st_size;max_bytes=max(1,int(settings.BROWSER_TRANSFER_MAX_MB))*1024*1024
            if size_bytes>max_bytes:return {"success":False,"request_success":False,"side_effects":False,"error":"Upload exceeds owner transfer quota","size_bytes":size_bytes,"max_bytes":max_bytes}
            digest = cls._hash_file(source)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True); page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if page.is_visible(success_selector):
                    return {"success":False,"request_success":False,"environment_verified":False,"error":"Success selector was already visible before upload; it cannot verify this submission","side_effects":False}
                cooperative_checkpoint("before_browser_upload")

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                # Local file attach (no remote submission yet) is cancellable
                # without remote side effects.
                run_cancellable_blocking_call(
                    lambda: page.set_input_files(input_selector, str(source)),
                    cancel=_abort_inflight,
                    description="browser upload attach",
                )
                cooperative_checkpoint("before_browser_upload_submit")

                def _submit_and_wait() -> None:
                    page.click(submit_selector)
                    page.wait_for_selector(success_selector, timeout=30000, state="visible")

                # From the submit click onward, cancellation cannot prove the
                # remote service never received the payload.
                run_cancellable_blocking_call(
                    _submit_and_wait,
                    cancel=_abort_inflight,
                    description="browser upload submit",
                )
                observed = page.is_visible(success_selector)
                # Service-specific receipt extraction (owner-configured adapter):
                # the service's own receipt ID, extracted from the observed page.
                service_receipt = None
                adapter = cls.ADAPTERS.match(url)
                if adapter is not None and adapter.receipt_selector:
                    try:
                        element = page.query_selector(adapter.receipt_selector)
                        if element is not None:
                            if adapter.receipt_attribute == "text":
                                raw_receipt = element.inner_text()
                            else:
                                raw_receipt = element.get_attribute(adapter.receipt_attribute)
                            receipt_id = str(raw_receipt or "").strip() or None
                            if receipt_id:
                                service_receipt = {
                                    "service_id": adapter.service_id,
                                    "adapter_id": adapter.adapter_id,
                                    "receipt_id": receipt_id,
                                    "extracted_via": f"{adapter.receipt_selector}@{adapter.receipt_attribute}",
                                }
                    except Exception as exc:
                        app_logger.warning(f"Service receipt extraction failed for {adapter.service_id}: {exc}")
                        service_receipt = None  # honest: extraction failed, not invented
                session_id=f"browser_session_{uuid.uuid4().hex[:12]}"
                tab=cls.GROUNDING.observe_tab(session_id=session_id,url=page.url,title=page.title(),profile_type="ephemeral",evidence=["set_input_files completed","submit clicked",f"success selector visible:{success_selector}"])
                event_evidence=[f"local_sha256:{digest}",f"success_selector:{success_selector}"]
                if service_receipt:
                    event_evidence.append(f"service_receipt:{service_receipt['service_id']}:{service_receipt['receipt_id']}")
                event=cls.GROUNDING.record_event(tab.tab_id,"upload","completed" if observed else "unknown",evidence=event_evidence)
                browser.close();browser=None
            result={"success":observed,"request_success":True,"environment_verified":observed,"verification_unknown":not observed,"uploaded_file":str(source),"uploaded_sha256":digest,"size_bytes":size_bytes,"tab_grounding":tab.to_dict(),"upload_event":event,"auth_state":"unknown","side_effects":True,"service_receipt":service_receipt}
            if adapter is not None and service_receipt is not None and adapter.delete_supported:
                # A service-specific delete flow exists for this receipt: the
                # rollback becomes a concrete proposal, still requiring separate
                # Level-3 authorization to execute.
                result["rollback_supported"]=True
                result["rollback_reason"]=f"Owner adapter {adapter.adapter_id} defines a delete flow for {adapter.service_id}; deletion requires separate Level-3 authorization."
                result["rollback_compensation"]={"action":"browser_delete_upload","payload":{"service_id":adapter.service_id,"receipt_id":service_receipt["receipt_id"]}}
            else:
                result["rollback_supported"]=False
                result["rollback_reason"]="Remote upload cannot be deterministically removed without a service-specific delete API."+(f" (receipt extracted for {adapter.service_id}, but no delete flow is configured.)" if adapter is not None and service_receipt is not None else "")
            return result
        except ExecutionCancelled: raise
        except Exception as exc:
            return {"success":False,"request_success":True,"environment_verified":False,"verification_unknown":True,"side_effects":True,"error":str(exc),"note":"Submission may have reached the remote service; retry requires fresh observation and authorization."}
        finally:
            if browser is not None:
                try:browser.close()
                except Exception:pass

    @classmethod
    def delete_uploaded_file(cls, service_id: str, receipt_id: str) -> Dict[str, Any]:
        """Level-3 service-specific deletion of a previously uploaded receipt.

        Runs ONLY the owner-configured delete flow for the service: the adapter's
        delete URL template (receipt id URL-quoted) plus an observed confirmation
        selector. Deletion is verified by that observation; it is never assumed
        from navigation alone, and Arena cannot undo a deletion (re-upload is a
        fresh authorized action).
        """
        if not service_id or not receipt_id:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": "service_id and receipt_id are required"}
        adapter = cls.ADAPTERS.get_by_service(str(service_id))
        if adapter is None:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"No owner-configured browser adapter for service '{service_id}'",
                    "note": "Service-specific deletion requires owner adapter configuration; refusing rather than improvising a delete flow."}
        if not adapter.delete_supported:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"Adapter '{service_id}' has no delete flow configured",
                    "note": "delete_url_template and confirm_selector are required for deletion."}
        from urllib.parse import quote
        delete_url = adapter.delete_url_template.format(receipt_id=quote(str(receipt_id), safe=""))
        browser = None
        try:
            cooperative_checkpoint("before_browser_delete_upload")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                def _navigate_and_confirm() -> None:
                    page.goto(delete_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_selector(adapter.confirm_selector, timeout=30000, state="visible")

                # Remote destructive action: cancellable in flight, with the
                # standing caveat that cancellation cannot prove the service
                # never processed the request.
                run_cancellable_blocking_call(
                    _navigate_and_confirm, cancel=_abort_inflight,
                    description="browser delete upload",
                )
                observed = page.is_visible(adapter.confirm_selector)
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["owner-configured delete flow", f"service:{adapter.service_id}", f"receipt:{receipt_id}"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "upload_delete", "completed" if observed else "unknown",
                    evidence=[f"delete_url:{delete_url}", f"confirm_selector:{adapter.confirm_selector}"],
                )
                browser.close(); browser = None
            return {
                "success": observed, "request_success": True,
                "environment_verified": observed, "verification_unknown": not observed,
                "service_id": adapter.service_id, "receipt_id": str(receipt_id),
                "delete_url": delete_url, "tab_grounding": tab.to_dict(),
                "delete_event": event, "side_effects": True,
                "rollback_supported": False,
                "rollback_reason": "A completed deletion cannot be undone by Arena; re-upload is a fresh action requiring authorization.",
                "note": "Deletion verified by the adapter's confirmation selector observation, nothing stronger.",
            }
        except ExecutionCancelled:
            raise
        except Exception as exc:
            return {"success": False, "request_success": True, "environment_verified": False,
                    "verification_unknown": True, "side_effects": True, "error": str(exc),
                    "note": "Delete request may have reached the service; outcome requires re-observation."}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def navigate_and_extract(
        cls,
        url: str,
        fill_inputs: Optional[Dict[str, str]] = None,
        click_selectors: Optional[List[str]] = None,
        submit_form: bool = False
    ) -> Dict[str, Any]:
        """
        Automates real browser navigation using Playwright with HTTP fallback.
        Navigates to URL, fills inputs, clicks elements, takes a screenshot, and extracts page text.
        Submitting forms or clicking submit buttons enforces Level 3 Safety Policy approval.
        """
        cls.ensure_dir()
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Safety Check: Submitting forms or publishing data requires Level 3 approval
        if submit_form:
            allowed, reason, level = PolicyEvaluator.evaluate_action("submit_form", {"url": url})
            if not allowed:
                return {
                    "success": False,
                    "error": f"Policy Blocked: {reason}",
                    "authority_level": level,
                    "url": url
                }

        filename = f"browser_{uuid.uuid4().hex[:8]}.png"
        screenshot_path = cls.SCREENSHOTS_DIR / filename

        try:
            cooperative_checkpoint("before_playwright_import")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                cooperative_checkpoint("before_browser_launch")
                browser = p.chromium.launch(headless=True)
                cooperative_checkpoint("after_browser_launch")
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})

                app_logger.info(f"Playwright navigating to '{url}'...")
                cooperative_checkpoint("before_browser_navigation")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("after_browser_navigation")

                # Fill out input fields if specified
                if fill_inputs:
                    for selector, value in fill_inputs.items():
                        cooperative_checkpoint("before_browser_fill")
                        try:
                            if page.is_visible(selector):
                                page.fill(selector, value)
                        except ExecutionCancelled:
                            raise
                        except Exception as ie:
                            app_logger.warning(f"Could not fill input '{selector}': {ie}")

                # Click elements if specified
                if click_selectors:
                    for selector in click_selectors:
                        cooperative_checkpoint("before_browser_click")
                        try:
                            if page.is_visible(selector):
                                page.click(selector)
                                page.wait_for_timeout(1000)
                        except ExecutionCancelled:
                            raise
                        except Exception as ce:
                            app_logger.warning(f"Could not click '{selector}': {ce}")

                cooperative_checkpoint("before_browser_capture")
                page.screenshot(path=str(screenshot_path))
                page_title = page.title()
                page_text = page.inner_text("body") if page.query_selector("body") else ""
                cooperative_checkpoint("before_browser_close")
                browser.close()

            audit_logger.info(f"Automated browser navigation to '{url}' completed.")
            browser_session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
            tab = cls.GROUNDING.observe_tab(
                session_id=browser_session_id, url=url, title=page_title,
                profile_type="ephemeral",
                evidence=["Playwright page.url", "Playwright page.title", "page screenshot captured"],
            )

            return {
                "success": True,
                "url": url,
                "title": page_title,
                "content_snippet": page_text[:5000],
                "screenshot_path": str(screenshot_path),
                "image_url": f"/static/workspace/screenshots/{filename}",
                "text_length": len(page_text),
                "browser_session_id": browser_session_id,
                "tab_grounding": tab.to_dict(),
                "profile_type": "ephemeral",
                "auth_state": "unknown",
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Playwright launch notice ({e}). Falling back to HTTP HTML scraper...")
            # Fallback using httpx & BeautifulSoup if Playwright browser binaries are not downloaded locally
            try:
                import httpx
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
                    resp = run_cancellable_blocking_call(
                        lambda: client.get(url),
                        cancel=client.close,
                        description="browser HTTP fallback",
                    )
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        text = soup.get_text(separator="\n", strip=True)
                        title = soup.title.string if soup.title and soup.title.string else url
                        return {
                            "success": True,
                            "url": url,
                            "title": title,
                            "content_snippet": text[:5000],
                            "screenshot_path": "",
                            "image_url": "",
                            "text_length": len(text)
                        }
            except ExecutionCancelled:
                raise
            except Exception:
                pass

            return {
                "success": False,
                "available": False,
                "url": url,
                "error": (
                    "Browser automation and HTTP fallback both failed; navigation was not verified. "
                    f"Playwright error: {e}"
                ),
                "title": "",
                "content_snippet": "",
                "screenshot_path": "",
                "image_url": "",
                "text_length": 0,
            }
    @classmethod
    def _download_destination(cls, suggested_filename: str) -> Path:
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = Path(suggested_filename or "download.bin").name
        candidate = cls.DOWNLOADS_DIR / safe_name
        if candidate.exists():
            candidate = cls.DOWNLOADS_DIR / f"{candidate.stem}_{uuid.uuid4().hex[:8]}{candidate.suffix}"
        return candidate

    @classmethod
    def ensure_dir(cls):
        cls.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def download_file(cls, url: str, click_selector: str, expected_size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Download one file through an ephemeral tab and verify the local artifact.

        The transfer is disk-reserved before launch (worst-case quota when the
        size is unknown) and the save phase is owner-cancellable in flight; a
        cancelled save removes its partial artifact and releases the reservation.
        """
        if not url or not click_selector:
            return {"success": False, "error": "URL and click selector are required"}
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        max_bytes = max(1, int(settings.BROWSER_TRANSFER_MAX_MB)) * 1024 * 1024
        # Unknown size ⇒ reserve the worst-case quota, never zero.
        reserve_bytes = max(1, int(expected_size_bytes)) if expected_size_bytes else max_bytes
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # probe target must exist
        reservation = cls.DISK_LEDGER.reserve(
            "browser_download", reserve_bytes,
            target_root=cls.DOWNLOADS_DIR,
            execution_id=current_execution_id(),
        )
        if not reservation.get("success"):
            return {
                "success": False,
                "request_success": False,
                "side_effects": False,
                "error": reservation.get("detail", reservation.get("error", "insufficient_disk_space")),
                "disk_reservation": reservation,
            }
        reservation_id = reservation["reservation"]["reservation_id"]
        browser = None
        destination: Optional[Path] = None
        try:
            cooperative_checkpoint("before_browser_download")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("before_download_click")
                with page.expect_download(timeout=30000) as download_info:
                    page.click(click_selector)
                download = download_info.value
                destination = cls._download_destination(download.suggested_filename)

                def _abort_inflight() -> None:
                    # Closing the browser context aborts an in-flight transfer.
                    for interrupt in (
                        lambda: download.cancel(),
                        lambda: browser.close(),
                    ):
                        try:
                            interrupt()
                        except Exception:
                            pass

                # The remote fetch itself is cancellable: the cooperative runner
                # polls the owner cancel flag and invokes the browser abort.
                run_cancellable_blocking_call(
                    lambda: download.save_as(str(destination)),
                    cancel=_abort_inflight,
                    description="browser download save",
                )
                cooperative_checkpoint("after_download_save")
                if not destination.is_file():
                    cls.DISK_LEDGER.release(reservation_id, reason="download produced no artifact")
                    return {"success": False, "error": "Download completed but file was not observed"}
                size_bytes = destination.stat().st_size
                if size_bytes > max_bytes:
                    destination.unlink(missing_ok=True)
                    cls.DISK_LEDGER.release(reservation_id, reason="oversized artifact removed")
                    return {"success":False,"request_success":True,"error":"Downloaded artifact exceeded owner transfer quota and was removed","size_bytes":size_bytes,"max_bytes":max_bytes,"environment_verified":not destination.exists(),"side_effects":False,"disk_reservation":{"reservation_id":reservation_id,"status":"released"}}
                digest = cls._hash_file(destination)
                # Completed: the artifact now physically occupies the space.
                cls.DISK_LEDGER.consume(reservation_id, size_bytes, reason="verified download completed")
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["Playwright download event", "page.url", "page.title"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "download", "completed",
                    evidence=[f"path:{destination}", f"sha256:{digest}"],
                )
                browser.close(); browser = None
            return {
                "success": True, "environment_verified": True,
                "download_path": str(destination), "download_sha256": digest,
                "size_bytes": size_bytes,
                "browser_session_id": session_id, "tab_grounding": tab.to_dict(),
                "download_event": event, "profile_type": "ephemeral",
                "auth_state": "unknown", "side_effects": True,
                "rollback_path": str(destination), "rollback_sha256": digest,
                "disk_reservation": {
                    "reservation_id": reservation_id,
                    "reserved_bytes": reserve_bytes,
                    "actual_bytes": size_bytes,
                    "status": "consumed",
                },
            }
        except ExecutionCancelled:
            # Never assert the peer aborted cleanly: only local cleanup is known.
            partial_removed = None
            if destination is not None:
                try:
                    destination.unlink(missing_ok=True)
                    partial_removed = not destination.exists()
                except Exception:
                    partial_removed = False
            cls.DISK_LEDGER.release(reservation_id, reason="cancelled in flight")
            raise
        except Exception as exc:
            cls.DISK_LEDGER.release(reservation_id, reason=f"download failed: {exc}"[:120])
            return {"success": False, "available": False, "error": str(exc)}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def upload_file(cls, url: str, input_selector: str, file_path: str,
                    submit_selector: str, success_selector: str) -> Dict[str, Any]:
        """Upload and submit one file; success requires an observed success selector."""
        source = Path(file_path)
        if not source.is_file():
            return {"success": False, "request_success": False, "error": "Upload file not found"}
        if not all((url, input_selector, submit_selector, success_selector)):
            return {"success": False, "request_success": False, "error": "URL, input, submit and success selectors are required"}
        if not url.startswith(("http://", "https://")): url = f"https://{url}"
        browser = None
        try:
            size_bytes=source.stat().st_size;max_bytes=max(1,int(settings.BROWSER_TRANSFER_MAX_MB))*1024*1024
            if size_bytes>max_bytes:return {"success":False,"request_success":False,"side_effects":False,"error":"Upload exceeds owner transfer quota","size_bytes":size_bytes,"max_bytes":max_bytes}
            digest = cls._hash_file(source)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True); page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if page.is_visible(success_selector):
                    return {"success":False,"request_success":False,"environment_verified":False,"error":"Success selector was already visible before upload; it cannot verify this submission","side_effects":False}
                cooperative_checkpoint("before_browser_upload")

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                # Local file attach (no remote submission yet) is cancellable
                # without remote side effects.
                run_cancellable_blocking_call(
                    lambda: page.set_input_files(input_selector, str(source)),
                    cancel=_abort_inflight,
                    description="browser upload attach",
                )
                cooperative_checkpoint("before_browser_upload_submit")

                def _submit_and_wait() -> None:
                    page.click(submit_selector)
                    page.wait_for_selector(success_selector, timeout=30000, state="visible")

                # From the submit click onward, cancellation cannot prove the
                # remote service never received the payload.
                run_cancellable_blocking_call(
                    _submit_and_wait,
                    cancel=_abort_inflight,
                    description="browser upload submit",
                )
                observed = page.is_visible(success_selector)
                # Service-specific receipt extraction (owner-configured adapter):
                # the service's own receipt ID, extracted from the observed page.
                service_receipt = None
                adapter = cls.ADAPTERS.match(url)
                if adapter is not None and adapter.receipt_selector:
                    try:
                        element = page.query_selector(adapter.receipt_selector)
                        if element is not None:
                            if adapter.receipt_attribute == "text":
                                raw_receipt = element.inner_text()
                            else:
                                raw_receipt = element.get_attribute(adapter.receipt_attribute)
                            receipt_id = str(raw_receipt or "").strip() or None
                            if receipt_id:
                                service_receipt = {
                                    "service_id": adapter.service_id,
                                    "adapter_id": adapter.adapter_id,
                                    "receipt_id": receipt_id,
                                    "extracted_via": f"{adapter.receipt_selector}@{adapter.receipt_attribute}",
                                }
                    except Exception as exc:
                        app_logger.warning(f"Service receipt extraction failed for {adapter.service_id}: {exc}")
                        service_receipt = None  # honest: extraction failed, not invented
                session_id=f"browser_session_{uuid.uuid4().hex[:12]}"
                tab=cls.GROUNDING.observe_tab(session_id=session_id,url=page.url,title=page.title(),profile_type="ephemeral",evidence=["set_input_files completed","submit clicked",f"success selector visible:{success_selector}"])
                event_evidence=[f"local_sha256:{digest}",f"success_selector:{success_selector}"]
                if service_receipt:
                    event_evidence.append(f"service_receipt:{service_receipt['service_id']}:{service_receipt['receipt_id']}")
                event=cls.GROUNDING.record_event(tab.tab_id,"upload","completed" if observed else "unknown",evidence=event_evidence)
                browser.close();browser=None
            result={"success":observed,"request_success":True,"environment_verified":observed,"verification_unknown":not observed,"uploaded_file":str(source),"uploaded_sha256":digest,"size_bytes":size_bytes,"tab_grounding":tab.to_dict(),"upload_event":event,"auth_state":"unknown","side_effects":True,"service_receipt":service_receipt}
            if adapter is not None and service_receipt is not None and adapter.delete_supported:
                # A service-specific delete flow exists for this receipt: the
                # rollback becomes a concrete proposal, still requiring separate
                # Level-3 authorization to execute.
                result["rollback_supported"]=True
                result["rollback_reason"]=f"Owner adapter {adapter.adapter_id} defines a delete flow for {adapter.service_id}; deletion requires separate Level-3 authorization."
                result["rollback_compensation"]={"action":"browser_delete_upload","payload":{"service_id":adapter.service_id,"receipt_id":service_receipt["receipt_id"]}}
            else:
                result["rollback_supported"]=False
                result["rollback_reason"]="Remote upload cannot be deterministically removed without a service-specific delete API."+(f" (receipt extracted for {adapter.service_id}, but no delete flow is configured.)" if adapter is not None and service_receipt is not None else "")
            return result
        except ExecutionCancelled: raise
        except Exception as exc:
            return {"success":False,"request_success":True,"environment_verified":False,"verification_unknown":True,"side_effects":True,"error":str(exc),"note":"Submission may have reached the remote service; retry requires fresh observation and authorization."}
        finally:
            if browser is not None:
                try:browser.close()
                except Exception:pass

    @classmethod
    def delete_uploaded_file(cls, service_id: str, receipt_id: str) -> Dict[str, Any]:
        """Level-3 service-specific deletion of a previously uploaded receipt.

        Runs ONLY the owner-configured delete flow for the service: the adapter's
        delete URL template (receipt id URL-quoted) plus an observed confirmation
        selector. Deletion is verified by that observation; it is never assumed
        from navigation alone, and Arena cannot undo a deletion (re-upload is a
        fresh authorized action).
        """
        if not service_id or not receipt_id:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": "service_id and receipt_id are required"}
        adapter = cls.ADAPTERS.get_by_service(str(service_id))
        if adapter is None:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"No owner-configured browser adapter for service '{service_id}'",
                    "note": "Service-specific deletion requires owner adapter configuration; refusing rather than improvising a delete flow."}
        if not adapter.delete_supported:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"Adapter '{service_id}' has no delete flow configured",
                    "note": "delete_url_template and confirm_selector are required for deletion."}
        from urllib.parse import quote
        delete_url = adapter.delete_url_template.format(receipt_id=quote(str(receipt_id), safe=""))
        browser = None
        try:
            cooperative_checkpoint("before_browser_delete_upload")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                def _navigate_and_confirm() -> None:
                    page.goto(delete_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_selector(adapter.confirm_selector, timeout=30000, state="visible")

                # Remote destructive action: cancellable in flight, with the
                # standing caveat that cancellation cannot prove the service
                # never processed the request.
                run_cancellable_blocking_call(
                    _navigate_and_confirm, cancel=_abort_inflight,
                    description="browser delete upload",
                )
                observed = page.is_visible(adapter.confirm_selector)
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["owner-configured delete flow", f"service:{adapter.service_id}", f"receipt:{receipt_id}"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "upload_delete", "completed" if observed else "unknown",
                    evidence=[f"delete_url:{delete_url}", f"confirm_selector:{adapter.confirm_selector}"],
                )
                browser.close(); browser = None
            return {
                "success": observed, "request_success": True,
                "environment_verified": observed, "verification_unknown": not observed,
                "service_id": adapter.service_id, "receipt_id": str(receipt_id),
                "delete_url": delete_url, "tab_grounding": tab.to_dict(),
                "delete_event": event, "side_effects": True,
                "rollback_supported": False,
                "rollback_reason": "A completed deletion cannot be undone by Arena; re-upload is a fresh action requiring authorization.",
                "note": "Deletion verified by the adapter's confirmation selector observation, nothing stronger.",
            }
        except ExecutionCancelled:
            raise
        except Exception as exc:
            return {"success": False, "request_success": True, "environment_verified": False,
                    "verification_unknown": True, "side_effects": True, "error": str(exc),
                    "note": "Delete request may have reached the service; outcome requires re-observation."}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def navigate_and_extract(
        cls,
        url: str,
        fill_inputs: Optional[Dict[str, str]] = None,
        click_selectors: Optional[List[str]] = None,
        submit_form: bool = False
    ) -> Dict[str, Any]:
        """
        Automates real browser navigation using Playwright with HTTP fallback.
        Navigates to URL, fills inputs, clicks elements, takes a screenshot, and extracts page text.
        Submitting forms or clicking submit buttons enforces Level 3 Safety Policy approval.
        """
        cls.ensure_dir()
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Safety Check: Submitting forms or publishing data requires Level 3 approval
        if submit_form:
            allowed, reason, level = PolicyEvaluator.evaluate_action("submit_form", {"url": url})
            if not allowed:
                return {
                    "success": False,
                    "error": f"Policy Blocked: {reason}",
                    "authority_level": level,
                    "url": url
                }

        filename = f"browser_{uuid.uuid4().hex[:8]}.png"
        screenshot_path = cls.SCREENSHOTS_DIR / filename

        try:
            cooperative_checkpoint("before_playwright_import")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                cooperative_checkpoint("before_browser_launch")
                browser = p.chromium.launch(headless=True)
                cooperative_checkpoint("after_browser_launch")
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})

                app_logger.info(f"Playwright navigating to '{url}'...")
                cooperative_checkpoint("before_browser_navigation")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("after_browser_navigation")

                # Fill out input fields if specified
                if fill_inputs:
                    for selector, value in fill_inputs.items():
                        cooperative_checkpoint("before_browser_fill")
                        try:
                            if page.is_visible(selector):
                                page.fill(selector, value)
                        except ExecutionCancelled:
                            raise
                        except Exception as ie:
                            app_logger.warning(f"Could not fill input '{selector}': {ie}")

                # Click elements if specified
                if click_selectors:
                    for selector in click_selectors:
                        cooperative_checkpoint("before_browser_click")
                        try:
                            if page.is_visible(selector):
                                page.click(selector)
                                page.wait_for_timeout(1000)
                        except ExecutionCancelled:
                            raise
                        except Exception as ce:
                            app_logger.warning(f"Could not click '{selector}': {ce}")

                cooperative_checkpoint("before_browser_capture")
                page.screenshot(path=str(screenshot_path))
                page_title = page.title()
                page_text = page.inner_text("body") if page.query_selector("body") else ""
                cooperative_checkpoint("before_browser_close")
                browser.close()

            audit_logger.info(f"Automated browser navigation to '{url}' completed.")
            browser_session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
            tab = cls.GROUNDING.observe_tab(
                session_id=browser_session_id, url=url, title=page_title,
                profile_type="ephemeral",
                evidence=["Playwright page.url", "Playwright page.title", "page screenshot captured"],
            )

            return {
                "success": True,
                "url": url,
                "title": page_title,
                "content_snippet": page_text[:5000],
                "screenshot_path": str(screenshot_path),
                "image_url": f"/static/workspace/screenshots/{filename}",
                "text_length": len(page_text),
                "browser_session_id": browser_session_id,
                "tab_grounding": tab.to_dict(),
                "profile_type": "ephemeral",
                "auth_state": "unknown",
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Playwright launch notice ({e}). Falling back to HTTP HTML scraper...")
            # Fallback using httpx & BeautifulSoup if Playwright browser binaries are not downloaded locally
            try:
                import httpx
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
                    resp = run_cancellable_blocking_call(
                        lambda: client.get(url),
                        cancel=client.close,
                        description="browser HTTP fallback",
                    )
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        text = soup.get_text(separator="\n", strip=True)
                        title = soup.title.string if soup.title and soup.title.string else url
                        return {
                            "success": True,
                            "url": url,
                            "title": title,
                            "content_snippet": text[:5000],
                            "screenshot_path": "",
                            "image_url": "",
                            "text_length": len(text)
                        }
            except ExecutionCancelled:
                raise
            except Exception:
                pass

            return {
                "success": False,
                "available": False,
                "url": url,
                "error": (
                    "Browser automation and HTTP fallback both failed; navigation was not verified. "
                    f"Playwright error: {e}"
                ),
                "title": "",
                "content_snippet": "",
                "screenshot_path": "",
                "image_url": "",
                "text_length": 0,
            }
    @classmethod
    def ensure_dir(cls):
        cls.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def download_file(cls, url: str, click_selector: str, expected_size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Download one file through an ephemeral tab and verify the local artifact.

        The transfer is disk-reserved before launch (worst-case quota when the
        size is unknown) and the save phase is owner-cancellable in flight; a
        cancelled save removes its partial artifact and releases the reservation.
        """
        if not url or not click_selector:
            return {"success": False, "error": "URL and click selector are required"}
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        max_bytes = max(1, int(settings.BROWSER_TRANSFER_MAX_MB)) * 1024 * 1024
        # Unknown size ⇒ reserve the worst-case quota, never zero.
        reserve_bytes = max(1, int(expected_size_bytes)) if expected_size_bytes else max_bytes
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # probe target must exist
        reservation = cls.DISK_LEDGER.reserve(
            "browser_download", reserve_bytes,
            target_root=cls.DOWNLOADS_DIR,
            execution_id=current_execution_id(),
        )
        if not reservation.get("success"):
            return {
                "success": False,
                "request_success": False,
                "side_effects": False,
                "error": reservation.get("detail", reservation.get("error", "insufficient_disk_space")),
                "disk_reservation": reservation,
            }
        reservation_id = reservation["reservation"]["reservation_id"]
        browser = None
        destination: Optional[Path] = None
        try:
            cooperative_checkpoint("before_browser_download")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("before_download_click")
                with page.expect_download(timeout=30000) as download_info:
                    page.click(click_selector)
                download = download_info.value
                destination = cls._download_destination(download.suggested_filename)

                def _abort_inflight() -> None:
                    # Closing the browser context aborts an in-flight transfer.
                    for interrupt in (
                        lambda: download.cancel(),
                        lambda: browser.close(),
                    ):
                        try:
                            interrupt()
                        except Exception:
                            pass

                # The remote fetch itself is cancellable: the cooperative runner
                # polls the owner cancel flag and invokes the browser abort.
                run_cancellable_blocking_call(
                    lambda: download.save_as(str(destination)),
                    cancel=_abort_inflight,
                    description="browser download save",
                )
                cooperative_checkpoint("after_download_save")
                if not destination.is_file():
                    cls.DISK_LEDGER.release(reservation_id, reason="download produced no artifact")
                    return {"success": False, "error": "Download completed but file was not observed"}
                size_bytes = destination.stat().st_size
                if size_bytes > max_bytes:
                    destination.unlink(missing_ok=True)
                    cls.DISK_LEDGER.release(reservation_id, reason="oversized artifact removed")
                    return {"success":False,"request_success":True,"error":"Downloaded artifact exceeded owner transfer quota and was removed","size_bytes":size_bytes,"max_bytes":max_bytes,"environment_verified":not destination.exists(),"side_effects":False,"disk_reservation":{"reservation_id":reservation_id,"status":"released"}}
                digest = cls._hash_file(destination)
                # Completed: the artifact now physically occupies the space.
                cls.DISK_LEDGER.consume(reservation_id, size_bytes, reason="verified download completed")
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["Playwright download event", "page.url", "page.title"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "download", "completed",
                    evidence=[f"path:{destination}", f"sha256:{digest}"],
                )
                browser.close(); browser = None
            return {
                "success": True, "environment_verified": True,
                "download_path": str(destination), "download_sha256": digest,
                "size_bytes": size_bytes,
                "browser_session_id": session_id, "tab_grounding": tab.to_dict(),
                "download_event": event, "profile_type": "ephemeral",
                "auth_state": "unknown", "side_effects": True,
                "rollback_path": str(destination), "rollback_sha256": digest,
                "disk_reservation": {
                    "reservation_id": reservation_id,
                    "reserved_bytes": reserve_bytes,
                    "actual_bytes": size_bytes,
                    "status": "consumed",
                },
            }
        except ExecutionCancelled:
            # Never assert the peer aborted cleanly: only local cleanup is known.
            partial_removed = None
            if destination is not None:
                try:
                    destination.unlink(missing_ok=True)
                    partial_removed = not destination.exists()
                except Exception:
                    partial_removed = False
            cls.DISK_LEDGER.release(reservation_id, reason="cancelled in flight")
            raise
        except Exception as exc:
            cls.DISK_LEDGER.release(reservation_id, reason=f"download failed: {exc}"[:120])
            return {"success": False, "available": False, "error": str(exc)}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def upload_file(cls, url: str, input_selector: str, file_path: str,
                    submit_selector: str, success_selector: str) -> Dict[str, Any]:
        """Upload and submit one file; success requires an observed success selector."""
        source = Path(file_path)
        if not source.is_file():
            return {"success": False, "request_success": False, "error": "Upload file not found"}
        if not all((url, input_selector, submit_selector, success_selector)):
            return {"success": False, "request_success": False, "error": "URL, input, submit and success selectors are required"}
        if not url.startswith(("http://", "https://")): url = f"https://{url}"
        browser = None
        try:
            size_bytes=source.stat().st_size;max_bytes=max(1,int(settings.BROWSER_TRANSFER_MAX_MB))*1024*1024
            if size_bytes>max_bytes:return {"success":False,"request_success":False,"side_effects":False,"error":"Upload exceeds owner transfer quota","size_bytes":size_bytes,"max_bytes":max_bytes}
            digest = cls._hash_file(source)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True); page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if page.is_visible(success_selector):
                    return {"success":False,"request_success":False,"environment_verified":False,"error":"Success selector was already visible before upload; it cannot verify this submission","side_effects":False}
                cooperative_checkpoint("before_browser_upload")

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                # Local file attach (no remote submission yet) is cancellable
                # without remote side effects.
                run_cancellable_blocking_call(
                    lambda: page.set_input_files(input_selector, str(source)),
                    cancel=_abort_inflight,
                    description="browser upload attach",
                )
                cooperative_checkpoint("before_browser_upload_submit")

                def _submit_and_wait() -> None:
                    page.click(submit_selector)
                    page.wait_for_selector(success_selector, timeout=30000, state="visible")

                # From the submit click onward, cancellation cannot prove the
                # remote service never received the payload.
                run_cancellable_blocking_call(
                    _submit_and_wait,
                    cancel=_abort_inflight,
                    description="browser upload submit",
                )
                observed = page.is_visible(success_selector)
                # Service-specific receipt extraction (owner-configured adapter):
                # the service's own receipt ID, extracted from the observed page.
                service_receipt = None
                adapter = cls.ADAPTERS.match(url)
                if adapter is not None and adapter.receipt_selector:
                    try:
                        element = page.query_selector(adapter.receipt_selector)
                        if element is not None:
                            if adapter.receipt_attribute == "text":
                                raw_receipt = element.inner_text()
                            else:
                                raw_receipt = element.get_attribute(adapter.receipt_attribute)
                            receipt_id = str(raw_receipt or "").strip() or None
                            if receipt_id:
                                service_receipt = {
                                    "service_id": adapter.service_id,
                                    "adapter_id": adapter.adapter_id,
                                    "receipt_id": receipt_id,
                                    "extracted_via": f"{adapter.receipt_selector}@{adapter.receipt_attribute}",
                                }
                    except Exception as exc:
                        app_logger.warning(f"Service receipt extraction failed for {adapter.service_id}: {exc}")
                        service_receipt = None  # honest: extraction failed, not invented
                session_id=f"browser_session_{uuid.uuid4().hex[:12]}"
                tab=cls.GROUNDING.observe_tab(session_id=session_id,url=page.url,title=page.title(),profile_type="ephemeral",evidence=["set_input_files completed","submit clicked",f"success selector visible:{success_selector}"])
                event_evidence=[f"local_sha256:{digest}",f"success_selector:{success_selector}"]
                if service_receipt:
                    event_evidence.append(f"service_receipt:{service_receipt['service_id']}:{service_receipt['receipt_id']}")
                event=cls.GROUNDING.record_event(tab.tab_id,"upload","completed" if observed else "unknown",evidence=event_evidence)
                browser.close();browser=None
            result={"success":observed,"request_success":True,"environment_verified":observed,"verification_unknown":not observed,"uploaded_file":str(source),"uploaded_sha256":digest,"size_bytes":size_bytes,"tab_grounding":tab.to_dict(),"upload_event":event,"auth_state":"unknown","side_effects":True,"service_receipt":service_receipt}
            if adapter is not None and service_receipt is not None and adapter.delete_supported:
                # A service-specific delete flow exists for this receipt: the
                # rollback becomes a concrete proposal, still requiring separate
                # Level-3 authorization to execute.
                result["rollback_supported"]=True
                result["rollback_reason"]=f"Owner adapter {adapter.adapter_id} defines a delete flow for {adapter.service_id}; deletion requires separate Level-3 authorization."
                result["rollback_compensation"]={"action":"browser_delete_upload","payload":{"service_id":adapter.service_id,"receipt_id":service_receipt["receipt_id"]}}
            else:
                result["rollback_supported"]=False
                result["rollback_reason"]="Remote upload cannot be deterministically removed without a service-specific delete API."+(f" (receipt extracted for {adapter.service_id}, but no delete flow is configured.)" if adapter is not None and service_receipt is not None else "")
            return result
        except ExecutionCancelled: raise
        except Exception as exc:
            return {"success":False,"request_success":True,"environment_verified":False,"verification_unknown":True,"side_effects":True,"error":str(exc),"note":"Submission may have reached the remote service; retry requires fresh observation and authorization."}
        finally:
            if browser is not None:
                try:browser.close()
                except Exception:pass

    @classmethod
    def delete_uploaded_file(cls, service_id: str, receipt_id: str) -> Dict[str, Any]:
        """Level-3 service-specific deletion of a previously uploaded receipt.

        Runs ONLY the owner-configured delete flow for the service: the adapter's
        delete URL template (receipt id URL-quoted) plus an observed confirmation
        selector. Deletion is verified by that observation; it is never assumed
        from navigation alone, and Arena cannot undo a deletion (re-upload is a
        fresh authorized action).
        """
        if not service_id or not receipt_id:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": "service_id and receipt_id are required"}
        adapter = cls.ADAPTERS.get_by_service(str(service_id))
        if adapter is None:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"No owner-configured browser adapter for service '{service_id}'",
                    "note": "Service-specific deletion requires owner adapter configuration; refusing rather than improvising a delete flow."}
        if not adapter.delete_supported:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"Adapter '{service_id}' has no delete flow configured",
                    "note": "delete_url_template and confirm_selector are required for deletion."}
        from urllib.parse import quote
        delete_url = adapter.delete_url_template.format(receipt_id=quote(str(receipt_id), safe=""))
        browser = None
        try:
            cooperative_checkpoint("before_browser_delete_upload")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                def _navigate_and_confirm() -> None:
                    page.goto(delete_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_selector(adapter.confirm_selector, timeout=30000, state="visible")

                # Remote destructive action: cancellable in flight, with the
                # standing caveat that cancellation cannot prove the service
                # never processed the request.
                run_cancellable_blocking_call(
                    _navigate_and_confirm, cancel=_abort_inflight,
                    description="browser delete upload",
                )
                observed = page.is_visible(adapter.confirm_selector)
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["owner-configured delete flow", f"service:{adapter.service_id}", f"receipt:{receipt_id}"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "upload_delete", "completed" if observed else "unknown",
                    evidence=[f"delete_url:{delete_url}", f"confirm_selector:{adapter.confirm_selector}"],
                )
                browser.close(); browser = None
            return {
                "success": observed, "request_success": True,
                "environment_verified": observed, "verification_unknown": not observed,
                "service_id": adapter.service_id, "receipt_id": str(receipt_id),
                "delete_url": delete_url, "tab_grounding": tab.to_dict(),
                "delete_event": event, "side_effects": True,
                "rollback_supported": False,
                "rollback_reason": "A completed deletion cannot be undone by Arena; re-upload is a fresh action requiring authorization.",
                "note": "Deletion verified by the adapter's confirmation selector observation, nothing stronger.",
            }
        except ExecutionCancelled:
            raise
        except Exception as exc:
            return {"success": False, "request_success": True, "environment_verified": False,
                    "verification_unknown": True, "side_effects": True, "error": str(exc),
                    "note": "Delete request may have reached the service; outcome requires re-observation."}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def navigate_and_extract(
        cls,
        url: str,
        fill_inputs: Optional[Dict[str, str]] = None,
        click_selectors: Optional[List[str]] = None,
        submit_form: bool = False
    ) -> Dict[str, Any]:
        """
        Automates real browser navigation using Playwright with HTTP fallback.
        Navigates to URL, fills inputs, clicks elements, takes a screenshot, and extracts page text.
        Submitting forms or clicking submit buttons enforces Level 3 Safety Policy approval.
        """
        cls.ensure_dir()
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Safety Check: Submitting forms or publishing data requires Level 3 approval
        if submit_form:
            allowed, reason, level = PolicyEvaluator.evaluate_action("submit_form", {"url": url})
            if not allowed:
                return {
                    "success": False,
                    "error": f"Policy Blocked: {reason}",
                    "authority_level": level,
                    "url": url
                }

        filename = f"browser_{uuid.uuid4().hex[:8]}.png"
        screenshot_path = cls.SCREENSHOTS_DIR / filename

        try:
            cooperative_checkpoint("before_playwright_import")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                cooperative_checkpoint("before_browser_launch")
                browser = p.chromium.launch(headless=True)
                cooperative_checkpoint("after_browser_launch")
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})

                app_logger.info(f"Playwright navigating to '{url}'...")
                cooperative_checkpoint("before_browser_navigation")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("after_browser_navigation")

                # Fill out input fields if specified
                if fill_inputs:
                    for selector, value in fill_inputs.items():
                        cooperative_checkpoint("before_browser_fill")
                        try:
                            if page.is_visible(selector):
                                page.fill(selector, value)
                        except ExecutionCancelled:
                            raise
                        except Exception as ie:
                            app_logger.warning(f"Could not fill input '{selector}': {ie}")

                # Click elements if specified
                if click_selectors:
                    for selector in click_selectors:
                        cooperative_checkpoint("before_browser_click")
                        try:
                            if page.is_visible(selector):
                                page.click(selector)
                                page.wait_for_timeout(1000)
                        except ExecutionCancelled:
                            raise
                        except Exception as ce:
                            app_logger.warning(f"Could not click '{selector}': {ce}")

                cooperative_checkpoint("before_browser_capture")
                page.screenshot(path=str(screenshot_path))
                page_title = page.title()
                page_text = page.inner_text("body") if page.query_selector("body") else ""
                cooperative_checkpoint("before_browser_close")
                browser.close()

            audit_logger.info(f"Automated browser navigation to '{url}' completed.")
            browser_session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
            tab = cls.GROUNDING.observe_tab(
                session_id=browser_session_id, url=url, title=page_title,
                profile_type="ephemeral",
                evidence=["Playwright page.url", "Playwright page.title", "page screenshot captured"],
            )

            return {
                "success": True,
                "url": url,
                "title": page_title,
                "content_snippet": page_text[:5000],
                "screenshot_path": str(screenshot_path),
                "image_url": f"/static/workspace/screenshots/{filename}",
                "text_length": len(page_text),
                "browser_session_id": browser_session_id,
                "tab_grounding": tab.to_dict(),
                "profile_type": "ephemeral",
                "auth_state": "unknown",
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Playwright launch notice ({e}). Falling back to HTTP HTML scraper...")
            # Fallback using httpx & BeautifulSoup if Playwright browser binaries are not downloaded locally
            try:
                import httpx
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
                    resp = run_cancellable_blocking_call(
                        lambda: client.get(url),
                        cancel=client.close,
                        description="browser HTTP fallback",
                    )
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        text = soup.get_text(separator="\n", strip=True)
                        title = soup.title.string if soup.title and soup.title.string else url
                        return {
                            "success": True,
                            "url": url,
                            "title": title,
                            "content_snippet": text[:5000],
                            "screenshot_path": "",
                            "image_url": "",
                            "text_length": len(text)
                        }
            except ExecutionCancelled:
                raise
            except Exception:
                pass

            return {
                "success": False,
                "available": False,
                "url": url,
                "error": (
                    "Browser automation and HTTP fallback both failed; navigation was not verified. "
                    f"Playwright error: {e}"
                ),
                "title": "",
                "content_snippet": "",
                "screenshot_path": "",
                "image_url": "",
                "text_length": 0,
            }


    @classmethod
    def download_file(cls, url: str, click_selector: str, expected_size_bytes: Optional[int] = None, use_profile: bool = False) -> Dict[str, Any]:
        """Download one file through an ephemeral tab and verify the local artifact.

        The transfer is disk-reserved before launch (worst-case quota when the
        size is unknown) and the save phase is owner-cancellable in flight; a
        cancelled save removes its partial artifact and releases the reservation.
        """
        if not url or not click_selector:
            return {"success": False, "error": "URL and click selector are required"}
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        max_bytes = max(1, int(settings.BROWSER_TRANSFER_MAX_MB)) * 1024 * 1024
        # Unknown size ⇒ reserve the worst-case quota, never zero.
        reserve_bytes = max(1, int(expected_size_bytes)) if expected_size_bytes else max_bytes
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)  # probe target must exist
        reservation = cls.DISK_LEDGER.reserve(
            "browser_download", reserve_bytes,
            target_root=cls.DOWNLOADS_DIR,
            execution_id=current_execution_id(),
        )
        if not reservation.get("success"):
            return {
                "success": False,
                "request_success": False,
                "side_effects": False,
                "error": reservation.get("detail", reservation.get("error", "insufficient_disk_space")),
                "disk_reservation": reservation,
            }
        reservation_id = reservation["reservation"]["reservation_id"]
        browser = None
        destination: Optional[Path] = None
        try:
            cooperative_checkpoint("before_browser_download")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = cls._launch(playwright.chromium, use_profile=use_profile)
                if browser is None:
                    return {"success": False, "refused": True,
                            "error": "Browser profile is already in use by another Arena session"}
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("before_download_click")
                with page.expect_download(timeout=30000) as download_info:
                    page.click(click_selector)
                download = download_info.value
                destination = cls._download_destination(download.suggested_filename)

                def _abort_inflight() -> None:
                    # Closing the browser context aborts an in-flight transfer.
                    for interrupt in (
                        lambda: download.cancel(),
                        lambda: browser.close(),
                    ):
                        try:
                            interrupt()
                        except Exception:
                            pass

                # The remote fetch itself is cancellable: the cooperative runner
                # polls the owner cancel flag and invokes the browser abort.
                run_cancellable_blocking_call(
                    lambda: download.save_as(str(destination)),
                    cancel=_abort_inflight,
                    description="browser download save",
                )
                cooperative_checkpoint("after_download_save")
                if not destination.is_file():
                    cls.DISK_LEDGER.release(reservation_id, reason="download produced no artifact")
                    return {"success": False, "error": "Download completed but file was not observed"}
                size_bytes = destination.stat().st_size
                if size_bytes > max_bytes:
                    destination.unlink(missing_ok=True)
                    cls.DISK_LEDGER.release(reservation_id, reason="oversized artifact removed")
                    return {"success":False,"request_success":True,"error":"Downloaded artifact exceeded owner transfer quota and was removed","size_bytes":size_bytes,"max_bytes":max_bytes,"environment_verified":not destination.exists(),"side_effects":False,"disk_reservation":{"reservation_id":reservation_id,"status":"released"}}
                digest = cls._hash_file(destination)
                # Completed: the artifact now physically occupies the space.
                cls.DISK_LEDGER.consume(reservation_id, size_bytes, reason="verified download completed")
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["Playwright download event", "page.url", "page.title"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "download", "completed",
                    evidence=[f"path:{destination}", f"sha256:{digest}"],
                )
                browser.close(); browser = None
            return {
                "success": True, "environment_verified": True,
                "download_path": str(destination), "download_sha256": digest,
                "size_bytes": size_bytes,
                "browser_session_id": session_id, "tab_grounding": tab.to_dict(),
                "download_event": event, "profile_type": "ephemeral",
                "auth_state": "unknown", "side_effects": True,
                "rollback_path": str(destination), "rollback_sha256": digest,
                "disk_reservation": {
                    "reservation_id": reservation_id,
                    "reserved_bytes": reserve_bytes,
                    "actual_bytes": size_bytes,
                    "status": "consumed",
                },
            }
        except ExecutionCancelled:
            # Never assert the peer aborted cleanly: only local cleanup is known.
            partial_removed = None
            if destination is not None:
                try:
                    destination.unlink(missing_ok=True)
                    partial_removed = not destination.exists()
                except Exception:
                    partial_removed = False
            cls.DISK_LEDGER.release(reservation_id, reason="cancelled in flight")
            raise
        except Exception as exc:
            cls.DISK_LEDGER.release(reservation_id, reason=f"download failed: {exc}"[:120])
            return {"success": False, "available": False, "error": str(exc)}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def upload_file(cls, url: str, input_selector: str, file_path: str,
                    submit_selector: str, success_selector: str, use_profile: bool = False) -> Dict[str, Any]:
        """Upload and submit one file; success requires an observed success selector."""
        source = Path(file_path)
        if not source.is_file():
            return {"success": False, "request_success": False, "error": "Upload file not found"}
        if not all((url, input_selector, submit_selector, success_selector)):
            return {"success": False, "request_success": False, "error": "URL, input, submit and success selectors are required"}
        if not url.startswith(("http://", "https://")): url = f"https://{url}"
        browser = None
        try:
            size_bytes=source.stat().st_size;max_bytes=max(1,int(settings.BROWSER_TRANSFER_MAX_MB))*1024*1024
            if size_bytes>max_bytes:return {"success":False,"request_success":False,"side_effects":False,"error":"Upload exceeds owner transfer quota","size_bytes":size_bytes,"max_bytes":max_bytes}
            digest = cls._hash_file(source)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = cls._launch(playwright.chromium, use_profile=use_profile); page = browser.new_page()
                if browser is None:
                    return {"success": False, "refused": True,
                            "error": "Browser profile is already in use by another Arena session"}
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if page.is_visible(success_selector):
                    return {"success":False,"request_success":False,"environment_verified":False,"error":"Success selector was already visible before upload; it cannot verify this submission","side_effects":False}
                cooperative_checkpoint("before_browser_upload")

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                # Local file attach (no remote submission yet) is cancellable
                # without remote side effects.
                run_cancellable_blocking_call(
                    lambda: page.set_input_files(input_selector, str(source)),
                    cancel=_abort_inflight,
                    description="browser upload attach",
                )
                cooperative_checkpoint("before_browser_upload_submit")

                def _submit_and_wait() -> None:
                    page.click(submit_selector)
                    page.wait_for_selector(success_selector, timeout=30000, state="visible")

                # From the submit click onward, cancellation cannot prove the
                # remote service never received the payload.
                run_cancellable_blocking_call(
                    _submit_and_wait,
                    cancel=_abort_inflight,
                    description="browser upload submit",
                )
                observed = page.is_visible(success_selector)
                # Service-specific receipt extraction (owner-configured adapter):
                # the service's own receipt ID, extracted from the observed page.
                service_receipt = None
                adapter = cls.ADAPTERS.match(url)
                if adapter is not None and adapter.receipt_selector:
                    try:
                        element = page.query_selector(adapter.receipt_selector)
                        if element is not None:
                            if adapter.receipt_attribute == "text":
                                raw_receipt = element.inner_text()
                            else:
                                raw_receipt = element.get_attribute(adapter.receipt_attribute)
                            receipt_id = str(raw_receipt or "").strip() or None
                            if receipt_id:
                                service_receipt = {
                                    "service_id": adapter.service_id,
                                    "adapter_id": adapter.adapter_id,
                                    "receipt_id": receipt_id,
                                    "extracted_via": f"{adapter.receipt_selector}@{adapter.receipt_attribute}",
                                }
                    except Exception as exc:
                        app_logger.warning(f"Service receipt extraction failed for {adapter.service_id}: {exc}")
                        service_receipt = None  # honest: extraction failed, not invented
                session_id=f"browser_session_{uuid.uuid4().hex[:12]}"
                tab=cls.GROUNDING.observe_tab(session_id=session_id,url=page.url,title=page.title(),profile_type="ephemeral",evidence=["set_input_files completed","submit clicked",f"success selector visible:{success_selector}"])
                event_evidence=[f"local_sha256:{digest}",f"success_selector:{success_selector}"]
                if service_receipt:
                    event_evidence.append(f"service_receipt:{service_receipt['service_id']}:{service_receipt['receipt_id']}")
                event=cls.GROUNDING.record_event(tab.tab_id,"upload","completed" if observed else "unknown",evidence=event_evidence)
                browser.close();browser=None
            result={"success":observed,"request_success":True,"environment_verified":observed,"verification_unknown":not observed,"uploaded_file":str(source),"uploaded_sha256":digest,"size_bytes":size_bytes,"tab_grounding":tab.to_dict(),"upload_event":event,"auth_state":"unknown","side_effects":True,"service_receipt":service_receipt}
            if adapter is not None and service_receipt is not None and adapter.delete_supported:
                # A service-specific delete flow exists for this receipt: the
                # rollback becomes a concrete proposal, still requiring separate
                # Level-3 authorization to execute.
                result["rollback_supported"]=True
                result["rollback_reason"]=f"Owner adapter {adapter.adapter_id} defines a delete flow for {adapter.service_id}; deletion requires separate Level-3 authorization."
                result["rollback_compensation"]={"action":"browser_delete_upload","payload":{"service_id":adapter.service_id,"receipt_id":service_receipt["receipt_id"]}}
            else:
                result["rollback_supported"]=False
                result["rollback_reason"]="Remote upload cannot be deterministically removed without a service-specific delete API."+(f" (receipt extracted for {adapter.service_id}, but no delete flow is configured.)" if adapter is not None and service_receipt is not None else "")
            return result
        except ExecutionCancelled: raise
        except Exception as exc:
            return {"success":False,"request_success":True,"environment_verified":False,"verification_unknown":True,"side_effects":True,"error":str(exc),"note":"Submission may have reached the remote service; retry requires fresh observation and authorization."}
        finally:
            if browser is not None:
                try:browser.close()
                except Exception:pass

    @classmethod
    def delete_uploaded_file(cls, service_id: str, receipt_id: str) -> Dict[str, Any]:
        """Level-3 service-specific deletion of a previously uploaded receipt.

        Runs ONLY the owner-configured delete flow for the service: the adapter's
        delete URL template (receipt id URL-quoted) plus an observed confirmation
        selector. Deletion is verified by that observation; it is never assumed
        from navigation alone, and Arena cannot undo a deletion (re-upload is a
        fresh authorized action).
        """
        if not service_id or not receipt_id:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": "service_id and receipt_id are required"}
        adapter = cls.ADAPTERS.get_by_service(str(service_id))
        if adapter is None:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"No owner-configured browser adapter for service '{service_id}'",
                    "note": "Service-specific deletion requires owner adapter configuration; refusing rather than improvising a delete flow."}
        if not adapter.delete_supported:
            return {"success": False, "request_success": False, "side_effects": False,
                    "error": f"Adapter '{service_id}' has no delete flow configured",
                    "note": "delete_url_template and confirm_selector are required for deletion."}
        from urllib.parse import quote
        delete_url = adapter.delete_url_template.format(receipt_id=quote(str(receipt_id), safe=""))
        browser = None
        try:
            cooperative_checkpoint("before_browser_delete_upload")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()

                def _abort_inflight() -> None:
                    try: browser.close()
                    except Exception: pass

                def _navigate_and_confirm() -> None:
                    page.goto(delete_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_selector(adapter.confirm_selector, timeout=30000, state="visible")

                # Remote destructive action: cancellable in flight, with the
                # standing caveat that cancellation cannot prove the service
                # never processed the request.
                run_cancellable_blocking_call(
                    _navigate_and_confirm, cancel=_abort_inflight,
                    description="browser delete upload",
                )
                observed = page.is_visible(adapter.confirm_selector)
                session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
                tab = cls.GROUNDING.observe_tab(
                    session_id=session_id, url=page.url, title=page.title(),
                    profile_type="ephemeral",
                    evidence=["owner-configured delete flow", f"service:{adapter.service_id}", f"receipt:{receipt_id}"],
                )
                event = cls.GROUNDING.record_event(
                    tab.tab_id, "upload_delete", "completed" if observed else "unknown",
                    evidence=[f"delete_url:{delete_url}", f"confirm_selector:{adapter.confirm_selector}"],
                )
                browser.close(); browser = None
            return {
                "success": observed, "request_success": True,
                "environment_verified": observed, "verification_unknown": not observed,
                "service_id": adapter.service_id, "receipt_id": str(receipt_id),
                "delete_url": delete_url, "tab_grounding": tab.to_dict(),
                "delete_event": event, "side_effects": True,
                "rollback_supported": False,
                "rollback_reason": "A completed deletion cannot be undone by Arena; re-upload is a fresh action requiring authorization.",
                "note": "Deletion verified by the adapter's confirmation selector observation, nothing stronger.",
            }
        except ExecutionCancelled:
            raise
        except Exception as exc:
            return {"success": False, "request_success": True, "environment_verified": False,
                    "verification_unknown": True, "side_effects": True, "error": str(exc),
                    "note": "Delete request may have reached the service; outcome requires re-observation."}
        finally:
            if browser is not None:
                try: browser.close()
                except Exception: pass

    @classmethod
    def navigate_and_extract(
        cls,
        url: str,
        fill_inputs: Optional[Dict[str, str]] = None,
        click_selectors: Optional[List[str]] = None,
        submit_form: bool = False,
        use_profile: bool = False
    ) -> Dict[str, Any]:
        """
        Automates real browser navigation using Playwright with HTTP fallback.
        Navigates to URL, fills inputs, clicks elements, takes a screenshot, and extracts page text.
        Submitting forms or clicking submit buttons enforces Level 3 Safety Policy approval.
        """
        cls.ensure_dir()
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Safety Check: Submitting forms or publishing data requires Level 3 approval
        if submit_form:
            allowed, reason, level = PolicyEvaluator.evaluate_action("submit_form", {"url": url})
            if not allowed:
                return {
                    "success": False,
                    "error": f"Policy Blocked: {reason}",
                    "authority_level": level,
                    "url": url
                }

        filename = f"browser_{uuid.uuid4().hex[:8]}.png"
        screenshot_path = cls.SCREENSHOTS_DIR / filename

        try:
            cooperative_checkpoint("before_playwright_import")
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                cooperative_checkpoint("before_browser_launch")
                browser = cls._launch(p.chromium, use_profile=use_profile)
                if browser is None:
                    return {"success": False, "refused": True,
                            "error": "Browser profile is already in use by another Arena session"}
                cooperative_checkpoint("after_browser_launch")
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})

                app_logger.info(f"Playwright navigating to '{url}'...")
                cooperative_checkpoint("before_browser_navigation")
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                cooperative_checkpoint("after_browser_navigation")

                # Fill out input fields if specified
                if fill_inputs:
                    for selector, value in fill_inputs.items():
                        cooperative_checkpoint("before_browser_fill")
                        try:
                            if page.is_visible(selector):
                                page.fill(selector, value)
                        except ExecutionCancelled:
                            raise
                        except Exception as ie:
                            app_logger.warning(f"Could not fill input '{selector}': {ie}")

                # Click elements if specified
                if click_selectors:
                    for selector in click_selectors:
                        cooperative_checkpoint("before_browser_click")
                        try:
                            if page.is_visible(selector):
                                page.click(selector)
                                page.wait_for_timeout(1000)
                        except ExecutionCancelled:
                            raise
                        except Exception as ce:
                            app_logger.warning(f"Could not click '{selector}': {ce}")

                cooperative_checkpoint("before_browser_capture")
                page.screenshot(path=str(screenshot_path))
                page_title = page.title()
                page_text = page.inner_text("body") if page.query_selector("body") else ""
                cooperative_checkpoint("before_browser_close")
                browser.close()

            audit_logger.info(f"Automated browser navigation to '{url}' completed.")
            browser_session_id = f"browser_session_{uuid.uuid4().hex[:12]}"
            tab = cls.GROUNDING.observe_tab(
                session_id=browser_session_id, url=url, title=page_title,
                profile_type="ephemeral",
                evidence=["Playwright page.url", "Playwright page.title", "page screenshot captured"],
            )

            return {
                "success": True,
                "url": url,
                "title": page_title,
                "content_snippet": page_text[:5000],
                "screenshot_path": str(screenshot_path),
                "image_url": f"/static/workspace/screenshots/{filename}",
                "text_length": len(page_text),
                "browser_session_id": browser_session_id,
                "tab_grounding": tab.to_dict(),
                "profile_type": "ephemeral",
                "auth_state": "unknown",
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.warning(f"Playwright launch notice ({e}). Falling back to HTTP HTML scraper...")
            # Fallback using httpx & BeautifulSoup if Playwright browser binaries are not downloaded locally
            try:
                import httpx
                from bs4 import BeautifulSoup
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
                    resp = run_cancellable_blocking_call(
                        lambda: client.get(url),
                        cancel=client.close,
                        description="browser HTTP fallback",
                    )
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        text = soup.get_text(separator="\n", strip=True)
                        title = soup.title.string if soup.title and soup.title.string else url
                        return {
                            "success": True,
                            "url": url,
                            "title": title,
                            "content_snippet": text[:5000],
                            "screenshot_path": "",
                            "image_url": "",
                            "text_length": len(text)
                        }
            except ExecutionCancelled:
                raise
            except Exception:
                pass

            return {
                "success": False,
                "available": False,
                "url": url,
                "error": (
                    "Browser automation and HTTP fallback both failed; navigation was not verified. "
                    f"Playwright error: {e}"
                ),
                "title": "",
                "content_snippet": "",
                "screenshot_path": "",
                "image_url": "",
                "text_length": 0,
            }
