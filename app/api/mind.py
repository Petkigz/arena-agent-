"""Mind API — owner-visible window onto BeanieMind.

Phase 1 (roadmap): identity / state / entries.
Phases 3–5 (roadmap): the world model, the self model, and unified memory
become things the owner can READ and TEACH through — conversation remains the
primary teaching surface; these endpoints are the inspectable substrate
behind it.

Read endpoints never mutate. Teaching endpoints (world entities/relations/
observations, memories, social) are typed, fail-fast, and honest — an
unknown type or a missing prerequisite is a clear failure, never a silent
coercion (AGENT_INVARIANTS §7).
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.mind import BeanieMind

router = APIRouter()


# ── Phase 1: identity / state / entries ─────────────────────────────────────
@router.get("/mind/identity")
def mind_identity() -> dict:
    """The persisted 'I am Beanie' record plus development milestones."""
    return BeanieMind.get_instance().describe()


@router.get("/mind/state")
def mind_state() -> dict:
    """The BeanieState skeleton (M2): every room, honestly marked
    ok / wired / unavailable."""
    return {
        "success": True,
        "identity": BeanieMind.get_instance().identity.get("name", "Beanie"),
        "state": BeanieMind.get_instance().state(),
    }


@router.get("/mind/entries")
def mind_entries(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """Recent inputs through the one door, newest first."""
    mind = BeanieMind.get_instance()
    return {
        "success": True,
        "entries": mind.entries(limit=limit),
        "stats": mind.entry_stats(),
    }


# ── Phase 3: the world model ────────────────────────────────────────────────
@router.get("/mind/world")
def mind_world() -> dict:
    """Ontology + landscape of the persistent world model."""
    world = BeanieMind.get_instance().world
    return {"success": True, "ontology": world.ontology(), "stats": world.stats()}


@router.get("/mind/world/about")
def mind_world_about(name: str = Query(min_length=1)) -> dict:
    """Everything known about one subject (entity, states, relationships)."""
    return {"success": True, **BeanieMind.get_instance().world.what_do_i_know_about(name)}


@router.get("/mind/world/understand")
def mind_world_understand(text: str = Query(min_length=1)) -> dict:
    """Pre-action world understanding for a goal description (Phase 2/3
    direction): matched entities + their latest states + visible gaps."""
    return BeanieMind.get_instance().world.understand(text)


class WorldEntityIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=40)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/mind/world/entities")
def mind_world_remember_entity(body: WorldEntityIn) -> dict:
    """Teach Beanie an entity (owner surface; probes use observe_state)."""
    return BeanieMind.get_instance().world.remember_entity(
        name=body.name, entity_type=body.entity_type,
        attributes=body.attributes, confidence=body.confidence)


class WorldRelationIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=80)
    object: str = Field(min_length=1, max_length=200)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/mind/world/relations")
def mind_world_relate(body: WorldRelationIn) -> dict:
    """Typed edge between two KNOWN entities."""
    return BeanieMind.get_instance().world.relate(
        subject_name=body.subject, predicate=body.predicate,
        object_name=getattr(body, "object"), confidence=body.confidence)


class WorldObservationIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=80)
    value: Any
    source: str = Field(min_length=1, max_length=120)
    observation_type: str = Field(default="direct")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/mind/world/observations")
def mind_world_observe(body: WorldObservationIn) -> dict:
    """State WITH provenance — the world model's honesty contract."""
    return BeanieMind.get_instance().world.observe_state(
        subject_name=body.subject, predicate=body.predicate, value=body.value,
        source=body.source, observation_type=body.observation_type,
        confidence=body.confidence)


# ── Phase 4: the self model ─────────────────────────────────────────────────
@router.get("/mind/self")
def mind_self() -> dict:
    """Identity + capabilities + limitations + experiences (profile)."""
    mind = BeanieMind.get_instance()
    return mind.self_model.profile(memory_counts=mind.memory.counts())


@router.get("/mind/self/assess")
def mind_self_assess(task: str = Query(min_length=1)) -> dict:
    """Genuine internal state for 'can I do this?' — knowledge, confidence,
    evidence, possible actions (roadmap Phase 4 acceptance example)."""
    return {"success": True, **BeanieMind.get_instance().self_model.assess(task)}


# ── Phase 5: unified memory ─────────────────────────────────────────────────
@router.get("/mind/memory")
def mind_memory() -> dict:
    """The memory landscape: every kind, where it lives, how much exists."""
    return BeanieMind.get_instance().memory.overview()


@router.get("/mind/memory/meta")
def mind_memory_meta(q: str = Query(min_length=1)) -> dict:
    """Meta-memory (roadmap Phase 5): remembered_done / knows_how /
    heard_about / unknown — with the evidence behind the classification."""
    return {"success": True, **BeanieMind.get_instance().memory.meta.ask(q)}


class MemoryIn(BaseModel):
    kind: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=4000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source: Optional[str] = None
    task_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    outcome: Optional[str] = None
    success: Optional[bool] = None


@router.post("/mind/memory")
def mind_memory_remember(body: MemoryIn) -> dict:
    """Typed remembering through the unified facade."""
    return BeanieMind.get_instance().memory.remember(
        kind=body.kind, content=body.content, importance=body.importance,
        source=body.source, task_id=body.task_id, tags=body.tags,
        outcome=body.outcome, success=body.success)


class SocialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="person")
    relationship: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)
    provenance: str = Field(default="owner_taught", max_length=120)


@router.post("/mind/memory/social")
def mind_social_remember(body: SocialIn) -> dict:
    """Remember a person/organization/relationship."""
    return BeanieMind.get_instance().memory.social.remember(
        name=body.name, kind=body.kind, relationship=body.relationship,
        notes=body.notes, provenance=body.provenance)


@router.get("/mind/memory/social")
def mind_social_list(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """The social memory landscape."""
    social = BeanieMind.get_instance().memory.social
    return {"success": True, "count": social.count(), "people": social.list_people(limit=limit)}


# ── Phase 2: world-first reasoning ─────────────────────────────────────────
@router.get("/mind/brief")
def mind_brief_preview(text: str = Query(min_length=1)) -> dict:
    """Preview the world-first brief for a request WITHOUT running it:
    world context → self state → relevant memory, exactly in the order the
    mind uses before any capability is identified."""
    brief = BeanieMind.get_instance().world_first.assemble_brief(text)
    return {"success": True, "brief": brief}


@router.get("/mind/briefs")
def mind_briefs(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """Recent world-first briefs actually assembled at the door (newest
    first), with the attention-gate delivery decision for each."""
    mind = BeanieMind.get_instance()
    return {"success": True, "briefs": mind.briefs(limit=limit)}


# ── Phase 6: general learning ──────────────────────────────────────────────
class ExperienceIn(BaseModel):
    kind: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=1, max_length=4000)
    source: str = Field(min_length=1, max_length=120)
    outcome: Optional[str] = None
    success: Optional[bool] = None
    prediction: Optional[str] = None
    predicted_confidence: Optional[float] = None
    action_type: Optional[str] = None
    goal_type: Optional[str] = None


@router.post("/mind/learn")
def mind_learn(body: ExperienceIn) -> dict:
    """Submit an experience to the one learning loop (action outcome,
    conversation, correction, observation, media, demonstration, experiment).
    success must be evidence the caller has — never a guess."""
    return BeanieMind.get_instance().learn(body.model_dump(exclude_none=True))


@router.get("/mind/learning")
def mind_learning_stats() -> dict:
    """The learning landscape: experiences by kind and novelty."""
    return {"success": True, **BeanieMind.get_instance().learning.stats()}


@router.get("/mind/learning/events")
def mind_learning_events(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """Recent learning events, newest first (owner-inspectable)."""
    return {"success": True,
            "events": BeanieMind.get_instance().learning.events(limit=limit)}
