# Provenance Hardening Plan

## Goal

Tighten the evidence provenance contract from procedural checks to structural guarantees. Make it impossible for unverified evidence to enter the belief system through type-level enforcement rather than runtime checks.

## Current State

The evidence architecture has strong runtime guards:
- Admissibility gate in `BeliefEngine.ingest()`
- Source deduplication in `BeliefStore.revise()`
- Explicit `belief_value` / `hypothesis_value` separation in `RevisionResult`
- `inspect()` is read-only, never routes through hypotheses

But the contract is still procedural — enforced by convention and runtime checks, not by types.

## Phase 1: Canonical Source Types

**Problem:** `is_admissible()` uses substring matching on source strings. A source like `"verified_execution_result_audit"` would be incorrectly rejected.

**Solution:** Replace string sources with a canonical enum.

### Changes

1. Create `app/cognition/source_types.py`:
   ```python
   class SourceType(str, Enum):
       # Admissible (environmental probes)
       OS_PROCESS_PROBE = "os_process_probe"
       FILESYSTEM_PROBE = "filesystem_probe"
       SCREEN_CAPTURE_PROBE = "screen_capture_file_probe"
       ADB_BATTERY_PROBE = "adb_battery_probe"
       ADB_TELEPHONY_PROBE = "adb_telephony_probe"
       ADB_WINDOW_PROBE = "adb_window_probe"
       WEB_SEARCH_PROBE = "web_search_probe"
       DIAGNOSTIC_PROBE = "diagnostic_system_probe"
       ENVIRONMENT_GROUNDING = "environment_grounding_engine"
       
       # Inadmissible (claims, not observations)
       USER_INPUT = "user_input"
       MASTER_AGENT = "master_agent"
       EXECUTION_RESULT = "execution_result"
       SELF_REPORTED = "self_reported"
       SYSTEM_APP_INVENTORY = "system_app_inventory"
   ```

2. Update `BeliefEngine.is_admissible()` to check enum membership:
   ```python
   ADMISSIBLE_SOURCES = frozenset({
       SourceType.OS_PROCESS_PROBE,
       SourceType.FILESYSTEM_PROBE,
       ...
   })
   
   def is_admissible(cls, source: SourceType, ...) -> bool:
       return source in cls.ADMISSIBLE_SOURCES
   ```

3. Update all callers to pass `SourceType` enum values instead of strings.

4. Update `PROVENANCE_WEIGHTS` in `beliefs.py` to use `SourceType` keys.

**Completion:** All source parameters are `SourceType` enum values. No string matching.

---

## Phase 2: Required Observation Type

**Problem:** `BeliefEngine.ingest()` defaults `observation_type="direct"`. A caller that forgets to specify it silently gets direct evidence.

**Solution:** Make `observation_type` required (no default).

### Changes

1. Create `app/cognition/observation_types.py`:
   ```python
   class ObservationType(str, Enum):
       DIRECT = "direct"              # Environmental probe
       ENVIRONMENTAL = "environmental" # System topology
       INFERRED = "inferred"          # Derived from other observations
       SELF_REPORTED = "self_reported" # Tool output, LLM, execution trace
   ```

2. Update `BeliefEngine.ingest()` signature:
   ```python
   def ingest(self, ..., observation_type: ObservationType) -> RevisionResult:
       # No default — caller must explicitly classify
   ```

3. Update `WorldIngestor.ingest()` to require `observation_type`.

4. Update all callers (runtime, reasoning_loop, environment_grounding) to pass explicit `ObservationType`.

5. Update `Evidence` dataclass to use `ObservationType` enum.

**Completion:** No default `observation_type`. Every evidence submission explicitly classified.

---

## Phase 3: Admissible Evidence Type

**Problem:** `Evidence` dataclass doesn't carry admissibility. An `Evidence` instance can exist that looks legitimate but never passed the gate.

**Solution:** Split into `Evidence` (raw) and `AdmissibleEvidence` (gate-checked). Only `AdmissibleEvidence` enters `BeliefStore`.

### Changes

1. Update `Evidence` dataclass:
   ```python
   @dataclass
   class Evidence:
       source: SourceType
       value: Any
       confidence: float
       observed_at: str
       evidence_id: str
       observation_id: Optional[str]
       observation_type: ObservationType
   ```

2. Create `AdmissibleEvidence`:
   ```python
   @dataclass
   class AdmissibleEvidence(Evidence):
       admissible: Literal[True] = True
       # Only constructible via BeliefEngine.admit()
   ```

3. Update `BeliefStore.observe()` signature:
   ```python
   def observe(self, ..., evidence: AdmissibleEvidence) -> Belief:
       # Only accepts gate-checked evidence
   ```

4. Update `BeliefEngine.ingest()`:
   ```python
   def ingest(self, ...) -> RevisionResult:
       evidence = Evidence(source=source, ...)
       if self.is_admissible(source, observation_type, confidence):
           admissible = AdmissibleEvidence(**asdict(evidence))
           belief = self.beliefs.observe(..., evidence=admissible)
       ...
   ```

5. Update `BeliefStore._save_to_db()` and `_load_from_db()` to persist `observation_type`.

**Completion:** Type system enforces that only gate-checked evidence enters `BeliefStore`.

---

## Phase 4: Verified Reflection

**Problem:** `ReflectionEngine.reflect_on_task_execution()` takes a raw string and stores LLM output with `confidence=0.95`.

**Solution:** Accept `GoalVerificationResult`, derive confidence from verification quality.

### Changes

1. Update `ReflectionEngine.reflect_on_task_execution()`:
   ```python
   def reflect_on_task_execution(
       cls,
       task_title: str,
       task_goal: str,
       verification_result: GoalVerificationResult,
       user_feedback: Optional[str] = None
   ) -> Dict[str, Any]:
       # Build structured context from verified outcome
       verified = verification_result.verified_success
       met = len(verification_result.met_conditions)
       failed = len(verification_result.failed_conditions)
       evidence_quality = verification_result.evidence_quality  # new field
       
       # Derive confidence from verification quality
       if verified and evidence_quality >= 0.8:
           confidence = 0.9
       elif verified:
           confidence = 0.7
       elif failed:
           confidence = 0.5
       else:
           confidence = 0.3
       
       # Store with derived confidence
       mem_id = db.create_memory({
           "content": mem_content,
           "category": "task_reflection",
           "source": "self_reflection_engine",
           "confidence": confidence  # derived, not hardcoded
       })
   ```

2. Add `evidence_quality` field to `GoalVerificationResult`:
   ```python
   @dataclass
   class GoalVerificationResult:
       ...
       evidence_quality: float = 0.0  # 0.0-1.0, derived from evidence admissibility/confidence
   ```

3. Update `GoalVerifier.verify_goal_achievement()` to compute `evidence_quality` from the observations used.

4. Update `MemoryLearner.process_outcome_reflection()` to pass `verification_result` directly to `ReflectionEngine`.

5. Remove the legacy `outcome_summary: str` parameter from `ReflectionEngine`.

**Completion:** Reflection confidence derived from verification quality, not hardcoded.

---

## Execution Order

1. **Phase 1** (Canonical Sources) — foundation for all others
2. **Phase 2** (Required Observation Type) — builds on Phase 1
3. **Phase 3** (Admissible Evidence Type) — builds on Phases 1+2
4. **Phase 4** (Verified Reflection) — independent, can run in parallel with Phase 3

Each phase is independently testable and committable. No phase breaks existing tests if done incrementally.

## Estimated Impact

| Phase | Files Changed | Risk | Value |
|-------|--------------|------|-------|
| 1 | ~15 | Low | Eliminates substring false-positives |
| 2 | ~10 | Low | Eliminates silent default assumptions |
| 3 | ~8 | Medium | Type-level provenance enforcement |
| 4 | ~5 | Low | Reflection confidence grounded in evidence |

## Success Criteria

After all phases:
- No string source matching anywhere in the belief system
- No default `observation_type` — every submission explicitly classified
- `BeliefStore.observe()` only accepts `AdmissibleEvidence` — type-enforced
- Reflection confidence derived from `GoalVerificationResult.evidence_quality`
- All 616+ existing tests still pass
- New tests verify type-level enforcement
