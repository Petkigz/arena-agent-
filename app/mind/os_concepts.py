"""OSConceptLayer — Phase 12 (Beanie AGI roadmap): true OS-level
generalization (map item M10).

The roadmap's rule: don't build WindowsTool / MacTool / LinuxTool /
AndroidTool as separate intelligence. Build ONE concept layer — open,
close, move, copy, rename, search, install, configure, read, write,
observe, click, type, navigate, communicate — and let the embodiment layer
map concepts to platforms. Then "how I accomplish this on one body"
generalizes to the other bodies.

Mechanics (deterministic, no LLM):
- ``express(intent)`` — parse an intent into (concept, target); the concept
  is platform-free; the mapping is derived from the REAL tool manifest by
  term evidence (no hand-catalogued platform tables to rot);
- ``transfer(...)`` — take a procedure (explicit steps, or one the owner
  taught through Phase 7) and re-express every step for a TARGET body:
  each step resolves to a capability on that body, or is flagged as a
  visible gap — generalization you can inspect, not a claim;
- ``concepts()`` — the vocabulary itself, with per-body coverage, so the
  owner can see exactly where her bodies differ.

Honesty rules:
- the layer EXPRESSES and MAPS; it never executes (same doctrine as
  Phase 11 — the cycle's authorization path keeps acting);
- every mapping carries its evidence (matched terms);
- a step with no embodiment on the target body is a flagged GAP, never a
  fabricated capability.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional

from app.mind.embodiment import _EMBODIMENT_HINTS
from app.utils.logger import app_logger

# the roadmap's concept verbs, platform-free. Synonyms expand deterministically.
_CONCEPT_VERBS: Dict[str, Dict[str, Any]] = {
    "open": {"synonyms": ["launch", "start"],
             "args": "target", "meaning": "make an app/file/resource active"},
    "close": {"synonyms": ["quit", "exit"],
              "args": "target", "meaning": "stop an active app/window"},
    "move": {"synonyms": [], "args": "source, destination",
             "meaning": "relocate an object"},
    "copy": {"synonyms": ["duplicate"], "args": "source, destination",
             "meaning": "replicate an object"},
    "rename": {"synonyms": [], "args": "target, new_name",
               "meaning": "give an object a new name"},
    "search": {"synonyms": ["find", "look"], "args": "query",
               "meaning": "locate objects matching a query"},
    "install": {"synonyms": [], "args": "package",
                "meaning": "add software to a body"},
    "configure": {"synonyms": ["settings"], "args": "target, value",
                  "meaning": "change how a body/setting behaves"},
    "read": {"synonyms": ["view"], "args": "target",
             "meaning": "take content in"},
    "write": {"synonyms": ["save"], "args": "target, content",
              "meaning": "put content out"},
    "observe": {"synonyms": ["inspect", "screenshot"], "args": "target",
                "meaning": "perceive state without changing it"},
    "click": {"synonyms": ["press", "tap"], "args": "target",
              "meaning": "activate a UI element"},
    "type": {"synonyms": ["enter", "input"], "args": "text",
             "meaning": "enter text"},
    "navigate": {"synonyms": ["browse", "visit"], "args": "destination",
                 "meaning": "move through a space (web, files, menus)"},
    "communicate": {"synonyms": ["message", "notify", "sms", "email"],
                    "args": "recipient",
                    "meaning": "exchange information with someone"},
}

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "your", "you", "are", "was", "were", "can", "could", "would", "should",
    "please", "into", "onto", "not", "but", "all", "any", "her", "his",
    "how", "what", "when", "then", "them", "these", "those", "want", "need",
})


def _terms(text: str) -> List[str]:
    out: List[str] = []
    for t in re.findall(r"[a-z0-9]{3,}", str(text).lower()):
        if t in _STOPWORDS:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # same light stem as the motor system
        out.append(t)
    return out


def current_platform() -> str:
    """The body she is currently running on — deterministic fact."""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    return sys.platform


class OSConceptLayer:
    """Platform-free concepts in; per-body capability maps out."""

    def __init__(self, mind: Any) -> None:
        self.mind = mind

    # ── express: intent → platform-free concept + per-body mapping ───────
    def express(self, intent: str) -> Dict[str, Any]:
        intent = str(intent or "").strip()
        if not intent:
            return {"success": False, "reason": "express needs an intent"}
        tokens = _terms(intent)
        verb, concept = self._find_concept(tokens)
        if concept is None:
            return {"success": False,
                    "reason": f"'{intent[:80]}' contains no OS concept verb "
                              "(open/close/copy/search/...)",
                    "concept_verbs": sorted(_CONCEPT_VERBS)}
        target_words = [t for t in tokens if t != verb]
        mapping = self._map_concept(concept)
        bodies = sorted(b for b, caps in mapping.items() if caps)
        return {
            "success": True,
            "epistemic_kind": "concept",
            "concept": concept,
            "meaning": _CONCEPT_VERBS[concept]["meaning"],
            "target": " ".join(target_words) or None,
            "mapping": mapping,
            "bodies": bodies,
            # learned on one body, doable on more than one → generalizes
            "generalizes": len(bodies) >= 2,
            "current_body": current_platform(),
        }

    @staticmethod
    def _find_concept(tokens: List[str]):
        """First concept verb in the utterance wins (deterministic)."""
        synonyms: Dict[str, str] = {}
        for concept, meta in _CONCEPT_VERBS.items():
            synonyms[concept] = concept
            for syn in meta["synonyms"]:
                synonyms[syn] = concept
        for tok in tokens:
            if tok in synonyms:
                return tok, synonyms[tok]
        return None, None

    def _map_concept(self, concept: str) -> Dict[str, List[Dict[str, Any]]]:
        """Which capabilities on which bodies implement this concept —
        derived from the live manifest by term evidence."""
        manifest = self._manifest()
        vocab = {concept} | set(_CONCEPT_VERBS[concept]["synonyms"])
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "pc": [], "android": [], "web": []}
        for action_type, entry in manifest.items():
            name = str(entry.get("name") or action_type)
            desc = str(entry.get("description") or "")
            cat = str(entry.get("category") or "")
            hay = set(_terms(f"{name} {desc} {cat}")) | {name.lower()}
            matched = sorted(vocab & hay)
            if not matched:
                continue
            body = self._body_of(name, cat, desc)
            buckets[body].append({
                "action_type": action_type,
                "matched_terms": matched,
                "safety_level": entry.get("safety_level", 0),
            })
        for body in buckets:
            buckets[body].sort(key=lambda c: c["action_type"])
        return buckets

    @staticmethod
    def _body_of(name: str, category: str, desc: str) -> str:
        low = f"{name} {category} {desc}".lower()
        for body, hints in _EMBODIMENT_HINTS:
            if any(h in low for h in hints):
                return body
        return "pc"

    # ── transfer: a procedure from one body, re-expressed for another ────
    def transfer(self, to_platform: str,
                 steps: Optional[List[str]] = None,
                 procedure: Optional[str] = None) -> Dict[str, Any]:
        """The roadmap's crown jewel: learn it on one body, generalize it
        to another. Steps come from the caller OR from a Phase-7 taught
        procedure. Every step resolves on the target body — or is flagged
        as a visible gap."""
        to_platform = str(to_platform or "").strip().lower()
        if to_platform not in ("pc", "android", "web"):
            return {"success": False,
                    "reason": "to_platform must be pc, android, or web"}
        if steps is None and procedure:
            loaded = self._load_procedure(procedure)
            if not loaded:
                return {"success": False,
                        "reason": f"no taught procedure named "
                                  f"'{procedure[:60]}'"}
            steps = loaded["steps"]
            source = f"taught procedure '{loaded['name']}'"
        elif steps:
            steps = [str(s) for s in steps if str(s).strip()]
            source = "explicit steps"
        else:
            return {"success": False,
                    "reason": "transfer needs steps or a taught procedure"}

        plan: List[Dict[str, Any]] = []
        resolved = gaps = 0
        for step in steps:
            exp = self.express(step)
            if not exp.get("success"):
                plan.append({"step": step, "concept": None,
                             "capability": None,
                             "status": "not an OS concept — cannot transfer"})
                gaps += 1
                continue
            concept = exp["concept"]
            candidates = exp["mapping"].get(to_platform) or []
            if candidates:
                resolved += 1
                plan.append({"step": step, "concept": concept,
                             "capability": candidates[0]["action_type"],
                             "alternatives": [c["action_type"]
                                              for c in candidates[1:4]],
                             "evidence": candidates[0]["matched_terms"],
                             "status": "resolved on target body"})
            else:
                gaps += 1
                plan.append({"step": step, "concept": concept,
                             "capability": None,
                             "status": f"no {to_platform} embodiment for "
                                       f"'{concept}' — visible gap"})
        return {"success": True, "to_platform": to_platform, "source": source,
                "steps": plan, "resolved": resolved, "gaps": gaps,
                "generalized": resolved > 0 and gaps == 0}

    def _load_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Read a Phase-7 taught procedure from the taught-skills store and
        split its numbered summary back into steps."""
        try:
            from app.tools.skill_teaching_engine import SkillTeachingEngine
            skills = SkillTeachingEngine.list_taught_skills(
                category="owner_taught_procedure")
        except Exception as exc:
            app_logger.warning(f"Taught-skills store unreadable: {exc}")
            return None
        match = next((s for s in skills
                      if str(s.get("skill_name", "")).lower()
                      == str(name).lower()), None)
        if match is None:
            return None
        steps = re.split(r";\s*\d+\)|^\d+\)", str(match.get("instructions", "")))
        steps = [s.strip(" .") for s in steps if s.strip(" .")]
        # the leading "Procedure 'goal':" header rides the first fragment
        steps = [re.sub(r"^Procedure[^:]*:\s*", "", s, count=1) for s in steps]
        # whichever fragment kept a number prefix, drop it
        steps = [re.sub(r"^\d+\)\s*", "", s) for s in steps]
        steps = [s for s in steps if s]
        return {"name": match.get("skill_name"), "steps": steps}

    # ── the vocabulary surface ───────────────────────────────────────────
    def concepts(self) -> Dict[str, Any]:
        """The concept vocabulary with per-body coverage — where her bodies
        agree and where they differ."""
        out: Dict[str, Any] = {}
        for concept in sorted(_CONCEPT_VERBS):
            mapping = self._map_concept(concept)
            coverage = {body: len(caps) for body, caps in mapping.items()}
            out[concept] = {
                "meaning": _CONCEPT_VERBS[concept]["meaning"],
                "synonyms": _CONCEPT_VERBS[concept]["synonyms"],
                "coverage": coverage,
                "generalizes": sum(1 for n in coverage.values() if n) >= 2,
            }
        return {"success": True, "current_body": current_platform(),
                "concept_verbs": out}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _manifest() -> Dict[str, Dict[str, Any]]:
        try:
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
            return manifest if isinstance(manifest, dict) else {}
        except Exception as exc:
            app_logger.warning(f"Manifest read failed: {exc}")
            return {}
