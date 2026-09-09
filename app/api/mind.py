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


# ── Phase 12: OS concept layer (one mind, many bodies) ─────────────────────
class ExpressIn(BaseModel):
    intent: str = Field(min_length=1, max_length=500)


@router.post("/mind/os/express")
def mind_os_express(body: ExpressIn) -> dict:
    """Intent → platform-free concept + per-body capability mapping
    (pc / android / web), derived from the live manifest by evidence."""
    return BeanieMind.get_instance().os_concepts.express(body.intent)


class TransferIn(BaseModel):
    to_platform: str = Field(min_length=1, max_length=20)
    steps: Optional[List[str]] = None
    procedure: Optional[str] = None


@router.post("/mind/os/transfer")
def mind_os_transfer(body: TransferIn) -> dict:
    """Learned on one body, generalized to another: every step resolves to
    a capability on the target body, or is flagged as a visible gap."""
    return BeanieMind.get_instance().os_concepts.transfer(
        body.to_platform, steps=body.steps, procedure=body.procedure)


@router.get("/mind/os/concepts")
def mind_os_concepts() -> dict:
    """The platform-free concept vocabulary with per-body coverage — where
    her bodies agree and where they differ."""
    return BeanieMind.get_instance().os_concepts.concepts()


# ── Phase 13: continuous perception ────────────────────────────────────────
class PerceiveIn(BaseModel):
    modality: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=1, max_length=2000)
    source: str = ""
    urgent: bool = False


@router.post("/mind/perception")
def mind_perceive(body: PerceiveIn) -> dict:
    """Register a typed perception (screen/desktop/phone/camera/audio/
    network/environment/owner). Judged for significance; never acted on."""
    return BeanieMind.get_instance().perception.perceive(
        body.modality, body.content, source=body.source, urgent=body.urgent)


@router.post("/mind/perception/drain")
def mind_perception_drain(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    """Ingest buffered changes from the silent background watcher into
    perceptions, now."""
    return BeanieMind.get_instance().perception.drain_background_observer(
        limit=limit)


@router.get("/mind/perception")
def mind_perception_stream(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """The perception stream: what she has perceived, and what she judged
    significant, with reasons."""
    p = BeanieMind.get_instance().perception
    return {"success": True, **p.stats(), "stream": p.stream(limit=limit)}


# ── Phase 14: attention (M8) ───────────────────────────────────────────────
class AttentionTaskIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/mind/attention/task")
def mind_attention_task(body: AttentionTaskIn) -> dict:
    """Set the current-task anchor — the rung every change is measured
    against ('may interfere with what you're doing')."""
    return BeanieMind.get_instance().attention.set_task(body.text)


@router.post("/mind/attention/review")
def mind_attention_review() -> dict:
    """Arbitrate now: attend to every perception not yet attended, then say
    what currently deserves thought (with reasons and any advisory)."""
    return BeanieMind.get_instance().attention.review()


@router.get("/mind/attention")
def mind_attention_focus(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """The attention ledger: what she decided deserved thought, at what
    ladder rung, why — plus the current task anchor and issued advisories."""
    a = BeanieMind.get_instance().attention
    return {"success": True, **a.stats(),
            "snapshot": a.snapshot(),
            "advisories": a.advisories(),
            "history": a.focus_history(limit=limit)}


# ── Phase 15: motivation and goals ─────────────────────────────────────────
@router.get("/mind/goals")
def mind_goals(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """The goal ledger: candidate goals from her own evidence, their
    relevance and status. Goals are evidence-derived, never random."""
    m = BeanieMind.get_instance().motivation
    return {"success": True, **m.stats(),
            "prioritized": m.prioritize(limit=limit),
            "ledger": m.goals(limit=limit)}


@router.post("/mind/goals/propose")
def mind_goals_propose(goal_id: Optional[int] = None) -> dict:
    """Turn the top candidate (or a specific goal) into an owner-facing
    question built from its evidence. A proposal is a question, never an
    action."""
    return BeanieMind.get_instance().motivation.propose(goal_id)


@router.post("/mind/goals/decide")
def mind_goals_decide(goal_id: int, accept: bool) -> dict:
    """The owner answers a proposal. Accepted goals execute through the
    normal door under her authority; declined goals are never re-proposed."""
    return BeanieMind.get_instance().motivation.decide(goal_id, accept)


# ── Phase 16: social intelligence (the owner model) ────────────────────────
class SocialNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/mind/social")
def mind_social_model() -> dict:
    """The persistent owner model: facets with evidence and observation
    counts, people, routines, communication style, shared history — all
    measured, never cold-read."""
    return {"success": True, **BeanieMind.get_instance().social.model()}


@router.post("/mind/social/note")
def mind_social_note(body: SocialNoteIn) -> dict:
    """Extract owner-model facets from one utterance (preferences,
    boundaries, emotion cues, people, interests). Listening never acts."""
    return BeanieMind.get_instance().social.note(body.text)


# ── Phase 17: personality development ──────────────────────────────────────
@router.get("/mind/personality")
def mind_personality_profile() -> dict:
    """The developing personality: basic identity plus traits derived from
    her real ledgers — experiences, calibration, curiosity, her own reply
    patterns, the owner's values, adaptation. Nothing invented."""
    p = BeanieMind.get_instance().personality
    return {"success": True, "profile": p.profile(),
            "values": p.values(),
            "communication": p.communication_patterns(),
            "changes": p.changes()}


@router.post("/mind/personality/derive")
def mind_personality_derive() -> dict:
    """Re-derive the profile from the ledgers now, snapshot it, and report
    what changed since the last snapshot — the verifiable record of
    'Beanie has changed'."""
    return BeanieMind.get_instance().personality.derive()


# ── Phase 18: owner authority ──────────────────────────────────────────────
class AuthorityCheckIn(BaseModel):
    action: str = Field(min_length=1, max_length=2000)
    safety_level: Optional[int] = None
    context: str = ""


class AuthorityAnswerIn(BaseModel):
    ask_id: int
    allow: bool


@router.get("/mind/authority")
def mind_authority_policy() -> dict:
    """The owner's authority policy: five lanes (always allowed / ask
    first / never do / trusted contexts / temporary) exactly as the owner
    stated them, plus open asks. No system morals, no invented
    restrictions."""
    return {"success": True, **BeanieMind.get_instance().authority.policy()}


@router.post("/mind/authority/check")
def mind_authority_check(body: AuthorityCheckIn) -> dict:
    """Where does this action sit in the owner's policy? Ask-first opens a
    typed requires_owner_approval ask — never a silent drop. Judges
    authorization only; never executes."""
    return BeanieMind.get_instance().authority.check(
        body.action, safety_level=body.safety_level, context=body.context)


@router.post("/mind/authority/answer")
def mind_authority_answer(body: AuthorityAnswerIn) -> dict:
    """The owner answers an open ask conversationally; the answer is
    obeyed. A declined ask is the owner's decision — the only reason it
    doesn't happen."""
    return BeanieMind.get_instance().authority.answer(body.ask_id, body.allow)


# ── Phase 19: self-reflection ──────────────────────────────────────────────
class ReflectionIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    kind: str = "experience"
    success: Optional[bool] = None
    goal_type: str = ""
    surprisal: Optional[float] = None


@router.get("/mind/reflection")
def mind_reflection_stream(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """The reflection ledger: after important experiences — what happened,
    what she believed, whether she was correct, what surprised her, what
    she learned, and whether to change her model. Evidence only; UNKNOWN
    preserved."""
    r = BeanieMind.get_instance().reflection
    return {"success": True, **r.stats(),
            "lessons": r.lessons(limit=limit),
            "stream": r.reflections(limit=limit)}


@router.post("/mind/reflection/reflect")
def mind_reflection_now(body: ReflectionIn) -> dict:
    """Reflect on one experience now. Success must be the verifier's word
    (True/False) or omitted — a missing verdict stays UNKNOWN, never
    guessed."""
    return BeanieMind.get_instance().reflection.reflect_on({
        "kind": body.kind, "content": body.content, "success": body.success,
        "goal_type": body.goal_type, "surprisal": body.surprisal,
    })


# ── Phase 20: self-improvement ─────────────────────────────────────────────
class ImprovementProposeIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class ImprovementIdIn(BaseModel):
    improvement_id: int = Field(ge=1)


@router.get("/mind/improvement")
def mind_improvement_stream(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """The self-improvement loop: capability gaps detected from evidence
    (2+ verified failures of the same thing), proposals, attempts, and
    measurements. The mechanism's typed word decides; nothing is claimed
    without verification."""
    imp = BeanieMind.get_instance().improvement
    return {"success": True, **imp.stats(),
            "gaps": imp.detect_gaps(),
            "stream": imp.improvements(limit=limit)}


@router.post("/mind/improvement/propose")
def mind_improvement_propose(body: ImprovementProposeIn) -> dict:
    """Investigate one candidate gap and, when the evidence shows a real
    pattern (2+ verified failures), record the proposal. Designs never
    execute."""
    imp = BeanieMind.get_instance().improvement
    evidence = imp.investigate(body.content)
    if not evidence.get("success"):
        return evidence
    return imp.design({"content": body.content,
                       "verified_failures": evidence["failure_count"]})


@router.post("/mind/improvement/implement")
def mind_improvement_implement(body: ImprovementIdIn) -> dict:
    """Run the wired synthesis mechanism for a proposal. The engine's own
    contract decides (sandbox test BEFORE install, hotload only if green);
    success is claimed only from its typed result."""
    return BeanieMind.get_instance().improvement.implement(body.improvement_id)


@router.post("/mind/improvement/measure")
def mind_improvement_measure(body: ImprovementIdIn) -> dict:
    """Measure an attempt against NEW verified experience: success with no
    new failures = retained; 2+ new failures = reverted for real; anything
    less = awaiting evidence, never guessed."""
    return BeanieMind.get_instance().improvement.measure(body.improvement_id)


# ── Phase 21: model evolution ──────────────────────────────────────────────
class EvolutionConsolidateIn(BaseModel):
    max_tasks: int = Field(default=50, ge=1, le=100)


class EvolutionDatasetIn(BaseModel):
    limit: int = Field(default=1000, ge=1, le=10000)


@router.get("/mind/evolution")
def mind_evolution_stream(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """Model evolution in three lanes: fast (memory/world/self updates
    already live at the door), medium (consolidation — appends, never
    deletes raw experience), long (dataset from her own verified ledger +
    sufficiency evaluation; adapter training stays on the owner's
    machine)."""
    evo = BeanieMind.get_instance().evolution
    return {"success": True, **evo.stats(), "fast": evo.fast_state(),
            "adapter": evo.adapter_status(), "runs": evo.runs(limit=limit)}


@router.post("/mind/evolution/consolidate")
def mind_evolution_consolidate(body: EvolutionConsolidateIn) -> dict:
    """Run the medium lane now: the wired consolidation engine (conflict
    replay, gists from repeated verified success, calibration refresh).
    Its telemetry is reported verbatim; raw experience is never
    deleted."""
    return BeanieMind.get_instance().evolution.consolidate(body.max_tasks)


@router.post("/mind/evolution/dataset")
def mind_evolution_dataset(body: EvolutionDatasetIn) -> dict:
    """Long lane: export her OWN verified ledger as a training dataset
    (JSONL, provenance per row). Unverified material never trains the
    model; an empty ledger exports nothing — never padded."""
    return BeanieMind.get_instance().evolution.dataset(body.limit)


@router.post("/mind/evolution/evaluate")
def mind_evolution_evaluate() -> dict:
    """Deterministic dataset sufficiency: volume floor + both outcome
    classes present. Arithmetic, never optimism."""
    return BeanieMind.get_instance().evolution.evaluate_dataset()
