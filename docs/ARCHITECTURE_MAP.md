# Arena Architecture Map (Phase 0)

**Status:** Phase 0 deliverable per `docs/AGI_ROADMAP.md` (owner directive,
2026-09-08). Classification ground truth of the codebase as of commit
`93321c2`. Nothing is deleted or moved; this is the map that future phases
navigate by.

**Method:** subsystem-level inventory (792 Python files; app+backend+desktop =
339), invocation-site analysis of the live cycle, and this session's live-test
evidence. Items marked ⚠️ are judgment calls the owner should confirm.
Confidence: HIGH = traced in code, MED = static analysis, LOW = flagged only.

## 0. The spine — what actually executes per message (HIGH)

One path carries every message. Everything else is either support for this
path, sensing, actuation, or record-keeping:

```
backend/message_router.MessageRouter.handle_message        (WS text/voice entry)
  → app/cognition/runtime.CognitiveRuntime.process_cognitive_cycle
      → goal_interpreter (SemanticGoalInterpreter v2)
      → capability ladder + capability_resolver (feasibility honesty)
      → tool_matcher → decision router (ANSWER/INVESTIGATE/DEFER/ACT)
      → ActionGate (safety levels, approval store)
      → app/agents/master_agent.MasterAgentOrchestrator.execute_proposal
          → app/tools/* (the actual hands)
      → app/cognition/perception.ObservationCollector (post-action probes)
      → app/cognition/goal_verifier.GoalVerifier (+ launch truth override)
      → completion_honesty + guard_visibility (deterministic backstops)
      → app/cognition/trace.CognitiveTrace (persistence)
  → websocket_server (streamed reply)
```

Supporting spine services: `app/llm.py` (model lanes: fast/main/code, loaded-only
selection), `app/cognition/parked_goal_recheck.py` (evidence-only auto-recheck),
`app/cognition/os_control_planner/raw_input_guard/os_grounding` (actuation
safety), `app/policy.py`, `app/cognition/execution_control.py`.

## 1. Classification — Mind layer (app/cognition, 143 files, 58k lines)

### 1a. SPINE — drives behavior (keep; this IS the mind's reasoning core)
HIGH confidence, traced: `runtime.py` (cycle orchestrator, ~5k lines — the
single most load-bearing file in the repo), `cognitive_router`,
`cognitive_pipeline`, `reasoning_loop`, `goal_interpreter`, `goal_lifecycle`,
`goal_replanner`, `goal_verifier`, `goal_decomposer`, `action_planner`,
`action_proposal`, `action_selection`, `action_outcomes`,
`prediction_engine`, `counterfactual_simulator`, `criticality_review`,
`resource_allocator`, `tool_matcher`, `tool_registry`, `capability_factory`,
`capability_resolver`, `plan_control`, `plan_freshness`,
`plan_step_reconciliation`, `step_verifier`, `condition_language`,
`execution_control`, `execution_result`, `execution_truth`,
`approval_store`, `owner_control`, `owner_decisions`, `adaptive_autonomy`,
`autonomy_*` (8 files: allocator/envelope/lease/preemption/run_ledger/schedule
— the autonomy governance family), `completion_honesty`, `guard_visibility`,
`parked_goal_recheck`, `os_control_planner`, `raw_input_guard`, `os_grounding`,
`privilege_model`, `epistemic_presentation`, `inference_profile`,
`prompt_slicer`, `session`, `trace`, `runtime_wiring`, `checkpoint`,
`observation_router`, `perception.py` ⚠️ (misnamed: it is the ObservationCollector,
belongs in Mind-support not perception).

### 1b. MEMORY — stores/retrieves experience (keep; consolidation is future work)
`memory.py`, `associative_memory`, `working_memory`, `blackboard`,
`world_model` + `world_ingest` + `source_types`, `semantic_matcher`
(retrieval + embedding), `consolidation`, `structured_lessons`,
`planning_patterns`, `analogical_memory`, `prospective_memory`,
`commitment_ledger`, `beliefs`/`belief_engine`, `confidence`/
`confidence_calibrator`, `app/memory/semantic_rag`, `app/database.py`
(SQLite store for ALL of the above), `app/cognition/trace.py`,
`hypotheses`, `memory_learning`, `learning_progress`.

### 1c. LEARNING — changes future behavior (keep; several are ⚠️ record-heavy)
`continual_learning`, `correction_measurements` (chat corrections),
`skill_induction`, `skill_classifier`, `training_examples`, `lora_evaluation`,
`structured_lessons`, `memory_learning`, `experiment_engine`,
`information_gain`, `criterion_evaluator`, `phase7_preferences`,
`identity_adaptation`, `identity_continuity`, `user_state`, `owner_model`.
⚠️ `cross_domain_transfer`, `concept_bridge`, `cultural_learning`: currently
RECORD similarity/lessons but no verified case of transferring a skill to a
new domain (owner's round-2 finding: "tasks must really complete" applies to
learning claims too).

### 1d. RECORDER — runs each cycle but only WRITES records (⚠️ central Phase-1 question)
These are invoked at trace-time (verified: their log lines cluster after the
reply is formed; none feeds the decision router or the reply):

`consciousness_simulation`, `creative_generation`, `social_cognition`,
`cultural_learning`, `cross_domain_transfer`, `strategic_planning`,
`causal_inference`, `metacognitive_monitor`, `self_reflection_engine`,
`embodied_cognition`, `advanced_cognitive_capabilities`, `functional_affect`,
`ethical_reasoning`, `common_sense/`, `language_grounding`,
`confidence_calibrator` (report), `intelligence_benchmark`,
`phase0_evaluation`, `phase1_evidence`, `phase1_task_evaluations`,
`verified_reflection`, `self_knowledge`, `self_model`, `correction_*`.

They are NOT junk — they are honest introspective bookkeeping (the owner's
exhaustive-logging requirement lives here), and `measure_capabilities` uses
them for the wiring-completeness scorecard. But they must stop being mistaken
for reasoning. **Phase-1 candidate (a):** either wire a recorder INTO the
spine where it earns its keep (e.g. causal_inference informing prediction) or
relabel its output as telemetry.

### 1e. ⚠️ UNCLEAR / needs owner decision
`cognitive_state`, `cognitive_router` vs `cognitive_pipeline` vs
`reasoning_cycle` vs `reasoning_loop` (four reasoning-module names; the spine
uses some, the others' roles are unclear), `environment_grounding` vs
`environment_state`, `diagnostic_ranking`, `disk_reservation`,
`ontology_schema`, `scene_causal` vs `scene_graph`, `temporal_vision`,
`strategy_outcomes`, `uncertainty_questions`, `events` vs `event_bus`,
`incubation_queue`, `response_grounding`, `browser_adapters` vs
`browser_grounding`.

## 2. Body — actuation (app/tools subset + android) (keep)
`universal_filesystem`, `doc_manager`, `doc_reader` ⚠️ (overlaps doc_manager),
`process_manager`, `package_installer`, `deep_os_controller`,
`desktop_control` ⚠️ (overlaps deep_os_controller), `accessibility_control`,
`win32_ghost_operator`, `app_inventory` (fuzzy matching, freshness),
`local_executor`, `disposable_sandbox`, `browser_automation`, `web_agent`,
`git_manager`, `backup_manager`, `universal_media_learner`,
`android_adb_controller`, `skill_teaching_engine`.

## 3. Senses — perception inputs (keep)
Sensors implemented as tools: `screen_capture`, `camera_capture`,
`display_topology`, `ocr_reader`, `object_detector`, `vlm_analyzer`,
`vision_analyzer`, `file_index`.
Sensor services: `app/perception/background_observer` (resource-light
watcher), `event_prioritizer`, `anticipation_engine`,
`app/cognition/visual_observer`, `scene_graph`, `temporal_vision` ⚠️,
`backend/voice/{audio_capture,vad,stt,wake_word,sample_wake_model}`.

## 4. Communication — voice/text transport (keep)
`app/server.py` (unified HTTP/WS + SPA), `backend/websocket_server`,
`backend/message_router`, `backend/voice/{tts,service,orchestrator,remote_audio}`,
`app/perception/{speech_to_text,text_to_speech,piper_voice}`,
`backend/api/*` (device/language/phase6/screenshot/speaker/theme/wakeword
routes), `backend/chat_corrections.py`.

## 5. Tools — capability plugins (keep; 60+ files, low architectural priority)
Everything else in app/tools: calculator, weather, calendar, email, messaging,
contacts, notes, spreadsheet, sql_query, pdf_toolkit, document_generator,
presentation_generator, media_studio, music_studio, translator, rss, recipes,
price_lookup, fact_checker, web_research, youtube_learner,
knowledge_indexer/domains, indexed_search, database_connector, connectors,
lora_manager, budget_tracker, finance_trader, invoice_generator, crypto_vault,
task_tools, workflow_engine, daily_briefing, content_creator, data_analyzer,
coder_brain, pure_code, ast_janitor, prosody_analyzer, network_diagnostics,
system_diagnostics, weather_service, location_service, translator.
⚠️ Feature-era "persona" tools with heavy overlap, low live-test usage:
`business_growth`, `pentest_company_assistant`, `cybersecurity_brain`,
`security_lab`, `security_canary`, `security_education`, `opsec_manager`,
`financial_legal_wellness`, `knowledge_domains`, `binary_analyzer`,
`plugin_registry` — Tool class, but candidates for demotion to plugins-on-demand.

## 6. Infrastructure (keep)
`app/config.py`, `app/database.py`, `app/utils/*` (incl. decision_trace),
`app/scheduler/*`, `app/runtime/resource_manager`, `app/policy.py`,
`app/settings_store.py`, `app/llm.py`, `app/tasks.py`, `app/tools/manifest.py`
(the tool registry — load-bearing), `app/api/*` (owner-control/automation
routers), `desktop_tray.py`, `app/static/`.

## 7. Interface — the owner's windows (keep both, by owner decision 2026-09-08)
`desktop/` (PySide6 native client — server-merged lifecycle, THE default UI),
`frontend/` (web SPA — served by app.server, browser fallback + LAN access).
Two frontends is a real duplication cost; the owner explicitly chose to keep
both alive for now (desktop auto-starts, browser is the fallback).

## 8. Legacy / Duplicate (do NOT delete yet; demote + gate in Phase 1)

| Item | Verdict | Evidence |
|---|---|---|
| `app/main.py` | **Legacy duplicate API surface** | separate core-only FastAPI app (REPOSITORY_AUDIT §4); carries its own `/tools/youtube-learn`, `/tools/web-search` etc. in parallel to the unified server's routers. HIGH |
| `backend/main.py` | Alias (harmless) | re-exports the unified app. HIGH |
| `app/agents/multi_agent.py` + `MultiAgentCoordinator` | ⚠️ Duplicate coordination concepts | two "multi-agent" notions coexist; recorded "task interaction between 2 agents" in traces is a recorder artifact |
| security_* family + pentest_company_assistant | ⚠️ Overlapping feature-era tools | five modules covering adjacent ground, none in live-test spine |
| `doc_manager` vs `doc_reader` vs `document_generator` vs `universal_filesystem` | ⚠️ Four doc surfaces | overlapping read/write paths |
| `desktop_control` vs `deep_os_controller` | ⚠️ Two desktop-actuation modules | guard path uses deep_os_controller |
| `app/cognition/perception.py` name | Misleading | it is the post-action observation collector, not a sensor |
| phase0/phase1 evaluation files | Evaluation scaffolding | fine to keep under Learning; not mind |

## 9. What Phase 0 changes in how we work (effective immediately)

1. **The spine is the reference path.** Any new capability is specified as:
   which spine stage it extends, which layer it belongs to, what evidence
   proves it works.
2. **Recorder ≠ reasoning.** No module counts as intelligence unless its
   output changes a decision or an action that cycle (telemetry must say
   "telemetry").
3. **No new parallel surfaces.** New endpoints belong in existing routers;
   new tools register in the manifest; nothing gets a second app object.
4. **Duplicates are gated, not deleted** — until the owner signs off each
   merge in Phase 1.
