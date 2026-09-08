"""DemonstrationTeaching — Phase 7 (Beanie AGI roadmap): learning from the
owner through conversation. "Beanie, watch this."

The roadmap scene, deterministic end-to-end (no LLM, no forms, no JSON)::

    You: "Beanie, watch this."            → a teaching session opens
    You: "This is how I organize files."  → the goal is captured
    You: steps...                         → each one is gathered
    You: "That's it."                     → she proposes her understanding:
        "So to organize files, you: 1) ... 2) ... Is that correct?"
    You: "Yes."                           → a generalized procedure is stored

What "stored" means (honestly, all three surfaces):
1. cognitive memory — a ``procedural`` record, owner-taught, success=True
   (owner-confirmed), so the world-first brief and memory search surface it;
2. the EXISTING taught-skills store (``SkillTeachingEngine.teach_skill``,
   the form-driven engine this phase integrates) — so the procedure stays
   executable/listable by the old surface too;
3. the Phase-6 learning loop — the confirmed demonstration is submitted as a
   verified ``demonstration`` experience (ledger + novelty bookkeeping).

Honesty rules:
- Markers are conservative; bare "watch this" only opens a session in a short
  message, so "watch this video for me" cannot hijack a lesson.
- Nothing is stored until the owner says the understanding is correct.
  A rejected proposal costs no fabricated knowledge: she asks again, and
  after two misreadings she stops and says so — nothing saved.
- Sessions are in-memory and expire (server restart = start over); that
  limitation is stated, not hidden.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# ── deterministic conversation markers (the ONLY interface — no forms) ─────
_START_ANYWHERE = (
    "watch how", "let me show you", "i'll show you", "ill show you",
    "this is how i", "here's how i", "heres how i", "this is how you",
    "teach you how", "show you how",
)
# bare openers only count in short messages ("watch this video..." must not
# open a lesson)
_START_SHORT_ONLY = ("watch this", "watch me")
_SHORT_START_MAX_WORDS = 5

_END_MARKERS = (
    "that's it", "thats it", "that's all", "thats all",
    "that's everything", "thats everything", "that's the whole",
    "that's the procedure", "thats the procedure", "end of demonstration",
)
_CANCEL_MARKERS = ("nevermind", "never mind", "cancel", "forget it", "stop teaching")
_CONFIRM_EXACT = {
    "yes", "yep", "yeah", "yup", "sure", "correct", "right", "exactly",
    "that's right", "thats right", "that is right", "that's correct",
    "thats correct", "yes, that's right", "yes that's right",
    "yes, correct", "yes, exactly",
}
_CONFIRM_PREFIXES = ("yes", "correct", "exactly")
# a hedge is not a verdict
_NOT_CONFIRM = ("correct me",)
_REJECT_EXACT = {"no", "nope", "wrong", "incorrect", "not right", "not quite"}
_REJECT_PREFIXES = ("no,", "no ", "not right", "not quite", "wrong", "incorrect")

_STEP_PREFIX = re.compile(
    r"^\s*(?:\d+[.)]\s*|[-*•]\s*|step\s*\d+\s*[:.)]?\s*"
    r"|(?:first|second|third|fourth|fifth|then|next|after that|finally|lastly|last)"
    r"\s*[,:]?\s+)")

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "your", "you", "are", "was", "were", "can", "could", "would", "should",
    "please", "into", "onto", "not", "but", "all", "any", "her", "his",
    "how", "what", "when", "then", "them", "these", "those", "there",
    "first", "second", "third", "fourth", "fifth", "finally", "lastly",
    "next", "after", "before", "each", "every", "just", "really",
})

SESSION_TTL_SECONDS = 1800  # an abandoned lesson expires, it never lingers
MAX_REVISIONS = 2           # misread twice → stop honestly, nothing saved
MAX_STEPS = 20
NAME_WORDS = 4


@dataclass
class TeachingSession:
    conversation_id: str
    goal: str
    steps: List[str] = field(default_factory=list)
    state: str = "gathering"  # gathering → proposed → (confirm|reject)
    revisions: int = 0
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    proposal: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id, "goal": self.goal,
            "state": self.state, "steps": list(self.steps),
            "revisions": self.revisions, "started_at": self.started_at,
            "last_activity": self.last_activity,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().rstrip(".!?")).lower()


def _clean_step(text: str) -> str:
    step = str(text).strip()
    for _ in range(2):  # "1. first, open it" → strip both lead-ins
        new = _STEP_PREFIX.sub("", step)
        if new == step:
            break
        step = new
    return step.strip(" ,;:")


def _goal_words(goal: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", goal.lower())
            if t not in _STOPWORDS]


class DemonstrationTeaching:
    """The conversational teaching interface (Phase 7 / M7). One organ, one
    state machine per conversation; persistence integrates the existing
    taught-skills store and the Phase-6 learning loop."""

    def __init__(self, mind: Any) -> None:
        self.mind = mind
        self._lock = threading.RLock()
        self._sessions: Dict[str, TeachingSession] = {}

    # ── the conversational door ──────────────────────────────────────────
    def handle_message(self, conversation_id: str, content: str) -> Optional[str]:
        """Returns a teaching reply when this message belongs to the teaching
        flow (the turn is consumed by the lesson); None when the message is
        ordinary conversation for the cognitive cycle."""
        text = str(content or "")
        if not text.strip():
            return None
        with self._lock:
            self._prune_expired()
            session = self._sessions.get(conversation_id)
            if session is None:
                started = self._maybe_start(conversation_id, text)
                return started
            session.last_activity = time.time()
            norm = _norm(text)
            if self._matches_any(norm, _CANCEL_MARKERS):
                del self._sessions[conversation_id]
                return ("Okay — lesson cancelled. I haven't stored anything "
                        "from it.")
            if session.state == "gathering":
                return self._handle_gathering(conversation_id, session, text, norm)
            return self._handle_proposed(conversation_id, session, norm)

    # ── start ────────────────────────────────────────────────────────────
    def _maybe_start(self, conversation_id: str, text: str) -> Optional[str]:
        low = text.lower()
        marker = self._find_marker(low, _START_ANYWHERE)
        if marker is None and len(low.split()) <= _SHORT_START_MAX_WORDS:
            marker = self._find_marker(low, _START_SHORT_ONLY)
        if marker is None:
            return None
        goal = self._extract_goal(text)
        session = TeachingSession(conversation_id=conversation_id, goal=goal)
        self._sessions[conversation_id] = session
        heard = f" about {goal}" if goal else ""
        return (f"I'm watching{heard}. Tell me each step in order — one at a "
                "time or as a list. Say \"that's it\" when you're done, or "
                "\"cancel\" to stop.")

    def _extract_goal(self, text: str) -> str:
        low = text.lower()
        marker = self._find_marker(low, _START_ANYWHERE) or \
            self._find_marker(low, _START_SHORT_ONLY)
        if marker is None:
            return ""
        goal = text[low.index(marker) + len(marker):].strip(" :.-—–")
        goal = re.sub(r"^(?:i|you)\s+", "", goal, flags=re.I)
        return goal.strip(" :.-—–")

    @staticmethod
    def _find_marker(low: str, markers) -> Optional[str]:
        for marker in markers:
            if marker in low:
                return marker
        return None

    @staticmethod
    def _matches_any(norm: str, markers) -> bool:
        return any(marker in norm for marker in markers)

    # ── gathering ────────────────────────────────────────────────────────
    def _handle_gathering(self, conversation_id: str, session: TeachingSession,
                          text: str, norm: str) -> str:
        if self._matches_any(norm, _START_ANYWHERE + _START_SHORT_ONLY):
            if not session.steps and not session.goal:
                # the owner is NAMING the lesson: "this is how I organize
                # files" — capture it as the goal, not as a step
                session.goal = self._extract_goal(text)
                heard = f" — {session.goal}" if session.goal else ""
                return f"Okay{heard}. Now each step, in order."
            return ("We're already mid-lesson — keep giving me steps, say "
                    "\"that's it\" when done, or \"cancel\".")
        if self._matches_any(norm, _END_MARKERS):
            if not session.steps:
                return ("I haven't caught any steps yet — tell me at least "
                        "one step first, or say \"cancel\".")
            session.state = "proposed"
            session.proposal = self._proposal(session)
            return session.proposal
        step = _clean_step(text)
        if not step:
            return "That came through empty — give me the step again?"
        if len(session.steps) >= MAX_STEPS:
            return (f"I've already got {MAX_STEPS} steps — say \"that's it\" "
                    "to review them, or \"cancel\".")
        session.steps.append(step)
        return f"Step {len(session.steps)} noted: {step}"

    # ── proposed ─────────────────────────────────────────────────────────
    def _handle_proposed(self, conversation_id: str, session: TeachingSession,
                         norm: str) -> Optional[str]:
        if self._is_confirm(norm):
            record = self._persist(session)
            del self._sessions[conversation_id]
            name = record.get("name") or "your procedure"
            return (f"Got it — \"{name}\" is now one of my procedures "
                    f"({len(session.steps)} steps, verified by you). I'll "
                    "remember it.")
        if self._is_reject(norm):
            session.revisions += 1
            session.steps = []
            session.state = "gathering"
            if session.revisions >= MAX_REVISIONS:
                del self._sessions[conversation_id]
                return ("I've misread this twice — I'd rather stop than "
                        "store something wrong. Nothing was saved. You can "
                        "start again anytime with \"watch this\".")
            return ("Okay, I had that wrong — nothing saved. Tell me the "
                    "steps again, and I'll ask you to check once more.")
        # anything else: don't lose the draft, ask for the verdict
        return ("Just tell me: \"yes\" if I understood correctly, or \"no\" "
                "and we'll go over the steps again.")

    @staticmethod
    def _starts_with_word(norm: str, word: str) -> bool:
        return (norm == word or norm.startswith(word + " ")
                or norm.startswith(word + ","))

    def _is_confirm(self, norm: str) -> bool:
        if any(self._starts_with_word(norm, p) for p in _NOT_CONFIRM):
            return False
        return (norm in _CONFIRM_EXACT
                or any(self._starts_with_word(norm, p) for p in _CONFIRM_PREFIXES))

    def _is_reject(self, norm: str) -> bool:
        return (norm in _REJECT_EXACT
                or any(self._starts_with_word(norm, p.rstrip(" ,"))
                       for p in _REJECT_PREFIXES))

    # ── the proposal (her stated understanding, before any storage) ──────
    @staticmethod
    def _proposal(session: TeachingSession) -> str:
        lines = "\n".join(f"{i}. {step}" for i, step in enumerate(session.steps, 1))
        lead = f"So to {session.goal}, you:" if session.goal else "So you:"
        return f"{lead}\n{lines}\nIs that correct?"

    # ── persistence: cognitive memory + taught-skills store + loop ────────
    def _persist(self, session: TeachingSession) -> Dict[str, Any]:
        numbered = "; ".join(f"{i}) {step}" for i, step in enumerate(session.steps, 1))
        summary = (f"Procedure '{session.goal}': {numbered}"
                   if session.goal else f"Procedure: {numbered}")
        words = _goal_words(session.goal) or _goal_words(" ".join(session.steps))
        name = "-".join(words[:NAME_WORDS]) or f"procedure-{int(time.time())}"
        tags = ["owner_taught", "procedure"] + words[:4]

        # 1. cognitive memory — the record her briefs/search surface
        memory_id = None
        try:
            out = self.mind.memory.remember(
                "procedural", summary, importance=0.8, source="owner_teaching",
                tags=tags, outcome="owner_confirmed", success=True)
            if out.get("success"):
                memory_id = out.get("memory_id")
        except Exception as exc:
            app_logger.warning(f"Procedure not stored in cognitive memory: {exc}")

        # 2. the EXISTING taught-skills store (integration, not duplication)
        skill_stored = False
        try:
            from app.tools.skill_teaching_engine import SkillTeachingEngine
            res = SkillTeachingEngine.teach_skill(
                skill_name=name, category="owner_taught_procedure",
                trigger_keywords=words or [name], instructions=summary,
                sample_commands="",
                safety_rules="Owner-taught procedure; owner's scope only.")
            skill_stored = bool(res.get("success"))
        except Exception as exc:
            app_logger.warning(f"Taught-skills store skipped (non-fatal): {exc}")

        # 3. the Phase-6 learning loop — a VERIFIED demonstration experience
        learned = False
        try:
            rec = self.mind.learn({
                "kind": "demonstration", "content": summary,
                "source": "owner_teaching", "success": True,
                "outcome": "owner_confirmed", "goal_type": name,
            })
            learned = bool(rec.get("success"))
        except Exception as exc:
            app_logger.warning(f"Demonstration not fed to learning loop: {exc}")

        return {"name": name, "memory_id": memory_id,
                "skill_stored": skill_stored, "learned": learned,
                "summary": summary}

    # ── owner/inspection surface ─────────────────────────────────────────
    def sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._prune_expired()
            return [s.to_dict() for s in self._sessions.values()]

    def _prune_expired(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        for cid in [cid for cid, s in self._sessions.items()
                    if s.last_activity < cutoff]:
            del self._sessions[cid]
