"""Autonomous multi-step Web Agent — a professional-grade browser coworker.

Executes a structured sequence of web actions (navigate → fill → click → submit
→ extract) against real pages via Playwright (with HTTP fallback), then
synthesizes a result with the local LLM and optionally persists it to memory.

Design:
- Declarative steps (deterministic), so the agent can be audited and trusted.
- Optional LLM-driven loop (plan → act) gated behind `autonomous=True`.
- Every action is logged; submit_form stays behind Level-3 policy approval
  (enforced in BrowserAutomation).
- Graceful degradation: Playwright → HTTP scraper → explicit offline result.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.llm import llm_client, require_real_completion
from app.tools.browser_automation import BrowserAutomation
from app.tools.knowledge_indexer import KnowledgeIndexer
from app.utils.logger import app_logger, audit_logger

# Valid step verbs, kept explicit so the LLM can't emit arbitrary actions.
VALID_STEPS = {"navigate", "fill", "click", "submit", "extract", "wait"}


class WebAgent:
    """Execute declarative, multi-step web workflows and summarize outcomes."""

    @classmethod
    def _normalize_url(cls, url: str) -> str:
        url = url.strip()
        return url if url.startswith(("http://", "https://")) else f"https://{url}"

    @classmethod
    def _validate_steps(cls, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate a step list, returning an error dict on the first bad step."""
        if not steps:
            return {"error": "No steps provided."}
        for i, step in enumerate(steps):
            verb = step.get("action") or step.get("verb")
            if verb not in VALID_STEPS:
                return {"error": f"Step {i}: invalid action '{verb}' (allowed: {sorted(VALID_STEPS)})."}
        return {}

    @classmethod
    def execute_web_workflow(
        cls,
        objective: str,
        target_url: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        complexity: str = "main",
        auto_save_memory: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a web workflow for an objective.

        `steps` is an ordered list of dicts:
            {"action": "navigate", "url": "..."}            # (optional; target_url is used first)
            {"action": "fill", "selector": "#q", "value": "..."}
            {"action": "click", "selector": "button[type=submit]"}
            {"action": "submit", "selector": "form"}        # triggers Level-3 policy check
            {"action": "extract", "selector": "#results"}   # optional scoped extraction
            {"action": "wait", "ms": 1000}

        If `steps` is omitted, the agent just navigates + extracts (read-only).
        """
        app_logger.info(f"WebAgent workflow '{objective}' on '{target_url}' ({len(steps or [])} step(s))")

        # Validate steps before touching the browser.
        if steps:
            bad = cls._validate_steps(steps)
            if bad.get("error"):
                return {"success": False, **bad, "objective": objective, "target_url": target_url}

        # P0 bottleneck #6: steps are executed AS AN ORDERED SEQUENCE.
        # The old partitioning into fill/click/submit buckets reordered the
        # workflow (all fills, then all clicks, waits dropped entirely) —
        # which breaks real sites requiring click -> wait -> DOM update ->
        # fill -> click -> extract. Steps are normalized and passed through
        # in their declared order; BrowserAutomation runs them sequentially.
        normalized_steps: List[Dict[str, Any]] = []
        for step in (steps or []):
            verb = str(step.get("action") or step.get("verb") or "").lower().strip()
            entry: Dict[str, Any] = {"action": verb}
            if verb == "navigate":
                target_url = cls._normalize_url(step.get("url") or target_url)
                entry["url"] = target_url
            elif verb == "fill":
                entry["selector"] = step.get("selector")
                entry["value"] = str(step.get("value", ""))
            elif verb in ("click", "submit", "extract"):
                if step.get("selector"):
                    entry["selector"] = step["selector"]
            elif verb == "wait":
                try:
                    entry["ms"] = int(step.get("ms", 0) or 0)
                except (TypeError, ValueError):
                    entry["ms"] = 0
            normalized_steps.append(entry)

        target_url = cls._normalize_url(target_url)

        # ── Execute the browser automation (sequential workflow) ──
        browser_res = BrowserAutomation.navigate_and_extract(
            target_url,
            steps=normalized_steps or None,
        )
        if not browser_res.get("success"):
            return browser_res

        page_title = browser_res.get("title", target_url)
        page_content = browser_res.get("content_snippet", "")[:10000]

        # ── Synthesize a result with the local LLM ──
        system_prompt = (
            "You are a meticulous web-research assistant. Analyze the extracted "
            "page content against the user's objective and produce a concise, "
            "well-structured summary: (1) Did it satisfy the objective, "
            "(2) key facts/data with no fabrication, (3) recommended next step. "
            "If the content does not contain the answer, say so plainly."
        )
        user_prompt = (
            f"Web Objective: {objective}\n"
            f"Target URL: {target_url} (Title: {page_title})\n"
            f"Extracted Content:\n```\n{page_content}\n```"
        )

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_prompt}],
                complexity=complexity,
                max_tokens=800,
            )
            summary = require_real_completion(llm_res)
        except Exception as e:
            app_logger.warning(f"WebAgent LLM synthesis failed: {e}")
            summary = f"Web workflow executed, but summarization failed: {e}"

        result: Dict[str, Any] = {
            "success": True,
            "objective": objective,
            "target_url": target_url,
            "page_title": page_title,
            "steps_executed": len(steps or []),
            "step_log": browser_res.get("step_log", []),
            "extracts": browser_res.get("extracts", {}),
            # Honest outcome fields (P0 #8) — surfaced, never flattened.
            "request_success": browser_res.get("request_success", True),
            "browser_available": browser_res.get("browser_available", None),
            "page_retrieved": browser_res.get("page_retrieved", None),
            "interaction_executed": browser_res.get("interaction_executed", None),
            "environment_verified": browser_res.get("environment_verified", None),
            "execution_success": browser_res.get("execution_success", True),
            "agent_summary": summary,
            "screenshot_path": browser_res.get("screenshot_path", ""),
            "image_url": browser_res.get("image_url", ""),
        }

        if auto_save_memory and summary:
            try:
                mem_id = KnowledgeIndexer.index_web_knowledge(
                    {"success": True, "title": f"Web: {objective}", "url": target_url,
                     "domain": target_url, "ai_summary": summary},
                    category="web_workflow",
                )
                result["memory_id"] = mem_id
            except Exception as e:
                app_logger.warning(f"WebAgent memory save failed: {e}")

        audit_logger.info(f"WebAgent completed '{objective}' ({result['steps_executed']} step(s)) on {target_url}")
        return result
