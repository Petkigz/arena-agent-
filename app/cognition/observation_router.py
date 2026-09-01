"""Deterministic routing of host-state questions to real read-only observations.

Live lesson (owner machine): 'how many icons do I have on my desktop' was
classified knowledge_query → pure LLM answer. The agent HAS eyes (screen
capture, filesystem, process list) but the LLM intent classifier never routes
there, so every question becomes chatbot-level guessing.

This module does NOT trust the classifier for observable facts. A small
deterministic pattern set maps host-state questions to concrete Level-0
read-only observation plans. The runtime executes the plan, then answers
FROM THE EVIDENCE, never from imagination.

Honesty: only read-only observations are auto-planned (Level 0). Anything
that changes the world still goes through the normal proposal → gate →
approval path. Patterns are conservative; anything unmatched is untouched.
"""
from __future__ import annotations

import os
import re
import string
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ObservationPlan:
    action_type: str
    payload: Dict[str, Any]
    evidence_hint: str
    question_kind: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _file_search_roots() -> List[str]:
    """Roots for user-file questions: the all_user_files scope from the
    unified filesystem scope system (home + every other fixed drive on
    Windows — the owner's music does not always live under the profile;
    live incident: 'songs called kaba/ordinary' existed on another drive
    while the agent walked only C:\\Users\\... and reported nothing).
    Single source of truth: UniversalFilesystem.resolve_scope_roots.
    This is still a scoped walk, NOT an Everything-style MFT index — evidence
    text must stay honest about that."""
    from app.tools.universal_filesystem import UniversalFilesystem
    return [str(r) for r in UniversalFilesystem.resolve_scope_roots("all_user_files")]


def _desktop_directories() -> List[str]:
    dirs = []
    home = os.path.expanduser("~")
    for candidate in (os.path.join(home, "Desktop"),):
        if os.path.isdir(candidate):
            dirs.append(candidate)
    public = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")
    if os.path.isdir(public):
        dirs.append(public)
    return dirs


def _strip_artist_tail(name: str) -> tuple:
    """'ordinary by alex warren' -> ('ordinary', 'alex warren').

    Live bug: the file question kept the artist in the search query
    ('ordinary by alex warren') — the file 'Alex Warren - Ordinary.mp3'
    contains neither that phrase (exact miss) nor the same word order
    (fuzzy miss), so a correctly-spelled question answered 'not there'.
    Media files are named 'Artist - Title.ext': search the title, keep the
    artist as a preference hint."""
    m = re.match(r"^(.*?)\s+by\s+([A-Za-z][\w\s.&'-]+)$", name.strip())
    if m:
        title, artist = m.group(1).strip(), m.group(2).strip()
        if title and len(title) >= 2:
            return title, artist
    return name.strip(), ""


def _clean_subject(name: Optional[str]) -> Optional[str]:
    """Validate an extracted subject: non-empty, sane length, not a
    prepositional fragment ('in that movie') or bare pronoun."""
    if not name:
        return None
    name = name.strip().strip("'\"?.! ")
    if not (1 <= len(name) <= 80):
        return None
    if re.match(
        r"^(?:in|on|at|of|by|for|from|with|to|as|the|a|an|that|this|it|there|here|my|your|called|named|titled)\b",
        name,
    ):
        return None
    return name


def _extract_file_subject(text: str) -> Optional[str]:
    """Pull '<name>' out of '... called/named/titled <name> ...' file phrasing."""
    m = re.search(
        r"\b(?:called|named|titled)\s+(.+?)(?:\s+on my (?:pc|computer|machine|laptop|desktop)\b)?"
        r"(?:\s+(?:that )?(?:i have|do i have|i own|have i got|are there|is there)\b)?\s*[?.!]*$",
        text,
    )
    if not m:
        return None
    name = m.group(1).strip().strip("'\"")
    name = re.split(r"\s+(?:on|in|from)\s+my\s+", name)[0].strip().strip("'\"?.! ")
    return _clean_subject(name)


_FILE_NOUN = (
    r"(song|track|album|file|document|photo|picture|image|video|movie|clip|"
    r"pdf|folder|presentation|spreadsheet|note|audio|music|recording|"
    r"audiobook|ebook|podcast|episode|ringtone|wallpaper|beat|remix|"
    r"sample|font|archive|screenshot|backup|everything|anything)s?"
)

_FILE_EXTS = (
    r"mp3|wav|flac|m4a|aac|ogg|opus|mid|midi|pdf|docx?|xlsx?|pptx?|txt|csv|md|rtf|"
    r"jpg|jpeg|png|gif|bmp|webp|svg|mp4|mkv|avi|mov|wmv|webm|zip|rar|7z|tar|gz|"
    r"exe|msi|apk|iso|json|xml|yml|yaml|py|js|ts|html|css|java|ps1|bat|ttf"
)

# Request-verb lead noise that may precede a filename the ext-token regex
# captures (it spans spaces, so 'find files matching report.pdf' captures
# the whole clause). Stripped from the FRONT only, repeatedly. A name word
# that is not in this list ('report', 'invoice') is never touched.
_EXT_NAME_LEAD_NOISE = re.compile(
    r"^(?:(?:can|could|do|does|did|is|are|was|were|will|would|have|has|had|"
    r"i|you|we|my|me|the|a|an|all|any|every|some|"
    r"where|what|which|who|whose|when|why|how|many|much|there|"
    r"find|search|look|locate|list|show|give|get|check|see|tell|know|"
    r"files?|documents?|docs?|photos?|pictures?|images?|songs?|tracks?|"
    r"music|videos?|movies?|clips?|notes?|recordings?|"
    r"matching|matches?|called|named|titled|for|about|on|in|at|of)\b\s*)+",
    re.IGNORECASE,
)

# Questions that want the file ITSELF acted on (open/play/delete/…) are NOT
# read-only searches — the action pipeline owns them.
# ── Game detection for installed_games evidence ──────────────────────────
# Heuristic, deliberately broad: an entry counts if the app name/category
# contains game words, a known launcher/publisher, or a common game title.
_GAME_WORDS = (
    "game", "gaming", "steam", "epic games", "riot", "origin", "ea app",
    "ea sports", "ubisoft", "ubisoft connect", "battle.net", "battlenet",
    "blizzard", "gog galaxy", "minecraft", "roblox", "fortnite", "valorant",
    "league of legends", "counter-strike", "counter strike", "cs2", "dota",
    "football manager", "sports interactive", "the sims", "grand theft auto",
    "gta", "call of duty", "warzone", "apex legends", "rocket league",
    "among us", "terraria", "stardew", "hollow knight", "hades", "celeste",
    "cuphead", "cyberpunk", "witcher", "skyrim", "fallout", "elder scrolls",
    "forza", "halo", "gears of war", "sea of thieves", "elden ring",
    "dark souls", "pubg", "overwatch", "diablo", "starcraft", "warcraft",
    "hearthstone", "genshin", "chess", "solitaire", "minesweeper", "mahjong",
    "pinball", "age of empires", "civilization", "total war", "crusader kings",
    "hearts of iron", "stellaris", "cities skyline", "planet coaster",
    "zoo tycoon", "rollercoaster", "farming simulator", "farm simulator",
    "euro truck", "american truck", "flight simulator", "msfs", "xbox",
    "playstation", "nintendo", "emulator", "dolphin", "rpcs3", "pcsx",
    "retroarch", "dosbox",
)


def _filter_game_apps(apps: list) -> List[str]:
    """Return the app names that look like games/launchers from an app scan."""
    found: List[str] = []
    for a in apps:
        name = str(a.get("app_name", a.get("name", a)) if isinstance(a, dict) else a)
        haystack = name.lower()
        if isinstance(a, dict):
            haystack += " " + str(a.get("source_category", "")).lower()
        if any(w in haystack for w in _GAME_WORDS):
            found.append(name)
    return found


_FILE_ACTION_INTENT = (
    r"\b(play|open|launch|start|run|execute|delete|deleting|deleted|remove|removing|removed|"
    r"rename|renaming|renamed|move|moving|moved|copy|copying|copied|cut|send|sending|sent|"
    r"email|share|sharing|upload|install|uninstall|edit|editing|modify|write|create|make|"
    r"set|change|changing|changed|apply|switch|"
    r"convert|compress|extract|burn|print|download|downloading|downloaded)\b"
)

# Questions ABOUT a named work (summary, lyrics, artist) want knowledge, not
# a directory listing.
_FILE_CONTENT_INTENT = (
    r"\b(summar\w*|explain|lyrics?|who (?:wrote|sings|sang|made|performed|produced)|"
    r"artist|meaning|tell me about|review|translate|analy[sz]e|define|opinion|"
    # 'about' only blocks as a content lead ('what about the song called X'),
    # not as a reference tail ('the song i asked about').
    r"(?:tell|ask|know|talk|read|learn|more|something|info|information|details?) about|"
    r"all about|what about|how about)\b"
)

_PRONOUN_QUERY = (
    r"\b(where (?:is|are|was|were|can i find) (?:it|that)|where'?s (?:it|that)|"
    r"where did i (?:save|put|download) (?:it|that)|(?:look for|find|search for|locate) (?:it|that)|"
    r"(?:location|path|folder|directory) of (?:it|that)|"
    r"is (?:it|that) on my (?:pc|computer|machine|laptop|desktop))\b"
)

_BARE_SEARCH_STOPWORDS = (
    r"^(out|it|me|him|her|them|us|this|that|something|anything|everything|"
    r"up|down|new|a|an|the|my|some|more|another|one|two)\b"
)


def _extract_search_name(t: str) -> Optional[str]:
    """Extract a search subject from bare search phrasing ('find london',
    'search my pc for tema ensingo', 'locate the file report')."""
    m = re.search(r"\b(?:search|find|locate|look for)\b\s*(.*)$", t)
    if not m:
        return None
    rest = m.group(1).strip()
    rest = re.sub(r"^(?:my|the|a|an|all|any|every)\s+", "", rest)
    rest = re.sub(r"^(?:pc|computer|machine|laptop|desktop|system|phone|drive)\s+(?:for\s+)?", "", rest)
    rest = re.sub(r"^(?:files?|music|songs?|tracks?|documents?|photos?|pictures?|videos?|movies?)\s+(?:for\s+|called\s+|named\s+)?", "", rest)
    rest = re.sub(r"\s+on (?:my|the) (?:pc|computer|machine|laptop|desktop)\s*[?.!]*$", "", rest)
    rest = rest.strip().strip("'\"?.! ")
    if not rest or len(rest) < 2 or len(rest) > 60:
        return None
    if re.match(_BARE_SEARCH_STOPWORDS, rest):
        return None
    if re.search(r"\b(yesterday|last week|last night|made|created|wrote|edited|about)\b", rest):
        return None  # topical/time reference, not a filename
    if len(rest.split()) > 5:
        return None
    return rest


def _extract_file_question_subject(t: str) -> Optional[str]:
    """Best-effort subject for a file question: 'called X', quoted \"X\",
    an X.ext token, 'do i have X on my pc', or bare search phrasing."""
    name = _extract_file_subject(t)
    if name:
        return name
    quoted = re.search(r'["\']([^"\']{1,80})["\']', t)
    if quoted:
        return quoted.group(1).strip()
    ext_token = re.search(r"\b([\w\- ]{1,60}\.(?:" + _FILE_EXTS + r"))\b", t)
    if ext_token:
        # Strip the request-verb lead noise the span regex swallows:
        # 'find files matching report.pdf' must search for 'report.pdf',
        # not the whole clause — search_files matches filename SUBSTRINGS
        # and no filename contains the request phrase (the P0 #16 lesson,
        # applied to this path; found while fixing DIAG F7: every 'find
        # files matching X.ext' question answered 'no files found' while
        # the file existed). A shorter query can only match MORE files,
        # never miss; a leading word that is NOT request noise ('report')
        # survives intact.
        stripped = _EXT_NAME_LEAD_NOISE.sub("", ext_token.group(1)).strip()
        return stripped or ext_token.group(1).strip()
    # 'do i have london on my pc' — no noun, but the 'on my pc' tail grounds
    # it as a host question.
    have_on_pc = re.search(
        r"\b(?:do i have|have i got|is there|does my (?:pc|computer) have)\s+"
        r"(?:a|an|the|any)?\s*(.+?)\s+on my (?:pc|computer|machine|laptop|desktop)\b",
        t,
    )
    if have_on_pc:
        cand = have_on_pc.group(1).strip().strip("'\"?.! ")
        if 1 <= len(cand) <= 60:
            return cand
    return _extract_search_name(t)


def _extract_pronoun_subject(recent_user_messages: List[str]) -> Optional[str]:
    """Scan back through prior turns for a file question with a subject."""
    for prev in reversed(recent_user_messages):
        prev_l = (prev or "").lower().strip()
        if not prev_l:
            continue
        if re.search(r"\b" + _FILE_NOUN + r"\b", prev_l):
            prev_name = _extract_file_subject(prev_l) or _extract_file_question_subject(prev_l)
            if prev_name:
                return prev_name
    return None


# ── Data-statistic asks (DIAG F3 follow-up, live D2, 2026-09-01): the
# arithmetic branch's comment says statistic asks "fall through to the
# data pipeline" — but no such branch existed, so 'tell me the average of
# the amount column' ran the chat pipeline, the mean (computed by
# analyze_data's own describe()) never became evidence, and the goal
# stalled in waiting_for_evidence. The SAME chain as arithmetic (D1)
# applies: plan the deterministic tool, render the value as VERIFIED
# evidence, record it as ground truth for the verifier.
#
# Detector scope is CONSERVATIVE (like the calculator): the request must
# name BOTH '<statistic> of <column> column' AND an explicit data file
# (.csv/.xlsx/.xls). Statistics are limited to what pandas describe()
# reports directly (mean/average, median, min, max) — no derived math
# (a sum reconstructed as mean*count would fabricate precision).
_DATA_STATISTIC_WORDS = {
    "average": "mean", "mean": "mean", "median": "median",
    "minimum": "min", "min": "min", "maximum": "max", "max": "max",
}
_DATA_FILE_RE = re.compile(
    r"(?:[A-Za-z]:)?(?:[\\/][^\s,]+)+\.(?:csv|xlsx|xls)\b"
    r"|\b[\w\-.]+\.(?:csv|xlsx|xls)\b",
    re.IGNORECASE,
)
_STAT_COL_RE = re.compile(
    r"\b(average|mean|median|minimum|maximum|min|max)\s+(?:of\s+)?(?:the\s+)?"
    r"['\"]?(?!(?:of|the|a|an|in|for|from|column)\b)(\w+)['\"]?\s+column\b"
    r"|\b(average|mean|median|minimum|maximum|min|max)\s+(?:of\s+)?(?:the\s+)?"
    r"column\s+['\"]?(\w+)['\"]?",
    re.IGNORECASE,
)


def _extract_data_statistic_request(text: str) -> Optional[Dict[str, str]]:
    """'<statistic> of <column> column' + an explicit data file, or None."""
    t = str(text or "").strip()
    file_match = _DATA_FILE_RE.search(t)
    if not file_match:
        return None
    stat_match = _STAT_COL_RE.search(t)
    if not stat_match:
        return None
    word, column = stat_match.group(1), stat_match.group(2)
    if not word:  # 'column <name>' spelling
        word, column = stat_match.group(3), stat_match.group(4)
    return {
        "file_path_str": file_match.group(0),
        "statistic": _DATA_STATISTIC_WORDS[word.lower()],
        "column": column,
    }


# describe() key for each supported statistic word.
_DESCRIBE_KEY = {"mean": "mean", "median": "50%", "min": "min", "max": "max"}


def extract_statistic_from_analysis(
    result: Any, plan: ObservationPlan
) -> Optional[Dict[str, Any]]:
    """Pull the requested statistic out of an analyze_data result.

    Returns {'statistic', 'column', 'value', 'value_str'} or None — None
    is HONEST: a failed analysis, a missing column, or a non-numeric
    column means no number exists, and none may be invented. The value
    comes from pandas describe() via the tool's own summary_stats."""
    if not isinstance(result, dict) or not result.get("success"):
        return None
    stats = result.get("summary_stats") or {}
    column = str(plan.payload.get("column", "")).strip()
    key = _DESCRIBE_KEY.get(str(plan.payload.get("statistic", "")))
    if not column or key is None:
        return None
    col_stats = stats.get(column)
    if not isinstance(col_stats, dict) or key not in col_stats:
        return None
    try:
        value = float(col_stats[key])
    except (TypeError, ValueError):
        return None
    return {
        "statistic": plan.payload["statistic"],
        "column": column,
        "value": value,
        "value_str": _num_str(value),
    }


def _num_str(value: float) -> str:
    """Honest rendering, same rule as the calculator: ints stay ints,
    floats keep their exact repr."""
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def plan_observation(text: str, recent_user_messages: Optional[List[str]] = None) -> Optional[ObservationPlan]:
    """Map a host-state question to a read-only observation plan, or None.

    `recent_user_messages` (most recent last, current turn excluded) lets
    follow-up questions resolve pronouns: 'where is it located' after 'do i
    have a song called kaba on my pc' searches for kaba.
    """
    t = (text or "").lower().strip()
    if len(t) < 6:
        return None

    # ── Arithmetic (DIAG F3b, live D1: the 3B chat model answered
    # 17*24=396; ground truth 408). Exact answers come from the
    # deterministic calculator, never the language model. The detector is
    # the ONE shared implementation in app.tools.calculator — conservative
    # by design, so statistic asks ('the average of the amount column')
    # fall through to the data pipeline.
    try:
        from app.tools.calculator import DeterministicCalculator
        arithmetic_expr = DeterministicCalculator.extract_expression(text)
    except Exception:
        arithmetic_expr = None
    if arithmetic_expr:
        return ObservationPlan(
            action_type="calculate_expression",
            payload={"expression": arithmetic_expr},
            evidence_hint="Exact arithmetic evaluated deterministically.",
            question_kind="arithmetic",
        )

    # ── Data-statistic asks (live D2, 2026-09-01): '<statistic> of
    # <column> column' over a named data file. The arithmetic comment
    # above promised these "fall through to the data pipeline" — this IS
    # that pipeline: analyze_data's describe() holds the exact value, so
    # the ask is answered from deterministic evidence, never chat.
    data_stat_req = _extract_data_statistic_request(text)
    if data_stat_req:
        return ObservationPlan(
            action_type="analyze_data",
            payload=data_stat_req,
            evidence_hint="Exact statistic from deterministic dataset analysis.",
            question_kind="data_statistic",
        )

    # ── System state (memory/disk/CPU/battery/network) ─────────────────
    if re.search(r"\b(how much|how many).{0,20}\b(ram|memory|disk|storage|space|cpu|gpu|battery|charge)\b|\b(check|what).{0,15}\b(ram|memory|disk|storage|cpu|gpu|battery|charge|space)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="System resource usage from live process enumeration.",
            question_kind="system_resources",
        )

    # IP / network address.
    if re.search(r"\b(my|the|what).{0,10}\b(ip|ip address|network address|mac address|local ip|external ip)\b|\bwhat.{0,10}my ip\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Network adapters and addresses from the host.",
            question_kind="network_address",
        )

    # OS version / system info. NOT window/tab/browser questions.
    if re.search(r"\b(what|which|check).{0,15}\b(version|os version|operating system|system info|macos|linux|ubuntu|build)\b|\b(system information|system info|os version)\b|\bwhat.{0,5}\bwindows\b.{0,10}\b(version|edition|build)\b", t):
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="System version and installed software from the host.",
            question_kind="system_info",
        )

    # Battery / power status.
    if re.search(r"\b(battery|charge level|power status|charging|plugged in|on battery)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Power and battery state from the host.",
            question_kind="power_status",
        )

    # ── Capability self-check: 'can you access my computer / use it for
    # tasks?' — the recurring 'I don't have access' apology is factually
    # wrong: the tool registry is observable. Answer from it. (See the
    # separate 'can you see my desktop' screen pattern below — see/view is
    # deliberately NOT in this verb list.)
    if re.search(
        r"\b(?:can|could|do|does)\s+you\s+(?:access|use|control|manage|handle)\b"
        r".{0,30}\b(computer|pc|machine|system|laptop|files?|filesystem|desktop|data|tasks?)\b"
        r"|\bdo you have (?:access|permission)s?\b.{0,30}\b(computer|pc|machine|system|laptop|files?|filesystem|desktop)\b",
        t,
    ):
        return ObservationPlan(
            action_type="list_capabilities",
            payload={},
            evidence_hint=(
                "Registered tool inventory from the capability registry — answer "
                "capability questions from this evidence; the agent demonstrably "
                "has filesystem, app, and OS-control tools."
            ),
            question_kind="capability_selfcheck",
        )

    # ── Internet / web capability self-check: 'can you access the internet /
    # do you have internet?' — same failure family as the access apology
    # above (live transcript: 'can you access the internet' got 'without
    # direct internet connectivity ... I can't confirm'). The registry holds
    # web tools (web_search, browser sessions) and network tools (ping, DNS,
    # traceroute): observable fact, answer from it. Gated to capability
    # QUESTIONS ('can/could/do/are you …'); a polite TASK like 'can you
    # search the web for X' contains ' for ' and is left to the task paths.
    internet_cap = re.search(
        r"\b(?:can|could|do|does)\s+you\s+"
        r"(?:access|use|browse|search|check|get|go|connect(?:ed)?(?:\s+to)?)\b"
        r".{0,25}\b(internet|web|online|network|wifi|websites?|webpages?)\b"
        r"|\bdo you have\b.{0,20}\b(internet|web|online|network|wifi|internet connection)\b"
        r"|\bare you (?:online|connected)\b"
        r"|\bis there (?:an )?internet\b",
        t,
    )
    if internet_cap and " for " not in t:
        return ObservationPlan(
            action_type="list_capabilities",
            payload={"focus": "internet"},
            evidence_hint=(
                "Registered tool inventory from the capability registry — answer "
                "the internet/web capability question from this evidence; the "
                "registry contains web and network tools."
            ),
            question_kind="capability_selfcheck",
        )

    # ── File existence questions ('do i have a song called kaba on my pc') ──
    # Live bug: this question was routed to the mobile_phone domain (substring
    # 'call' matched 'called') and DEFERRED with a terse non-answer. A
    # file-existence question is directly observable: search the user's home
    # directory and answer from the evidence.
    file_q = re.search(
        r"\b(do i have|is there|have i got|got)\b.{0,40}\b"
        r"(song|track|album|file|document|photo|picture|image|video|movie|clip|pdf|folder|presentation|spreadsheet|note)s?\b"
        r"(?:.{0,40}\b(?:called|named|titled)\b\s*(.+?))?"
        r"\s*(?:on my (?:pc|computer|machine|laptop|desktop))?\s*[?.!]*$",
        t,
    )
    if file_q:
        name = (file_q.group(3) or "").strip().strip("'\"")
        if name:
            name = re.split(r"\s+(?:on|in|from)\s+my\s+", name)[0].strip().strip("'\"?.! ")
        artist = ""
        if name:
            name, artist = _strip_artist_tail(name)
        if name and 1 <= len(name) <= 80:
            home = os.path.expanduser("~")
            # 'do i have a song called london' must not be answered with the
            # tzdata 'Europe\London' folder: point the model at media files.
            media_noun = file_q.group(2)
            media_hint = ""
            if media_noun in (
                "song", "track", "album", "music", "audio", "recording",
                "video", "movie", "clip", "photo", "picture", "image",
            ):
                media_hint = (
                    f" The user asked about a {media_noun} — prioritize matching media "
                    "files (.mp3/.wav/.flac/.m4a/.ogg etc.) and ignore unrelated "
                    "directories that merely contain the name."
                )
            return ObservationPlan(
                action_type="search_files",
                payload={"query": name, "root_dir": _file_search_roots(), "max_results": 20},
                evidence_hint=(
                    f"Filesystem search for '{name}' (user home + other fixed drives) — "
                    "answer whether it exists from these results."
                    + (f" The owner named the artist '{artist}' — prefer files matching both "
                       "artist and title (e.g. 'Artist - Title.ext')." if artist else "")
                    + media_hint
                ),
                question_kind="file_existence",
            )

    # ── Follow-up 'what about X' right after a file/music question ──
    # Live transcript: 'give me a list of all the songs called kaba' was
    # answered from search evidence, then the follow-up 'what about ordinaryr
    # by alex warren' fell to the raw LLM and got an improvised answer
    # instead of another filesystem search. Route it when the follow-up
    # names a media/file noun itself OR the recent turns established
    # file/music context (via recent_user_messages).
    what_about = re.match(r"^\s*(?:what|how)\s+about\s+(.+?)\s*[?.!]*$", t)
    if what_about:
        subject = what_about.group(1).strip()
        media_ctx = any(
            re.search(
                r"\b(song|track|album|music|file|document|photo|picture|image|"
                r"video|movie|clip|pdf|folder|presentation|spreadsheet)s?\b",
                m,
            )
            for m in (recent_user_messages or [])
        )
        m_noun = re.match(
            r"^(?:the\s+)?(song|track|album|file|document|photo|picture|image|"
            r"video|movie|clip|pdf|folder)s?\s+(?:called\s+|named\s+)?(.+)$",
            subject,
        )
        if m_noun:
            followup_name = m_noun.group(2).strip()
        elif media_ctx:
            followup_name = subject
        else:
            followup_name = ""
        # 'X by <artist>' — media files are usually named 'Artist - Title.ext';
        # search the title, keep the artist as a preference hint.
        artist = ""
        m_artist = re.match(r"^(.*?)\s+by\s+([A-Za-z][\w\s.&'-]+)$", followup_name)
        if m_artist:
            followup_name, artist = m_artist.group(1).strip(), m_artist.group(2).strip()
        followup_name = followup_name.strip("\"'").strip()
        # Pronoun/filler subjects ('how about another one') are not names —
        # leave them to the conversational path.
        if re.fullmatch(
            r"(?:another(?:\s+one)?|more|that|it|this|them|those|these|one|"
            r"the\s+(?:other|rest|same)(?:\s+one)?)",
            followup_name,
        ):
            followup_name = ""
        if followup_name and 1 <= len(followup_name) <= 80:
            home = os.path.expanduser("~")
            hint = (
                f"Filesystem search for '{followup_name}' (user home + other fixed drives)"
            )
            if artist:
                hint += (
                    f" (asked as '{followup_name}' by '{artist}' — prefer media files "
                    "matching both, e.g. 'Artist - Title.ext')"
                )
            hint += (
                " — answer whether it exists from these results. Prioritize matching "
                "media files (.mp3/.wav/.flac/.m4a/.ogg etc.) and ignore unrelated "
                "directories that merely contain the name."
            )
            return ObservationPlan(
                action_type="search_files",
                payload={"query": followup_name, "root_dir": _file_search_roots(), "max_results": 20},
                evidence_hint=hint,
                question_kind="file_search",
            )

    # ── File questions (broad): enumeration / location / any search intent ──
    # Live bug: only yes/no existence questions ('do i have a song called X')
    # were observable. 'give me a list of all of the songs called london i
    # have' fell through to the LLM, which apologized about having no file
    # access while the deterministic search tool sat unused. The bar is now
    # deliberately LOW: any question that names a file subject and doesn't
    # clearly want an ACTION on it or content ABOUT it gets a real search —
    # a false positive costs one cheap directory walk; a false negative
    # produces the 'I don't have access' apology the owner is tired of.
    has_file_noun = re.search(r"\b" + _FILE_NOUN + r"\b", t) is not None
    has_extension = re.search(r"\b[\w\-]+\.(?:" + _FILE_EXTS + r")\b", t) is not None
    # 'do i have london on my pc' — the 'on my pc' tail grounds it as a host
    # question even without a file noun.
    have_on_pc = bool(re.search(
        r"\b(?:do i have|have i got|is there|does my (?:pc|computer) have|did i (?:save|put|download))\b"
        r".{0,60}\bon my (?:pc|computer|machine|laptop|desktop)\b", t,
    ))
    noun_or_ext = has_file_noun or has_extension or have_on_pc
    search_verb = re.search(
        r"\b(search|find|locate|look(?:ing)? for|search(?:ing|ed)? for|trying to find)\b", t
    ) is not None
    read_intent = bool(re.search(
        r"\b(list|show|find|search|locate|look for|looking for|searching for|trying to find|"
        r"want to find|need to find|want to know|wanna know|enumerate|all|every|any|"
        r"how many|how much|where|which|what|do i have|does my (?:pc|computer|machine) have|"
        r"do i own|did i (?:save|put|download)|is there|have i got|got|do you see|did you find|"
        r"can|could|do|does|did|is|are|was|were|will|would)\b", t,
    )) or t.endswith("?")
    blocked_intent = re.search(_FILE_ACTION_INTENT + "|" + _FILE_CONTENT_INTENT, t) is not None

    name = _extract_file_question_subject(t)

    # Follow-up pronouns/references: 'where is it located', 'find it', or
    # 'where's the song i asked about' — no name in THIS message, so resolve
    # the subject from the conversation's recent turns.
    context_ref = re.search(_PRONOUN_QUERY, t) or (
        bool(re.search(r"\bwhere\b|\blocation\b|\bpath\b|\bfolder\b|\bdirectory\b", t))
        and has_file_noun
    )
    if name is None and recent_user_messages and context_ref:
        prev_name = _extract_pronoun_subject(recent_user_messages)
        if prev_name:
            name = prev_name
            noun_or_ext = True
            read_intent = True

    if name and not blocked_intent and ((noun_or_ext and read_intent) or search_verb):
        name, _artist = _strip_artist_tail(name)
        home = os.path.expanduser("~")
        is_location = bool(re.search(r"\bwhere\b|\blocation\b|\bpath\b|\bfolder\b|\bdirectory\b", t))
        is_existence = bool(re.search(
            r"\b(do i have|is there|have i got|got|does my (?:pc|computer) have|do i own|any)\b", t
        )) and not search_verb and not is_location and not re.search(
            r"\b(how many|how much|list|all|every|show|give|which|what|enumerate)\b", t
        )
        kind = "file_location" if is_location else ("file_existence" if is_existence else "file_search")
        max_results = 20 if kind == "file_existence" else 50
        # 'do i have a song called london' must not be answered with the
        # tzdata 'Europe\London' folder: when the question names a medium
        # (song/music/video/...), tell the model to prefer matching files of
        # that type and ignore same-named directories.
        media_noun = re.search(
            r"\b(song|songs|track|tracks|album|music|audio|recording|audiobook|podcast|"
            r"video|videos|movie|movies|clip|photo|photos|picture|pictures|image|images)\b", t
        )
        media_hint = ""
        if media_noun:
            media_hint = (
                f" The user asked about {media_noun.group(1)} — prioritize matching media "
                "files (.mp3/.wav/.flac/.m4a/.ogg etc.) and ignore unrelated directories "
                "that merely contain the name."
            )
        return ObservationPlan(
            action_type="search_files",
            payload={"query": name, "root_dir": _file_search_roots(), "max_results": max_results},
            evidence_hint=(
                f"Filesystem search for '{name}' (user home + other fixed drives) — "
                + ("give the full path(s) of every match from these results."
                   if is_location else
                   "answer from these results.")
                + media_hint
            ),
            question_kind=kind,
        )

    # Connected devices / USB.
    if re.search(r"\b(connected|attached|usb|devices?|drives?|mount(ed|s)?|printers?|cameras?|scanners?)\b.{0,20}\b(what|list|show|connected|plugged)\b|\bwhat.{0,10}\b(devices|usb|drives)\b|\b(list|show).{0,10}\b(devices|usb|drives|printers|cameras)\b", t):
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="Connected hardware and devices from the host.",
            question_kind="connected_devices",
        )

    # Startup programs / services. NOT "what apps are running" (that's
    # running_processes) — requires actual startup/boot context.
    if re.search(r"\b(startup|boot|auto.?start)\b|\bservices?\b.{0,20}\b(what|list|show|running|enabled)\b|\bwhat.{0,10}\b(starts|runs)\b.{0,5}\b(at|on|during)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Running services and startup programs from the host.",
            question_kind="startup_programs",
        )

    # Clipboard contents.
    if re.search(r"\b(what|check|show).{0,10}\bclipboard\b|\bclipboard.{0,10}\b(what|content|contents)\b|\bwhat did i copy\b", t):
        return ObservationPlan(
            action_type="clipboard_inspect",
            payload={},
            evidence_hint="Clipboard contents inspected read-only.",
            question_kind="clipboard",
        )

    # Network status / connectivity.
    if re.search(r"\b(network|internet|wifi|ethernet|connection)\b.{0,20}\b(status|connected|online|offline|working|available)\b|\bam i (online|connected)\b|\b(is my|check my).{0,10}\b(internet|network|wifi|connection)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Network adapters and connectivity state from the host.",
            question_kind="network_status",
        )

    # ── Browser-specific observations ──────────────────────────────────
    # (tabs/windows already handled above; these are content/history)

    # Browser history.
    if re.search(r"\b(browser|browsing|web)\b.{0,10}\b(history|history)\b|\bwhat (sites|pages|websites).{0,20}\b(visit|open|browse)\b|\bmy (recent|browsing) history\b", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Open browser windows as an indicator of browsing activity.",
            question_kind="browser_history",
        )

    # Downloads folder contents.
    if re.search(r"\bdownloads?\b|\bdownload folder\b", t):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        return ObservationPlan(
            action_type="list_directory",
            payload={"directories": [{"path": downloads}], "include_hidden": False},
            evidence_hint="Downloads folder contents from the filesystem.",
            question_kind="downloads_folder",
        )

    # Desktop icons / files on the desktop → count directory entries.
    if re.search(r"\b(icons?|shortcuts?|files?)\b.*\bdesktop\b|\bdesktop\b.*\b(icon|shortcut|file)s?\b", t):
        dirs = _desktop_directories()
        if dirs:
            paths = [{"path": d} for d in dirs]
            return ObservationPlan(
                action_type="list_directory",
                payload={"directories": paths, "include_hidden": False},
                evidence_hint="Desktop directory entries counted from the filesystem.",
                question_kind="desktop_contents",
            )

    # "Can you see my desktop/screen" — seeing questions get eyes.
    if re.search(r"\b(can|could) you (see|view|look at|check)\b.{0,30}\b(desktop|screen|monitor|display)\b", t) or \
       re.search(r"\b(do you have (access|eyes))\b.{0,30}\b(desktop|screen|monitor|display)\b", t):
        return ObservationPlan(
            action_type="screen_capture",
            payload={"filename": "observation.png"},
            evidence_hint="Live screenshot captured from the primary display.",
            question_kind="screen_contents",
        )

    # What's on my screen / screenshot questions.
    if re.search(r"\b(on (my|the) screen|screenshot|what am i looking at|my (screen|display))\b", t):
        return ObservationPlan(
            action_type="screen_capture",
            payload={"filename": "observation.png"},
            evidence_hint="Live screenshot captured from the primary display.",
            question_kind="screen_contents",
        )

    # Browser tabs (how many tabs are open / list my tabs).
    if re.search(r"\b(tabs?\b.{0,20}\b(open|browser|chrome|edge|firefox)|how many tabs|list.{0,15}tabs|open tabs)\b", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Browser and desktop windows enumerated from the host (tabs appear as window titles).",
            question_kind="browser_tabs",
        )

    # Running apps / processes.
    if re.search(r"\b(running|open) (apps?|programs?|process(es)?|applications?)\b|\b(apps?|programs?|process(es)?|applications?)\b.{0,5}\b(running|open)\b|\bwhat.{0,20}running\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Live process list observed from the host.",
            question_kind="running_processes",
        )

    # Open windows.
    if re.search(r"\b(open|active|browser) windows?\b|\bwhich windows? (are )?open\b|how many.{0,15}windows", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Open desktop windows enumerated from the host.",
            question_kind="open_windows",
        )

    # Installed applications (NOT running/startup — those have their own patterns).
    # Games get their own kind: any non-action question mentioning games
    # routes to the app inventory with game-aware evidence (live lesson:
    # 'where are my games' / 'how can i check my games on pc' got generic
    # File Explorer instructions from the LLM while the app scan sat unused).
    games_q = bool(re.search(r"\bgames?\b", t)) and not re.search(
        r"\b(play|open|launch|start|install|uninstall|delete|remove|download|buy|"
        r"update|mod|patch|cheat|cheats|walkthrough|review|trailer|about|watch|"
        r"stream|episode|season|series|movie|song|book)\b", t,
    )
    if (re.search(
        r"\b(installed|what|which|how many|how much|list|show|any|do i have|got)\b.{0,30}"
        r"\b(apps?|programs?|applications?|software|games?)\b|\bwhich software\b",
        t,
    ) and not re.search(r"\b(running|startup|boot|auto.?start|services?)\b", t)) or games_q:
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="Installed applications scanned from the host.",
            question_kind="installed_games" if games_q else "installed_apps",
        )

    return None


def render_observation_evidence(result: Any, plan: ObservationPlan) -> str:
    """Render an executed observation into compact evidence text for the LLM."""
    try:
        data = result if isinstance(result, dict) else {}
        if plan.action_type == "search_files":
            # search_files returns a plain list of matches (possibly empty) —
            # an EMPTY list is valid evidence of absence, not an error.
            results = result if isinstance(result, list) else []
            query = plan.payload.get("query", "?")
            raw_root = plan.payload.get("root_dir", "the workspace")
            root = (
                ", ".join(str(r) for r in raw_root)
                if isinstance(raw_root, (list, tuple))
                else str(raw_root)
            )
            exact = [r for r in results if not r.get("fuzzy_match")]
            fuzzy = [r for r in results if r.get("fuzzy_match")]
            is_dir = lambda r: r.get("type") == "directory"  # noqa: E731
            _no_match_guidance = (
                "This was a live filename walk of those locations with a time "
                "budget (system folders skipped) — NOT an Everything-style "
                "machine-wide index. Do NOT claim the file does not exist "
                "anywhere on the computer; say exactly which locations were "
                "searched and ask the owner for the folder or drive to search "
                "next."
            )
            if plan.question_kind in ("file_search", "file_location"):
                # Enumeration/location: the owner asked for EVERY match (or
                # its path) — render the full list so the reply can enumerate.
                if exact:
                    lines = [
                        f"- {r.get('file_name', r)}"
                        f"{' [folder]' if is_dir(r) else ''} -> {r.get('file_path', r)}"
                        for r in exact[:50]
                    ]
                    cap_note = (
                        "\n(The list may be truncated at the result cap.)"
                        if len(exact) >= int(plan.payload.get("max_results", 20))
                        else ""
                    )
                    return (
                        f"OBSERVED from filesystem search for '{query}': {len(exact)} match(es) "
                        f"under {root}:\n" + "\n".join(lines) + cap_note
                        + "\nAnswer ONLY from this evidence: enumerate the matches with their full "
                        "paths. If the list is empty, say no files matched."
                    )
                if fuzzy:
                    lines = [
                        f"- {r.get('file_name', r)}"
                        f"{' [folder]' if is_dir(r) else ''} -> {r.get('file_path', r)}"
                        f" (similarity {r.get('fuzzy_score')})"
                        for r in fuzzy[:20]
                    ]
                    return (
                        f"OBSERVED from filesystem search for '{query}': NO exact filename "
                        f"matches under {root}, but {len(fuzzy)} close match(es) — likely what "
                        "the owner meant (possible typo in the request):\n" + "\n".join(lines)
                        + "\nAnswer from this evidence: present these as the closest matches, "
                        "say the search name did not match exactly, and give the full paths."
                    )
                return (
                    f"OBSERVED from filesystem search for '{query}': NO matches found under "
                    f"{root}. {_no_match_guidance}"
                )
            if exact:
                paths = "; ".join(
                    f"{r.get('file_path', r)}{' [folder]' if is_dir(r) else ''}"
                    for r in exact[:10]
                )
                return (
                    f"OBSERVED from filesystem search for '{query}': {len(exact)} match(es) "
                    f"under {root}: {paths}"
                )
            if fuzzy:
                paths = "; ".join(
                    f"{r.get('file_path', r)} (similarity {r.get('fuzzy_score')})"
                    for r in fuzzy[:10]
                )
                return (
                    f"OBSERVED from filesystem search for '{query}': no exact matches under "
                    f"{root}, but close match(es): {paths}. Present these as the likely "
                    "intended files; the requested name did not match exactly."
                )
            return (
                f"OBSERVED from filesystem search for '{query}': NO matches found under {root}. "
                + _no_match_guidance
            )
        if plan.action_type == "list_directory" and data.get("success"):
            parts = []
            for listing in data.get("listings", []):
                entries = listing.get("entries", [])
                shown = ", ".join(entries[:40])
                parts.append(f"{listing.get('directory')}: {listing.get('count', len(entries))} entries ({shown})")
            total = sum(l.get("count", len(l.get("entries", []))) for l in data.get("listings", []))
            return f"OBSERVED from the filesystem: {total} total desktop entries. " + " | ".join(parts)
        if plan.action_type == "screen_capture" and data.get("success"):
            return f"OBSERVED: a live screenshot was captured at {data.get('file_path')}; describe answers from it."
        if plan.action_type == "list_processes" and data.get("success"):
            processes = data.get("processes", data.get("list", []))
            sample = ", ".join(str(p) for p in processes[:30])
            return f"OBSERVED: {data.get('count', len(processes))} running processes. Sample: {sample}"
        if plan.action_type == "list_windows" and data.get("success"):
            windows = data.get("open_windows", data.get("windows", []))
            titles = ", ".join(str(w) for w in windows[:25])
            return f"OBSERVED open windows: {windows and len(windows)} — {titles}"
        if plan.action_type == "list_capabilities" and data.get("success"):
            cats = data.get("categories", {})
            cat_lines = "\n".join(
                f"- {cat}: {', '.join(names[:8])}" + (" …" if len(names) > 8 else "")
                for cat, names in cats.items()
            )
            base = (
                f"OBSERVED from the capability registry: {data.get('tool_count', '?')} registered "
                f"tools across {len(cats)} categories:\n{cat_lines}\n"
            )
            if plan.payload.get("focus") == "internet":
                web_tools = cats.get("web", [])
                # web_search is the headline capability — alphabetical slicing
                # would bury it behind the browser_* tools.
                web_headline = [n for n in web_tools if n == "web_search"] + [
                    n for n in web_tools if n != "web_search"
                ]
                net_tools = cats.get("network", [])
                return (
                    base
                    + "Answer ONLY from this evidence. The agent demonstrably HAS "
                    f"internet/web tools — web ({', '.join(web_headline[:8])}) and network "
                    f"({', '.join(net_tools[:5])}). NEVER claim it has no internet access "
                    "or cannot browse/search the web; those tools are registered. If the "
                    "user wants live proof of connectivity, offer to run a network check "
                    "(ping / resolve_dns)."
                )
            return (
                base
                + "Answer ONLY from this evidence. The agent demonstrably HAS local access — "
                "filesystem tools (search, move, copy, delete), app inventory, OS control, "
                "screen capture. NEVER claim it cannot access this machine; if a specific "
                "task needs approval, say which action and that it will ask."
            )
        if plan.action_type == "list_apps" and data.get("success"):
            apps = data.get("applications", data.get("apps", []))
            if plan.question_kind == "installed_games":
                # Game questions must be answered from an actual filtered
                # list — 'OBSERVED 1027 apps, sample of 40' cannot be
                # counted and the LLM improvises File Explorer instructions.
                games = _filter_game_apps(apps)
                listing = "\n".join(f"- {g}" for g in games[:40])
                return (
                    f"OBSERVED {len(apps)} installed applications total; {len(games)} "
                    f"look like games or game launchers:\n{listing}\n"
                    "Answer ONLY from this evidence: count/list the games above. If "
                    "none matched, say the app inventory shows no games — do not "
                    "invent instructions."
                )
            names = ", ".join(str(a) for a in apps[:40])
            return f"OBSERVED {len(apps)} installed applications. Sample: {names}"
        if plan.action_type == "calculate_expression":
            if data.get("success"):
                return (
                    f"VERIFIED CALCULATION (deterministic tool, exact — do not "
                    f"recompute or second-guess it): "
                    f"{data.get('expression')} = {data.get('value_str')}\n"
                    f"State {data.get('value_str')} as the answer to the arithmetic "
                    f"question. Never substitute your own arithmetic."
                )
            return (
                f"CALCULATION ATTEMPTED but failed: {data.get('error', 'unknown error')} "
                f"for expression {data.get('expression', '?')!r}. Say the calculation "
                f"could not be completed and why — do not guess a number."
            )
        if plan.action_type == "analyze_data":
            stat = extract_statistic_from_analysis(result, plan)
            if stat:
                return (
                    f"VERIFIED DATA ANALYSIS (deterministic tool, exact — do not "
                    f"recompute or second-guess it): {stat['statistic']} of "
                    f"'{stat['column']}' in {data.get('file_name', 'the dataset')} "
                    f"= {stat['value_str']}\n"
                    f"State {stat['value_str']} as the answer to the question. "
                    f"Never substitute your own arithmetic."
                )
            if not data.get("success"):
                return (
                    f"DATA ANALYSIS ATTEMPTED but failed: "
                    f"{data.get('error', 'unknown error')}. Say the analysis "
                    f"could not be completed and why — do not guess a number."
                )
            columns = ", ".join(str(c) for c in (data.get("columns") or [])[:10])
            return (
                f"DATA ANALYSIS RAN but the requested statistic/column was not "
                f"found in the dataset (available columns: {columns or 'unknown'}). "
                f"Say what was found and what is missing — do not guess a number."
            )
        return f"OBSERVATION ATTEMPTED ({plan.action_type}) but returned no usable evidence: {str(result)[:200]}"
    except Exception:
        return f"OBSERVATION ATTEMPTED ({plan.action_type}) but could not be rendered."
