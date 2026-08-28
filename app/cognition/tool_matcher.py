"""Deterministic manifest-first routing: the manifest decides, the LLM advises.

Root cause of the 'chatbot level' behavior (live, owner machine): every
message was classified by the fast model into 3 intents x 7 domains, and the
7 domains map to ~10 canned candidates — the ~180-tool manifest was never
consulted. This matcher inverts the authority:

  1. A deterministic scorer matches the user's words against the REAL tool
     manifest (names, descriptions, synonyms) plus a control-verb requirement.
  2. A confident, unique match FORCES the ACT branch with that exact tool —
     regardless of what intent bucket the LLM emitted.
  3. No confident match → the existing pipeline is untouched (questions,
     observations, chat all behave exactly as before).

Payload extraction is best-effort and deterministic (file paths, URLs);
anything missing surfaces through the existing gates as an honest typed
error or an owner question — never a hallucinated parameter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import app_logger

# General OS control: unrecognized settings requests go to the planner,
# not to chat. This is ONE routing rule replacing hundreds of per-action tools.
OS_CONTROL_ACTION = "os_control_plan"
from app.cognition.os_control_planner import _is_os_control_request

# Commands, not questions. A control verb anywhere in the message marks intent
# to ACT ("can you change my wallpaper" contains 'change').
CONTROL_VERBS = {
    "change", "set", "make", "open", "launch", "start", "run", "move", "rename",
    "copy", "delete", "remove", "search", "find", "list", "show", "create",
    "make", "send", "download", "upload", "compress", "archive", "extract",
    "type", "click", "press", "install", "uninstall", "update", "count",
    "play", "stop", "close", "kill", "terminate", "wallpaper", "encrypt",
    "decrypt", "backup", "restore", "screenshot", "capture", "analyze",
}

# Words that appear in tool names/descriptions but carry no matching signal.
STOPWORDS = {
    "a", "an", "the", "my", "me", "you", "can", "could", "please", "to", "for",
    "of", "in", "on", "at", "with", "and", "or", "is", "are", "it", "this",
    "that", "i", "want", "need", "would", "like", "do", "does", "have", "has",
    "your", "our", "all", "everything", "now", "then", "use", "using",
    "verified", "one", "file", "system", "new", "some", "just", "up", "out",
}

# High-frequency control synonyms the descriptions don't share with user speech.
SYNONYMS: Dict[str, List[str]] = {
    "set_wallpaper": ["wallpaper", "background", "desktop background"],
    "launch_app": ["open app", "launch app", "start app", "open application",
                   "launch application", "start application", "run app"],
    "screen_capture": ["screenshot", "capture screen", "grab screen"],
    "move_file": ["move file", "move the file", "relocate file"],
    "search_files": ["find file", "find files", "search file", "search files",
                     "search my files", "find my files", "search my documents"],
    "web_search": ["search the web", "google", "look up", "search",
                   "search for", "find information"],
    "create_backup": ["back up", "backup my", "make a backup"],
    "compress_files": ["zip", "compress", "archive"],
    "list_apps": ["installed apps", "installed programs", "installed applications"],
    "list_processes": ["running apps", "running programs", "running processes"],
    "terminate_process_verified": ["kill process", "terminate process", "end process"],
    "clipboard_inspect": ["clipboard", "what did i copy"],
}

_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+\.\w{2,6}")
_URL_RE = re.compile(r"https?://\S+")
_RELIMG_RE = re.compile(r"(?:[\w.\-]+/)*[\w.\-]+\.(?:jpg|jpeg|png|bmp|webp|gif)", re.I)

_MIN_SCORE = 2.0
_MIN_MARGIN = 1.0


@dataclass(frozen=True)
class ToolMatch:
    action_type: str
    score: float
    runner_up: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    matched_terms: Tuple[str, ...] = ()


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z_]+", text.lower()) if t not in STOPWORDS and len(t) > 2]


_SEARCH_AFTER_RE = re.compile(
    r"\b(?:search(?:\s+(?:the\s+)?web)?(?:\s+for)?|google|look\s+up|find)\s+"
    r"(?:for\s+|the\s+web\s+for\s+|on\s+(?:the\s+)?(?:web|internet|google)\s+for\s+)*"
    r"(.+?)(?:\s+(?:on\s+the\s+)?(?:web|internet|google|online)|$)",
    re.I,
)

def _extract_payload(text: str, action_type: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    path = _PATH_RE.search(text)
    if not path:
        img = _RELIMG_RE.search(text)
        if img:
            path = img
    if path:
        payload["image_path"] = path.group(0)
        payload["path"] = path.group(0)
        payload["source_path"] = path.group(0)
        payload["file_path"] = path.group(0)
    url = _URL_RE.search(text)
    if url:
        payload["url"] = url.group(0)
    # Search queries: extract JUST the search terms, not the whole sentence.
    if action_type == "web_search":
        # Strip browser/app instructions before extracting the query.
        cleaned = re.sub(r"(?:can\s+you\s+)?(?:open|launch|start|use)\s+\w+\s+(?:and|then|to)\s+", "", text, flags=re.I)
        search = _SEARCH_AFTER_RE.search(cleaned)
        if search:
            query = search.group(1).strip().rstrip("?.!")
            # Skip pure articles/prepositions that survive the regex.
            if query.lower() in ("the", "a", "an", "for", "on", "in", "web", "internet"):
                query = ""
            # Strip conversational filler the user directed at the agent.
            query = re.sub(r"^\s*(?:for\s+)?(?:me\s+|my\s+)", "", query, flags=re.I).strip()
            if query:
                payload["query"] = query
    return payload


def match_control_tool(user_text: str, manifest: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[ToolMatch]:
    """Deterministic best-tool match for a control request, or None.

    A match requires: (a) a control verb in the message, (b) a manifest tool
    scoring at least _MIN_SCORE from name/description/synonym overlap, and
    (c) a clear winner (margin >= _MIN_MARGIN or the only tool at threshold).
    """
    text = (user_text or "").lower().strip()
    if len(text) < 4:
        return None
    words = set(re.findall(r"[a-z_]+", text))
    if not (words & CONTROL_VERBS):
        return None

    try:
        if manifest is None:
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
    except Exception as exc:
        app_logger.warning(f"Tool matcher could not load the manifest: {exc}")
        return None

    text_tokens = set(_tokens(text))
    scored: List[Tuple[float, str, Tuple[str, ...]]] = []
    for action_type, entry in manifest.items():
        haystack = f"{action_type.replace('_', ' ')} {entry.get('description', '')}".lower()
        tool_tokens = set(_tokens(haystack))
        overlap = text_tokens & tool_tokens
        score = float(len(overlap))
        matched: List[str] = list(overlap)
        raw_words = words  # unfiltered: synonym phrases may contain stopwords
        for phrase in SYNONYMS.get(action_type, []):
            phrase_tokens = set(re.findall(r"[a-z_]+", phrase))
            if phrase in text or (phrase_tokens and phrase_tokens <= raw_words):
                score += 2.0
                matched.append(phrase)
        # The tool's own name appearing verbatim in the message is a strong signal.
        name_words = set(action_type.split("_")) - STOPWORDS
        if name_words and name_words <= words:
            score += 2.0
            matched.append(action_type)
        if score > 0:
            scored.append((score, action_type, tuple(sorted(set(matched)))))

    if not scored:
        # General OS control fallback: a settings-change request with no
        # specific tool match routes to the OS planner instead of chat.
        if _is_os_control_request(text):
            return ToolMatch(
                action_type=OS_CONTROL_ACTION, score=1.0,
                payload={}, matched_terms=("os_settings",))
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best, matched_terms = scored[0]
    if best_score < _MIN_SCORE:
        # Below the specific-tool threshold: still try OS control before chat.
        if _is_os_control_request(text):
            return ToolMatch(
                action_type=OS_CONTROL_ACTION, score=1.0,
                payload={}, matched_terms=("os_settings",))
        return None
    if len(scored) > 1 and (best_score - scored[1][0]) < _MIN_MARGIN and scored[1][0] >= _MIN_SCORE:
        return None  # ambiguous: let the normal pipeline handle it
    payload = _extract_payload(user_text, action_type=best)
    return ToolMatch(action_type=best, score=best_score,
                     runner_up=scored[1][1] if len(scored) > 1 else None,
                     payload=payload, matched_terms=matched_terms)
