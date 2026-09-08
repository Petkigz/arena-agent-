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


# ── Phase 7: learning from the owner ("Beanie, watch this") ────────────────
@router.get("/mind/procedures")
def mind_procedures() -> dict:
    """Procedures the owner taught through conversation (and any taught
    skills). Teaching itself happens in chat — this is the inspection
    window."""
    procedures: list = []
    all_taught: list = []
    note = None
    try:
        from app.tools.skill_teaching_engine import SkillTeachingEngine
        procedures = SkillTeachingEngine.list_taught_skills(
            category="owner_taught_procedure")
        all_taught = SkillTeachingEngine.list_taught_skills()
    except Exception as exc:
        note = f"taught-skills store unavailable: {exc}"
    return {"success": True, "procedures": procedures,
            "total_taught_skills": len(all_taught),
            **({"note": note} if note else {}),
            "how_to_teach": "In chat: \"Beanie, watch this\", then the steps, "
                            "then \"that's it\", then confirm with \"yes\"."}


@router.get("/mind/teaching/sessions")
def mind_teaching_sessions() -> dict:
    """Active teaching sessions (in-memory; they expire when abandoned)."""
    return {"success": True,
            "sessions": BeanieMind.get_instance().teaching.sessions()}


# ── Phase 8: learning from images, video, web media ────────────────────────
class MediaLearnIn(BaseModel):
    target: str = Field(min_length=1, max_length=2000)
    focus: Optional[str] = None
    context: Optional[str] = None
    deep: bool = False


@router.post("/mind/learn/media")
def mind_learn_media(body: MediaLearnIn) -> dict:
    """Observe a media target (YouTube URL, image, audio/video file, web
    page) and run the experience through the one learning loop.
    Deterministic observation first; ``deep=true`` additionally asks the
    existing LLM analysers. Watching is never counted as verification."""
    return BeanieMind.get_instance().media_learning.learn_from_media(
        body.target, focus=body.focus, context=body.context, deep=body.deep)


# ── Phase 9: curiosity / the UNKNOWN system ────────────────────────────────
@router.get("/mind/curiosity")
def mind_curiosity(limit: int = Query(default=10, ge=1, le=100)) -> dict:
    """What Beanie knows she doesn't know: open unknowns by priority
    (encounters first, recency second) + the resolution ledger."""
    mind = BeanieMind.get_instance()
    return {"success": True, **mind.curiosity.stats(),
            "top": mind.curiosity.curiosities(limit=limit)}


class InvestigateIn(BaseModel):
    topic: Optional[str] = None


@router.post("/mind/curiosity/investigate")
def mind_curiosity_investigate(body: InvestigateIn) -> dict:
    """Investigate before asking: search her own memory for the top open
    unknown (or a named one). Real evidence closes it; no evidence keeps it
    open and names the next honest step."""
    return BeanieMind.get_instance().curiosity.investigate(body.topic)


class ResolveUnknownIn(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/mind/curiosity/resolve")
def mind_curiosity_resolve(body: ResolveUnknownIn) -> dict:
    """The owner answers an open unknown."""
    return BeanieMind.get_instance().curiosity.resolve(body.topic, body.answer)


# ── Phase 10: reasoning & imagination (simulate / compare) ─────────────────
class SimulateIn(BaseModel):
    action_type: str = Field(min_length=1, max_length=120)


@router.post("/mind/imagination/simulate")
def mind_imagination_simulate(body: SimulateIn) -> dict:
    """Run a candidate action in her head BEFORE acting: prediction +
    her own verified history + open unknowns + deterministic counsel."""
    return BeanieMind.get_instance().imagination.simulate(body.action_type)


class CompareRealityIn(BaseModel):
    action_type: str = Field(min_length=1, max_length=120)
    success: bool
    surprisal: Optional[float] = None
    source: str = "owner"


@router.post("/mind/imagination/compare")
def mind_imagination_compare(body: CompareRealityIn) -> dict:
    """Compare a prediction with reality. success must be EVIDENCE the
    owner has; the outcome becomes training data through the learning
    loop."""
    return BeanieMind.get_instance().imagination.compare(
        body.action_type, body.success, surprisal=body.surprisal,
        source=body.source)


@router.get("/mind/imagination")
def mind_imagination(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    """The prediction-vs-reality ledger: confirmed/refuted comparisons,
    mean surprisal, and the epistemic ladder."""
    mind = BeanieMind.get_instance()
    return {"success": True, **mind.imagination.stats(),
            "records": mind.imagination.records(limit=limit)}


# ── Phase 11: embodied intelligence (the motor system) ─────────────────────
class MotorPlanIn(BaseModel):
    intent: str = Field(min_length=1, max_length=500)


@router.post("/mind/embodiment/plan")
def mind_embodiment_plan(body: MotorPlanIn) -> dict:
    """Concept → motor pathways. She says what she needs in concept terms
    ("interact with my phone"); the capability layer figures out how.
    Plans only — execution stays with the cycle's authorization path."""
    return BeanieMind.get_instance().embodiment.motor_plan(body.intent)


@router.get("/mind/embodiment")
def mind_embodiment(concept: Optional[str] = Query(default=None, max_length=200)) -> dict:
    """Her body image: what her body can do, grouped by category,
    optionally filtered by concept."""
    return BeanieMind.get_instance().embodiment.body_map(concept)
