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
        "persona string only — the seed of 'I am Beanie'; must become a real "
        "identity record inside the Mind"),
    "app/agents/master_agent.py": (
        "embodiment/action-execution", "DEMOTE", "AUTHORITY",
        "action executor (hands); must not be perceived as a brain"),
    "app/agents/self_evolving_agent.py": (
        "learning/self-improvement", "INTEGRATE", "",
        "Phase 20 material: one mechanism of self-improvement"),
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
        "owner-governed identity adaptation — personality-development seed"),
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
        "owner-authority/approvals", "KEEP", "", ""),
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
        "mind/imagination", "KEEP", "", "prediction vs outcome surprisal"),
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
        "embodiment/os-abstraction", "INTEGRATE", "",
        "seed of the Phase-12 OS concept abstraction (one planner, all OSes)"),
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
        "capabilities/registry", "DEMOTE", "TOOL-FIRST",
        "manifest-first routing IS the tool-first thinking Phase 2 replaces; "
        "keep as capability resolution invoked AFTER world reasoning"),
    "app/cognition/capability_resolver.py": (
        "capabilities/registry", "KEEP", "", ""),
    "app/cognition/capability_factory.py": (
        "capabilities/registry", "KEEP", "", "dynamic capability synthesis"),
    "app/cognition/semantic_matcher.py": (
        "capabilities/registry", "KEEP", "", ""),

    # ── MOTIVATION / CURIOSITY (Phases 9, 15) ────────────────────────────
    "app/cognition/autonomous_goal_generator.py": (
        "mind/motivation", "INTEGRATE", "", ""),
    "app/cognition/autonomous_goal_executor.py": (
        "mind/motivation", "INTEGRATE", "", ""),
    "app/cognition/periodic_autonomous_cycle.py": (
        "mind/motivation", "INTEGRATE", "", ""),
    "app/cognition/learning_progress.py": (
        "mind/motivation", "KEEP", "", "curiosity: explore growing competence"),
    "app/cognition/information_gain.py": (
        "mind/motivation", "KEEP", "", "information-seeking primitives"),
    "app/cognition/phase7_preferences.py": (
        "mind/motivation", "INTEGRATE", "", "preference & novelty evaluation"),
    "app/cognition/parked_goal_recheck.py": (
        "mind/motivation", "KEEP", "", "wired in server lifespan"),
    "app/cognition/attention_manager.py": (
        "mind/attention", "INTEGRATE", "ATTENTION",
        "43-line seed — the Phase-14 attention system must grow here"),

    # ── LEARNING family (Phases 6-8, 21) ─────────────────────────────────
    "app/cognition/continual_learning.py": (
        "learning/consolidation", "INTEGRATE", "", ""),
    "app/cognition/consolidation.py": (
        "learning/consolidation", "INTEGRATE", "", ""),
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

    # ── REFLECTION cluster (Phase 19) ────────────────────────────────────
    "app/cognition/verified_reflection.py": (
        "mind/reflection", "MERGE", "REFLECTION",
        "three reflection engines exist — one reflection in the Mind"),
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
        "metacognition feeds the self model + anticipation"),

    # ── PERCEPTION layer (Phases 11, 13) ─────────────────────────────────
    "app/cognition/perception.py": (
        "perception/environment", "INTEGRATE", "",
        "observation collector — post-action probes today"),
    "app/cognition/visual_observer.py": (
        "perception/vision", "INTEGRATE", "", ""),
    "app/cognition/temporal_vision.py": (
        "perception/vision", "KEEP", "", "stream-isolated tracking"),
    "app/perception/background_observer.py": (
        "perception/environment", "KEEP", "", "charter §5④ silent watcher"),
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
        "learning/demonstration", "INTEGRATE", "",
        "form-driven today; Phase 7 makes conversation the teacher"),
    "app/tools/universal_media_learner.py": (
        "learning/media", "INTEGRATE", "", "Phase-8 nucleus"),
    "app/tools/youtube_learner.py": (
        "learning/media", "INTEGRATE", "", ""),
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
    "app/cognition/social_cognition.py": (
        "learning/social", "INTEGRATE", "", "Phase 16 engine"),
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
