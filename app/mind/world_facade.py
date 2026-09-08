"""WorldModelFacade — Phase 3 (Beanie AGI roadmap): reasoning ABOUT the world.

The repository already has a persistent, provenance-enforced ``WorldModel``
(entities / relationships / observations). It was wired for POST-action
verification. Phase 3 adds the missing half: a facade through which the mind
can *understand the environment before acting* — the roadmap's world-first
direction — plus the roadmap's ontology (People, Places, Devices,
Applications, Files, Websites, Accounts, Objects, Concepts, Events,
Processes).

Design rules kept from the existing model (they are the honesty contract):

- Entity attributes hold identity/descriptor data only. Environmental STATE
  lives in Observations with provenance — never in attributes.
- No fabrication: ``understand`` reports what is known and lists what is NOT
  known (``gaps``). An unknown stays unknown until observed.
- Deterministic: token/entity matching only — no LLM in this layer.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# The roadmap's ontology (docs/AGI_ROADMAP.md, Phase 3). Relationships and
# States are edges/observations in the underlying model, not entity types.
WORLD_ENTITY_TYPES = {
    "person": "a human being (owner, contacts, collaborators)",
    "place": "a physical or logical location",
    "device": "a phone, computer, or other hardware the owner uses",
    "application": "software installed on a device",
    "file": "a document, media file, or any filesystem object",
    "website": "a site or web service the owner uses",
    "account": "a named account or credential context (never the secret itself)",
    "object": "a physical or digital object that fits no other type",
    "concept": "an idea, topic, or domain of knowledge",
    "event": "something that happened or is scheduled",
    "process": "a running or recurring procedure",
}

_STATE_PREDICATES = ("status", "state", "running", "location", "owner_of", "editing")


class WorldModelFacade:
    """The mind's view of the world model (injected store — no globals)."""

    def __init__(self, world: Any) -> None:
        self.world = world

    def _wired(self) -> Optional[Dict[str, Any]]:
        if self.world is None:
            return {"success": False, "reason": "world model not wired"}
        return None

    # ── ontology ─────────────────────────────────────────────────────────
    def ontology(self) -> Dict[str, Any]:
        return {
            "entity_types": dict(WORLD_ENTITY_TYPES),
            "states": "environmental state is stored as provenance-tracked observations, never entity attributes",
            "relationships": "typed edges between entities (e.g. uses / contains / editing)",
        }

    # ── learning surface (owner teaches, probes observe) ─────────────────
    def remember_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Add or update an entity. Typed and fail-fast (invariant #7): an
        unknown entity_type is rejected with the valid vocabulary, never
        silently coerced."""
        if (guard := self._wired()) is not None:
            return guard
        name = str(name or "").strip()
        if not name:
            return {"success": False, "reason": "empty entity name"}
        if entity_type not in WORLD_ENTITY_TYPES:
            return {
                "success": False,
                "reason": f"unknown entity_type '{entity_type}'",
                "valid_types": sorted(WORLD_ENTITY_TYPES),
            }
        attrs = dict(attributes or {})
        # The underlying model rejects state keys in attributes — strip and
        # report them honestly instead of raising mid-teach.
        moved_to_observations = {
            k: attrs.pop(k) for k in list(attrs) if k in getattr(self.world, "ENTITY_STATE_KEYS", frozenset())
        }
        entity = self.world.upsert_entity(name=name, entity_type=entity_type, attributes=attrs, confidence=confidence)
        result: Dict[str, Any] = {
            "success": True,
            "entity_id": getattr(entity, "id", None),
            "name": name,
            "entity_type": entity_type,
        }
        if moved_to_observations:
            result["state_fields_belong_in_observations"] = sorted(moved_to_observations)
        return result

    def relate(self, subject_name: str, predicate: str, object_name: str,
               confidence: float = 1.0) -> Dict[str, Any]:
        """Typed edge between two KNOWN entities. Missing endpoints are an
        honest failure — fabricating entities to satisfy a relationship would
        be invention, not learning."""
        subject = self._resolve(subject_name)
        obj = self._resolve(object_name)
        missing = [n for n, e in ((subject_name, subject), (object_name, obj)) if e is None]
        if missing:
            return {
                "success": False,
                "reason": f"unknown entities: {missing} — teach them first (remember_entity)",
            }
        rel = self.world.relate(subject.id, str(predicate), obj.id, confidence=confidence)
        return {"success": True, "relationship_id": getattr(rel, "id", None),
                "subject": subject_name, "predicate": str(predicate), "object": object_name}

    def observe_state(self, subject_name: str, predicate: str, value: Any,
                      source: str, observation_type: str = "direct",
                      confidence: float = 1.0) -> Dict[str, Any]:
        """Record a state observation WITH provenance (the model's contract:
        state never lives in entity attributes)."""
        if not source:
            return {"success": False, "reason": "observations require a source (provenance)"}
        from uuid import uuid4
        from app.cognition.world_model import Observation
        try:
            obs = self.world.observe(Observation(
                id=uuid4().hex, subject=str(subject_name), predicate=str(predicate),
                value=value, source=str(source), observation_type=observation_type,
                confidence=confidence,
            ))
        except Exception as exc:
            return {"success": False, "reason": f"{type(exc).__name__}: {exc}"}
        return {"success": True, "observation_id": getattr(obs, "id", None)}

    # ── reasoning surface (pre-action understanding) ─────────────────────
    def _resolve(self, name: str):
        try:
            return self.world.resolve_entity(str(name).strip())
        except Exception:
            return None

    def entity(self, name: str) -> Optional[Dict[str, Any]]:
        e = self._resolve(name)
        return self._entity_dict(e) if e else None

    def entities(self, entity_type: Optional[str] = None,
                 name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            found = self.world.find_entities(name=name, entity_type=entity_type)[: int(limit)]
        except Exception:
            return []
        return [self._entity_dict(e) for e in found]

    def what_do_i_know_about(self, name: str) -> Dict[str, Any]:
        """Everything known about one subject: entity, its recent states, its
        relationships. The honest answer may be 'nothing yet'."""
        if self.world is None:
            return {"known": False, "subject": name, "reason": "world model not wired"}
        e = self._resolve(name)
        if e is None:
            return {"known": False, "subject": name,
                    "reason": "no entity by this name in the world model yet"}
        try:
            observations = [self._obs_dict(o) for o in self.world.recent_observations(subject=e.name, limit=20)]
        except Exception:
            observations = []
        relationships: List[Dict[str, Any]] = []
        try:
            for rel in self.world.related(e.id)[:20]:
                obj = self.world.get_entity(rel.object_id)
                relationships.append({
                    "predicate": rel.predicate,
                    "object": obj.name if obj else rel.object_id,
                    "confidence": rel.confidence,
                })
            for rel in self.world.related_to(e.id)[:20]:
                subj = self.world.get_entity(rel.subject_id)
                relationships.append({
                    "predicate": f"^{rel.predicate}",  # incoming edge marker
                    "subject": subj.name if subj else rel.subject_id,
                    "confidence": rel.confidence,
                })
        except Exception:
            pass
        return {"known": True, "entity": self._entity_dict(e),
                "recent_observations": observations, "relationships": relationships}

    def understand(self, text: str) -> Dict[str, Any]:
        """Pre-action world context for a goal description.

        Deterministic: entities whose names (or alias attributes) appear in
        the text are matched; their latest states are attached; everything
        mentioned-but-unknown is listed under ``gaps`` so the reasoning layer
        can decide to investigate or ask — never paper over.
        """
        text = str(text or "")
        if self.world is None:
            return {"success": False, "reason": "world model not wired",
                    "matched_entities": [], "gaps": []}
        lowered = text.lower()
        matched: List[Dict[str, Any]] = []
        try:
            all_entities = self.world.find_entities()
        except Exception:
            all_entities = []
        for e in all_entities:
            names = {e.name.lower()}
            aliases = (e.attributes or {}).get("aliases")
            if isinstance(aliases, list):
                names |= {str(a).lower() for a in aliases if str(a).strip()}
            if any(n and n in lowered for n in names):
                latest: Dict[str, Any] = {}
                try:
                    for o in self.world.recent_observations(subject=e.name, limit=3):
                        latest.setdefault(o.predicate, self._obs_dict(o))
                except Exception:
                    pass
                matched.append({"entity": self._entity_dict(e), "latest_states": latest})
        # Gap detection: salient nouns with no entity behind them.
        gaps: List[str] = []
        for token in re.findall(r"[a-z][a-z0-9_-]{3,}", lowered):
            if token in ("find", "open", "that", "this", "what", "where", "yesterday",
                         "today", "please", "could", "would", "show", "editing"):
                continue
            if any(token in (m["entity"]["name"].lower()) for m in matched):
                continue
            if self._resolve(token) is None and len(gaps) < 8:
                if token not in gaps:
                    gaps.append(token)
        return {
            "success": True,
            "text": text,
            "matched_entities": matched,
            "gaps": gaps,  # UNKNOWN stays visible — Phase 9 investigates these
            "note": "world context assembled BEFORE capability selection (roadmap Phase 2 direction)",
        }

    def stats(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        total = 0
        try:
            for e in self.world.find_entities():
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
                total += 1
        except Exception:
            pass
        return {"entity_count": total, "by_type": by_type,
                "ontology_size": len(WORLD_ENTITY_TYPES)}

    # ── serialization helpers ────────────────────────────────────────────
    @staticmethod
    def _entity_dict(e: Any) -> Dict[str, Any]:
        return {
            "id": getattr(e, "id", None), "name": getattr(e, "name", None),
            "entity_type": getattr(e, "entity_type", None),
            "attributes": getattr(e, "attributes", {}),
            "confidence": getattr(e, "confidence", None),
            "first_seen": getattr(e, "first_seen", None),
            "last_seen": getattr(e, "last_seen", None),
        }

    @staticmethod
    def _obs_dict(o: Any) -> Dict[str, Any]:
        return {
            "predicate": getattr(o, "predicate", None),
            "value": getattr(o, "value", None),
            "source": getattr(o, "source", None),
            "observation_type": getattr(o, "observation_type", None),
            "confidence": getattr(o, "confidence", None),
            "observed_at": getattr(o, "observed_at", None),
        }
