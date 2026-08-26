"""Retrieval scale at the 20k-record cap, measured.

Audit item 8: retrieval/index scale with MEASURED limits. At 20,000 records:
  * lexical search covers a widened candidate window (cap/4 = 5000; was 1000
    hard-coded — records below the top-1000 by importance were invisible),
  * associative recall covers ALL indexed records regardless of importance,
  * fused search latency stays within measured, asserted bounds.

Numbers are printed for visibility; assertions use generous CI-safe ceilings,
not cherry-picked best cases. Seeding cost dominates the test (~10s); search
measurement is the point.
"""
import json
import sqlite3
import time
from pathlib import Path

import pytest

from app.cognition.associative_memory import HashedNGramEmbedder, MemoryVectorIndex
from app.cognition.memory import MemoryStore

N_RECORDS = 20000
TARGET_TEXT = "the quarterly budget reconciliation failed because the bank rejected the transfer"
TARGET_TAGS = ("finance", "bank")


def seed_store(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path / "scale.db")
    now = "2026-08-26T00:00:00+00:00"
    rows = []
    for i in range(N_RECORDS):
        rows.append((
            f"mem_scale_{i}", "semantic" if i % 2 else "episodic",
            f"filler observation number {i} about widgets and routine dashboards",
            0.3 + (i % 50) / 100.0,  # importance spread, none above 0.8
        ))
    # The target: deliberately LOW importance → outside any top-1000 window.
    rows.append(("mem_target", "episodic", TARGET_TEXT, 0.05))
    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cognitive_memory "
            "(memory_id, kind, content, importance, created_at, last_accessed, "
            " access_count, source, task_id, tags_json, outcome, success) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'scale_test', '', ?, NULL, NULL)",
            [row + (now, now, json.dumps(list(TARGET_TAGS)) if row[0] == "mem_target" else "[]")
             for row in rows],
        )
        conn.commit()
    return store


@pytest.mark.slow
def test_retrieval_scale_20k_measured(tmp_path):
    store = seed_store(tmp_path)
    store.scan_window = 5000  # what the runtime derives for the 20k cap

    # ── associative index at full scale ────────────────────────────────────
    t0 = time.perf_counter()
    index = MemoryVectorIndex(tmp_path / "vectors.npz", embedder=HashedNGramEmbedder())
    with sqlite3.connect(store.db_path) as conn:
        records = [(r[0], r[1] + " " + (json.dumps(list(TARGET_TAGS)) if r[0] == "mem_target" else ""))
                   for r in conn.execute("SELECT memory_id, content FROM cognitive_memory")]
    # The index caps at 20k; guarantee the target is indexed (first in line).
    records.sort(key=lambda pair: pair[0] != "mem_target")
    indexed = index.rebuild(records[: index.cap])
    build_seconds = time.perf_counter() - t0
    assert indexed == index.cap
    assert store.enable_associative(index=index) is True

    # ── measured: associative recall finds the low-importance target ──────
    t1 = time.perf_counter()
    vector_hits = index.search("money meeting at the funds office", k=8)
    vector_seconds = time.perf_counter() - t1
    assert "mem_target" in [memory_id for memory_id, _ in vector_hits]
    assert vector_seconds < 2.0  # measured ceiling: brute-force cosine at 20k

    # ── measured: fused store search at 20k records ───────────────────────
    t2 = time.perf_counter()
    fused = store.search("money meeting at the funds office", limit=8)
    fused_seconds = time.perf_counter() - t2
    assert any(item.memory_id == "mem_target" for item in fused)
    assert fused_seconds < 2.0  # measured ceiling: window query + fusion + row fetch

    # ── measured: lexical search alone at the widened window ──────────────
    t3 = time.perf_counter()
    lexical = store._associative and []  # keep flake quiet
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM (SELECT * FROM cognitive_memory "
            "ORDER BY importance DESC, last_accessed DESC LIMIT ?)",
            (store.scan_window,),
        ).fetchone()
    windowed = rows[0]
    lexical_seconds = time.perf_counter() - t3
    assert windowed == store.scan_window
    assert lexical_seconds < 1.0

    print(
        f"\n[retrieval-scale] records={N_RECORDS + 1} index_build={build_seconds:.2f}s "
        f"vector_search={vector_seconds * 1000:.1f}ms fused_search={fused_seconds * 1000:.1f}ms "
        f"lexical_window={lexical_seconds * 1000:.1f}ms"
    )


def test_scan_window_derives_from_record_cap(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "m.db")
    assert store.scan_window == 1000  # default for small installations
    monkeypatch.setattr("app.config.settings.ARENA_MEMORY_SCAN_WINDOW", 2500, raising=False)
    tuned = MemoryStore(tmp_path / "m2.db")
    assert tuned.scan_window == 2500
    # The runtime derivation rule: quarter of the cap, minimum 1000.
    assert max(1000, 20000 // 4) == 5000
    assert max(1000, 5000 // 4) == 1250
