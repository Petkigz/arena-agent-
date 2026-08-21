"""RSS/Atom aggregator — fetch feeds, parse them deterministically, optionally
summarize with the shared LLM.

Strong-tools-thin-model: `fetch_feed` and `parse_feed` are pure code (httpx +
stdlib XML, no LLM). The optional `summarize_feed` step uses the ONE llm_client
and only sees the already-parsed items, so it can't invent titles or links — it
only condenses text the parser actually extracted.

Safety model (manifest authoritative): Level 0 (read-only; fetches public feeds).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

from app.llm import llm_client, extract_reply
from app.utils.logger import app_logger, audit_logger


def _local(tag: str) -> str:
    """Strip an XML namespace: '{http://...}title' → 'title'."""
    return tag.rsplit("}", 1)[-1]


def _first_text(elem: ET.Element, name: str) -> str:
    for c in elem:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _first_link(elem: ET.Element, name: str = "link") -> str:
    for c in elem:
        if _local(c.tag) == name:
            href = c.get("href")
            if href:
                return href.strip()
            return (c.text or "").strip()
    return ""


class RssAggregator:
    @classmethod
    def fetch_feed(cls, url: str, limit: int = 20, timeout: float = 15.0) -> Dict[str, Any]:
        """Fetch and parse a feed over HTTP(S)."""
        url = (url or "").strip()
        if not url:
            return {"success": False, "error": "A feed URL is required."}
        if not url.lower().startswith(("http://", "https://")):
            return {"success": False, "error": "Feed URL must start with http:// or https://."}
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            app_logger.warning(f"Feed fetch failed for {url}: {e}")
            return {"success": False, "error": f"Could not fetch feed: {e}"}

        return cls.parse_feed(resp.text, limit=limit)

    @classmethod
    def parse_feed(cls, xml_text: str, limit: int = 20) -> Dict[str, Any]:
        """Parse RSS 2.0 or Atom XML into structured items (deterministic)."""
        limit = max(1, min(int(limit), 100))
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return {"success": False, "error": "Feed is not valid XML."}

        items: List[Dict[str, str]] = []
        title = ""
        root_local = _local(root.tag)

        if root_local == "feed":  # Atom
            title = _first_text(root, "title")
            for entry in root:
                if _local(entry.tag) != "entry":
                    continue
                items.append({
                    "title": _first_text(entry, "title"),
                    "link": _first_link(entry, "link"),
                    "summary": _first_text(entry, "summary") or _first_text(entry, "content"),
                    "published": _first_text(entry, "updated") or _first_text(entry, "published"),
                })
        elif root_local == "rss":  # RSS 2.0
            channel = next((c for c in root if _local(c.tag) == "channel"), None)
            if channel is None:
                return {"success": False, "error": "RSS feed has no <channel> element."}
            title = _first_text(channel, "title")
            for item in channel:
                if _local(item.tag) != "item":
                    continue
                items.append({
                    "title": _first_text(item, "title"),
                    "link": _first_link(item, "link"),
                    "summary": _first_text(item, "description"),
                    "published": _first_text(item, "pubDate"),
                })
        else:
            return {"success": False, "error": f"Unrecognized feed root element: '{root_local}'."}

        truncated = len(items) > limit
        return {
            "success": True,
            "title": title,
            "items": items[:limit],
            "count": len(items[:limit]),
            "truncated": truncated,
        }

    @classmethod
    def summarize_feed(cls, url: str, limit: int = 5, llm=None) -> Dict[str, Any]:
        """Fetch + parse a feed, then condense its items with the shared LLM.

        The model only sees the parsed titles/summaries (never invents links).
        Falls back to a deterministic list of titles if the LLM returns nothing.
        """
        parsed = cls.fetch_feed(url, limit=limit)
        if not parsed.get("success"):
            return parsed

        items = parsed.get("items", [])
        if not items:
            return {**parsed, "summary": "The feed contained no items."}

        llm = llm or llm_client
        digest = "\n".join(f"- {it.get('title', '')}: {it.get('summary', '')[:200]}" for it in items)
        system = (
            "You summarize a news feed. Write 2-4 concise sentences covering the "
            "key items below. Do NOT add facts, links, or numbers that are not in "
            "the items. Output only the summary."
        )
        user = f"Feed title: {parsed.get('title', '')}\n\nItems:\n{digest}"
        summary = extract_reply(
            llm.generate_chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                complexity="fast", max_tokens=400,
            ),
            fallback="",
        )
        if not summary.strip():
            summary = "Items: " + "; ".join(it.get("title", "") for it in items)
        return {**parsed, "summary": summary.strip()}
