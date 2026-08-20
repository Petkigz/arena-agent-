# Roadmap: Cognitive Assistant → Compounding Intelligence

## Current State (Baseline)

```
✅ Solid cognitive scaffolding
✅ Evidence discipline (provenance, tri-state verification, closed boundary)
✅ 40+ capabilities
✅ 323 tests enforcing invariants
✅ WAITING_FOR_EVIDENCE lifecycle state
✅ Approval gate model
```

**What works:** The system tries, observes, verifies, and replans. It doesn't fabricate success.

**What's missing:** The system doesn't get smarter. Task #324 is handled identically to task #1.

---

## Phase 1: Learning from Experience

**Goal:** The system gets measurably better at tasks it has seen before.

**Current problem:** MemoryLearner records lessons. ReflectionEngine logs outcomes. But nothing influences future decisions based on past experience. The cognitive cycle is stateless across sessions.

### Deliverables

#### 1A. Belief Revision Engine
- Beliefs are hypotheses with confidence, not facts
- Contradictory evidence reduces confidence (doesn't delete)
- Evidence ages — older observations carry less weight
- Beliefs carry provenance chains (what evidence supports them)
- **Completion:** Beliefs update correctly when contradicted; stale beliefs decay

#### 1B. Outcome-Influenced Strategy Selection
- Every completed task records: goal_type, strategy_used, outcome, latency, surprise
- ActionPlanner queries past outcomes when selecting strategies
- Strategies that failed for a task_type are deprioritized (not deleted)
- Strategies that succeeded are boosted
- **Completion:** After 3 failures of strategy A for task_type X, the system picks strategy B first

#### 1C. Reflection That Changes Behavior
- ReflectionEngine produces structured lessons (not just text logs)
- Lessons are queryable: "what went wrong last time I tried X?"
- CounterfactualSimulator uses past lessons to weight simulations
- **Completion:** System can answer "why did this fail before?" and acts on the answer

#### 1D. Session Continuity
- Cognitive state persists across restarts (beliefs, strategy scores, lessons)
- On startup, the system loads its learned state
- World model entities carry temporal metadata (first_seen, last_seen, confidence_decay)
- **Completion:** Kill and restart the system; it remembers what it learned

### Tests
- Belief revision under contradiction
- Strategy deprioritization after repeated failure
- Reflection lesson retrieval and application
- State persistence across simulated restarts

---

## Phase 2: Persistent World Model

**Goal:** The system understands relationships, causality, and time in its environment.

**Current problem:** WorldModel is a key-value store. It records "chrome.status = running" but doesn't know that Chrome is a browser, that browsers display web pages, or that killing Chrome means the web search results disappear.

### Deliverables

#### 2A. Entity Relationship Graph
- Entities have typed relationships (depends_on, contains, produces, located_at)
- Relationships are learned from observations (not hardcoded)
- Relationship strength is confidence-weighted
- **Completion:** System can answer "what depends on Chrome?" and "what does this file belong to?"

#### 2B. Temporal Reasoning
- Observations carry timestamps and decay
- Entity states have history (status changed from X to Y at time T)
- Stale observations are flagged, not silently trusted
- Time-based queries: "what changed in the last hour?"
- **Completion:** System can reason about "before" and "after" and "how long ago"

#### 2C. Causal Prediction
- Action outcomes are modeled: "if I do X, Y usually happens"
- Predictions are generated before execution
- Prediction errors (surprisal) update causal models
- **Completion:** CounterfactualSimulator uses learned causal models, not just heuristics

#### 2D. World Model Consistency Checks
- Contradictory entity states are detected and flagged
- Impossible states trigger investigation (not silent acceptance)
- **Completion:** System notices when two beliefs conflict and investigates

### Tests
- Relationship traversal and inference
- Temporal decay and staleness detection
- Causal prediction accuracy
- Contradiction detection

---

## Phase 3: Transfer Learning

**Goal:** Skills learned in one domain improve performance in related domains.

**Current problem:** Learning to search files doesn't help with web searching. Learning to organize code doesn't help organize documents. Every capability is siloed.

### Deliverables

#### 3A. Skill Abstraction Layer
- Actions are classified by abstract skill type (search, organize, create, communicate, analyze)
- Strategy patterns are tagged with skill types
- Success in one search task transfers confidence to other search tasks
- **Completion:** After succeeding at file search, web search strategy selection benefits

#### 3B. Analogical Reasoning
- System can identify structural similarities between tasks
- "This is like that time I..." triggers relevant memory retrieval
- Analogies are validated (not just surface-level keyword matching)
- **Completion:** System explicitly reasons "this task is structurally similar to X"

#### 3C. Domain-General Planning Patterns
- Common planning patterns are extracted from successful task sequences
- Patterns are reusable across domains (decompose → execute → verify → report)
- **Completion:** A learned planning pattern from code tasks applies to research tasks

### Tests
- Cross-domain skill transfer measurement
- Analogy validity checking
- Pattern extraction and reuse

---

## Phase 4: Continuous Perception

**Goal:** The system monitors its environment continuously, not just after actions.

**Current problem:** The system observes only after executing an action. A human secretary monitors continuously — notices changes, anticipates needs, acts proactively.

### Deliverables

#### 4A. Background Observation Loop
- Low-priority thread periodically probes environment (processes, files, devices)
- Changes are detected and ingested into WorldModel
- Observation frequency adapts to importance (active tasks get more frequent probes)
- **Completion:** System notices environment changes without being asked

#### 4B. Event-Driven Cognition
- Significant environment changes trigger cognitive evaluation
- "The printer just came online" → "the pending print job can now execute"
- Events are prioritized (urgent vs informational)
- **Completion:** System reacts to environment changes proactively

#### 4C. Anticipatory Action
- Based on patterns, the system predicts what the user will need next
- "User always checks email after morning briefing" → pre-fetch
- Anticipations require approval for sensitive actions
- **Completion:** System prepares resources before they're requested

### Tests
- Background loop doesn't interfere with foreground tasks
- Event detection and prioritization
- Anticipation accuracy

---

## Phase 5: Meta-Cognition

**Goal:** The system reasons about its own reasoning and allocates resources strategically.

**Current problem:** The system uses the same amount of compute for "what time is it?" as for "analyze this codebase." It doesn't know what it's good at or bad at.

### Deliverables

#### 5A. Self-Model
- System tracks its own capability performance per domain
- Knows "I'm good at file search, weak at code analysis"
- Routes tasks to appropriate model (fast vs reasoning) based on self-assessment
- **Completion:** System can answer "what am I good at?" with evidence

#### 5B. Confidence Calibration
- Predicted confidence correlates with actual success rate
- Overconfident predictions are penalized and adjusted
- System says "I'm 60% sure" when it's right 60% of the time
- **Completion:** Calibrated confidence across task types

#### 5C. Strategic Resource Allocation
- Complex tasks get more reasoning cycles, simpler tasks get fewer
- Investigation depth adapts to task importance
- Bounded exploration: knows when to stop investigating
- **Completion:** Average latency decreases for simple tasks without quality loss on complex ones

### Tests
- Self-model accuracy
- Confidence calibration curves
- Resource allocation efficiency

---

## Phase 6: Integration & Autonomous Operation

**Goal:** All pieces work together for sustained autonomous operation with oversight.

### Deliverables

#### 6A. Long-Horizon Goal Decomposition
- Complex goals are broken into sub-goals with dependencies
- Sub-goals are executed, verified, and composed
- Partial progress is tracked and reported
- **Completion:** System handles "set up a complete development environment" as a multi-step project

#### 6B. Multi-Session Project Management
- Projects span multiple sessions with persistent state
- Progress is tracked across sessions
- Context is restored on resume
- **Completion:** System picks up where it left off across days

#### 6C. Autonomous Operation with Oversight
- System operates autonomously on approved task classes
- Reports progress at intervals
- Escalates when uncertain or blocked
- Owner can review and adjust at any time
- **Completion:** System runs a full workday of approved tasks with periodic check-ins

---

## Execution Principles

1. **Each phase produces working, tested code before moving to the next**
2. **No architectural rewrites** — each phase extends the existing foundation
3. **Measure improvement** — each phase must demonstrate measurable capability gain
4. **Local-first** — everything runs on your hardware with local models
5. **You define scope** — I implement what you approve, nothing more
6. **Push after each milestone** — you audit incrementally

## Realistic Assessment

- Phases 1-2 are achievable with your current setup and Qwen models
- Phase 3 starts pushing the limits of what local 9B models can do for analogical reasoning
- Phase 4 requires careful resource management (background loops on a single machine)
- Phases 5-6 may benefit from larger models when available, but the architecture supports them regardless
- The entire roadmap builds on the evidence foundation we've tightened — nothing requires throwing away what exists

## Where to Start

Phase 1A: Belief Revision Engine. That's the single highest-leverage change — making beliefs update from evidence is the foundation that everything else in the roadmap depends on.
