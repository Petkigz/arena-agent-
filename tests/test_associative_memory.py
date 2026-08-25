"""Associative memory: vector recall fused with lexical ranking.

A deterministic hashed-ngram embedder (512-d, signed feature hashing + concept
bridges) gives paraphrase recall with zero token overlap; an optional LM Studio
embedding provider upgrades quality on the owner machine and degrades honestly
when unreachable. Fusion is reciprocal-rank; failures keep lexical search.
"""
import numpy as np

from app.cognition.associative_memory import (
    HashedNGramEmbedder,
    LMStudioEmbedder,
    MemoryVectorIndex,
    default_embedder,
)
from app.cognition.memory import MemoryStore


def test_hashed_embedder_is_deterministic_and_normalized():
    embedder = HashedNGramEmbedder()
    a = embedder.embed("Chrome crashed while opening the dashboard")
    b = embedder.embed("Chrome crashed while opening the dashboard")
    assert a == b
    assert abs(np.linalg.norm(a) - 1.0) < 1e-5
    assert len(a) == 512


def test_similarity_orders_paraphrase_above_unrelated():
    embedder = HashedNGramEmbedder()
    target = np.array(embedder.embed("The budget discussion with the bank ended"))
    paraphrase = np.array(embedder.embed("money meeting about funds"))
    unrelated = np.array(embedder.embed("water the garden each morning"))
    cos = lambda v: float(target @ v)  # all normalized
    assert cos(paraphrase) > cos(unrelated)


def test_zero_overlap_paraphrase_recall_beats_lexical_only():
    store = MemoryStore(":memory:" if False else __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()) / "m.db")
    index = MemoryVectorIndex(
        __import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "v.npz",
        embedder=HashedNGramEmbedder(),
    )
    assert store.enable_associative(index=index) is True
    target = store.add("episodic", "The budget discussion with the bank ended without agreement", tags=("finance",))
    for filler in ("Water the garden each morning", "Compress the weekly backups on Friday"):
        store.add("semantic", filler, importance=1.0)
    hits = store.search("money meeting at the funds office", limit=3)
    assert any(item.memory_id == target.memory_id for item in hits)
    assert hits[0].memory_id == target.memory_id  # fused recall ranks it first


def test_exact_lexical_matches_still_rank_first():
    store_dir = __import__("pathlib").Path(__import__("tempfile").mkdtemp())
    store = MemoryStore(store_dir / "m.db")
    store.enable_associative(index=MemoryVectorIndex(store_dir / "v.npz", embedder=HashedNGramEmbedder()))
    exact = store.add("semantic", "kubernetes rollout finished", tags=("deploy",))
    store.add("semantic", "unrelated garden note", importance=1.0)
    hits = store.search("kubernetes rollout", limit=2)
    assert hits and hits[0].memory_id == exact.memory_id


def test_vector_index_persists_and_resumes_without_rebuild(tmp_path):
    calls = {"embedded": 0}

    class CountingEmbedder(HashedNGramEmbedder):
        def embed(self, text):
            calls["embedded"] += 1
            return super().embed(text)

    index_path = tmp_path / "v.npz"
    first = MemoryVectorIndex(index_path, embedder=CountingEmbedder())
    first.add("m1", "alpha note")
    first.add("m2", "beta note")
    baseline = calls["embedded"]

    resumed = MemoryVectorIndex(index_path, embedder=CountingEmbedder())
    assert resumed.count() == 2  # loaded from disk
    assert calls["embedded"] == baseline  # no re-embedding at load
    hits = resumed.search("alpha", k=1)
    assert hits and hits[0][0] == "m1"


def test_provider_change_rebuilds_instead_of_mixing_spaces(tmp_path):
    class OtherEmbedder(HashedNGramEmbedder):
        name = "different-provider"

    index = MemoryVectorIndex(tmp_path / "v.npz", embedder=HashedNGramEmbedder())
    index.add("m1", "note")
    swapped = MemoryVectorIndex(tmp_path / "v.npz", embedder=OtherEmbedder())
    assert swapped.count() == 0  # refused to load foreign vectors


def test_unreachable_lmstudio_degrades_to_hashed(tmp_path):
    provider = LMStudioEmbedder("http://127.0.0.1:1", "fake-model", timeout=0.2)
    assert provider.embed("probe") is None  # honest failure, no fake vectors
    chosen = default_embedder()  # no URL configured → hashed
    assert chosen.name == "hashed-ngram-512"


def test_associative_failures_never_break_lexical_search(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "m.db")
    store.enable_associative(index=MemoryVectorIndex(tmp_path / "v.npz", embedder=HashedNGramEmbedder()))
    target = store.add("semantic", "kubernetes rollout finished")

    class BrokenIndex:
        def search(self, *a, **k):
            raise RuntimeError("index exploded")

        def add(self, *a, **k):
            return True

    store._associative = BrokenIndex()
    hits = store.search("kubernetes rollout", limit=2)  # fusion fails → lexical kept
    assert hits and hits[0].memory_id == target.memory_id


def test_enable_associative_backfills_once_then_resumes(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.add("semantic", "early record one")
    store.add("semantic", "early record two")
    first_index = MemoryVectorIndex(tmp_path / "v.npz", embedder=HashedNGramEmbedder())
    assert store.enable_associative(index=first_index) is True
    assert first_index.count() == 2

    # Simulate a restart: a new store over the same DB and index file resumes
    # from the persisted index instead of re-embedding everything.
    restarted = MemoryStore(tmp_path / "m.db")
    resumed_index = MemoryVectorIndex(tmp_path / "v.npz", embedder=HashedNGramEmbedder())
    embed_calls = {"n": 0}
    original_embed = resumed_index.embedder.embed

    def counting_embed(text):
        embed_calls["n"] += 1
        return original_embed(text)

    resumed_index.embedder.embed = counting_embed
    restarted.enable_associative(index=resumed_index)
    assert resumed_index.count() == 2
    assert embed_calls["n"] == 0  # no backfill re-embedding on resume
    restarted.add("semantic", "late record three")
    assert resumed_index.count() == 3  # incremental add indexed
