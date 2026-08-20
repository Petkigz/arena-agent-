"""
Phase 1B: Outcome-Influenced Strategy Selection Tests.

Verifies that:
- Task outcomes are recorded (goal_type, action_type, success, latency, surprisal)
- Historical success rates influence strategy selection
- Strategies with repeated failures are deprioritized (not deleted)
- Strategies with success are boosted
- Insufficient history has no influence (returns 1.0 adjustment)
- After 3 consecutive failures, strategy is strongly deprioritized
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.cognition.strategy_outcomes import StrategyOutcomeStore, StrategyOutcome, StrategyScore
from app.cognition.counterfactual_simulator import CounterfactualSimulator


# ── StrategyOutcomeStore ──────────────────────────────────────────────


class TestStrategyOutcomeStore:

    def test_record_outcome_stores_correctly(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        outcome = store.record_outcome(
            goal_type="action_intent",
            action_type="open_application",
            success=True,
            latency_ms=150.0,
            surprisal=0.1,
            goal_text="Open Photoshop"
        )
        assert outcome.success is True
        assert outcome.action_type == "open_application"
        assert outcome.goal_type == "action_intent"
        assert store.total_recorded() == 1

    def test_record_multiple_outcomes(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True, 100.0, 0.1)
        store.record_outcome("action_intent", "open_application", True, 120.0, 0.05)
        store.record_outcome("action_intent", "open_application", False, 200.0, 0.8)
        assert store.total_recorded() == 3

    def test_score_strategy_computes_success_rate(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True)
        store.record_outcome("action_intent", "open_application", True)
        store.record_outcome("action_intent", "open_application", False)

        score = store.score_strategy("action_intent", "open_application")
        assert score is not None
        assert score.total_attempts == 3
        assert score.successes == 2
        assert score.failures == 1
        assert abs(score.success_rate - 2/3) < 0.01

    def test_score_strategy_nonexistent_returns_none(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        assert store.score_strategy("nonexistent", "nonexistent") is None

    def test_consecutive_failures_tracked(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("search_intent", "search_files", True)
        store.record_outcome("search_intent", "search_files", False)
        store.record_outcome("search_intent", "search_files", False)
        store.record_outcome("search_intent", "search_files", False)

        score = store.score_strategy("search_intent", "search_files")
        assert score.consecutive_failures == 3

    def test_consecutive_failures_reset_by_success(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("search_intent", "search_files", False)
        store.record_outcome("search_intent", "search_files", False)
        store.record_outcome("search_intent", "search_files", True)  # resets streak

        score = store.score_strategy("search_intent", "search_files")
        assert score.consecutive_failures == 0

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "outcomes.db")
        store1 = StrategyOutcomeStore(db_path=db_path)
        store1.record_outcome("action_intent", "open_application", True, 100.0, 0.1)
        store1.record_outcome("action_intent", "open_application", False, 200.0, 0.5)

        store2 = StrategyOutcomeStore(db_path=db_path)
        assert store2.total_recorded() == 2
        score = store2.score_strategy("action_intent", "open_application")
        assert score.total_attempts == 2


# ── Adjustment Factor ─────────────────────────────────────────────────


class TestAdjustmentFactor:

    def test_no_history_returns_neutral(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        assert store.adjustment_factor("action_intent", "open_application") == 1.0

    def test_insufficient_history_returns_neutral(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True)
        # Only 1 attempt — below MIN_ATTEMPTS_FOR_INFLUENCE (2)
        assert store.adjustment_factor("action_intent", "open_application") == 1.0

    def test_high_success_rate_boosts(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(5):
            store.record_outcome("action_intent", "open_application", True)

        factor = store.adjustment_factor("action_intent", "open_application")
        assert factor > 1.0, f"Expected boost, got {factor}"

    def test_low_success_rate_penalizes(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True)
        for _ in range(4):
            store.record_outcome("action_intent", "open_application", False)

        factor = store.adjustment_factor("action_intent", "open_application")
        assert factor < 1.0, f"Expected penalty, got {factor}"

    def test_consecutive_failures_strong_penalty(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        # 5 consecutive failures
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", False)

        factor = store.adjustment_factor("search_intent", "search_files")
        assert factor < 0.5, f"Expected strong penalty for 5 consecutive failures, got {factor}"

    def test_adjustment_clamped_between_0_1_and_1_5(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        # All successes
        for _ in range(20):
            store.record_outcome("action_intent", "open_application", True)
        factor = store.adjustment_factor("action_intent", "open_application")
        assert 0.1 <= factor <= 1.5

        # All failures
        store2 = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes2.db"))
        for _ in range(20):
            store2.record_outcome("action_intent", "open_application", False)
        factor2 = store2.adjustment_factor("action_intent", "open_application")
        assert 0.1 <= factor2 <= 1.5


# ── CounterfactualSimulator Integration ───────────────────────────────


class TestCounterfactualWithOutcomes:

    def test_simulation_without_outcome_store_unchanged(self):
        """Without outcome store, behavior is identical to before."""
        candidates = [
            {"name": "Search Files", "action_type": "search_files", "payload": {"query": "report"}},
            {"name": "Web Search", "action_type": "web_search", "payload": {"query": "report"}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Find document report", candidates
        )
        # All branches should have history_adjustment = 1.0
        for branch in result.competing_branches:
            assert branch.history_adjustment == 1.0

    def test_failed_strategy_penalized_in_simulation(self, tmp_path):
        """Strategy with consecutive failures gets lower utility."""
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        # Record 4 consecutive failures for search_files on search_intent
        for _ in range(4):
            store.record_outcome("search_intent", "search_files", False)
        # Record successes for web_search on search_intent
        for _ in range(4):
            store.record_outcome("search_intent", "web_search", True)

        candidates = [
            {"name": "Search Files", "action_type": "search_files", "payload": {"query": "report"}},
            {"name": "Web Search", "action_type": "web_search", "payload": {"query": "report"}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Find document report", candidates,
            goal_type="search_intent", outcome_store=store
        )

        # search_files should be penalized, web_search should be boosted
        search_branch = next(b for b in result.competing_branches if b.hypothetical_action == "search_files")
        web_branch = next(b for b in result.competing_branches if b.hypothetical_action == "web_search")

        assert search_branch.history_adjustment < 1.0
        assert web_branch.history_adjustment > 1.0
        assert web_branch.utility_score > search_branch.utility_score

    def test_three_failures_deprioritize_strategy(self, tmp_path):
        """
        Completion criteria: After 3 failures of strategy A for task_type X,
        the system picks strategy B first.
        """
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        # Strategy A fails 3 times
        for _ in range(3):
            store.record_outcome("action_intent", "open_application", False)
        # Strategy B succeeds 3 times
        for _ in range(3):
            store.record_outcome("action_intent", "web_search", True)

        candidates = [
            {"name": "Open App", "action_type": "open_application", "payload": {"app_name": "chrome"}},
            {"name": "Web Search", "action_type": "web_search", "payload": {"query": "chrome"}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Open Chrome", candidates,
            goal_type="action_intent", outcome_store=store
        )

        # Strategy B (web_search) should win despite open_application normally having higher goal_fit
        assert result.winning_branch.hypothetical_action == "web_search"

    def test_failed_strategy_not_deleted(self, tmp_path):
        """
        Failed strategies remain available as fallbacks — they are deprioritized,
        not removed from the candidate list.
        """
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for _ in range(5):
            store.record_outcome("action_intent", "open_application", False)

        candidates = [
            {"name": "Open App", "action_type": "open_application", "payload": {}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Open Chrome", candidates,
            goal_type="action_intent", outcome_store=store
        )

        # Strategy still selected (it's the only option), just with reduced utility
        assert result.winning_branch.hypothetical_action == "open_application"
        assert result.winning_branch.history_adjustment < 1.0


# ── Strategy Scores Reporting ─────────────────────────────────────────


class TestStrategyScoresReporting:

    def test_all_scores_lists_recorded_strategies(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True)
        store.record_outcome("action_intent", "open_application", True)
        store.record_outcome("search_intent", "search_files", False)
        store.record_outcome("search_intent", "web_search", True)

        all_scores = store.all_scores()
        assert len(all_scores) == 3  # 3 unique (goal_type, action_type) pairs

    def test_all_scores_filtered_by_goal_type(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True)
        store.record_outcome("search_intent", "search_files", True)

        action_scores = store.all_scores(goal_type="action_intent")
        assert len(action_scores) == 1
        assert action_scores[0].goal_type == "action_intent"

    def test_recent_outcomes_returns_latest(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        for i in range(10):
            store.record_outcome("action_intent", "open_application", i % 2 == 0)

        recent = store.recent_outcomes("action_intent", "open_application", limit=3)
        assert len(recent) == 3

    def test_avg_latency_computed_correctly(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        store.record_outcome("action_intent", "open_application", True, latency_ms=100.0)
        store.record_outcome("action_intent", "open_application", True, latency_ms=200.0)
        store.record_outcome("action_intent", "open_application", True, latency_ms=300.0)

        score = store.score_strategy("action_intent", "open_application")
        assert abs(score.avg_latency_ms - 200.0) < 0.01
