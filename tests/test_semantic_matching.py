"""P0 review #4: semantic (not just keyword) capability discovery.

rank_tools used to be tokens + synonyms + description overlap — it knows
WHAT TOOLS EXIST, not WHAT CAPABILITY IS CONCEPTUALLY APPROPRIATE. The
semantic layer adds goal-vs-tool similarity on top, fully local:

  embeddings  LM Studio /v1/embeddings when an embedding model is loaded
  local       in-process TF-IDF fuzz (word + char-trigram) as the floor

The lexical scorer stays authoritative for exact matches; semantic
relevance ADDS evidence so conceptual matches with zero token overlap can
enter the candidate set. Backend failure never breaks discovery.
"""

from unittest.mock import patch

import pytest

from app.cognition.semantic_matcher import (
    _calibrate,
    _pick_embedding_model,
    semantic_scores,
)
from app.cognition.tool_matcher import rank_tools

CONCEPTUAL_GOAL = "make the photo take less disk space"


def _fake_semantic(scores, backend="embeddings"):
    def fake(user_text, tool_texts):
        return scores, backend

    return fake


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.Client: serves /models then /embeddings."""

    def __init__(self, model_ids, embeddings=None, fail=False):
        self.model_ids = model_ids
        self.embeddings = embeddings or {}
        self.fail = fail
        self.embedding_calls = []

    def get(self, url, timeout=None):
        assert url.endswith("/models")
        return _FakeResponse({"data": [{"id": i} for i in self.model_ids]})

    def post(self, url, json=None, timeout=None):
        assert url.endswith("/embeddings")
        self.embedding_calls.append(json["input"])
        if self.fail:
            raise ConnectionError("embedding server down")
        return _FakeResponse({
            "data": [{"embedding": self.embeddings.get(text, [0.0, 0.0])}
                     for text in json["input"]]
        })

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# --- calibration -------------------------------------------------------------

def test_calibration_dead_zone_and_saturation():
    assert _calibrate(0.0) == 0.0
    assert _calibrate(0.15) == 0.0            # noise stays noise
    assert _calibrate(0.375) == pytest.approx(0.5)  # midpoint
    assert _calibrate(0.6) == 1.0             # saturation
    assert _calibrate(0.95) == 1.0


# --- embedding backend -------------------------------------------------------

def test_model_pick_prefers_embedding_models():
    client = _FakeClient(["qwen2.5-9b-instruct", "nomic-embed-text-v1.5"])
    with patch.dict("app.cognition.semantic_matcher._embed_model_cache", clear=True):
        assert _pick_embedding_model(client) == "nomic-embed-text-v1.5"


def test_model_pick_never_uses_a_chat_model():
    client = _FakeClient(["qwen2.5-9b-instruct", "llama-3-8b"])
    with patch.dict("app.cognition.semantic_matcher._embed_model_cache", clear=True):
        assert _pick_embedding_model(client) is None


def test_semantic_scores_uses_embeddings_when_model_available():
    goal = "shrink the archive"
    tool_texts = {"compress_files": "compress files to a zip", "phone_call": "make a phone call"}
    client = _FakeClient(
        ["nomic-embed"],
        embeddings={
            goal: [1.0, 0.0],
            "compress files to a zip": [0.9, 0.1],
            "make a phone call": [0.0, 1.0],
        },
    )
    with patch("app.cognition.semantic_matcher.httpx.Client", lambda: client), \
         patch.dict("app.cognition.semantic_matcher._embed_model_cache", clear=True), \
         patch("app.cognition.semantic_matcher._status_logged",
               {"embeddings": True, "fallback": True}):
        scores, backend = semantic_scores(goal, tool_texts)
    assert backend == "embeddings"
    assert scores["compress_files"] > 0.7
    assert scores["phone_call"] == 0.0


def test_tool_embeddings_are_cached_per_manifest():
    goal = "shrink the archive"
    tools = {"a": "alpha tool", "b": "beta tool"}
    client = _FakeClient(["nomic-embed"], embeddings={goal: [1.0, 0.0]})
    with patch("app.cognition.semantic_matcher.httpx.Client", lambda: client), \
         patch.dict("app.cognition.semantic_matcher._embed_model_cache", clear=True), \
         patch.dict("app.cognition.semantic_matcher._tool_embedding_cache", clear=True), \
         patch("app.cognition.semantic_matcher._status_logged",
               {"embeddings": True, "fallback": True}):
        semantic_scores(goal, tools)
        semantic_scores(goal, tools)
    # One batched call for the tool corpus; the goal hit the lru cache.
    assert len(client.embedding_calls) == 1


# --- local fallback ----------------------------------------------------------

def test_local_fallback_when_no_embedding_model():
    scores, backend = semantic_scores(
        "compression my vacation photos",
        {"compress_files": "compress files to a zip", "phone_call": "make a phone call"},
    )
    assert backend == "local"
    assert scores["compress_files"] > scores["phone_call"]


def test_local_fallback_fuzzy_matches_morphological_variants():
    """'compression' never token-matches 'compress'; char-trigrams do."""
    scores, backend = semantic_scores(
        "compression of my archive files",
        {"compress_files": "compress files to a zip", "phone_call": "make a phone call"},
    )
    assert backend == "local"
    assert scores["compress_files"] >= 0.5
    assert scores["compress_files"] > scores["phone_call"]


def test_semantic_scores_never_raises_on_bad_backend():
    with patch("app.cognition.semantic_matcher.embed_texts",
               side_effect=RuntimeError("boom")):
        scores, backend = semantic_scores("anything", {"t": "a tool"})
    assert backend in ("local", "none")


# --- fusion in rank_tools ----------------------------------------------------

def test_conceptual_match_enters_candidate_set_with_embeddings():
    """THE review case: 'make the photo take less disk space' shares no
    tokens with compress_files — only semantic similarity can propose it."""
    with patch("app.cognition.tool_matcher.semantic_scores",
               _fake_semantic({"compress_files": 0.9})):
        hits = rank_tools(CONCEPTUAL_GOAL, limit=5)
    actions = [h.action_type for h in hits]
    assert "compress_files" in actions
    match = next(h for h in hits if h.action_type == "compress_files")
    assert match.semantic_score == 0.9
    assert match.semantic_backend == "embeddings"


def test_exact_lexical_match_still_outranks_conceptual_only():
    with patch("app.cognition.tool_matcher.semantic_scores",
               _fake_semantic({"camera_photo": 1.0, "compress_files": 0.2})):
        hits = rank_tools("compress my vacation photos into a zip", limit=5)
    assert hits[0].action_type == "compress_files"


def test_weak_similarity_never_boosts_noise():
    """char-trigram fuzziness made 'photo' look like 'phone'; calibrated
    similarity below 0.5 must not manufacture candidates."""
    hits = rank_tools(CONCEPTUAL_GOAL, limit=5)  # local backend, no embeddings
    assert "phone_call" not in [h.action_type for h in hits]


def test_backend_failure_never_breaks_discovery():
    with patch("app.cognition.tool_matcher.semantic_scores",
               side_effect=RuntimeError("semantic layer exploded")):
        hits = rank_tools("compress my vacation photos into a zip", limit=5)
    assert hits[0].action_type == "compress_files"
    assert hits[0].semantic_backend is None


def test_matches_expose_their_semantic_evidence():
    hits = rank_tools("compress my vacation photos into a zip", limit=3)
    assert hits
    assert hits[0].semantic_backend in ("local", "none")
    assert hits[0].semantic_score is not None
