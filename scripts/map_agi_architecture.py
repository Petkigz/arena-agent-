#!/usr/bin/env python3
"""Phase 0 (Beanie AGI Roadmap): whole-repository architecture map.

Classifies every production Python module into the AGI layer model from
docs/AGI_ROADMAP.md and assigns one disposition:

    KEEP      already fits the target architecture
    INTEGRATE useful; must become part of the unified Mind
    MERGE     duplicate/overlapping intelligence (see cluster id)
    DEMOTE    useful capability/loop but must not make cognitive decisions
    LEGACY    preserve temporarily; stop building on it
    (MISSING  rows are listed in AGI_ARCHITECTURE_MAP.md — concepts with no file)

Layers follow the roadmap's target architecture:
    mind/*, memory/*, models/{world,self,owner}, learning/*, perception/*,
    embodiment/*, capabilities/*, communication/*, evaluation/*,
    owner-authority/*, infrastructure/*

Re-runnable (owner standing rule, like scripts/audit_dead_code.py):
    python scripts/map_agi_architecture.py
Writes docs/AGI_ARCHITECTURE_MAP_FILES.csv and prints summary counts.
It does NOT move, rename, or delete anything — mapping only (Phase 0 freeze).
"""

from __future__ import annotations

import ast
import csv
import pathlib
import sys
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "AGI_ARCHITECTURE_MAP_FILES.csv"

# ─────────────────────────────────────────────────────────────────────────
# Directory defaults (path prefix -> (layer, disposition, cluster, note))
# ─────────────────────────────────────────────────────────────────────────
DIR_DEFAULTS = {
    "app/tools": (
        "capabilities/general", "KEEP", "",
        "manifest capability; motor-system unit for the future Mind"),
    "app/cognition": (
        "mind/cognition-core", "INTEGRATE", "",
        "cognition module; becomes an organ of BeanieMind"),
    "app/agents": (
        "mind/decision", "DEMOTE", "",
        "thin loop; must not act as an independent brain"),
    "app/memory": (
        "memory", "INTEGRATE", "",
        "memory subsystem; folds into the unified memory facade"),
    "app/perception": (
        "perception/environment", "INTEGRATE", "",
        "perception module"),
    "app/api": (
        "communication/api", "KEEP", "",
        "HTTP surface for the mind's state/actions"),
    "app/utils": (
        "infrastructure/utils", "KEEP", "", ""),
    "app/runtime": (
        "infrastructure/resources", "KEEP", "", ""),
    "app/scheduler": (
        "infrastructure/scheduling", "KEEP", "", ""),
    "backend/api": (
        "communication/api", "KEEP", "", ""),
    "backend/voice": (
        "communication/voice", "KEEP", "", ""),
    "desktop": (
        "communication/presence", "KEEP", "",
        "desktop client of the one Mind (Phase 23)"),
    "scripts": (
        "evaluation/ops", "KEEP", "", ""),
}

# ─────────────────────────────────────────────────────────────────────────
# Explicit per-file overrides: path -> (layer, disposition, cluster, note)
# Encodes the Phase-0 judgment; anything not listed falls to DIR_DEFAULTS.
# ─────────────────────────────────────────────────────────────────────────
OVERRIDES = {
    # ── package roots ────────────────────────────────────────────────────
    "app/__init__.py": ("infrastructure/package", "KEEP", "", ""),
    "backend/__init__.py": ("infrastructure/package", "KEEP", "", ""),
    "app/agents/__init__.py": ("infrastructure/package", "KEEP", "", ""),
    "app/mind/__init__.py": ("infrastructure/package", "KEEP", "", ""),

    # ── THE MIND ITSELF (Phase 1, LIVE 2026-09-08 — the target architecture
    #    is no longer hypothetical; these ARE the unified mind) ─────────────
    "app/mind/beanie_mind.py": (
        "mind/cognition-core", "KEEP", "AUTHORITY",
        "Phase 1 LIVE: the one canonical door — BeanieMind.process(...)"),
    "app/mind/identity.py": (
        "mind/identity", "KEEP", "AUTHORITY",
        "Phase 1 LIVE: 'I am Beanie' as persisted state (M1)"),
    "app/mind/state.py": (
        "mind/cognition-core", "KEEP", "STATE",
        "Phase 1 LIVE: BeanieState skeleton — 15 rooms, honestly marked (M2)"),
    "app/mind/world_facade.py": (
        "models/world", "KEEP", "WORLD",
        "Phase 3 LIVE: ontology + pre-action understanding over the existing "
        "WorldModel (the verification-side store stays authoritative)"),
    "app/mind/self_facade.py": (
        "models/self", "KEEP", "SELF",
        "Phase 4 LIVE: genuine self-assessment (knowledge/confidence/"
        "possible_actions) + capability awareness (authority ≠ intelligence)"),
    "app/mind/memory_facade.py": (
        "memory", "KEEP", "MEMORY",
        "Phase 5 LIVE: UnifiedMemory over all eight kinds + NEW social store "
        "and meta-memory (M3, M5 resolved)"),
    "app/mind/world_first.py": (
        "mind/reasoning", "KEEP", "TOOL-FIRST",
        "Phase 2 LIVE: world-first brief (world → self → memory) assembled "
        "before capability identification — the tool_matcher demotion's "
        "counterpart (M6 consumption resolved)"),
    "app/mind/learning_loop.py": (
        "mind/learning", "KEEP", "LEARNING",
        "Phase 6 LIVE: the ONE general learning loop every experience passes "
        "through (observe → interpret → compare → novelty → hypothesis → "
        "test → outcome → update model → store → confidence); success is "
        "evidence only — attempted ≠ succeeded"),
    "app/mind/teaching.py": (
        "mind/learning", "KEEP", "LEARNING",
        "Phase 7 LIVE: conversation is the teaching interface ('watch this') "
        "— M7 resolved; confirmed procedures integrate the taught-skills "
        "store and enter the Phase-6 loop as verified demonstrations"),
    "app/mind/media_learning.py": (
        "mind/learning", "KEEP", "LEARNING",
        "Phase 8 LIVE: images/video/audio/web enter the ONE Phase-6 loop as "
        "media experiences — deterministic observation first; watching is "
        "never verification (success=None)"),
    "app/mind/curiosity.py": (
        "mind/curiosity", "KEEP", "CURIOSITY",
        "Phase 9 LIVE: the internal UNKNOWN system — brief gaps become "
        "records, encounters compound, investigation searches memory first, "
        "resolution paths counted (knowledge/investigation/owner)"),
    "app/mind/imagination.py": (
        "mind/imagination", "KEEP", "IMAGINATION",
        "Phase 10 LIVE: simulate before acting (prediction + own verified "
        "history + open unknowns + counsel); compare prediction vs reality "
        "into a ledger + confirmed/refuted training data (M11 resolved)"),
    "app/mind/embodiment.py": (
        "mind/motor", "KEEP", "EMBODIMENT",
        "Phase 11 LIVE: the 184 capabilities as her motor system — concepts "
        "in, ranked pathways out (plans only, never execution); authority "
        "surfaced, motor gaps become unknowns"),
    "app/mind/os_concepts.py": (
        "mind/motor", "KEEP", "EMBODIMENT",
        "Phase 12 LIVE (M10): ONE platform-free concept layer over all "
        "bodies — express/transfer/coverage from the live manifest by "
        "evidence; no per-OS intelligence, gaps visible not fabricated"),
    "app/mind/perception.py": (
        "mind/perception", "KEEP", "SENSES",
        "Phase 13 LIVE: the SENSE side — typed perceptions over eight "
        "channels, significance judged (urgency/novelty/curiosity) with "
        "reasons, silent-watcher changes ingested; perception ≠ belief ≠ "
        "action"),
    "app/mind/attention.py": (
        "mind/attention", "KEEP", "ATTENTION",
        "Phase 14 LIVE (M8): the arbitrator between perception and thought "
        "— roadmap ladder from evidence on the record, repeats demoted, "
        "watermark review, one open unknown surfaced when quiet, "
        "popup-over-task advisory; decides only, never acts"),
    "app/mind/motivation.py": (
        "mind/motivation", "KEEP", "MOTIVATION",
        "Phase 15 LIVE: goals from evidence only (open unknowns, parked "
        "goals, owner speech, attention verdicts, verified failures, "
        "learned rhythms) — relevance as named contributions, recurrence "
        "compounds, proposals are questions (acted: False), accepted goals "
        "execute through the normal door under owner authority"),
    "app/api/mind.py": (
        "communication/api", "KEEP", "",
        "Phase 1 LIVE: owner window onto identity/state/entries"),

    # ── THE COGNITIVE AUTHORITY QUESTION ─────────────────────────────────
    "app/cognition/runtime.py": (
        "mind/cognition-core", "INTEGRATE", "AUTHORITY",
        "de-facto brain today (singleton composition root, 5.3k lines); "
        "becomes the interior of BeanieMind — not a separate authority"),
    "app/cognition/cognitive_pipeline.py": (
        "mind/cognition-core", "LEGACY", "AUTHORITY",
        "delegating enforcer over the runtime; compat surface only"),
    "app/cognition/pipeline.py": (
        "mind/cognition-core", "LEGACY", "AUTHORITY",
        "compat aliases (PipelineBridge); stop building on it"),
    "app/memory/coworker_brain.py": (
        "mind/identity", "INTEGRATE", "AUTHORITY",
        "persona string only — the seed of 'I am Beanie'; superseded as the "
        "identity record by BeanieIdentity (Phase 1), which Phase 17 uses "
        "as the basic identity its derived personality starts from"),
    "app/agents/master_agent.py": (
        "embodiment/action-execution", "DEMOTE", "AUTHORITY",
        "action executor (hands); must not be perceived as a brain"),
    "app/agents/self_evolving_agent.py": (
        "learning/self-improvement", "INTEGRATE", "IMPROVEMENT",
        "Phase 20 LIVE: the verify-before-install synthesis engine — the "
        "one MECHANISM that app/mind/improvement.py calls; the organ "
        "decides, this engine executes-and-verifies"),
    "app/agents/coding_agent.py": (
        "capabilities/code", "DEMOTE", "", "task loop, thin-agent contract"),
    "app/agents/data_analysis_agent.py": (
        "capabilities/data", "DEMOTE", "", "task loop, thin-agent contract"),
    "app/agents/multi_agent.py": (
        "capabilities/agent", "DEMOTE", "",
        "collaboration loop; cognition stays in the Mind"),
    "app/agents/proactive_coworker_daemon.py": (
        "mind/motivation", "INTEGRATE", "",
        "proactive behavior feed for the motivation system"),

    # ── MODELS/WORLD (Phase 3) ───────────────────────────────────────────
    "app/cognition/world_model.py": (
        "models/world", "INTEGRATE", "WORLD",
        "exists but verification-oriented (post-action probes); must also "
        "serve pre-action world understanding"),
    "app/cognition/world_ingest.py": (
        "models/world", "INTEGRATE", "WORLD", ""),
    "app/cognition/observation_router.py": (
        "models/world", "INTEGRATE", "WORLD",
        "host-state questions → real observations"),
    "app/cognition/environment_state.py": (
        "models/world", "MERGE", "WORLD",
        "overlaps world_model/environment_grounding — one world surface"),
    "app/cognition/environment_grounding.py": (
        "models/world", "MERGE", "WORLD", ""),
    "app/cognition/embodied_boundary.py": (
        "models/world", "MERGE", "WORLD", ""),
    "app/cognition/os_grounding.py": (
        "models/world", "INTEGRATE", "WORLD",
        "task↔app↔process↔window evidence links"),
    "app/cognition/scene_graph.py": (
        "models/world", "INTEGRATE", "WORLD", "deterministic scene state"),
    "app/cognition/scene_causal.py": (
        "mind/imagination", "INTEGRATE", "", "causal replay of scenes"),
    "app/cognition/browser_grounding.py": (
        "models/world", "INTEGRATE", "WORLD", ""),
    "app/cognition/ontology_schema.py": (
        "models/world", "KEEP", "", "owner-controlled ontology revisions"),

    # ── MODELS/SELF (Phase 4) ────────────────────────────────────────────
    "app/cognition/self_model.py": (
        "models/self", "MERGE", "SELF",
        "exists (Phase 5A); merge with self_knowledge/identity_*"),
    "app/cognition/self_knowledge.py": (
        "models/self", "MERGE", "SELF", ""),
    "app/cognition/identity_continuity.py": (
        "models/self", "MERGE", "SELF", ""),
    "app/cognition/identity_adaptation.py": (
        "models/self", "MERGE", "SELF",
        "owner-governed identity adaptation — personality-development seed; "
        "Phase 17 built the authoritative derived-personality organ "
        "app/mind/personality.py"),
    "app/cognition/self_recovery.py": (
        "models/self", "MERGE", "SELF", ""),
    "app/api/self_awareness.py": (
        "models/self", "KEEP", "SELF", "API window onto the self model"),
    "app/cognition/functional_affect.py": (
        "models/self", "INTEGRATE", "",
        "bounded functional affect telemetry (social/emotional context)"),

    # ── MODELS/OWNER + OWNER AUTHORITY (Phases 16, 18) ───────────────────
    "app/cognition/owner_model.py": (
        "models/owner", "INTEGRATE", "",
        "exists: counted patterns from owner decisions; becomes the "
        "relationship model"),
    "app/cognition/user_state.py": (
        "models/owner", "MERGE", "OWNER", "merge with owner_model"),
    "app/memory/human_nature_engine.py": (
        "models/owner", "INTEGRATE", "OWNER", ""),
    "app/cognition/owner_charter.py": (
        "owner-authority/values", "KEEP", "",
        "owner's values as top directive (charter §2)"),
    "app/cognition/owner_control.py": (
        "owner-authority/control-plane", "KEEP", "", ""),
    "app/cognition/owner_decisions.py": (
        "owner-authority/decisions", "KEEP", "", ""),
    "app/cognition/approval_store.py": (
        "owner-authority/approvals", "KEEP", "AUTHORITY",
        "runtime approval-request store; Phase 18's authoritative policy is "
        "app/mind/authority.py — five owner-stated lanes, asks opened and "
        "obeyed"),
    "app/cognition/adaptive_autonomy.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_allocator.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_envelope.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_lease.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_preemption.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_run_ledger.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/cognition/autonomy_schedule.py": (
        "owner-authority/autonomy", "KEEP", "", ""),
    "app/memory/decision_constitution.py": (
        "owner-authority/values", "KEEP", "", ""),
    "app/policy.py": (
        "owner-authority/policy", "KEEP", "", ""),

    # ── MEMORY family (Phase 5) ──────────────────────────────────────────
    "app/cognition/memory.py": (
        "memory/episodic+semantic+procedural", "INTEGRATE", "MEMORY",
        "the future unified-memory facade nucleus"),
    "app/cognition/working_memory.py": (
        "memory/working", "INTEGRATE", "MEMORY", ""),
    "app/cognition/prospective_memory.py": (
        "memory/working", "INTEGRATE", "MEMORY", ""),
    "app/cognition/associative_memory.py": (
        "memory/semantic", "MERGE", "MEMORY", ""),
    "app/cognition/analogical_memory.py": (
        "memory/semantic", "MERGE", "MEMORY", "analogical reasoning layer"),
    "app/memory/semantic_rag.py": (
        "memory/semantic", "MERGE", "MEMORY",
        "legacy global RAG path — fold into the facade"),
    "app/cognition/common_sense/__init__.py": (
        "memory/semantic", "KEEP", "", "static common-sense KB"),
    "app/cognition/common_sense/causal_knowledge.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/common_sense_knowledge_base.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/everyday_knowledge.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/human_behavior.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/physical_world.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/spatial_knowledge.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/technology_knowledge.py": (
        "memory/semantic", "KEEP", "", ""),
    "app/cognition/common_sense/temporal_knowledge.py": (
        "memory/semantic", "KEEP", "", ""),

    # ── REASONING / IMAGINATION (Phases 2, 10) ───────────────────────────
    "app/cognition/belief_engine.py": (
        "mind/reasoning", "MERGE", "BELIEF",
        "two belief systems exist — consolidate to one"),
    "app/cognition/beliefs.py": (
        "mind/reasoning", "MERGE", "BELIEF", ""),
    "app/cognition/hypotheses.py": (
        "mind/reasoning", "INTEGRATE", "BELIEF", ""),
    "app/cognition/reasoning_cycle.py": (
        "mind/reasoning", "MERGE", "LOOP",
        "two cognitive loops exist — one loop in the Mind"),
    "app/cognition/reasoning_loop.py": (
        "mind/reasoning", "MERGE", "LOOP", ""),
    "app/cognition/counterfactual_simulator.py": (
        "mind/imagination", "KEEP", "", "mental simulation of strategies"),
    "app/cognition/prediction_engine.py": (
        "mind/imagination", "KEEP", "IMAGINATION",
        "prediction vs outcome surprisal; Phase 10 wires it into "
        "app/mind/imagination.py (simulate before acting, compare vs "
        "reality — M11 connected)"),
    "app/cognition/goal_interpreter.py": (
        "mind/reasoning", "KEEP", "", "goal representation v2"),
    "app/cognition/concept_bridge.py": (
        "mind/reasoning", "KEEP", "", "symptoms → concepts expansion"),
    "app/cognition/diagnostic_ranking.py": (
        "mind/reasoning", "KEEP", "", ""),
    "app/cognition/incubation_queue.py": (
        "mind/imagination", "KEEP", "", "bounded background reasoning"),

    # ── DECISION / PLANNING family (MERGE cluster) ───────────────────────
    "app/cognition/action_planner.py": (
        "mind/decision", "MERGE", "PLANNERS", ""),
    "app/cognition/strategic_planning.py": (
        "mind/decision", "MERGE", "PLANNERS", ""),
    "app/cognition/planning_patterns.py": (
        "mind/decision", "MERGE", "PLANNERS", ""),
    "app/cognition/goal_decomposer.py": (
        "mind/decision", "INTEGRATE", "PLANNERS", ""),
    "app/cognition/goal_replanner.py": (
        "mind/decision", "INTEGRATE", "PLANNERS", ""),
    "app/cognition/project_manager.py": (
        "mind/decision", "INTEGRATE", "PLANNERS", ""),
    "app/cognition/project_scheduler.py": (
        "mind/decision", "INTEGRATE", "PLANNERS", ""),
    "app/cognition/os_control_planner.py": (
        "embodiment/os-abstraction", "INTEGRATE", "EMBODIMENT",
        "the platform-command executor UNDER the Phase-12 concept layer "
        "(app/mind/os_concepts.py owns the platform-free abstraction; this "
        "plans the per-OS shell command when the cycle acts)"),
    "app/cognition/plan_control.py": (
        "owner-authority/plan-review", "KEEP", "", ""),
    "app/cognition/plan_freshness.py": (
        "mind/decision", "KEEP", "", ""),
    "app/cognition/plan_step_reconciliation.py": (
        "mind/decision", "KEEP", "", ""),
    "app/cognition/action_selection.py": (
        "mind/decision", "INTEGRATE", "", ""),
    "app/cognition/action_proposal.py": (
        "mind/decision", "KEEP", "", "multi-gate proposal engine"),
    "app/cognition/action_outcomes.py": (
        "learning/experience", "INTEGRATE", "", ""),
    "app/cognition/strategy_outcomes.py": (
        "learning/experience", "INTEGRATE", "", ""),
    "app/cognition/criterion_evaluator.py": (
        "mind/decision", "KEEP", "", ""),
    "app/cognition/criticality_review.py": (
        "mind/decision", "KEEP", "", ""),
    "app/cognition/resource_allocator.py": (
        "mind/decision", "KEEP", "", ""),
    "app/cognition/condition_language.py": (
        "mind/decision", "KEEP", "", ""),

    # ── CAPABILITY AUTHORITY (Phase 2 demotion target) ───────────────────
    "app/cognition/tool_registry.py": (
        "capabilities/registry", "KEEP", "",
        "single capability authority — called BY the mind, never as it"),
    "app/cognition/tool_matcher.py": (
        "capabilities/registry", "DEMOTE", "EMBODIMENT",
        "manifest-first routing IS the tool-first thinking Phase 2 replaces; "
        "Phase 11 gives it the demoted job for real: primary capability "
        "resolver inside app/mind/embodiment.py (concepts → motor pathways)"),
    "app/cognition/capability_resolver.py": (
        "capabilities/registry", "KEEP", "", ""),
    "app/cognition/capability_factory.py": (
        "capabilities/registry", "KEEP", "", "dynamic capability synthesis"),
    "app/cognition/semantic_matcher.py": (
        "capabilities/registry", "KEEP", "", ""),

    # ── MOTIVATION / CURIOSITY (Phases 9, 15) ────────────────────────────
    "app/cognition/autonomous_goal_generator.py": (
        "mind/motivation", "INTEGRATE", "MOTIVATION",
        "Phase 7 seed (GoalSource/AutonomousGoal + store), LIVE via the "
        "owner-control autonomy API; Phase 15 built the authoritative "
        "evidence-first goal organ app/mind/motivation.py — goals from "
        "evidence, never random"),
    "app/cognition/autonomous_goal_executor.py": (
        "mind/motivation", "INTEGRATE", "MOTIVATION",
        "execution-plan seed under the authority layer; Phase-15 accepted "
        "goals execute through the normal door, not around it"),
    "app/cognition/periodic_autonomous_cycle.py": (
        "mind/motivation", "INTEGRATE", "MOTIVATION", ""),
    "app/cognition/learning_progress.py": (
        "mind/motivation", "KEEP", "", "curiosity: explore growing competence"),
    "app/cognition/information_gain.py": (
        "mind/motivation", "KEEP", "", "information-seeking primitives"),
    "app/cognition/phase7_preferences.py": (
        "mind/motivation", "INTEGRATE", "", "preference & novelty evaluation"),
    "app/cognition/parked_goal_recheck.py": (
        "mind/motivation", "KEEP", "MOTIVATION",
        "wired in server lifespan; Phase 15 LIVE: its parked "
        "(waiting_for_evidence) goals feed app/mind/motivation.py as the "
        "unfinished_goal evidence source"),
    "app/cognition/attention_manager.py": (
        "mind/attention", "INTEGRATE", "ATTENTION",
        "43-line seed, LIVE in the cognitive cycle (runtime.py:159) as the "
        "in-cycle focus tracker; Phase 14 built the authoritative "
        "perception-stream arbitrator as the mind organ "
        "app/mind/attention.py — one cognitive authority"),

    # ── LEARNING family (Phases 6-8, 21) ─────────────────────────────────
    "app/cognition/continual_learning.py": (
        "learning/consolidation", "INTEGRATE", "EVOLUTION",
        "regression-gated continual-learning cycles — long-lane material "
        "for the Phase-21 organ app/mind/evolution.py"),
    "app/cognition/consolidation.py": (
        "learning/consolidation", "INTEGRATE", "EVOLUTION",
        "Phase 21 LIVE: the WIRED medium-lane engine — "
        "app/mind/evolution.py delegates consolidation (conflict replay, "
        "gists from repeated verified success, calibration refresh) to "
        "it and claims only its audited telemetry; appends, never "
        "deletes raw experience (the forgetting guard)"),
    "app/cognition/skill_induction.py": (
        "learning/experience", "INTEGRATE", "",
        "action sequences → skills (procedural memory feed)"),
    "app/cognition/skill_classifier.py": (
        "learning/experience", "INTEGRATE", "", ""),
    "app/cognition/structured_lessons.py": (
        "learning/experience", "INTEGRATE", "", ""),
    "app/cognition/training_examples.py": (
        "learning/consolidation", "KEEP", "", "owner-reviewed LoRA candidates"),
    "app/cognition/lora_evaluation.py": (
        "learning/consolidation", "KEEP", "", ""),
    "app/cognition/causal_inference.py": (
        "learning/causal", "KEEP", "", ""),
    "app/cognition/cross_domain_transfer.py": (
        "learning/transfer", "KEEP", "", "owner-deferred embedding completion"),
    "app/cognition/memory_learning.py": (
        "learning/experience", "MERGE", "REFLECTION", ""),
    "app/cognition/intelligence_benchmark.py": (
        "evaluation/regression", "KEEP", "",
        "isolated longitudinal benchmark — regression-style, NOT the "
        "Phase-24 generalization tasks"),
    "app/cognition/phase0_evaluation.py": (
        "evaluation/learning", "KEEP", "", ""),
    "app/cognition/phase1_evidence.py": (
        "evaluation/learning", "KEEP", "", ""),
    "app/cognition/phase1_task_evaluations.py": (
        "evaluation/learning", "KEEP", "", ""),
    "app/cognition/correction_measurements.py": (
        "evaluation/learning", "INTEGRATE", "",
        "owner-correction telemetry — feeds learning-from-owner"),
    "app/skill_acquisition.py": (
        "learning/demonstration", "INTEGRATE", "",
        "closest thing to demonstration learning today"),
    "backend/chat_corrections.py": (
        "learning/conversation", "INTEGRATE", "",
        "in-chat owner corrections — Phase-7 teaching surface"),

    # ── REFLECTION cluster (Phase 19 LIVE: app/mind/reflection.py is the
    #    authoritative reflection; these three legacy engines fold into it) ─
    "app/cognition/verified_reflection.py": (
        "mind/reflection", "MERGE", "REFLECTION",
        "three reflection engines existed — Phase 19 made one reflection "
        "in the Mind (app/mind/reflection.py)"),
    "app/cognition/self_reflection_engine.py": (
        "mind/reflection", "MERGE", "REFLECTION", ""),
    "app/memory/reflection_engine.py": (
        "mind/reflection", "MERGE", "REFLECTION", ""),

    # ── HONESTY / EPISTEMICS (permanent truth boundaries) ────────────────
    "app/cognition/completion_honesty.py": (
        "mind/cognition-core", "KEEP", "", "truth boundary"),
    "app/cognition/response_grounding.py": (
        "mind/cognition-core", "KEEP", "", "truth boundary"),
    "app/cognition/epistemic_presentation.py": (
        "mind/cognition-core", "KEEP", "", ""),
    "app/cognition/uncertainty_questions.py": (
        "mind/cognition-core", "KEEP", "", "ask instead of acting on weak evidence"),
    "app/cognition/guard_visibility.py": (
        "mind/cognition-core", "KEEP", "", "charter §6"),
    "app/cognition/confidence_calibrator.py": (
        "mind/reasoning", "KEEP", "", ""),
    "app/cognition/confidence.py": (
        "mind/reasoning", "LEGACY", "",
        "owner-deferred prototype (charter §5⑦); test-only"),
    "app/cognition/cognitive_router.py": (
        "mind/cognition-core", "LEGACY", "",
        "owner-deferred prototype (charter §5⑦); test-only"),
    "app/cognition/autonomous_operator.py": (
        "mind/motivation", "LEGACY", "",
        "owner-deferred prototype (charter §5⑦); test-only"),

    # ── EXECUTION TRUTH / GOALS (keep — evidence discipline) ─────────────
    "app/cognition/execution_result.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/execution_truth.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/execution_control.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/goal_lifecycle.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/goal_verifier.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/step_verifier.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/commitment_ledger.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/checkpoint.py": ("infrastructure/persistence", "KEEP", "", ""),
    "app/cognition/source_types.py": ("mind/cognition-core", "KEEP", "", ""),
    "app/cognition/event_bus.py": ("infrastructure/events", "KEEP", "", ""),
    "app/cognition/events.py": ("infrastructure/events", "KEEP", "", ""),
    "app/cognition/session.py": ("infrastructure/session", "KEEP", "", ""),
    "app/cognition/trace.py": ("evaluation/trace", "KEEP", "", ""),
    "app/cognition/cognitive_state.py": (
        "mind/cognition-core", "INTEGRATE", "STATE",
        "fragment of future BeanieState (working state)"),
    "app/cognition/blackboard.py": (
        "mind/cognition-core", "INTEGRATE", "STATE",
        "fragment of future BeanieState (ephemeral loop memory)"),
    "app/cognition/runtime_wiring.py": (
        "mind/cognition-core", "INTEGRATE", "", "phase-module wiring glue"),
    "app/cognition/prompt_slicer.py": (
        "infrastructure/inference", "KEEP", "", ""),
    "app/cognition/inference_profile.py": (
        "infrastructure/inference", "KEEP", "", ""),
    "app/cognition/metacognitive_monitor.py": (
        "models/self", "INTEGRATE", "SELF",
        "introspection seed (records cognitive processes, reads "
        "goal_verified); Phase 19's app/mind/reflection.py is the "
        "authoritative reflection alongside it"),

    # ── PERCEPTION layer (Phases 11, 13) ─────────────────────────────────
    "app/cognition/perception.py": (
        "perception/environment", "INTEGRATE", "",
        "observation collector — post-action probes today"),
    "app/cognition/visual_observer.py": (
        "perception/vision", "INTEGRATE", "", ""),
    "app/cognition/temporal_vision.py": (
        "perception/vision", "KEEP", "", "stream-isolated tracking"),
    "app/perception/background_observer.py": (
        "perception/environment", "KEEP", "SENSES",
        "charter §5④ silent watcher; Phase 13 wires its buffered "
        "EnvironmentChanges into app/mind/perception.py (drained at the "
        "door + on demand)"),
    "app/perception/event_prioritizer.py": (
        "perception/environment", "KEEP", "", "classify → dedupe → decision"),
    "app/perception/anticipation_engine.py": (
        "mind/attention", "INTEGRATE", "ATTENTION", "charter §5②"),
    "app/perception/speech_to_text.py": (
        "perception/audio", "KEEP", "", ""),
    "app/perception/text_to_speech.py": (
        "communication/voice", "KEEP", "", ""),
    "app/perception/piper_voice.py": (
        "communication/voice", "KEEP", "", ""),

    # ── SENSES currently disguised as tools (INTEGRATE into perception) ──
    "app/tools/screen_capture.py": (
        "perception/screen", "INTEGRATE", "SENSES", ""),
    "app/tools/camera_capture.py": (
        "perception/vision", "INTEGRATE", "SENSES", ""),
    "app/tools/ocr_reader.py": (
        "perception/vision", "INTEGRATE", "SENSES", ""),
    "app/tools/object_detector.py": (
        "perception/vision", "INTEGRATE", "SENSES", ""),
    "app/tools/vision_analyzer.py": (
        "perception/vision", "INTEGRATE", "SENSES", ""),
    "app/tools/vlm_analyzer.py": (
        "perception/vision", "INTEGRATE", "SENSES", ""),
    "app/tools/prosody_analyzer.py": (
        "perception/audio", "INTEGRATE", "SENSES", ""),

    # ── LEARNING currently disguised as tools ────────────────────────────
    "app/tools/skill_teaching_engine.py": (
        "learning/demonstration", "INTEGRATE", "LEARNING",
        "Phase 7 LIVE: still the durable taught-skills store, but the TEACHER "
        "is now conversation (app/mind/teaching.py) — the form-driven path is "
        "the fallback, not the interface"),
    "app/tools/universal_media_learner.py": (
        "learning/media", "INTEGRATE", "LEARNING",
        "Phase 8 LIVE: stays the deep-analysis capability; app/mind/"
        "media_learning.py now routes its deterministic scrape (and its LLM "
        "analyses, on request) into the Phase-6 loop"),
    "app/tools/youtube_learner.py": (
        "learning/media", "INTEGRATE", "LEARNING",
        "Phase 8 LIVE: stays the transcript/deep-analysis capability; "
        "app/mind/media_learning.py feeds transcripts into the Phase-6 loop "
        "as media experiences (watching is never verification)"),
    "app/tools/knowledge_indexer.py": (
        "learning/media", "INTEGRATE", "", ""),
    "app/tools/lora_manager.py": (
        "learning/consolidation", "KEEP", "", ""),

    # ── EMBODIMENT currently disguised as tools (Phase 12) ───────────────
    "app/tools/deep_os_controller.py": (
        "embodiment/windows", "KEEP", "OS", ""),
    "app/tools/win32_ghost_operator.py": (
        "embodiment/windows", "KEEP", "OS", ""),
    "app/tools/desktop_control.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/accessibility_control.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/process_manager.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/app_inventory.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/display_topology.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/package_installer.py": (
        "embodiment/generic", "KEEP", "OS", ""),
    "app/tools/android_adb_controller.py": (
        "embodiment/android", "KEEP", "OS",
        "owner's phone — first-class (charter §4)"),
    "app/tools/browser_automation.py": (
        "embodiment/browser", "KEEP", "OS", ""),
    "app/tools/web_agent.py": (
        "embodiment/browser", "DEMOTE", "OS",
        "autonomous loop — cognition must move to the Mind"),
    "app/tools/universal_filesystem.py": (
        "embodiment/filesystem", "KEEP", "OS", ""),
    "app/tools/file_index.py": (
        "embodiment/filesystem", "KEEP", "OS", ""),
    "app/tools/indexed_search.py": (
        "embodiment/filesystem", "KEEP", "OS", ""),
    "app/tools/doc_manager.py": (
        "embodiment/filesystem", "KEEP", "OS", ""),
    "app/tools/backup_manager.py": (
        "embodiment/filesystem", "KEEP", "OS", ""),
    "app/tools/local_executor.py": (
        "embodiment/generic", "KEEP", "OS", "the escape-hatch effector"),
    "app/cognition/raw_input_guard.py": (
        "owner-authority/safety-gates", "KEEP", "", ""),
    "app/cognition/disk_reservation.py": (
        "infrastructure/resources", "KEEP", "", ""),
    "app/cognition/privilege_model.py": (
        "models/world", "KEEP", "", "OS privilege evidence"),
    "app/cognition/browser_adapters.py": (
        "embodiment/browser", "KEEP", "", ""),

    # ── SOCIAL / PERSONALITY / PHASE ENGINES (16-21) ─────────────────────
    "app/mind/social.py": (
        "mind/social", "KEEP", "SOCIAL",
        "Phase 16 LIVE: the persistent OWNER relationship model — facets "
        "(preference/boundary/emotion/interest/person) from what the owner "
        "said, routines/style/history MEASURED from the door ledger and "
        "claimed only with enough evidence; never pretends to be human, "
        "never cold-reads"),
    "app/mind/personality.py": (
        "mind/personality", "KEEP", "PERSONALITY",
        "Phase 17 LIVE: the DEVELOPING personality — basic identity plus "
        "traits derived from her real ledgers (experiences, calibration, "
        "curiosity, her own reply patterns, the owner's values only, "
        "adaptation); derive() snapshots + diffs = the verifiable record "
        "of 'Beanie has changed'; describes, performs nothing"),
    "app/mind/authority.py": (
        "owner-authority/policy", "KEEP", "AUTHORITY",
        "Phase 18 LIVE: the OWNER's authority — five lanes of owner-stated "
        "rules (always / ask-first / never / trusted contexts / "
        "temporary), Phase-16 boundaries seed the never lane, risk "
        "patterns decide only WHEN TO ASK (ask-first opens a typed "
        "requires_owner_approval ask, never a silent drop), answers "
        "obeyed; no system morals; authority ≠ intelligence; judges "
        "authorization, never executes"),
    "app/mind/reflection.py": (
        "mind/reflection", "KEEP", "REFLECTION",
        "Phase 19 LIVE: the bridge between experience and development — "
        "after important (verified) experiences she answers what "
        "happened / what she believed / was she correct (verifier's word "
        "only, UNKNOWN preserved) / what surprised her / what she "
        "learned / change model? (refuted prediction → update; repeated "
        "verified failure → open unknown with curiosity) / remember? "
        "(the loop's own decision) — every answer from evidence on "
        "record, never narrated; reflecting performs nothing"),
    "app/mind/embodiments.py": (
        "mind/embodiments", "KEEP", "EMBODIMENT",
        "Phase 23 LIVE: the bodies of the ONE mind — desktop and Android "
        "both clients of the same mind, never two assistants; bodies "
        "announce from a fixed vocabulary (never invented), aliveness "
        "derived from heartbeats (never assumed), one presence message "
        "to every alive body (silent ones skipped honestly, deliveries "
        "never faked), bodies pull + acknowledge their own queue, and "
        "note_execution credits WHICH body's hands acted (hands, never "
        "brains); the door broadcasts the settled presence state after a "
        "verified cycle — background presence, one continuous "
        "conversation"),
    "app/mind/presence.py": (
        "mind/presence", "KEEP", "PRESENCE",
        "Phase 22 LIVE: voice-first presence — the state vocabulary is "
        "the design system's own machine (design/tokens.json → "
        "beanie.states); states derived from real signals, never staged, "
        "never invented; idle is honest, not a mask; the contextual "
        "window shows the complicated information when needed, not "
        "permanently (conversation, open asks, goals, unknowns, "
        "lessons); the voice-primary door sends transcripts through the "
        "ONE mind, settling state by the verifier's word only"),
    "app/mind/evolution.py": (
        "mind/evolution", "KEEP", "EVOLUTION",
        "Phase 21 LIVE: model evolution in three lanes — fast lane "
        "reported from the live wiring (never duplicated); medium lane "
        "delegates to the wired ConsolidationCoordinator when enough new "
        "verified learning accumulates (appends, never deletes raw "
        "experience — the forgetting guard); long lane exports her OWN "
        "verified ledger as a provenance dataset with deterministic "
        "sufficiency rules (arithmetic, never optimism) and reports "
        "adapter readiness — training stays on the owner's GPU machine, "
        "never claimed here"),
    "app/mind/improvement.py": (
        "mind/improvement", "KEEP", "IMPROVEMENT",
        "Phase 20 LIVE: self-improvement — detect capability gaps from "
        "evidence only (2+ verified failures of the same thing), "
        "investigate, design a proposal (designs never execute), run the "
        "wired SelfEvolvingAgent verify-before-install mechanism as ONE "
        "mechanism claiming only its typed word, measure from NEW "
        "verified experience (success + no new failures = retained; 2+ "
        "new failures = reverted for real; else awaiting, never guessed); "
        "the door proposes, never implements — execution stays an explicit "
        "owner-surface act"),
    "app/cognition/social_cognition.py": (
        "learning/social", "INTEGRATE", "SOCIAL",
        "Phase 16 seed (mental-state/emotion/relationship engine); the "
        "authoritative owner model is app/mind/social.py — this broader "
        "theory-of-mind engine stays available to it"),
    "app/cognition/ethical_reasoning.py": (
        "owner-authority/values", "KEEP", "",
        "annotates + routes to owner decision; never suppresses (charter §2)"),
    "app/cognition/consciousness_simulation.py": (
        "models/self", "INTEGRATE", "SELF", "Phase 19 engine"),
    "app/cognition/creative_generation.py": (
        "mind/imagination", "KEEP", "", ""),
    "app/cognition/cultural_learning.py": (
        "learning/social", "KEEP", "", ""),
    "app/cognition/embodied_cognition.py": (
        "perception/environment", "INTEGRATE", "", "Phase 20 engine"),
    "app/cognition/language_grounding.py": (
        "mind/reasoning", "KEEP", "", ""),
    "app/cognition/advanced_cognitive_capabilities.py": (
        "mind/cognition-core", "INTEGRATE", "",
        "Phase-14 monolith — candidate for split when the Mind forms"),

    # ── INFRASTRUCTURE / ENTRY ───────────────────────────────────────────
    "app/server.py": (
        "infrastructure/entry", "KEEP", "",
        "single authoritative server; Phase 1 redirects all inputs to "
        "BeanieMind.process"),
    "app/main.py": (
        "infrastructure/entry", "KEEP", "", "127 core REST routes"),
    "backend/main.py": (
        "infrastructure/entry", "LEGACY", "", "compat shim alias"),
    "backend/websocket_server.py": (
        "communication/text", "KEEP", "", ""),
    "backend/message_router.py": (
        "communication/text", "INTEGRATE", "ENTRIES",
        "WS entry — becomes a thin adapter calling BeanieMind.process"),
    "backend/voice/service.py": (
        "communication/voice", "INTEGRATE", "ENTRIES",
        "voice entry — must enter the same Mind"),
    "backend/voice/orchestrator.py": (
        "communication/voice", "KEEP", "", ""),
    "backend/voice/remote_audio.py": (
        "communication/voice", "KEEP", "", "phone audio ingestion"),
    "backend/voice/sample_wake_model.py": (
        "communication/voice", "KEEP", "", ""),
    "app/llm.py": (
        "infrastructure/inference", "KEEP", "",
        "LM Studio client; model router untouched (invariant #3)"),
    "app/config.py": ("infrastructure/config", "KEEP", "", ""),
    "app/database.py": ("infrastructure/persistence", "KEEP", "", ""),
    "app/tasks.py": ("infrastructure/persistence", "KEEP", "", ""),
    "app/settings_store.py": ("infrastructure/config", "KEEP", "", ""),
    "app/desktop_tray.py": (
        "communication/presence", "KEEP", "",
        "tray/autostart glue (charter §5⑥)"),
    "app/utils/decision_trace.py": (
        "evaluation/trace", "KEEP", "", "wired via lazy imports in llm.py"),
    "app/cognition/experiment_engine.py": (
        "mind/imagination", "INTEGRATE", "",
        "experimentation sandbox — Phase-9 curiosity effector"),
}

SKIP_PREFIXES = ("tests/", ".venv/", ".git/", "frontend/", "android/")


def iter_production_modules():
    for p in sorted(REPO.rglob("*.py")):
        s = str(p.relative_to(REPO))
        if any(s.startswith(x) for x in SKIP_PREFIXES) or "__pycache__" in s:
            continue
        if pathlib.PurePosixPath(s).parts[0] not in (
                "app", "backend", "desktop", "scripts"):
            continue
        yield p, s


def classify(rel: str):
    if rel in OVERRIDES:
        layer, disp, cluster, note = OVERRIDES[rel]
        if not layer:  # placeholder row
            return None
        return layer, disp, cluster, note
    for prefix, default in DIR_DEFAULTS.items():
        if rel.startswith(prefix + "/"):
            return default
    return None


def main() -> int:
    rows, unclassified = [], []
    for path, rel in iter_production_modules():
        c = classify(rel)
        if c is None:
            unclassified.append(rel)
            continue
        layer, disp, cluster, note = c
        try:
            nlines = len(path.read_text(errors="replace").splitlines())
            doc = ast.get_docstring(ast.parse(path.read_text(errors="replace"))) or ""
        except Exception:
            nlines, doc = -1, "!! parse error"
        first = doc.strip().splitlines()[0][:90] if doc.strip() else ""
        rows.append({
            "path": rel, "lines": nlines, "agi_layer": layer,
            "disposition": disp, "cluster": cluster,
            "module_summary": first, "phase0_note": note,
        })

    if unclassified:
        print("UNCLASSIFIED (add overrides or defaults):", file=sys.stderr)
        for u in unclassified:
            print("  ", u, file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {OUT.relative_to(REPO)} with {len(rows)} rows "
          f"({len(unclassified)} unclassified)")
    by_layer = Counter(r["agi_layer"].split("/")[0] for r in rows)
    by_disp = Counter(r["disposition"] for r in rows)
    print("top-level layers:", dict(by_layer.most_common()))
    print("dispositions:", dict(by_disp.most_common()))
    clusters = Counter(r["cluster"] for r in rows if r["cluster"])
    print("merge/integration clusters:", dict(clusters.most_common()))
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
