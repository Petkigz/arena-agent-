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

# Phone numbers: international (+256...), local (077...), or short codes.
# Used to gate communication verbs so "Call John" doesn't false-match
# phone_call (no number = no dialable target = ask or look up contacts).
_PHONE_RE = re.compile(
    r"\+?\d[\d\s\-()]{6,}\d")

# General OS control: unrecognized settings requests go to the planner,
# not to chat. This is ONE routing rule replacing hundreds of per-action tools.
OS_CONTROL_ACTION = "os_control_plan"
from app.cognition.os_control_planner import _is_os_control_request

# Commands, not questions. A control verb anywhere in the message marks intent
# to ACT ("can you change my wallpaper" contains 'change').
# COMPREHENSIVE: covers OS, browser, file, app, and system operations.
CONTROL_VERBS = {
    # Change/mutate
    "change", "set", "make", "open", "close", "modify", "adjust", "configure", "edit",
    "update", "upgrade", "reset", "restore", "revert", "toggle", "switch",
    "enable", "disable", "turn",
    # File operations
    "move", "rename", "copy", "delete", "remove", "create", "write",
    "save", "compress", "archive", "extract", "unzip", "zip",
    "upload", "download", "send", "share", "unshare",
    "encrypt", "decrypt", "backup", "burn", "print", "eject", "mount",
    "unmount",
    # App/OS operations
    "launch", "start", "run", "stop", "quit", "exit", "kill", "terminate",
    "restart", "reboot", "shutdown", "sleep", "hibernate", "wake",
    "lock", "unlock", "login", "logout", "logoff",
    "install", "uninstall", "repair",
    # Browser operations
    "navigate", "visit", "browse", "refresh", "reload", "scroll", "zoom",
    "fill", "enter", "submit", "click", "select", "check", "uncheck",
    "hover", "bookmark",
    # Display/UI operations
    "screenshot", "capture", "record", "minimize", "maximize", "restore",
    "snap", "tile", "cascade", "arrange", "resize", "scale", "rotate",
    "extend", "duplicate", "mirror", "hide", "show", "pin", "unpin",
    "wallpaper",
    # System/network operations
    "connect", "disconnect", "pair", "unpair", "scan", "sync", "block",
    "allow", "forward", "map", "clear", "empty", "clean", "purge",
    "flush", "release", "renew",
    # Audio/media
    "play", "pause", "mute", "unmute",
    # Search/observation commands
    "search", "find", "list", "count", "check", "verify", "test",
    "analyze", "inspect", "monitor", "track",
    # Communication (NOT call/text/message — too generic without a recipient;
    # these need phone numbers/addresses that the matcher doesn't extract)
    "notify",
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
    "phone_call": ["call", "dial", "phone", "ring"],
    "phone_sms": ["text", "sms", "message", "send a text", "send a message",
                  "send an sms"],
    "send_whatsapp": ["whatsapp", "whatsapp message"],
    "send_telegram": ["telegram", "telegram message"],
    "send_email": ["email", "send an email", "send an email to", "e-mail",
                   "mail"],
    "web_search": ["search the web", "google", "look up", "search",
                   "search for", "find information", "search google",
                   "web search", "search online", "search the internet"],
    "open_url": ["go to", "navigate to", "visit", "open website",
                 "open this url", "browse to", "open this page"],
    "browser_extract": ["extract the page", "get the page content",
                        "read the page", "scrape the page",
                        "what does this page say", "read this website"],
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

# ── File operations with explicit operands ────────────────────────────────
# Live bug (owner chat export 2026-08-29): 'move kaba.mp3 to my music
# folder' matched move_file but the payload was EMPTY — execution got no
# operands and failed, and the LLM apologized about lacking file access.
# 'rename london.mp3 to test.mp3' matched nothing at all. These patterns
# route file-management requests deterministically AND carry the operands.
_FILE_OP_NOUN = r"(?:files?|songs?|tracks?|albums?|documents?|docs?|photos?|pictures?|images?|videos?|movies?|clips?|notes?|folders?|archives?)"
_EXT_TOKEN = r"\.[A-Za-z0-9]{2,6}"
_MOVE_RE = re.compile(
    r"\b(?:move|rename)\s+(?:the\s+|my\s+|all\s+|every\s+)?"
    r"(?:" + _FILE_OP_NOUN + r"\s+)?(?:called\s+|named\s+)?"
    r"(.+?)\s+(?:to|into|in)\s+(.+?)\s*[?.!]*$", re.I)
_COPY_RE = re.compile(
    r"\bcopy\s+(?:the\s+|my\s+|all\s+)?"
    r"(?:" + _FILE_OP_NOUN + r"\s+)?(?:called\s+|named\s+)?"
    r"(.+?)\s+(?:to|into|in)\s+(.+?)\s*[?.!]*$", re.I)
_DELETE_CALLED_RE = re.compile(
    r"\b(?:delete|remove|trash)\s+(?:(?:all|every|the)\s+)?"
    r"(?:" + _FILE_OP_NOUN + r"\s+)?(?:called\s+|named\s+)\s*(.+?)\s*[?.!]*$", re.I)
_DELETE_FILE_RE = re.compile(
    r"\b(?:delete|remove|trash)\s+(?:(?:all|every|the)\s+)?(?:files?\s+)?"
    r"([\w\-.,'\"() ]+" + _EXT_TOKEN + r"(?:\s*(?:,|and)\s*[\w\-.,'\"() ]+" + _EXT_TOKEN + r")*)\s*[?.!]*$",
    re.I)


def _strip_trailing_clause(name: str) -> str:
    """'kaba from my playlist' -> 'kaba': drop subordinate clauses that
    aren't part of the file name."""
    return re.split(r"\s+(?:from|on|in|that|which|because)\s+", name.strip(), maxsplit=1, flags=re.I)[0].strip()


def _looks_like_path(text: str) -> bool:
    return bool(re.search(r"[\\/]|^[A-Za-z]:", text))


def _file_op_payload(source: str, destination: Optional[str] = None) -> Dict[str, Any]:
    """Build a payload carrying BOTH name forms; the execution layer resolves
    bare names to real paths via filesystem search."""
    payload: Dict[str, Any] = {}
    source = _strip_trailing_clause(source)
    if _looks_like_path(source):
        payload["source_path"] = source
    else:
        payload["source_name"] = source
    if destination is not None:
        destination = destination.strip()
        if _looks_like_path(destination):
            payload["destination_path"] = destination
        else:
            payload["destination_name"] = destination
    return payload


def _match_file_operation(text: str) -> Optional[ToolMatch]:
    """Deterministic file-management routing: move/rename/copy/delete with
    operands. Requires a file-ish signal (extension token, file noun, or
    called/named) so non-file sentences fall through untouched."""
    has_ext = bool(re.search(_EXT_TOKEN + r"\b", text))
    has_noun = bool(re.search(r"\b" + _FILE_OP_NOUN + r"\b", text))

    m = _MOVE_RE.search(text)
    if m and (has_ext or has_noun or "called" in text or "named" in text):
        return ToolMatch(action_type="move_file", score=3.0,
                         payload=_file_op_payload(m.group(1), m.group(2)),
                         matched_terms=("move/rename",))
    m = _COPY_RE.search(text)
    if m and (has_ext or has_noun or "called" in text or "named" in text):
        return ToolMatch(action_type="copy_file_verified", score=3.0,
                         payload=_file_op_payload(m.group(1), m.group(2)),
                         matched_terms=("copy",))
    m = _DELETE_CALLED_RE.search(text)
    if m:
        name = _strip_trailing_clause(m.group(1))
        if name:
            return ToolMatch(action_type="delete_files", score=3.0,
                             payload={"name": name},
                             matched_terms=("delete-by-name",))
    m = _DELETE_FILE_RE.search(text)
    if m and (has_ext or has_noun):
        names = [n.strip() for n in re.split(r"\s*(?:,|and)\s*", m.group(1).strip()) if n.strip()]
        return ToolMatch(action_type="delete_files", score=3.0,
                         payload={"names": names},
                         matched_terms=("delete",))
    return None


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
    has_phone_number = bool(_PHONE_RE.search(text))
    # Communication verbs are only control verbs when a dialable target is
    # present: 'call 0771234567' is an action; 'Call John' is a contact
    # lookup the OS planner or owner should resolve, not a blind dial.
    comm_verb_with_number = (
        has_phone_number and bool(words & {"call", "dial", "text", "sms"}))
    if not ((words & CONTROL_VERBS) or comm_verb_with_number):
        return None

    # File management with explicit operands routes deterministically (and
    # carries source/destination names — live bug: empty payloads).
    file_op = _match_file_operation(text)
    if file_op is not None:
        return file_op

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
        # Communication tools are gated on extractable targets:
        # phone_call/phone_sms need a phone number, send_email needs
        # an email address. Without the target they cannot route.
        is_comm = action_type in (
            "phone_call", "phone_sms", "send_whatsapp", "send_telegram")
        if is_comm and action_type in ("phone_call", "phone_sms") and not has_phone_number:
            continue  # no number -> cannot dial/text
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
                payload={"request": user_text}, matched_terms=("os_settings",))
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best, matched_terms = scored[0]
    if best_score < _MIN_SCORE:
        # Below the specific-tool threshold: still try OS control before chat.
        if _is_os_control_request(text):
            return ToolMatch(
                action_type=OS_CONTROL_ACTION, score=1.0,
                payload={"request": user_text}, matched_terms=("os_settings",))
        return None
    if len(scored) > 1 and (best_score - scored[1][0]) < _MIN_MARGIN and scored[1][0] >= _MIN_SCORE:
        return None  # ambiguous: let the normal pipeline handle it
    payload = _extract_payload(user_text, action_type=best)
    return ToolMatch(action_type=best, score=best_score,
                     runner_up=scored[1][1] if len(scored) > 1 else None,
                     payload=payload, matched_terms=matched_terms)


def rank_tools(
    user_text: str,
    limit: int = 6,
    domain_hint: Optional[str] = None,
    manifest: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[ToolMatch]:
    """Ranked capability DISCOVERY over the full manifest (P0 bottleneck #3).

    The manifest is the unified capability source; candidate generation must
    come from it by semantic matching, not from a hard-coded shortlist per
    domain. This exposes the scoring engine that match_control_tool uses
    internally, minus its act-gating (control verbs, winner margin): discovery
    PROPOSES, the planner and the action gates still decide.

    Scoring per tool: token overlap with the tool name + description, phrase
    synonyms, verbatim tool-name words, plus a boost when the tool's manifest
    category equals the goal's domain (domain knowledge informs ranking
    without hard-coding candidates)."""
    text = (user_text or "").lower().strip()
    if len(text) < 4:
        return []
    try:
        if manifest is None:
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
    except Exception as exc:
        app_logger.warning(f"Tool discovery could not load the manifest: {exc}")
        return []

    words = set(re.findall(r"[a-z_]+", text))
    text_tokens = set(_tokens(text))
    scored: List[Tuple[float, str, Tuple[str, ...]]] = []
    for action_type, entry in manifest.items():
        haystack = f"{action_type.replace('_', ' ')} {entry.get('description', '')}".lower()
        tool_tokens = set(_tokens(haystack))
        overlap = text_tokens & tool_tokens
        score = float(len(overlap))
        matched: List[str] = list(overlap)
        for phrase in SYNONYMS.get(action_type, []):
            phrase_tokens = set(re.findall(r"[a-z_]+", phrase))
            if phrase in text or (phrase_tokens and phrase_tokens <= words):
                score += 2.0
                matched.append(phrase)
        name_words = set(action_type.split("_")) - STOPWORDS
        if name_words and name_words <= words:
            score += 2.0
            matched.append(action_type)
        if domain_hint and str(entry.get("category", "")) == str(domain_hint):
            score += 1.5
        if score > 0:
            scored.append((score, action_type, tuple(sorted(set(matched)))))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    discovered: List[ToolMatch] = []
    for score, action_type, matched_terms in scored[: max(1, limit)]:
        if score < 1.5:
            break  # weak single-token overlaps are noise the domain baseline covers
        payload = _extract_payload(user_text, action_type=action_type)
        payload.setdefault("query", user_text)
        discovered.append(ToolMatch(
            action_type=action_type,
            score=score,
            payload=payload,
            matched_terms=matched_terms,
        ))
    return discovered
