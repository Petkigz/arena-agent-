"""Round 12 — coverage grind (owner order 3: "test it, grind until
coverage hits 80%").

Honest scope: these tests exercise REAL paths that shipped organs take
in production — the local fuzzy backend that answers when LM Studio is
down, the calibration math behind every semantic score, the Chooser's
evidence branches, the experiment spine's failure branches, and the
hardware-honesty note in training readiness. Every test asserts
behavior, not coverage; the missing-line map (coverage report
--show-missing) chose the targets.

Baseline before this file: semantic_matcher 62%, self_improvement_gate
73%, parked_goal_recheck 81%.
"""

import pytest

from app.cognition import semantic_matcher as sm
from app.mind import self_improvement_gate as gate


# ───────────────────────── fixtures ─────────────────────────

@pytest.fixture
def gr_db(monkeypatch, tmp_path):
    """Fresh temp DB, ledger backfill skipped (same shape as redteam/gate
    fixtures)."""
    import app.database as database_module
    from app.cognition import event_ledger as ledger
    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "grind.db"))
    database_module.db._init_db()
    monkeypatch.setattr(ledger, "_backfill_done", True)
    return database_module.db


@pytest.fixture
def sm_env(monkeypatch, tmp_path, gr_db):
    """semantic_matcher against the temp DB with every module cache
    cleared — order-independent."""
    monkeypatch.setenv("ARENA_EMBED_CACHE", "1")
    monkeypatch.setattr(sm, "_embed_model_cache", {})
    monkeypatch.setattr(sm, "_tool_embedding_cache", {})
    monkeypatch.setattr(sm, "_local_index_cache", {})
    monkeypatch.setattr(sm, "_last_embed_model", None)
    monkeypatch.setattr(sm, "_backend_state", {"current": None})
    # capture the REAL lru-cached function: tests may monkeypatch the
    # attribute with a plain lambda, and teardown must still clear the
    # real cache (monkeypatch undoes itself only AFTER this fixture)
    original_goal_cached = sm._embed_goal_cached
    original_goal_cached.cache_clear()
    yield sm
    original_goal_cached.cache_clear()


# ─────────────── semantic_matcher: calibration math ───────────────

class TestCalibration:
    def test_dead_zone_and_saturation_are_hard_edges(self):
        assert sm._calibrate(0.10) == 0.0   # below dead zone
        assert sm._calibrate(0.15) == 0.0   # at the edge
        assert sm._calibrate(0.60) == 1.0   # saturation
        assert sm._calibrate(0.95) == 1.0

    def test_between_edges_is_linear(self):
        # midpoint of (0.15, 0.60) is 0.375 → 0.5
        assert sm._calibrate(0.375) == pytest.approx(0.5)


class TestCosine:
    def test_identical_vectors_score_one(self):
        assert sm._cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert sm._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_mismatched_or_empty_dimensions_are_honest_zero(self):
        assert sm._cosine([1.0], [1.0, 2.0]) == 0.0
        assert sm._cosine([], []) == 0.0

    def test_zero_magnitude_never_divides_by_zero(self):
        assert sm._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# ─────────────── semantic_matcher: local fuzzy backend ───────────────

class TestLocalFuzzyBackend:
    def test_stopwords_and_short_words_are_filtered_from_grams(self):
        grams = sm._word_grams("please make a new photo album")
        assert "please" not in grams and "make" not in grams
        assert "photo" in grams and "album" in grams

    def test_char_grams_only_come_from_words_longer_than_three(self):
        grams = sm._char_grams("the cat compression")
        assert not any(g.startswith("c:^the") for g in grams)
        assert not any(g.startswith("c:^cat") for g in grams)
        assert any("comp" in g for g in grams)

    def test_vectorize_counts_word_and_char_grams(self):
        counts = sm._vectorize("compress compression")
        assert counts.get("compress", 0) >= 1
        assert any(k.startswith("c:") for k in counts)

    def test_index_is_cached_by_content_hash(self):
        texts = {"a tool": "compress image files", "b tool": "send email"}
        first = sm._build_local_index(texts)
        second = sm._build_local_index(dict(texts))
        assert first is second  # same object served from the cache

    def test_normalize_of_a_zero_vector_is_empty_not_nan(self):
        assert sm._normalize({"x": 0.0}) == {}

    def test_local_scores_rank_the_relevant_tool_first(self):
        scores = sm._local_scores(
            "compress my photos",
            {"compress_images": "compress image files to save space",
             "send_email": "send an email message to a contact"})
        assert scores["compress_images"] > scores["send_email"]

    def test_semantic_scores_refuses_empty_inputs_honestly(self):
        assert sm.semantic_scores("", {"t": "text"}) == ({}, "none")
        assert sm.semantic_scores("goal", {}) == ({}, "none")

    def test_semantic_scores_falls_back_to_local_backend(self, sm_env,
                                                          monkeypatch):
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)

        class DeadClient:
            def __enter__(self):
                raise OSError("no server here")

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(sm_env.httpx, "Client", lambda *a, **k: DeadClient())
        scores, backend = sm_env.semantic_scores(
            "compress my photos",
            {"compress_images": "compress image files",
             "send_email": "send an email"})
        assert backend == "local"
        assert scores["compress_images"] > scores["send_email"]

    def test_semantic_scores_uses_embeddings_when_backend_alive(self, sm_env,
                                                                monkeypatch):
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(sm_env.httpx, "Client", lambda *a, **k: FakeClient())
        monkeypatch.setattr(sm_env, "_pick_embedding_model",
                            lambda client: "fake-model")
        monkeypatch.setattr(sm_env, "_embed_goal_cached",
                            lambda text: (1.0, 0.0))
        monkeypatch.setattr(sm_env, "embed_texts", lambda texts: (
            [[1.0, 0.0]] + [[0.0, 1.0]] * (len(texts) - 1)))
        scores, backend = sm_env.semantic_scores(
            "goal text", {"first": "text one", "second": "text two"})
        assert backend == "embeddings"
        assert scores["first"] == 1.0   # identical direction, saturated
        assert scores["second"] == 0.0  # orthogonal, dead zone

    def test_pick_embedding_model_honors_the_configured_override(self,
                                                                 sm_env,
                                                                 monkeypatch):
        monkeypatch.setenv("ARENA_EMBED_MODEL", "nomic-embed-text")
        # the override short-circuits before any client is touched
        assert sm_env._pick_embedding_model(None) == "nomic-embed-text"


# ─────────────── semantic_matcher: cache + hermeticity edges ───────────────

class TestCacheEdges:
    def test_embed_texts_is_none_when_llm_disabled(self, sm_env, monkeypatch):
        monkeypatch.setenv("ARENA_LLM_DISABLED", "1")
        assert sm_env.embed_texts(["anything"]) is None

    def test_embed_texts_of_empty_batch_is_empty_not_error(self, sm_env):
        assert sm_env.embed_texts([]) == []

    def test_cache_put_skips_empty_vectors(self, sm_env):
        sm_env._cache_put(["alpha", "beta"], "model-A", [[0.1, 0.2], []])
        assert sm_env._cache_rescue(["alpha"]) == [[0.1, 0.2]]
        assert sm_env._cache_rescue(["beta"]) is None

    def test_rescue_without_model_knowledge_serves_latest_row(self, sm_env):
        # fresh process: _last_embed_model is None → unfiltered query is
        # the documented behavior (round 11/12)
        sm_env._cache_put(["gamma"], "model-A", [[0.3]])
        assert sm_env._last_embed_model == "model-A"
        sm_env._last_embed_model = None
        assert sm_env._cache_rescue(["gamma"]) == [[0.3]]

    def test_rescue_of_unknown_text_is_none(self, sm_env):
        assert sm_env._cache_rescue(["never embedded"]) is None

    def test_rescue_survives_a_broken_database(self, sm_env, monkeypatch):
        def explode():
            raise RuntimeError("db gone")

        monkeypatch.setattr(sm_env, "_cache_key", lambda t: explode())
        assert sm_env._cache_rescue(["x"]) is None

    def test_embed_goal_cached_wraps_the_backend_answer(self, sm_env,
                                                        monkeypatch):
        monkeypatch.setattr(sm_env, "embed_texts", lambda texts: [[0.5, 0.5]])
        assert sm_env._embed_goal_cached("goal") == (0.5, 0.5)
        sm_env._embed_goal_cached.cache_clear()
        monkeypatch.setattr(sm_env, "embed_texts", lambda texts: None)
        assert sm_env._embed_goal_cached("goal") is None


# ─────────────── self_improvement_gate: chooser evidence ───────────────

class TestChooserEvidence:
    def test_scoreboard_error_is_swallowed_not_fatal(self, gr_db):
        class ExplodingStore:
            def latest(self):
                raise RuntimeError("scoreboard unreadable")

        # must not raise; other evidence sources still run
        assert isinstance(
            gate.rank_improvement_targets(history_store=ExplodingStore()),
            list)

    def test_default_history_store_construction_works(self, gr_db):
        # history_store=None → the organ builds its own store against the
        # (empty) temp DB — production path when the API calls it plain
        assert isinstance(gate.rank_improvement_targets(), list)

    def test_failure_clusters_become_targets(self, gr_db):
        from app.cognition import event_ledger as ledger
        for i in range(2):
            eid = ledger.open_event("desktop-chat", f"task {i}")
            ledger.transition_event(
                eid, ledger.STATE_VERIFIED_FAILURE,
                reason="tool exited nonzero")
        clusters = gate.failure_clusters(limit=3)
        assert any(c["count"] >= 2 for c in clusters)

        class EmptyStore:
            def latest(self):
                return None

        targets = gate.rank_improvement_targets(history_store=EmptyStore())
        kinds = [t["kind"] for t in targets]
        assert "ledger_failure_cluster" in kinds

    def test_failure_cluster_read_survives_a_broken_db(self, gr_db,
                                                       monkeypatch):
        def explode():
            raise RuntimeError("no connection")

        monkeypatch.setattr(gr_db, "_get_connection", explode)
        assert gate.failure_clusters(limit=3) == []


# ─────────────── self_improvement_gate: experiment spine edges ───────────────

class TestExperimentSpineEdges:
    def test_record_experiment_refuses_empty_hypothesis(self, gr_db):
        assert gate.record_experiment("   ", "v", 1, 2) is None

    def test_record_experiment_survives_a_dead_ledger(self, gr_db,
                                                      monkeypatch):
        from app.cognition import event_ledger as ledger
        monkeypatch.setattr(ledger, "open_event",
                            lambda *a, **k: (_ for _ in ()).throw(
                                RuntimeError("ledger down")))
        assert gate.record_experiment("h", "v", 1, 2) is None

    def test_record_experiment_survives_no_event_id(self, gr_db,
                                                    monkeypatch):
        from app.cognition import event_ledger as ledger
        monkeypatch.setattr(ledger, "open_event", lambda *a, **k: None)
        assert gate.record_experiment("h", "v", 1, 2) is None

    def test_recent_and_pending_experiments_list_the_spine(self, gr_db):
        eid = gate.record_experiment("hypothesis under test", "v", 40, 41)
        assert eid
        recent = gate.recent_experiments(limit=10)
        assert any(e["event_id"] == eid for e in recent)
        # the spine stores hypotheses as "[experiment] <hypothesis>"
        # request text — the listing must surface the hypothesis inside it
        assert any("hypothesis under test" in e["hypothesis"]
                   for e in recent)
        pending = gate.pending_experiments(limit=10)
        assert any(e["event_id"] == eid for e in pending)

    def test_experiment_receipts_json_corruption_never_crashes(self, gr_db):
        eid = gate.record_experiment("h", "v", 40, 41)
        with gr_db._get_connection() as conn:
            conn.execute(
                "UPDATE cognitive_events SET receipt_json = '{broken' "
                "WHERE event_id = ?", (eid,))
            conn.commit()
        rows = gate.recent_experiments(limit=10)
        mine = [e for e in rows if e["event_id"] == eid]
        assert mine and mine[0]["receipts"] == []

    def test_owner_rejection_flips_only_real_experiments(self, gr_db):
        from app.cognition import event_ledger as ledger
        eid = gate.record_experiment("h", "v", 40, 39)  # regression
        # a regressed experiment is already terminal — rejection of a
        # fresh pending one is the owner path:
        eid2 = gate.record_experiment("h2", "v2", 40, 41)
        assert ledger.get_event(eid2)["state"] == \
            ledger.STATE_OBSERVATION_PENDING
        assert gate.reject_experiment(eid2, "not worth it") is True
        assert ledger.get_event(eid2)["state"] == \
            ledger.STATE_VERIFIED_FAILURE
        assert ledger.get_event(eid)["state"] == \
            ledger.STATE_VERIFIED_FAILURE  # untouched

    def test_is_experiment_is_false_when_the_ledger_explodes(self, gr_db,
                                                             monkeypatch):
        from app.cognition import event_ledger as ledger
        monkeypatch.setattr(ledger, "get_event",
                            lambda eid: (_ for _ in ()).throw(
                                RuntimeError("boom")))
        assert gate._is_experiment("anything") is False

    def test_pending_and_recent_reads_survive_errors(self, gr_db,
                                                     monkeypatch):
        def explode(*a, **k):
            raise RuntimeError("read failed")

        monkeypatch.setattr(gate, "_experiments", explode)
        assert gate.pending_experiments(limit=5) == []
        assert gate.recent_experiments(limit=5) == []


# ─────────────── self_improvement_gate: training readiness honesty ───────────────

class TestTrainingReadinessHardwareNote:
    def test_small_vram_is_stated_not_hidden(self, gr_db, monkeypatch):
        import app.settings_store as settings_store
        monkeypatch.setattr(settings_store, "get_hardware",
                            lambda: {"vram_gb": 8, "gpu": "RX 580"})
        report = gate.training_readiness()
        assert report["available"] is not None
        assert "8GB VRAM" in report.get("hardware_note", "")

    def test_big_vram_gets_no_scare_note(self, gr_db, monkeypatch):
        import app.settings_store as settings_store
        monkeypatch.setattr(settings_store, "get_hardware",
                            lambda: {"vram_gb": 24, "gpu": "RTX 4090"})
        report = gate.training_readiness()
        assert "hardware_note" not in report

    def test_broken_hardware_store_never_blocks_the_report(self, gr_db,
                                                           monkeypatch):
        import app.settings_store as settings_store

        def explode():
            raise RuntimeError("store gone")

        monkeypatch.setattr(settings_store, "get_hardware", explode)
        report = gate.training_readiness()
        assert "verdict" in report  # the note is best-effort, the report is not

    def test_training_readiness_reports_unavailable_on_db_failure(self,
                                                                  gr_db,
                                                                  monkeypatch):
        def explode():
            raise RuntimeError("db gone")

        monkeypatch.setattr(gr_db, "_get_connection", explode)
        report = gate.training_readiness()
        assert report["available"] is False
        assert "db gone" in report.get("reason", "")


# ─────────────── remaining honest edges (missing-line map) ───────────────

class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _MismatchClient:
    """Model discovery works; the embeddings POST returns the WRONG
    count — a dishonest provider payload the organ must refuse."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, timeout=None):
        return _StubResponse({"data": [{"id": "nomic-embed-text"}]})

    def post(self, url, json=None, timeout=None):
        return _StubResponse({"data": []})


class TestProviderDishonesty:
    def test_embed_texts_refuses_a_mismatched_provider_payload(self, sm_env,
                                                               monkeypatch):
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
        monkeypatch.setenv("ARENA_EMBEDDING_URL", "http://stub:9/v1")
        monkeypatch.setattr(sm_env.httpx, "Client", _MismatchClient)
        # 1 text in, 0 vectors out → honest None, never a padded guess
        assert sm_env.embed_texts(["open itunes"]) is None


class TestSemanticScoresFallbackEdges:
    def test_falls_back_local_when_tool_embedding_fails(self, sm_env,
                                                        monkeypatch):
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
        monkeypatch.setattr(sm_env, "_pick_embedding_model",
                            lambda client: "fake-model")
        monkeypatch.setattr(sm_env, "_embed_goal_cached",
                            lambda text: (1.0, 0.0))
        monkeypatch.setattr(sm_env, "embed_texts", lambda texts: None)
        scores, backend = sm_env.semantic_scores(
            "compress photos",
            {"compress_images": "compress image files",
             "send_email": "send an email"})
        assert backend == "local"  # goal embedded, tools didn't → local
        assert scores

    def test_reports_none_when_both_backends_fail(self, sm_env,
                                                  monkeypatch):
        monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)
        monkeypatch.setattr(sm_env, "_pick_embedding_model",
                            lambda client: None)  # no embedding model

        def explode(*a, **k):
            raise RuntimeError("local index broken")

        monkeypatch.setattr(sm_env, "_local_scores", explode)
        assert sm_env.semantic_scores("goal", {"t": "text"}) == ({}, "none")


class TestChooserCapabilityGaps:
    def test_capability_gaps_join_the_evidence(self, gr_db, monkeypatch):
        import app.mind as mind_pkg

        class FakeImprovement:
            @staticmethod
            def detect_gaps():
                return [{"capability": "summarization", "count": 3,
                         "evidence": "2 recorded misses"}]

        class FakeInst:
            improvement = FakeImprovement()

        class FakeMind:
            @staticmethod
            def get_instance():
                return FakeInst()

        monkeypatch.setattr(mind_pkg, "BeanieMind", FakeMind)

        class EmptyStore:
            def latest(self):
                return None

        targets = gate.rank_improvement_targets(
            history_store=EmptyStore(), include_capability_gaps=True)
        kinds = [t["kind"] for t in targets]
        assert "capability_gap" in kinds
        gap = next(t for t in targets if t["kind"] == "capability_gap")
        assert "summarization" in gap["target"]

    def test_capability_gap_read_failure_is_swallowed(self, gr_db,
                                                      monkeypatch):
        import app.mind as mind_pkg

        class BrokenImprovement:
            @staticmethod
            def detect_gaps():
                raise RuntimeError("phase 20 organ offline")

        class BrokenInst:
            improvement = BrokenImprovement()

        class BrokenMind:
            @staticmethod
            def get_instance():
                return BrokenInst()

        monkeypatch.setattr(mind_pkg, "BeanieMind", BrokenMind)

        class EmptyStore:
            def latest(self):
                return None

        # the gap reader failing must not kill the whole chooser
        assert isinstance(
            gate.rank_improvement_targets(
                history_store=EmptyStore(), include_capability_gaps=True),
            list)

    def test_chooser_outer_failure_returns_empty_list(self, gr_db,
                                                      monkeypatch):
        def explode(*a, **k):
            raise RuntimeError("evidence layer down")

        # failure_clusters swallows its OWN errors; this simulates a
        # failure OUTSIDE any inner guard — the outer net must hold
        monkeypatch.setattr(gate, "failure_clusters", explode)
        assert gate.rank_improvement_targets(history_store=None) == []


class TestGateKillSwitchAndExplosions:
    def test_kill_switch_silences_every_door(self, gr_db, monkeypatch):
        monkeypatch.setenv("ARENA_SELF_IMPROVEMENT", "0")
        assert gate.failure_clusters(limit=3) == []
        assert gate.rank_improvement_targets(history_store=None) == []
        assert gate.pending_experiments(limit=5) == []
        assert gate.recent_experiments(limit=5) == []
        assert gate.approve_experiment("any") is False
        assert gate.reject_experiment("any") is False

    def test_approve_survives_a_ledger_explosion(self, gr_db, monkeypatch):
        from app.cognition import event_ledger as ledger
        eid = gate.record_experiment("h", "v", 40, 41)
        assert eid

        def explode(*a, **k):
            raise RuntimeError("transition failed")

        monkeypatch.setattr(ledger, "transition_event", explode)
        assert gate.approve_experiment(eid) is False

    def test_reject_survives_a_ledger_explosion(self, gr_db, monkeypatch):
        from app.cognition import event_ledger as ledger
        eid = gate.record_experiment("h", "v", 40, 41)
        assert eid

        def explode(*a, **k):
            raise RuntimeError("transition failed")

        monkeypatch.setattr(ledger, "transition_event", explode)
        assert gate.reject_experiment(eid, "no") is False
