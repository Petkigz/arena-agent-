"""
Phase 3: Transfer Learning Tests.

3A: Skill Abstraction — success in one search transfers to other searches
3B: Analogical Reasoning — structurally similar tasks trigger relevant memory
3C: Planning Patterns — reusable action sequences across domains
"""

import pytest
from app.cognition.skill_classifier import SkillClassifier, SKILL_CATEGORIES
from app.cognition.analogical_memory import AnalogicalMemory, TaskSignature
from app.cognition.planning_patterns import PlanningPatternStore
from app.cognition.strategy_outcomes import StrategyOutcomeStore
from app.cognition.counterfactual_simulator import CounterfactualSimulator


# ── 3A: Skill Abstraction ────────────────────────────────────────────


class TestSkillClassifier:

    def test_classifies_known_actions(self):
        sc = SkillClassifier()
        assert sc.classify("search_files") == "search"
        assert sc.classify("web_search") == "search"
        assert sc.classify("open_application") == "execute"
        assert sc.classify("screen_capture") == "create"
        assert sc.classify("diagnostic") == "analyze"
        assert sc.classify("formulate_answer") == "communicate"

    def test_unknown_action_defaults_to_execute(self):
        sc = SkillClassifier()
        assert sc.classify("custom_tool_xyz") == "execute"

    def test_same_skill_detection(self):
        sc = SkillClassifier()
        assert sc.same_skill("search_files", "web_search") is True
        assert sc.same_skill("search_files", "open_application") is False

    def test_skill_siblings(self):
        sc = SkillClassifier()
        siblings = sc.skill_siblings("search_files")
        assert "web_search" in siblings
        assert "open_application" not in siblings

    def test_transfer_weight_same_action(self):
        sc = SkillClassifier()
        assert sc.transfer_weight("search_files", "search_files") == 1.0

    def test_transfer_weight_same_skill(self):
        sc = SkillClassifier()
        w = sc.transfer_weight("search_files", "web_search")
        assert w == 0.3  # Same skill = moderate transfer

    def test_transfer_weight_different_skill(self):
        sc = SkillClassifier()
        assert sc.transfer_weight("search_files", "open_application") == 0.0

    def test_transfer_adjustment_boosts_from_sibling_success(self):
        sc = SkillClassifier()
        store = StrategyOutcomeStore()
        # search_files succeeded 5 times
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)

        # web_search (same skill) should get a boost
        adj = sc.transfer_adjustment("web_search", store, "search_intent")
        assert adj > 1.0, f"Expected boost from sibling success, got {adj}"

    def test_transfer_adjustment_penalizes_from_sibling_failure(self):
        sc = SkillClassifier()
        store = StrategyOutcomeStore()
        # search_files failed 5 times
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", False, 100.0, 0.8)

        adj = sc.transfer_adjustment("web_search", store, "search_intent")
        assert adj < 1.0, f"Expected penalty from sibling failure, got {adj}"

    def test_transfer_adjustment_no_effect_different_skill(self):
        sc = SkillClassifier()
        store = StrategyOutcomeStore()
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)

        # open_application (different skill) should not be affected
        adj = sc.transfer_adjustment("open_application", store, "search_intent")
        assert adj == 1.0

    def test_register_custom_skill(self):
        sc = SkillClassifier()
        sc.register_skill("my_custom_search", "search")
        assert sc.classify("my_custom_search") == "search"
        assert sc.same_skill("my_custom_search", "search_files") is True

    def test_all_skills_groups(self):
        sc = SkillClassifier()
        groups = sc.all_skills()
        assert "search" in groups
        assert "execute" in groups
        assert "search_files" in groups["search"]


# ── 3A: Skill Transfer in Simulation ─────────────────────────────────


class TestSkillTransferSimulation:

    def test_skill_sibling_success_boosts_simulation(self, tmp_path):
        store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        sc = SkillClassifier()

        # search_files succeeded many times
        for _ in range(5):
            store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)

        candidates = [
            {"name": "Search Files", "action_type": "search_files", "payload": {}},
            {"name": "Web Search", "action_type": "web_search", "payload": {}},
        ]
        result = CounterfactualSimulator.simulate_competing_branches(
            "Find report", candidates,
            goal_type="search_intent",
            outcome_store=store,
            skill_classifier=sc
        )

        # web_search should benefit from search_files' success
        web_branch = next(b for b in result.competing_branches if b.hypothetical_action == "web_search")
        assert web_branch.history_adjustment > 1.0 or web_branch.utility_score > 0.5


# ── 3B: Analogical Reasoning ─────────────────────────────────────────


class TestAnalogicalMemory:

    def test_record_task_signature(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        sig = am.record_task(
            intent_type="search_intent",
            target_domain="filesystem",
            entity_types=["file"],
            action_type="search_files",
            success=True,
            outcome="achieved",
            goal_text="Find report.pdf"
        )
        assert sig.intent_type == "search_intent"
        assert sig.success is True
        assert am.total_signatures() == 1

    def test_find_analogies_same_structure(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find report.pdf")
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find invoice.docx")
        am.record_task("action_intent", "desktop_os", ["process"], "open_application",
                        True, "achieved", "Open Chrome")

        matches = am.find_analogies("search_intent", "filesystem", ["file"])
        assert len(matches) >= 2
        assert all(m.past_task.intent_type == "search_intent" for m in matches)

    def test_analogy_similarity_scoring(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        # Same intent, same domain, same entities → high similarity
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find report")
        # Same intent, different domain → lower similarity
        am.record_task("search_intent", "web", ["url"], "web_search",
                        True, "achieved", "Search web")
        # Different intent → lowest similarity
        am.record_task("action_intent", "desktop_os", ["process"], "open_application",
                        True, "achieved", "Open app")

        # Use low threshold to get all matches for comparison
        matches = am.find_analogies("search_intent", "filesystem", ["file"],
                                     min_similarity=0.1)
        assert len(matches) >= 2
        # First match should be the most similar (same everything)
        assert matches[0].similarity >= matches[-1].similarity

    def test_what_worked_for_returns_best_strategy(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find A")
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find B")
        am.record_task("search_intent", "filesystem", ["file"], "web_search",
                        False, "failed", "Find C")

        result = am.what_worked_for("search_intent", "filesystem")
        assert result is not None
        assert result["action_type"] == "search_files"
        assert result["times_succeeded"] == 2

    def test_what_failed_for_returns_failures(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        am.record_task("action_intent", "desktop_os", ["process"], "open_application",
                        False, "failed", "Open broken app")
        am.record_task("action_intent", "desktop_os", ["process"], "open_application",
                        False, "failed", "Open another broken app")

        failures = am.what_failed_for("action_intent", "desktop_os")
        assert len(failures) >= 1
        assert failures[0]["action_type"] == "open_application"
        assert failures[0]["times_failed"] == 2

    def test_no_analogies_for_novel_task(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        matches = am.find_analogies("novel_intent", "novel_domain", ["novel_entity"])
        assert len(matches) == 0

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "analogies.db")
        am1 = AnalogicalMemory(db_path=db_path)
        am1.record_task("search_intent", "filesystem", ["file"], "search_files",
                         True, "achieved", "Find report")

        am2 = AnalogicalMemory(db_path=db_path)
        assert am2.total_signatures() == 1

    def test_insight_generation(self, tmp_path):
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        am.record_task("search_intent", "filesystem", ["file"], "search_files",
                        True, "achieved", "Find report")

        matches = am.find_analogies("search_intent", "filesystem", ["file"])
        assert len(matches) >= 1
        assert "succeeded" in matches[0].insight.lower()
        assert "search_files" in matches[0].insight


# ── 3B: TaskSignature Similarity ─────────────────────────────────────


class TestTaskSignatureSimilarity:

    def test_identical_signatures_max_similarity(self):
        a = TaskSignature("1", "search_intent", "filesystem", ("file",), "search_files", True, 1, "achieved", "Find A")
        b = TaskSignature("2", "search_intent", "filesystem", ("file",), "web_search", True, 1, "achieved", "Find B")
        sim = a.similarity_to(b)
        assert sim >= 0.8  # Very similar (same intent, domain, entities, outcome)

    def test_different_intent_lower_similarity(self):
        a = TaskSignature("1", "search_intent", "filesystem", ("file",), "search_files", True, 1, "achieved", "")
        b = TaskSignature("2", "action_intent", "desktop_os", ("process",), "open_app", True, 1, "achieved", "")
        sim = a.similarity_to(b)
        assert sim < 0.5

    def test_structural_key_ignores_specifics(self):
        a = TaskSignature("1", "search_intent", "filesystem", ("file",), "search_files", True, 1, "achieved", "Find A")
        b = TaskSignature("2", "search_intent", "filesystem", ("file",), "web_search", True, 1, "achieved", "Find B")
        assert a.structural_key() == b.structural_key()


# ── 3C: Planning Patterns ────────────────────────────────────────────


class TestPlanningPatterns:

    def test_record_successful_sequence(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        pattern = store.record_sequence(
            intent_type="search_intent",
            action_sequence=["search_files"],
            success=True,
            successful_step=0
        )
        assert pattern.success is True
        assert pattern.action_sequence == ("search_files",)
        assert store.total_patterns() == 1

    def test_record_multi_step_sequence(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        pattern = store.record_sequence(
            intent_type="search_intent",
            action_sequence=["search_files", "web_search"],
            success=True,
            successful_step=1  # web_search was the one that worked
        )
        assert pattern.action_sequence == ("search_files", "web_search")
        assert pattern.successful_step == 1

    def test_repeated_pattern_updates_statistics(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["search_files"], False, -1)

        assert store.total_patterns() == 1  # Same pattern, updated
        patterns = store.successful_patterns("search_intent")
        assert len(patterns) == 1
        assert patterns[0].times_used == 3
        assert abs(patterns[0].success_rate - 2/3) < 0.01

    def test_suggest_patterns_for_intent(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["web_search"], True, 0)

        suggestions = store.suggest_patterns("search_intent")
        assert len(suggestions) >= 1
        # search_files pattern should rank higher (used more)
        assert suggestions[0].pattern.action_sequence == ("search_files",)

    def test_suggest_patterns_prefers_matching_first_action(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["web_search"], True, 0)

        suggestions = store.suggest_patterns("search_intent", first_action="search_files")
        # search_files should be boosted for matching first action
        assert suggestions[0].pattern.action_sequence == ("search_files",)

    def test_cross_domain_pattern_transfer(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        # Pattern worked for search_intent
        store.record_sequence("search_intent", ["search_files", "web_search"], True, 1)
        store.record_sequence("search_intent", ["search_files", "web_search"], True, 1)

        # Suggest for action_intent (cross-domain)
        cross = store.cross_domain_patterns("search_intent", "action_intent")
        assert len(cross) >= 1
        assert "Cross-domain" in cross[0].reason

    def test_cross_domain_skips_failed_in_target(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        store.record_sequence("search_intent", ["search_files"], True, 0)
        store.record_sequence("search_intent", ["search_files"], True, 0)
        # Same pattern failed in target
        store.record_sequence("action_intent", ["search_files"], False, -1)

        cross = store.cross_domain_patterns("search_intent", "action_intent")
        # Should not suggest pattern that already failed in target
        assert len(cross) == 0

    def test_only_successful_patterns_suggested(self, tmp_path):
        store = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))
        store.record_sequence("search_intent", ["search_files"], False, -1)
        store.record_sequence("search_intent", ["web_search"], True, 0)

        suggestions = store.suggest_patterns("search_intent")
        # Only successful patterns should be suggested
        assert all(s.pattern.success for s in suggestions)

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "patterns.db")
        store1 = PlanningPatternStore(db_path=db_path)
        store1.record_sequence("search_intent", ["search_files"], True, 0)
        store1.record_sequence("search_intent", ["search_files"], True, 0)

        store2 = PlanningPatternStore(db_path=db_path)
        assert store2.total_patterns() == 1
        patterns = store2.successful_patterns("search_intent")
        assert patterns[0].times_used == 2


# ── Phase 3 Integration ──────────────────────────────────────────────


class TestPhase3Integration:

    def test_full_transfer_learning_pipeline(self, tmp_path):
        """
        End-to-end: Record outcomes → classify skills → find analogies →
        suggest patterns → influence simulation.
        """
        outcome_store = StrategyOutcomeStore(db_path=str(tmp_path / "outcomes.db"))
        sc = SkillClassifier()
        am = AnalogicalMemory(db_path=str(tmp_path / "analogies.db"))
        pp = PlanningPatternStore(db_path=str(tmp_path / "patterns.db"))

        # Simulate history: search_files succeeds, web_search is untested
        for _ in range(5):
            outcome_store.record_outcome("search_intent", "search_files", True, 100.0, 0.1)
            am.record_task("search_intent", "filesystem", ["file"], "search_files",
                           True, "achieved", "Find report")
            pp.record_sequence("search_intent", ["search_files"], True, 0)

        # Now simulate a new search task
        candidates = [
            {"name": "Search Files", "action_type": "search_files", "payload": {}},
            {"name": "Web Search", "action_type": "web_search", "payload": {}},
        ]

        # web_search should benefit from skill transfer
        result = CounterfactualSimulator.simulate_competing_branches(
            "Find document", candidates,
            goal_type="search_intent",
            outcome_store=outcome_store,
            skill_classifier=sc
        )

        # Check analogies exist
        analogies = am.find_analogies("search_intent", "filesystem", ["file"])
        assert len(analogies) >= 1

        # Check patterns exist
        suggestions = pp.suggest_patterns("search_intent")
        assert len(suggestions) >= 1

        # Both branches should have non-zero utility
        for branch in result.competing_branches:
            assert branch.utility_score > 0
