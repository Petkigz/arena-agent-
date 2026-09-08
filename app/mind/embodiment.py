"""Embodiment — Phase 11 (Beanie AGI roadmap): the existing capabilities
become the motor system.

The roadmap's key change: Beanie doesn't know "tool #73". She knows "I need
to interact with my phone" — the capability layer figures out how. This
organ is that translation, deterministic end-to-end:

- ``motor_plan(intent)`` — she states an intent in CONCEPT terms; the organ
  expands the concept (a small deterministic synonym table), scans the tool
  manifest (184 capabilities) by real term overlap, consults the existing
  ``tool_matcher`` as a primary resolver when it fires, and returns ranked
  motor pathways: action type, category, embodiment (pc / android / web),
  and what authorization the action requires.
- ``body_map(concept=None)`` — her body image: what her body can do,
  grouped by category, optionally filtered by concept.

Honesty rules:
- the organ PLANS, it never EXECUTES — acting stays with the cognitive
  cycle's proposal/authorization/verification path (one cognitive
  authority; capability handlers are never invoked here);
- authority ≠ intelligence: a pathway she understands but is not
  authorized to take is surfaced as ``requires_owner_approval``, not
  hidden and not refused;
- a missing motor pathway is an honest ``None`` AND becomes an open
  unknown in the curiosity system (motor gaps are ignorance too);
- every candidate carries its evidence (matched terms) — no vibes.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# roadmap concept verbs/nouns → capability vocabulary. Small, explicit,
# deterministic — extended as she meets new bodies.
_CONCEPT_ALIASES = {
    "phone": ["android", "adb", "mobile", "sms", "call", "text"],
    "mobile": ["android", "adb", "mobile", "sms"],
    "document": ["file", "document", "read", "write"],
    "documents": ["file", "document"],
    "picture": ["image", "screenshot", "camera", "photo"],
    "pictures": ["image", "screenshot", "camera", "photo"],
    "video": ["video", "media", "record"],
    "website": ["browser", "web", "url", "navigate"],
    "webpage": ["browser", "web", "url", "navigate"],
    "app": ["application", "launch", "open", "program"],
    "application": ["application", "launch", "open", "program"],
    "screen": ["screen", "display", "screenshot", "monitor"],
    "message": ["message", "sms", "send", "communicate"],
    "email": ["email", "mail", "send", "communicate"],
    "sound": ["audio", "voice", "sound", "speak"],
    "music": ["audio", "media", "play"],
    "clipboard": ["clipboard", "copy", "paste"],
}

_EMBODIMENT_HINTS = (
    ("android", ("android", "adb")),
    ("web", ("browser", "web_", "url", "website")),
    ("pc", ()),
)

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "your", "you", "are", "was", "were", "can", "could", "would", "should",
    "please", "into", "onto", "not", "but", "all", "any", "her", "his",
    "need", "want", "interact", "use", "using", "via", "through", "some",
    "how", "what", "when", "then", "them", "these", "those",
})


def _terms(text: str) -> List[str]:
    out: List[str] = []
    for t in re.findall(r"[a-z0-9]{3,}", str(text).lower()):
        if t in _STOPWORDS:
            continue
        # light deterministic stemming: 'documents'/'files' must reach the
        # concept vocabulary ('document'/'file')
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


class Embodiment:
    """Her motor system: concepts in, ranked capabilities out — never
    execution."""

    def __init__(self, mind: Any) -> None:
        self.mind = mind

    # ── the motor plan ───────────────────────────────────────────────────
    def motor_plan(self, intent: str) -> Dict[str, Any]:
        intent = str(intent or "").strip()
        if not intent:
            return {"success": False, "reason": "motor plan needs an intent"}
        manifest = self._manifest()
        if not manifest:
            return {"success": False,
                    "reason": "tool manifest unavailable — the body map "
                              "cannot be read"}
        concept_terms = self._expand(intent)
        candidates = self._scan(manifest, concept_terms)
        primary = self._primary_match(intent)
        if primary:
            candidates = self._promote(candidates, primary)

        if not candidates:
            # a missing motor pathway is ignorance too — curiosity owns it
            try:
                self.mind.curiosity.register(
                    f"motor pathway: {intent[:80]}", source="embodiment_gap",
                    context=intent[:120])
            except Exception as exc:
                app_logger.warning(f"Motor gap not registered: {exc}")
            return {"success": True, "intent": intent,
                    "epistemic_kind": "plan", "motor_path": None,
                    "candidates": [],
                    "note": "I have no motor pathway for this yet — "
                            "registered as an open unknown"}

        return {"success": True, "intent": intent,
                "epistemic_kind": "plan",
                "motor_path": candidates[0]["action_type"],
                "candidates": candidates[:5],
                "note": "this is a PLAN, not an action — execution stays "
                        "with the cognitive cycle's authorization path"}

    def _expand(self, intent: str) -> List[str]:
        """Deterministic concept expansion: 'phone' also means android/adb/
        sms/... — the vocabulary of bodies she can inhabit."""
        terms = _terms(intent)
        expanded = list(terms)
        for term in terms:
            expanded.extend(_CONCEPT_ALIASES.get(term, []))
        return list(dict.fromkeys(expanded))  # dedupe, keep order

    def _scan(self, manifest: Dict[str, Dict[str, Any]],
              terms: List[str]) -> List[Dict[str, Any]]:
        term_set = set(terms)
        scored: List[Dict[str, Any]] = []
        for action_type, entry in manifest.items():
            name = str(entry.get("name") or action_type)
            desc = str(entry.get("description") or "")
            cat = str(entry.get("category") or "")
            hay_terms = set(_terms(f"{name} {desc} {cat}")) | \
                {name.lower(), cat.lower()}
            matched = sorted(term_set & hay_terms)
            if not matched:
                continue
            score = round(len(matched) / max(1, len(term_set)), 3)
            level = entry.get("safety_level", 0)
            try:
                level = int(level)
            except Exception:
                level = 0
            scored.append({
                "action_type": action_type,
                "category": cat,
                "description": desc[:200],
                "safety_level": level,
                "requires_owner_approval": level >= 3,
                "embodiment": self._embodiment_of(name, cat, desc),
                "matched_terms": matched,
                "score": score,
            })
        scored.sort(key=lambda c: (-c["score"], c["action_type"]))
        return scored

    @staticmethod
    def _embodiment_of(name: str, category: str, desc: str) -> str:
        low = f"{name} {category} {desc}".lower()
        for body, hints in _EMBODIMENT_HINTS:
            if any(h in low for h in hints):
                return body
        return "pc"

    def _primary_match(self, intent: str) -> Optional[Dict[str, Any]]:
        """The existing tool_matcher — the resolver the roadmap demoted the
        capability matcher to — gets first shot as the primary pathway."""
        try:
            from app.cognition.tool_matcher import match_control_tool
            match = match_control_tool(intent)
        except Exception as exc:
            app_logger.debug(f"Primary matcher unavailable: {exc}")
            return None
        if match is None:
            return None
        return {"action_type": getattr(match, "action_type", ""),
                "score": float(getattr(match, "score", 0.0)),
                "matched_terms": list(getattr(match, "matched_terms", ()))}

    def _promote(self, candidates: List[Dict[str, Any]],
                 primary: Dict[str, Any]) -> List[Dict[str, Any]]:
        action = primary.get("action_type")
        if not action:
            return candidates
        for cand in candidates:
            if cand["action_type"] == action:
                cand["primary_match"] = True
                cand["primary_score"] = primary.get("score")
                return [cand] + [c for c in candidates if c is not cand]
        # the matcher saw a pathway the term scan missed — trust it, but
        # keep the evidence honest
        return [{
            "action_type": action, "category": "",
            "description": "(surfaced by the capability resolver)",
            "safety_level": 0, "requires_owner_approval": False,
            "embodiment": "pc", "matched_terms": primary.get("matched_terms"),
            "score": primary.get("score"), "primary_match": True,
        }] + candidates

    # ── body image ───────────────────────────────────────────────────────
    def body_map(self, concept: Optional[str] = None) -> Dict[str, Any]:
        """What her body can do — grouped by category, optionally filtered
        by concept. Reading the map is not acting on it."""
        manifest = self._manifest()
        if not manifest:
            return {"success": False,
                    "reason": "tool manifest unavailable"}
        terms = set(self._expand(concept)) if concept else None
        by_category: Dict[str, int] = {}
        pathways: List[str] = []
        for action_type, entry in sorted(manifest.items()):
            cat = str(entry.get("category") or "other")
            hay = f"{entry.get('name', '')} {entry.get('description', '')} {cat}"
            if terms is not None and not (terms & set(_terms(hay))):
                continue
            by_category[cat] = by_category.get(cat, 0) + 1
            pathways.append(action_type)
        return {"success": True, "capabilities": len(pathways),
                "by_category": dict(sorted(by_category.items(),
                                           key=lambda kv: -kv[1])),
                "pathways": pathways[:50],
                **({"concept": concept} if concept else {})}

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
