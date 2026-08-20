"""
Phase 5: Meta-Cognition Tests.

5A: Self-Model — capability assessment, model routing, strengths/weaknesses
5B: Confidence Calibration — binned calibration, correction factors, ECE
5C: Resource Allocation — complexity classification, bounded exploration, stats
"""

import pytest
from app.cognition.self_model import SelfModel, CapabilityAssessment, SelfReport
from app.cognition.confidence_calibrator import ConfidenceCalibrator, CalibrationReport, NUM_BINS
from app.cognition.resource_allocator import (
    ResourceAllocator, TaskComplexity, ResourceAllocation, RESOURCE_BUDGETS
)
from app.cognition.strategy_outcomes import StrategyOutcomeStore


# ── 5A: Self-Model ───────────────────────────────────────────────────


class TestSelfModel:

    def _make_outcome_store_with_data(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        # search_files: 8 successes, 2 failures
        for _ in range(8):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)
        for _ in range(2):
            store.record_outcome("search_intent", "search_files", False, 200.0, 0.8)
        # open_application: 2 successes, 8 failures
        for _ in range(2):
            store.record_outcome("action_intent", "open_application", True, 150.0, 0.2)
        for _ in range(8):
            store.record_outcome("action_intent", "open_application", False, 300.0, 0.7)
        return store

    def test_assess_capability_strong(self, tmp_path):
        store = self._make_outcome_store_with_data(tmp_path)
        model = SelfModel(outcome_store=store)

        assessment = model.assess_capability("search_files", "search_intent")
        assert assessment is not None
        assert assessment.success_rate == 0.8
        assert assessment.is_strong is True
        assert assessment.is_weak is False
        assert assessment.proficiency_label in ("proficient", "expert")

    def test_assess_capability_weak(self, tmp_path):
        store = self._make_outcome_store_with_data(tmp_path)
        model = SelfModel(outcome_store=store)

        assessment = model.assess_capability("open_application", "action_intent")
        assert assessment is not None
        assert assessment.success_rate == 0.2
        assert assessment.is_weak is True
        assert assessment.is_strong is False
        assert assessment.proficiency_label == "struggling"

    def test_what_am_i_good_at(self, tmp_path):
        store = self._make_outcome_store_with_data(tmp_path)
        model = SelfModel(outcome_store=store)

        good = model.what_am_i_good_at()
        assert len(good) >= 1
        assert good[0].action_type == "search_files"

    def test_what_am_i_bad_at(self, tmp_path):
        store = self._make_outcome_store_with_data(tmp_path)
        model = SelfModel(outcome_store=store)

        bad = model.what_am_i_bad_at()
        assert len(bad) >= 1
        assert bad[0].action_type == "open_application"

    def test_generate_report(self, tmp_path):
        store = self._make_outcome_store_with_data(tmp_path)
        model = SelfModel(outcome_store=store)

        report = model.generate_report()
        assert isinstance(report, SelfReport)
        assert report.total_capabilities >= 2
        assert report.total_tasks_completed == 20
        assert 0.0 <= report.overall_success_rate <= 1.0
        assert len(report.model_routing_suggestions) >= 2

    def test_model_routing_strong_to_fast(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)

        model = SelfModel(outcome_store=store)
        model.assess_capability("search_files", "search_intent")

        assert model.suggest_model("search_files") == "fast"

    def test_model_routing_weak_to_reasoning(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(5):
            store.record_outcome("action_intent", "open_application", False, 300.0, 0.8)

        model = SelfModel(outcome_store=store)
        model.assess_capability("open_application", "action_intent")

        assert model.suggest_model("open_application") == "reasoning"

    def test_model_routing_unknown_to_reasoning(self):
        model = SelfModel()
        assert model.suggest_model("never_seen_before") == "reasoning"

    def test_explicit_model_preference(self):
        model = SelfModel()
        model.set_model_preference("custom_task", "fast")
        assert model.suggest_model("custom_task") == "fast"

    def test_proficiency_labels(self):
        # Expert: >= 90% with 3+ attempts
        a = CapabilityAssessment("a", "d", 10, 10, 1.0, 100, 0.1, 1.0)
        assert a.proficiency_label == "expert"

        # Untested: < 3 attempts
        b = CapabilityAssessment("b", "d", 2, 1, 0.5, 100, 0.5, 0.2)
        assert b.proficiency_label == "untested"


# ── 5B: Confidence Calibration ───────────────────────────────────────


class TestConfidenceCalibrator:

    def test_record_prediction_outcome(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        record = cal.record("search_files", 0.8, True, 0.2, "search_intent")
        assert record.predicted_confidence == 0.8
        assert record.actual_outcome is True
        assert cal.total_records() == 1

    def test_compute_bins(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # Record predictions in the 0.8-0.9 bin
        for _ in range(5):
            cal.record("test", 0.85, True)
        for _ in range(5):
            cal.record("test", 0.85, False)

        bins = cal.compute_bins()
        assert len(bins) == NUM_BINS
        # Bin 8 (0.8-0.9) should have 10 predictions, 50% success
        bin_8 = bins[8]
        assert bin_8.total_predictions == 10
        assert bin_8.actual_rate == 0.5

    def test_calibration_detects_overconfidence(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # System predicts 0.9 but only succeeds 50% of the time → overconfident
        for _ in range(10):
            cal.record("test", 0.95, True)
        for _ in range(10):
            cal.record("test", 0.95, False)

        report = cal.generate_report()
        bin_9 = report.bins[9]
        assert bin_9.actual_rate == 0.5
        assert bin_9.calibration_error > 0.3  # Big gap between 0.95 predicted and 0.5 actual

    def test_correction_factor_reduces_overconfidence(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # Overconfident: predicts 0.9 but succeeds 50%
        for _ in range(5):
            cal.record("test", 0.95, True)
        for _ in range(5):
            cal.record("test", 0.95, False)

        calibrated = cal.calibrate("test", 0.95)
        assert calibrated < 0.95  # Should be reduced

    def test_correction_factor_preserves_well_calibrated(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # Well-calibrated: predicts 0.8 and succeeds 80%
        for _ in range(8):
            cal.record("test", 0.85, True)
        for _ in range(2):
            cal.record("test", 0.85, False)

        calibrated = cal.calibrate("test", 0.85)
        # Should stay close to original
        assert abs(calibrated - 0.85) < 0.15

    def test_calibration_with_insufficient_data(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        cal.record("test", 0.8, True)

        # Only 1 record — below MIN_RECORDS_PER_BIN
        calibrated = cal.calibrate("test", 0.8)
        assert calibrated == 0.8  # No correction applied

    def test_ece_computation(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # Perfect calibration: predicted 0.5, succeeds 50%
        for _ in range(5):
            cal.record("test", 0.55, True)
        for _ in range(5):
            cal.record("test", 0.55, False)

        report = cal.generate_report()
        assert report.ece < 0.15  # Should be well-calibrated

    def test_report_is_calibrated_flag(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        # Perfectly calibrated
        for _ in range(10):
            cal.record("test", 0.55, True)
        for _ in range(10):
            cal.record("test", 0.55, False)

        report = cal.generate_report()
        assert report.is_calibrated is True

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "cal.db")
        cal1 = ConfidenceCalibrator(db_path=db_path)
        for _ in range(5):
            cal1.record("test", 0.8, True)

        cal2 = ConfidenceCalibrator(db_path=db_path)
        assert cal2.total_records() == 5

    def test_clamped_confidence(self, tmp_path):
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        record = cal.record("test", 1.5, True)  # Over 1.0
        assert record.predicted_confidence == 1.0


# ── 5C: Strategic Resource Allocation ────────────────────────────────


class TestResourceAllocator:

    def test_trivial_task_gets_fast_model(self):
        allocator = ResourceAllocator()
        alloc = allocator.allocate(
            action_type="search_files",
            candidates=[{"name": "Search", "action_type": "search_files"}]
        )
        assert alloc.complexity == TaskComplexity.TRIVIAL
        assert alloc.model == "fast"
        assert alloc.max_reasoning_cycles == 1

    def test_complex_task_gets_reasoning_model(self):
        from app.cognition.goal_interpreter import SemanticGoalRepresentation
        goal_rep = SemanticGoalRepresentation(
            user_query="Complex task",
            primary_intent_type="action_intent",
            target_domain="desktop_os",
            goal="Complex multi-step task",
            desired_outcome="Everything working",
            entities=["a", "b", "c", "d"],
            constraints=[], assumptions=[],
            unknowns=["unknown1", "unknown2", "unknown3"],
            preconditions=[],
            success_conditions=["condition1", "condition2"],
            failure_conditions=[],
            required_capabilities=["cap1", "cap2", "cap3"],
            risk_factors=[]
        )
        allocator = ResourceAllocator()
        alloc = allocator.allocate(
            goal_rep=goal_rep,
            action_type="complex_task",
            candidates=[{"name": f"C{i}"} for i in range(5)]
        )
        assert alloc.complexity in (TaskComplexity.COMPLEX, TaskComplexity.HARD)
        assert alloc.model == "reasoning"

    def test_override_complexity(self):
        allocator = ResourceAllocator()
        alloc = allocator.allocate(
            override_complexity=TaskComplexity.HARD
        )
        assert alloc.complexity == TaskComplexity.HARD
        assert alloc.model == "reasoning"
        assert "overridden" in alloc.classification_reason

    def test_resource_budgets_exist_for_all_complexities(self):
        for complexity in TaskComplexity:
            assert complexity in RESOURCE_BUDGETS
            budget = RESOURCE_BUDGETS[complexity]
            assert "model" in budget
            assert "max_reasoning_cycles" in budget
            assert "timeout_ms" in budget

    def test_higher_complexity_gets_more_resources(self):
        allocator = ResourceAllocator()
        trivial = allocator.allocate(override_complexity=TaskComplexity.TRIVIAL)
        complex_ = allocator.allocate(override_complexity=TaskComplexity.COMPLEX)
        hard = allocator.allocate(override_complexity=TaskComplexity.HARD)

        assert trivial.max_reasoning_cycles < complex_.max_reasoning_cycles
        assert complex_.max_reasoning_cycles < hard.max_reasoning_cycles
        assert trivial.timeout_ms < complex_.timeout_ms
        assert complex_.timeout_ms < hard.timeout_ms

    def test_bounded_exploration_stops_at_max_cycles(self):
        allocator = ResourceAllocator()
        assert allocator.should_stop_investigating(
            cycles_used=5, max_cycles=5, current_confidence=0.3
        ) is True

    def test_bounded_exploration_stops_at_high_confidence(self):
        allocator = ResourceAllocator()
        assert allocator.should_stop_investigating(
            cycles_used=1, max_cycles=5, current_confidence=0.9
        ) is True

    def test_bounded_exploration_continues_when_uncertain(self):
        allocator = ResourceAllocator()
        assert allocator.should_stop_investigating(
            cycles_used=1, max_cycles=5, current_confidence=0.3
        ) is False

    def test_record_outcome_and_stats(self):
        allocator = ResourceAllocator()
        alloc = allocator.allocate(override_complexity=TaskComplexity.SIMPLE)

        allocator.record_outcome(alloc, success=True, latency_ms=500.0)
        allocator.record_outcome(alloc, success=True, latency_ms=600.0)
        allocator.record_outcome(alloc, success=False, latency_ms=1000.0)

        stats = allocator.get_stats()
        assert stats.total_allocated == 3
        assert stats.by_complexity.get("simple", 0) == 3

    def test_efficiency_score(self):
        allocator = ResourceAllocator()
        alloc = allocator.allocate(override_complexity=TaskComplexity.SIMPLE)

        # All succeed quickly
        for _ in range(5):
            allocator.record_outcome(alloc, success=True, latency_ms=200.0)

        stats = allocator.get_stats()
        assert stats.efficiency_score > 0.5  # High efficiency

    def test_complexity_classification_with_history(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(10):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.05)

        allocator = ResourceAllocator(outcome_store=store)
        complexity, reason = allocator.classify_complexity(
            action_type="search_files",
            candidates=[{"name": "Search"}]
        )
        # Known, high-success, single candidate → trivial or simple
        assert complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE)
        assert "historical" in reason.lower()


# ── Phase 5 Integration ──────────────────────────────────────────────


class TestPhase5Integration:

    def test_self_model_feeds_resource_allocator(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)

        model = SelfModel(outcome_store=store)
        model.assess_capability("search_files", "search_intent")

        allocator = ResourceAllocator(self_model=model, outcome_store=store)
        alloc = allocator.allocate(action_type="search_files", candidates=[{"name": "Search"}])

        # Strong capability → fast model
        assert alloc.model == "fast"

    def test_calibrator_integrates_with_self_model(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))

        for _ in range(8):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)
            cal.record("search_files", 0.8, True)
        for _ in range(2):
            store.record_outcome("search_intent", "search_files", False, 200.0, 0.8)
            cal.record("search_files", 0.8, False)

        model = SelfModel(outcome_store=store)
        report = model.generate_report()
        cal_report = cal.generate_report()

        # Both should have data
        assert report.total_capabilities >= 1
        assert cal_report.total_records == 10

    def test_full_metacognition_pipeline(self, tmp_path):
        """Self-Model + Calibration + Resource Allocation working together."""
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        cal = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))

        # Build history
        for _ in range(10):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)
            cal.record("search_files", 0.85, True)
        for _ in range(2):
            store.record_outcome("search_intent", "search_files", False, 300.0, 0.7)
            cal.record("search_files", 0.85, False)

        # Self-model assesses
        model = SelfModel(outcome_store=store)
        good = model.what_am_i_good_at()
        assert any(a.action_type == "search_files" for a in good)

        # Calibrator adjusts confidence
        calibrated = cal.calibrate("search_files", 0.85)
        assert 0.0 <= calibrated <= 1.0

        # Allocator uses self-model for routing
        allocator = ResourceAllocator(self_model=model, outcome_store=store)
        alloc = allocator.allocate(action_type="search_files", candidates=[{"name": "Search"}])
        assert alloc.model in ("fast", "reasoning")
