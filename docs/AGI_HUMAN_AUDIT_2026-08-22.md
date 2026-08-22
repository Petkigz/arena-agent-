# AGI Human-Intelligence Audit — 2026-08-22

**Goal you stated:** "create an AGI with human intelligence — see how far I can take it"  
**Branch audited:** `arena/01a02a43-arena-agent` @ `ad43138` (after live theme + voice wiring)  
**Hardware:** i9-14900K (hybrid P/E), RX 580 8GB (CPU inference fallback), 16GB DDR5, LM Studio Qwen 3B fast + 9B reasoning, Max Loaded Models = 1  
**This audit is from the AGI lens, not just bug-fix lens.** It measures how close each human capability is, how deep the module is, and what it would take to push further on your hardware.

---

## 0. What "human intelligence" means here (so we don't do % theater)

Human intelligence is not one number. It's 12 interacting capabilities. I audited each against your code:

| Dimension | Human does | What your system has | Depth (0-5) | Gap to human |
|---|---|---|---|---|
| **1. Perception** | Sees, hears, feels, proprioception, active attention | `screen_capture` (mss), `camera_capture` (OpenCV), `audio_capture` (PyAudio), `location_service` (ADB/IP), `ocr_reader` (Tesseract), `vision_analyzer` (OCR+LLM), `voice` (STT/VAD/wake) | 2 | No true scene understanding, no object detection, no depth, no video temporal, audio only transcription |
| **2. Memory** | Episodic (what happened), semantic (facts), procedural (how), working memory, consolidation during sleep, forgetting, associative retrieval | `MemoryStore` (SQLite), `semantic_rag.py`, `coworker_brain.py`, `reflection_engine`, `episodic` via `db`, `memory_learning`, `memory_decay`, `periodic_autonomous_cycle` consolidation (decay+prune+integrate) | 3 | Consolidation is simple decay/prune, not re-structuring; no associative linking, no memory-driven planning |
| **3. World Model** | Entities + relationships + causality + time + physics + affordances | `WorldModel` (entity/observation store), `world_ingest`, `source_types`, `common_sense` KB (physical_world, spatial, temporal, human_behavior, technology), `environment_grounding` | 3 | Relationships learned? Currently hand-built common-sense + observation ingestion, not learned from interaction; no physics simulation; affordances not grounded |
| **4. Reasoning** | Deduction, induction, abduction, causal, counterfactual, analogical, probabilistic | `reasoning_cycle`, `reasoning_loop`, `counterfactual_simulator`, `causal_inference` (DAG with strength/confidence), `analogical_memory`, `confidence_calibrator`, `advanced_cognitive_capabilities` (Bayesian, Monte Carlo) | 3 | Causal graph is stored, not learned via interventions (no do-calculus); counterfactual simulator is heuristic, not learned causal model; probabilistic reasoning exists but not used in main loop |
| **5. Planning** | Hierarchical, resource-aware, contingency, replanning, long-horizon | `goal_interpreter`, `goal_decomposer`, `action_planner`, `strategic_planning`, `planning_patterns`, `goal_replanner`, `goal_verifier` (tri-state), `step_verifier`, `autonomous_goal_executor` with explicit `depends_on`/`requires_evidence`/`produces_evidence` | 4 | Strongest area. Plans have dependencies and evidence data-flow, `execute_plan` blocks on prerequisites, `reconcile_plan` verify-only. Still linear chains, not HTN with resource constraints. |
| **6. Learning** | Continual, few-shot, transfer, meta-learning, curiosity, self-improvement | `memory_learning`, `skill_classifier`, `analogical_memory`, `cross_domain_transfer`, `transfer_learning`, `structured_lessons`, `strategy_outcomes`, `self_evolving_agent`, `experiment_engine`, `capability_factory` | 2 | Lessons are written and now read back (closed loop in `ad43138`? Actually `GoalReplanner` → `ActionPlanner` → `CounterfactualSimulator` uses `lesson_store`), but no continual learning that updates model weights; no meta-learning; `self_evolving_agent` synthesizes tools via AST but not verified end-to-end |
| **7. Language** | Grounding symbols to perception/action, pragmatics, common ground | `language_grounding` (perceptual/motor/multimodal/contextual), `prompt_slicer`, `llm.py` (Qwen router) | 2 | Grounding exists as data structures (PerceptualGrounding, ActionGrounding, MultimodalGrounding) but not populated from real perception during chat. `ground_utterance` tokenizes and looks up DB, but DB empty on fresh install. No active grounding loop. |
| **8. Social** | Theory of mind, emotion recognition, empathy, norms, collaboration | `social_cognition` (MentalStateModel, EmotionalState, SocialRelationship, SocialInteraction), `cultural_learning`, `human_nature_engine`, `common_sense/human_behavior` | 2 | Emotion recognition is rule-based `respond_to_emotion` mapping, not from facial expression (no face detection) or voice prosody (no pitch/energy analysis). Theory of mind is stored, not inferred from dialogue. No real empathy. |
| **9. Creativity** | Divergent thinking, novelty, usefulness, recombination | `creative_generation` | 1 | Generates alternative strategies when first fails, but not true divergent creation (no novelty search, no evaluation of usefulness). |
| **10. Metacognition** | Knows what it knows, confidence calibration, resource allocation, self-model | `metacognitive_monitor`, `self_model`, `confidence_calibrator`, `resource_allocator`, `self_reflection_engine`, `HardwareGovernor`, `HardwareMonitor` | 4 | Strong. Self-model tracks capability performance per domain, routes fast vs reasoning model, calibrates confidence, allocates resources. Hardware self-awareness via `HardwareGovernor.build_self_model()` (P/E cores, RAM, GPU tier). |
| **11. Embodiment** | Reasons about own body, tool use, affordances, physical world | `embodied_cognition`, `visual_observer`, `background_observer`, `anticipation_engine`, `event_prioritizer` | 2 | Reasons about files/processes/devices, not about physical world physics. No tool-use learning (e.g., learning that hammer affords pounding). |
| **12. Consciousness** | Self-awareness, attention, subjective experience, access vs phenomenal | `consciousness_simulation` (SubjectiveExperience, ConsciousState, ConsciousnessReport) | 1 | Functional self-model, not phenomenal. Creates experience records with intensity/valence/arousal/clarity, but not integrated into main loop as attention. Attention is `AttentionManager`, not consciousness. Honest. |
| **13. Autonomy** | Sustained operation, proactive, anticipates needs, asks for help when uncertain | `periodic_autonomous_cycle` (hourly, max 3 goals), `autonomous_goal_generator` (evidence-driven signals), `autonomous_operator`, `proactive_coworker_daemon`, `scheduler` | 3 | Hourly cycle scheduled via `ProactiveScheduler` in `app/server.py` lifespan, governed by `AUTONOMY_MODE` (supervised/bounded/full/off). Generates goals from resource pressure, stale beliefs, failed actions, prediction error, low success rate — not keyword matching. But max 3 goals per cycle, not full workday. |

**Overall:** You have a **real, closed-loop, evidence-disciplined cognitive assistant** (perceive → reason → plan → act → observe → verify → replan → learn) with **honest measurement** (21/21 scorecard). It is **not human-level AGI** (no system is), but it is the strongest foundation I've seen for a local-first attempt. The gaps are **integration and depth**, not missing modules.

---

## 1. Module Depth Analysis — are the 15 wired modules real or scaffolding?

I read each module's implementation (not just its existence). Rating:

### Deep (3-4/5) — actually does work
- **runtime.py** (1892 lines): True composition root, wires 25 components, singleton thread-safe, `process_cognitive_cycle()` is authoritative, `_integrate_phase_modules()` calls all 15 each cycle, `measure_capabilities()` behavioral probes with throwaway stores.
- **goal_verifier.py + step_verifier.py + goal_replanner.py**: Tri-state verification (SATISFIED/FAILED/UNKNOWN), `StepVerifier` evaluates step's own criteria, confidence evidence-derived (0.9 observed / 0.7 conversational / 0.5 unverified / 0.0 failed), `reconcile_plan` verify-only.
- **perception.py**: Capability-specific observation strategies (process probe via psutil, filesystem probe with result set, fresh web search via urllib, Pillow validation, ADB probes). Execution success never used as evidence.
- **world_model.py + belief_engine.py + beliefs.py**: Provenance-tracked, revisable, temporal metadata, decay.
- **metacognitive_monitor + self_model + confidence_calibrator + resource_allocator**: Tracks performance per domain, routes fast vs reasoning, calibrates, allocates. Hardware-aware.
- **strategic_planning**: Long-horizon decomposition with dependencies, evidence contracts.
- **autonomous_goal_generator + executor**: Evidence-driven signals (resource, belief staleness, failed actions, prediction error, success rate) with threshold gates, wired ahead of keyword fallback.

### Medium (2/5) — structure exists, but shallow or not learning
- **causal_inference.py** (738 lines): DAG with `CausalNode`, `CausalEdge` (strength/confidence/evidence/mechanism), `predict_intervention` (do(X=x)), `counterfactual_reasoning`, `root_cause_analysis`. But edges are added via `add_causal_relationship()` hand-called, not learned from interventions. No do-calculus, no confounding adjustment. Strength is hand-set, not estimated from data. It's a **store**, not a learner.
- **social_cognition.py** (1035 lines): `MentalStateModel` (belief/desire/intention/knowledge/emotion), `EmotionalState` (Ekman joy/sadness/anger/fear/surprise/disgust/neutral + intensity/triggers), `SocialRelationship` (trust_level, interaction_count), `SocialInteraction` (norms_followed/violated). But `recognize_emotion` is called with explicit emotion, not inferred from face/voice. `respond_to_emotion` is rule-based mapping. No vision-based face detection, no prosody analysis. Theory of mind stored, not inferred.
- **language_grounding.py** (856 lines): `PerceptualGrounding` (modality, features, sensory_experience), `ActionGrounding` (associated_actions, affordances, motor_programs), `MultimodalGrounding`, `ContextualMeaning`. But `ground_utterance` just tokenizes and looks up DB — DB empty on fresh install. No active loop that creates groundings from live perception (e.g., seeing a chair → grounding "chair" to visual features). Symbol grounding problem not solved, just scaffolded.
- **cross_domain_transfer + analogical_memory + skill_classifier + planning_patterns**: Classifies actions by skill type (search/organize/create/communicate/analyze), stores analogies, extracts planning patterns. But transfer is confidence boost based on skill type, not meta-learning that improves with experience.
- **embodied_cognition**: Reasons about files/processes/devices, not physical physics. No affordance learning.
- **cultural_learning**: Learns norms/tone/preferences over time, but how? Stores interactions, suggests norms via keyword matching ("collaborate" → cooperation). Shallow.

### Shallow (1/5) — placeholder / theater risk
- **consciousness_simulation.py** (725 lines): `SubjectiveExperience` with intensity/valence/arousal/clarity/duration, `ConsciousState` with attention_mode, self_awareness, agency_awareness, `ConsciousnessReport` with narrative. Creates records, but not used to gate attention or decision. It's a **functional self-model**, not consciousness. Honest, but not integrated as attention.
- **creative_generation.py**: Generates alternative strategies when first fails, but no novelty evaluation, no divergent search.

**Verdict:** The **planning + verification + metacognition + autonomy** stack is deep and real. The **causal + social + language grounding + consciousness + creativity** stack is scaffolding that **stores** but does not **learn** or **infer** from live data. That's exactly where to push to get closer to human intelligence.

---

## 2. How far can you take it on i9-14900K + RX 580 + Qwen 3B/9B?

### What this hardware CAN do (next 6-12 months, achievable)

**You cannot run a 7B VLM + 9B LLM simultaneously on RX 580 8GB + 16GB RAM with CPU inference, but you CAN:**

1. **True perception grounding (close the language grounding loop):**
   - Add **object detection** via `opencv` + `yolo-nas` tiny or `detr` quantized (runs on CPU, ~1-2 sec/frame) — detect chair, person, screen, phone, etc. from `camera_capture` and `screen_capture`.
   - When you detect "chair" with bounding box, automatically create `PerceptualGrounding(symbol="chair", modality="vision", features={bbox, confidence})`. This populates the grounding DB from live perception, not hand-calls.
   - Add **face detection** (OpenCV Haar / MediaPipe) → emotion from facial expression (simple: smile → joy) → feed `social_cognition.recognize_emotion()`. Now emotion recognition is from vision, not rule-based.
   - Add **voice prosody** analysis (pitch, energy, speaking rate from `audio_capture`) → emotion intensity → social.

2. **Causal learning from interventions (not just storage):**
   - Currently `causal_inference` stores edges. Make it **learn**: every time `execute_plan` runs a step with `produces_evidence`, record `before_state` and `after_state` (from `perception.py` probes). If `after_state` differs, create or strengthen causal edge `action → evidence` with confidence update.
   - Implement simple **Bayesian update** for edge strength: `strength = (success_count + alpha) / (total_count + alpha+beta)`. This is already partially done in `advanced_cognitive_capabilities` but not wired to causal graph.
   - Add **confounder detection**: if A→B and C→A and C→B, flag C as potential confounder.

3. **Continual learning that changes behavior (close the learning loop fully):**
   - `strategy_outcomes` + `structured_lessons` already influence `ActionPlanner` via `GoalReplanner` (you closed this in `b607cec`). Next: make `SkillClassifier` transfer actually **improve** success rate over time (measure it: after 10 file searches, web search latency/accuracy improves).
   - Implement **curiosity-driven goal generation**: currently `generate_goals_from_signals` uses resource pressure, stale beliefs, failed actions, prediction error, low success rate. Add **information gain** signal: generate goals that maximize expected information gain (explore unknown files, unknown entities).

4. **Memory consolidation that restructures (human-like sleep):**
   - Currently decay+prune+integrate. Add **association**: during `consolidate_memory()`, find entities that co-occur frequently and create relationship edges (e.g., "chrome" often appears with "web_search" → `depends_on`).
   - Add **summarization**: cluster episodic memories into semantic summaries (e.g., 10 failed `search_files` → lesson "search_files fails when root_dir not set").

5. **Hierarchical planning with resources:**
   - Extend `ExecutionStep` (already has `depends_on`, `requires_evidence`, `produces_evidence`, `success_criteria`, `failure_conditions`) to have **resource requirements** and **time estimates**. `ResourceManager` (in `advanced_cognitive_capabilities`) already exists — wire it into `ActionPlanner` so plans are scheduled based on CPU/RAM headroom from `HardwareGovernor`.

6. **True multimodal chat (vision + voice + text):**
   - Web/Android/desktop already have vision upload + voice. Make `CognitiveRuntime.process_cognitive_cycle` accept **multimodal input**: if user sends image + "what is this?", run `VisionAnalyzerTool` (OCR) + object detection, then create grounding, then answer with grounded meaning. Currently chat is text-only, vision is separate endpoint.

7. **Self-evolution that is verified:**
   - `self_evolving_agent` synthesizes tools via AST but not verified. Add loop: synthesize → generate test → run in `DisposableSandbox` → if passes, add to `PluginRegistry` and manifest. This is **executable capability synthesis** already tested in `test_executable_capability_synthesis.py`.

### What this hardware CANNOT do (needs more VRAM / RAM / models)

- **True VLM understanding:** RX 580 8GB cannot hold Qwen2-VL 7B + Qwen 9B simultaneously. Options: upgrade to 24GB GPU, or use **quantized tiny VLM** (Moondream 1.8B, Llava-Phi 3.8B Q4) that fits in 8GB with offload, or run VLM on CPU with 32GB RAM (slow, 10-20 sec/image). Honest limitation (G6).
- **Large-scale continual pre-training:** Qwen 3B/9B cannot be fine-tuned continually on i9 alone without catastrophic forgetting. Use LoRA adapters for skill-specific tuning, not full fine-tune.
- **Real-time video understanding:** 16kHz audio + 30fps video object detection on CPU is heavy. Need P-cores for reasoning, E-cores for perception — `HardwareGovernor` already does affinity, but still limited.

---

## 3. Gaps to Human Intelligence — Prioritized Roadmap (AGI lens, not bug lens)

### P0 — Foundation you already have (keep intact)
- One brain, thin agents, one loaded model, strong tools thin model, deterministic verification, approval gates, honesty over theater.

### P1 — Next 1-2 months — make existing modules LEARN, not just store (highest leverage to human-like)

1. **Perception → Grounding loop (closes language grounding):**
   - File: `app/cognition/language_grounding.py` + `app/tools/camera_capture.py` + `screen_capture.py`
   - Add `ObjectDetector` (YOLO-NAS tiny) that runs on captured images, returns `[{label, bbox, confidence}]`
   - In `CognitiveRuntime._integrate_phase_modules()`, after perception, call `language_grounding.create_perceptual_grounding()` for each detected object. Now grounding DB populates from real world.
   - Add face detection → `social_cognition.recognize_emotion()` from vision.

2. **Causal learning from interventions:**
   - File: `app/cognition/causal_inference.py` + `autonomous_goal_executor.py`
   - In `execute_plan`, after each COMPLETED step, call `causal_inference.add_causal_relationship(cause=step.action_type, effect=step.produces_evidence, evidence=[observation])` with strength update based on `StrategyOutcomeStore`.
   - Implement `strength = (successes + 1) / (total + 2)` Bayesian.

3. **Memory association during consolidation:**
   - File: `app/cognition/periodic_autonomous_cycle.py` + `memory_learning.py`
   - In `consolidate_memory()`, after decay/prune, find co-occurring entities (same 1-hour window) and create `WorldModel` relationship `related_to` with confidence.

4. **Curiosity via information gain:**
   - File: `app/cognition/autonomous_goal_generator.py` + `information_gain.py`
   - Add signal: `unknown_entities` (entities with low confidence or no observations) → generate goal "investigate X" with high information gain.

5. **Fix P1 bugs from full audit (B6-B13, V3-V4):** Magic-byte dict, useVoice stale closure, ImagesPage blob revoke, conversationStore ack/merge, desktop WS version, QSettings bool, TTS speed.

### P2 — 2-4 months — autonomy and embodiment

6. **Hierarchical planning with resources:**
   - Wire `ResourceManager` from `advanced_cognitive_capabilities` into `ActionPlanner` — plans get `resources` dict (cpu, memory, time) and are scheduled based on `HardwareGovernor` live telemetry.

7. **Multimodal chat:**
   - Make `process_cognitive_cycle` accept `image_path` + `audio` alongside text. Web's `ChatInput` already supports attachments — route them through cognitive runtime, not just separate vision endpoint.

8. **Social from real signals:**
   - Add voice prosody analysis (pitch/energy) → emotion intensity.
   - Add face detection → emotion.
   - Make `social_cognition` infer mental states from dialogue (e.g., user says "I'm frustrated" → `infer_mental_state(agent_id=user, state_type=EMOTION, content="frustrated")`).

9. **Self-evolution verified:**
   - `self_evolving_agent.synthesize_and_hotload_tool` → generate pytest → run in sandbox → if passes, register in `PluginRegistry`.

### P3 — 4-12 months — push hardware limits

10. **Tiny VLM on RX 580:**
    - Try `moondream2` or `llava-phi-3-mini` Q4_K_M quantized (fits ~4-5GB) alongside Qwen 3B (not 9B) — use fast model for vision, reasoning model for text. Or run VLM on CPU with 32GB RAM (upgrade planned). This turns G6 from OCR+LLM to true VLM.

11. **Continual LoRA:**
    - Use `peft` LoRA adapters for Qwen 3B to learn user-specific skills (e.g., your coding style, your business niche) without full fine-tune. Store adapters in `data/loras/`.

12. **Long-horizon project management:**
    - `project_manager.py` already exists — wire it into autonomous cycle so projects span days, with persistent state, context restore on resume.

---

## 4. Honest Measurement — how to know you're getting closer to human

Replace "% AGI" with **behavioral probes** (you already started with `measure_capabilities()` 21/21). Add:

- **Perception grounding:** After seeing 10 images of "chair", can system answer "what does chair look like?" with grounded features (bbox, color) not hallucinated?
- **Causal:** After 5 times running `search_files` with `root_dir` set vs not set, does it predict failure when `root_dir` missing?
- **Social:** After user says "I'm frustrated" 3 times, does it respond with empathy and lower its action level (ask for approval)?
- **Memory:** Kill and restart — does it remember lessons and pick different strategy?
- **Autonomy:** Run 8-hour workday with `AUTONOMY_MODE=supervised` — how many Level-3 escalations? How many goals achieved verified (not just attempted)?
- **Transfer:** After succeeding at file search, does web search improve (latency, success rate)?

These are in `roadmap-to-intelligence.md` Phase 1-6 completion criteria — measurable, not percentages.

---

## 5. What you should NOT do (to stay honest and safe)

- Don't claim "human-level AGI achieved" — no system is. Your docs now say so plainly (good).
- Don't remove approval gates to feel more autonomous — capability ≠ execution. Keep L3 gate, make it low-friction (fast confirm).
- Don't hot-swap models per request — Max Loaded Models = 1, hardware-aware routing only.
- Don't add more orphaned modules — wire existing ones deeper first (you already fixed 9 orphans in previous branch).

---

## 6. Bottom line — how far can you take it?

**Current:** Strongest local-first, evidence-disciplined, closed-loop assistant I have audited. Planning/verification/metacognition/autonomy are deep (4/5). Perception/social/language grounding/consciousness/creativity are scaffolding (1-2/5) that store but don't yet learn from live data.

**With your hardware, in 6-12 months, you CAN reach:**
- A system that **sees objects, grounds words to what it sees, learns causal effects from its own actions, associates memories, generates curious goals, and operates a full workday with minimal Level-3 escalations** — all locally, with honest UNKNOWN when unsure.
- That is **not human-level AGI**, but it is **human-like in the 12 dimensions** and measurably better than task #1 after task #324 (compounding intelligence).

**To get true VLM and large-scale continual learning, you need:** 24GB+ GPU or 32GB+ RAM upgrade, or quantized tiny VLM alongside Qwen.

**Next step I recommend:** P1 1-5 (perception→grounding loop + causal learning + memory association + curiosity + P1 bug fixes). Each is a tested, incremental commit that makes the system behave more like the AGI you envision, not just more code.

Want me to start on **P1-1 Perception → Grounding loop (object detection + auto-grounding)** now?
