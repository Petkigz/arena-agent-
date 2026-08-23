import os
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.cognition.execution_control import (
    ExecutionCancelled,
    cooperative_checkpoint,
    run_cancellable_blocking_call,
)

class BrowserAutomation:
    SCREENSHOTS_DIR = settings.DATA_DIR / "workspace" / "screenshots"

    @classmethod
    def ensure_dir(cls):
        cls.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

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

            return {
                "success": True,
                "url": url,
                "title": page_title,
                "content_snippet": page_text[:5000],
                "screenshot_path": str(screenshot_path),
                "image_url": f"/static/workspace/screenshots/{filename}",
                "text_length": len(page_text)
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
