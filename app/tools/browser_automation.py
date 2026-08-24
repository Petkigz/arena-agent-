import os
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.cognition.browser_grounding import BrowserGroundingStore
from app.cognition.execution_control import (
    ExecutionCancelled,
    cooperative_checkpoint,
    run_cancellable_blocking_call,
)

class BrowserAutomation:
    SCREENSHOTS_DIR = settings.DATA_DIR / "workspace" / "screenshots"
    DOWNLOADS_DIR = settings.DATA_DIR / "workspace" / "downloads"
    GROUNDING = BrowserGroundingStore(settings.DATA_DIR / "browser_grounding.db")

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
    def download_file(cls, url: str, click_selector: str) -> Dict[str, Any]:
        """Download one file through an ephemeral tab and verify the local artifact."""
        if not url or not click_selector:
            return {"success": False, "error": "URL and click selector are required"}
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        browser = None
        try:
            import hashlib
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
                download.save_as(str(destination))
                cooperative_checkpoint("after_download_save")
                if not destination.is_file():
                    return {"success": False, "error": "Download completed but file was not observed"}
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
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
                "size_bytes": destination.stat().st_size,
                "browser_session_id": session_id, "tab_grounding": tab.to_dict(),
                "download_event": event, "profile_type": "ephemeral",
                "auth_state": "unknown", "side_effects": True,
                "rollback_path": str(destination), "rollback_sha256": digest,
            }
        except ExecutionCancelled:
            raise
        except Exception as exc:
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
            import hashlib
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True); page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if page.is_visible(success_selector):
                    return {"success":False,"request_success":False,"environment_verified":False,"error":"Success selector was already visible before upload; it cannot verify this submission","side_effects":False}
                cooperative_checkpoint("before_browser_upload")
                page.set_input_files(input_selector, str(source))
                page.click(submit_selector)
                page.wait_for_selector(success_selector, timeout=30000, state="visible")
                observed = page.is_visible(success_selector)
                session_id=f"browser_session_{uuid.uuid4().hex[:12]}"
                tab=cls.GROUNDING.observe_tab(session_id=session_id,url=page.url,title=page.title(),profile_type="ephemeral",evidence=["set_input_files completed","submit clicked",f"success selector visible:{success_selector}"])
                event=cls.GROUNDING.record_event(tab.tab_id,"upload","completed" if observed else "unknown",evidence=[f"local_sha256:{digest}",f"success_selector:{success_selector}"])
                browser.close();browser=None
            return {"success":observed,"request_success":True,"environment_verified":observed,"verification_unknown":not observed,"uploaded_file":str(source),"uploaded_sha256":digest,"tab_grounding":tab.to_dict(),"upload_event":event,"auth_state":"unknown","side_effects":True,"rollback_supported":False,"rollback_reason":"Remote upload cannot be deterministically removed without a service-specific delete API."}
        except ExecutionCancelled: raise
        except Exception as exc:
            return {"success":False,"request_success":True,"environment_verified":False,"verification_unknown":True,"side_effects":True,"error":str(exc),"note":"Submission may have reached the remote service; retry requires fresh observation and authorization."}
        finally:
            if browser is not None:
                try:browser.close()
                except Exception:pass

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
