"""
Phase 1C: Structured Lesson Extraction & Behavior Change Tests.

Verifies that:
- Failure types are deterministically classified from verification results
- Structured lessons are extracted without LLM calls
- Lessons are queryable by task_type, action_type, failure_type
- "what_went_wrong" answers why a strategy failed before
- Lessons influence CounterfactualSimulator utility scores
- Repeated same-type failures produce stronger penalties
- Success lessons are recorded (not just failures)
- Lessons persist across reloads
"""

import pytest
from app.cognition.structured_lessons import LessonStore, StructuredLesson, FAILURE_TYPES
from app.cognition.counterfactual_simulator import CounterfactualSimulator


# ── Failure Type Classification ────────────────────────────────────────


class TestFailureClassification:

    def test_blocked_state_classifies_as_gate_blocked(self):
        assert LessonStore.classify_failure_type("blocked", [], "") == "gate_blocked"

    def test_waiting_for_evidence_classifies_as_evidence_missing(self):
        assert LessonStore.classify_failure_type("waiting_for_evidence", [], "") == "evidence_missing"

    def test_crash_in_reply_classifies_as_process_crashed(self):
        assert LessonStore.classify_failure_type(
            "failed", [], "Photoshop process crashed on startup"
        ) == "process_crashed"

    def test_not_found_in_reply_classifies_as_file_not_found(self):
        assert LessonStore.classify_failure_type(
            "failed", [], "Error: File not found in workspace"
        ) == "file_not_found"

    def test_permission_denied_classifies_correctly(self):
        assert LessonStore.classify_failure_type(
            "failed", [], "Permission denied when accessing /root"
        ) == "permission_denied"

    def test_device_offline_classifies_correctly(self):
        assert LessonStore.classify_failure_type(
            "failed", [], "Device offline, no devices connected"
        ) == "device_offline"

    def test_timeout_classifies_correctly(self):
        assert LessonStore.classify_failure_type(
            "failed", [], "Operation timed out after 30 seconds"
        ) == "timeout"

    def test_process_not_running_from_conditions(self):
        assert LessonStore.classify_failure_type(
            "failed",
            ["failed_condition: app_process_running = true"],
            ""
        ) == "process_not_running"

    def test_file_not_found_from_conditions(self):
        assert LessonStore.classify_failure_type(
            "failed",
            ["failed_condition: file_path_identified = true"],
            ""
        ) == "file_not_found"

    def test_unclassified_failure_returns_execution_error(self):
        result = LessonStore.classify_failure_type("failed", [], "Something went wrong")
        assert result == "execution_error"


# ── Lesson Extraction ────────────────────────────────────────────────


class TestLessonExtraction:

    def test_extract_failure_lesson(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        lesson = store.extract_lesson(
            task_type="action_intent",
            action_type="open_application",
            final_state="failed",
            verified_success=False,
            failed_conditions=["app_process_running = true"],
            reply_text="Process crashed on startup",
            goal_text="Open Photoshop",
            latency_ms=250.0,
            surprisal=0.7
        )

        assert lesson.outcome == "failed"
        assert lesson.failure_type == "process_crashed"
        assert lesson.root_cause == FAILURE_TYPES["process_crashed"]
        assert lesson.corrective_action != ""
        assert lesson.confidence > 0.5  # High surprisal → higher confidence
        assert store.total_lessons() == 1

    def test_extract_success_lesson(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        lesson = store.extract_lesson(
            task_type="action_intent",
            action_type="open_application",
            final_state="achieved",
            verified_success=True,
            failed_conditions=[],
            reply_text="Chrome is running.",
            goal_text="Open Chrome"
        )

        assert lesson.outcome == "success"
        assert lesson.failure_type == ""
        assert lesson.root_cause == ""
        assert lesson.corrective_action == ""

    def test_blocked_lesson_classified_correctly(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        lesson = store.extract_lesson(
            task_type="action_intent",
            action_type="run_command",
            final_state="blocked",
            verified_success=False,
            failed_conditions=["blocked by policy_gate"],
            reply_text="Action blocked by safety policy",
            goal_text="Run system script"
        )

        assert lesson.failure_type == "gate_blocked"
        assert "approval" in lesson.corrective_action.lower()


# ── Query Interface ──────────────────────────────────────────────────


class TestLessonQuerying:

    def _populate_store(self, store):
        """Add a mix of success and failure lessons."""
        store.extract_lesson("action_intent", "open_application", "failed", False,
                             ["app_process_running = true"], "Process crashed", "Open Photoshop")
        store.extract_lesson("action_intent", "open_application", "failed", False,
                             ["app_process_running = true"], "Process crashed again", "Open Photoshop")
        store.extract_lesson("action_intent", "open_application", "achieved", True,
                             [], "Running", "Open Chrome")
        store.extract_lesson("search_intent", "search_files", "failed", False,
                             ["file_path_identified = true"], "File not found", "Find report.pdf")
        store.extract_lesson("search_intent", "web_search", "achieved", True,
                             [], "Found results", "Find report online")

    def test_query_lessons_by_task_type(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        action_lessons = store.query_lessons(task_type="action_intent")
        assert len(action_lessons) == 3

    def test_query_lessons_by_action_type(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        open_lessons = store.query_lessons(action_type="open_application")
        assert len(open_lessons) == 3

    def test_query_failures_only(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        failures = store.query_failures("action_intent")
        assert len(failures) == 2
        assert all(f.outcome != "success" for f in failures)

    def test_query_failures_by_action(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        failures = store.query_failures("action_intent", "open_application")
        assert len(failures) == 2

    def test_what_went_wrong_returns_failure_context(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        result = store.what_went_wrong("action_intent", "open_application")
        assert result is not None
        assert result["failure_type"] == "process_crashed"
        assert result["times_failed"] == 2
        assert result["corrective_action"] != ""

    def test_what_went_wrong_returns_none_for_no_failures(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        store.extract_lesson("action_intent", "open_application", "achieved", True,
                             [], "Running", "Open Chrome")

        assert store.what_went_wrong("action_intent", "open_application") is None

    def test_corrective_suggestion(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        store.extract_lesson("search_intent", "search_files", "failed", False,
                             ["file_path_identified = true"], "File not found", "Find report.pdf")

        suggestion = store.corrective_suggestion("search_intent", "search_files")
        assert suggestion is not None
        assert "search" in suggestion.lower() or "expand" in suggestion.lower()

    def test_failure_summary(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        self._populate_store(store)

        summary = store.failure_summary()
        assert summary["total_failures"] == 3
        assert "process_crashed" in summary["by_failure_type"]
        assert summary["most_failing_action"] == "open_application"


# ── Lesson Influence on Strategy Selection ────────────────────────────


class TestLessonInfluence:

    def test_no_lessons_returns_neutral(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        assert store.lesson_influence("action_intent", "open_application") == 1.0

    def test_repeated_failures_penalize(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        for _ in range(4):
            store.extract_lesson("action_intent", "open_application", "failed", False,
                                 ["app_process_running = true"], "Process crashed", "Open app")

        influence = store.lesson_influence("action_intent", "open_application")
        assert influence < 1.0, f"Expected penalty, got {influence}"

    def test_same_type_failures_penalize_more(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        # All same failure type
        for _ in range(3):
            store.extract_lesson("action_intent", "open_application", "failed", False,
                                 [], "Process crashed", "Open app")

        influence_same = store.lesson_influence("action_intent", "open_application")

        store2 = LessonStore(db_path=str(tmp_path / "lessons2.db"))
        # Mixed failure types
        store2.extract_lesson("action_intent", "web_search", "failed", False,
                              [], "Process crashed", "Search")
        store2.extract_lesson("action_intent", "web_search", "failed", False,
                              [], "File not found", "Search")
        store2.extract_lesson("action_intent", "web_search", "failed", False,
                              [], "Timed out", "Search")

        influence_mixed = store2.lesson_influence("action_intent", "web_search")

        # Same-type failures should have stronger penalty
        assert influence_same <= influence_mixed

    def test_influence_clamped(self, tmp_path):
        store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        for _ in range(20):
            store.extract_lesson("action_intent", "open_application", "failed", False,
                                 [], "Crash", "Open app")

        influence = store.lesson_influence("action_intent", "open_application")
        assert 0.3 <= influence <= 1.0


# ── CounterfactualSimulator Integration ───────────────────────────────


class TestLessonInfluencedSimulation:

    def test_simulation_with_lesson_store(self, tmp_path):
        lesson_store = LessonStore(db_path=str(tmp_path / "lessons.db"))
        # Record failures for search_files
        for _ in range(4):
            lesson_store.extract_lesson("search_intent", "search_files", "failed", False,
                                        ["file_path_identified = true"], "File not found", "Find report")
        # Record successes for web_search
        for _ in range(4):
            lesson_store.extract_lesson("search_intent", "web_search", "achieved", True,
                                        [], "Found results", "Find report")

        candidates = [
            {"name": "Search Files", "action_type": "search_files", "payload": {"query": "report"}},
            {"name": "Web Search", "action_type": "web_search", "payload": {"query": "report"}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Find document report", candidates,
            goal_type="search_intent", lesson_store=lesson_store
        )

        # search_files should be penalized by lessons
        search_branch = next(b for b in result.competing_branches if b.hypothetical_action == "search_files")
        web_branch = next(b for b in result.competing_branches if b.hypothetical_action == "web_search")

        assert search_branch.history_adjustment < 1.0
        assert web_branch.history_adjustment >= 1.0  # No failure lessons → neutral or better

    def test_lesson_and_outcome_stores_combine(self, tmp_path):
        from app.cognition.strategy_outcomes import StrategyOutcomeStore

        outcome_store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        lesson_store = LessonStore(db_path=str(tmp_path / "lessons.db"))

        # Record failures in both stores
        for _ in range(3):
            outcome_store.record_outcome("action_intent", "open_application", False)
            lesson_store.extract_lesson("action_intent", "open_application", "failed", False,
                                        [], "Crashed", "Open app")

        candidates = [
            {"name": "Open App", "action_type": "open_application", "payload": {}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Open Chrome", candidates,
            goal_type="action_intent",
            outcome_store=outcome_store,
            lesson_store=lesson_store
        )

        # Combined adjustment should be stronger than either alone
        branch = result.competing_branches[0]
        assert branch.history_adjustment < 0.7  # Both penalties combined


# ── Persistence ───────────────────────────────────────────────────────


class TestLessonPersistence:

    def test_lessons_persist_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "lessons.db")
        store1 = LessonStore(db_path=db_path)
        store1.extract_lesson("action_intent", "open_application", "failed", False,
                              ["app_process_running"], "Crashed", "Open Photoshop", surprisal=0.8)
        store1.extract_lesson("search_intent", "search_files", "achieved", True,
                              [], "Found", "Find report.pdf")

        store2 = LessonStore(db_path=db_path)
        assert store2.total_lessons() == 2

        failures = store2.query_failures("action_intent")
        assert len(failures) == 1
        assert failures[0].failure_type == "process_crashed"

    def test_what_went_wrong_after_reload(self, tmp_path):
        db_path = str(tmp_path / "lessons.db")
        store1 = LessonStore(db_path=db_path)
        store1.extract_lesson("action_intent", "open_application", "failed", False,
                              [], "Process crashed on startup", "Open Photoshop")

        store2 = LessonStore(db_path=db_path)
        result = store2.what_went_wrong("action_intent", "open_application")
        assert result is not None
        assert result["failure_type"] == "process_crashed"
        assert result["times_failed"] == 1
