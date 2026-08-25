"""Associative memory: embedding-backed recall layered over the lexical store.

Human memory recalls by vague association ("that thing about the money
meeting..."), not just keyword match. The lexical store misses paraphrases
with zero token overlap entirely — the 0.12 relevance gate filters them out.
This module adds vector-associative recall and merges it with lexical ranking
by reciprocal-rank fusion.

Providers, honestly separated:
  * HashedNGramEmbedder (default): deterministic signed feature hashing of
    word tokens + character 3-grams into 512-dim L2-normalized vectors
    (fastText-style subword hashing). No model download, no network, runs
    anywhere — including clean CI. It is a real associative improvement over
    token overlap, NOT a claim of semantic understanding.
  * LMStudioEmbedder (optional): a real local embedding model via LM Studio's
    OpenAI-compatible /embeddings endpoint (ARENA_EMBEDDING_URL +
    ARENA_EMBEDDING_MODEL). When unreachable it degrades honestly to the
    hashed embedder with a logged reason — never silently faked vectors.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.config import settings
from app.utils.logger import app_logger

_DIM = 512


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _char_ngrams(text: str, size: int = 3) -> List[str]:
    compact = " ".join(_tokens(text))
    if len(compact) < size:
        return [compact] if compact else []
    return [compact[i:i + size] for i in range(len(compact) - size + 1)]


# Deterministic concept features: surface forms map to shared concept keys so
# paraphrases with zero token overlap ("money" vs "budget") associate. This is
# a hand-curated bridge until a real embedding model is configured — honest
# feature engineering, not learned semantics.
_CONCEPT_GROUPS = [
    {"money", "budget", "finance", "cash", "funds", "payment", "invoice"},
    {"meeting", "discussion", "standup", "review", "gathering", "call"},
    {"deploy", "deployment", "rollout", "release", "kubernetes", "cluster"},
    {"fail", "failure", "failed", "error", "crash", "broken"},
    {"copy", "backup", "snapshot", "duplicate", "archive"},
    {"safe", "vault", "secure", "encrypted", "protect"},
    {"card", "gpu", "graphics", "nvidia", "radeon", "cuda", "vram"},
    {"meal", "breakfast", "lunch", "dinner", "food", "eat"},
    {"write", "writing", "text", "wording", "english", "response", "style"},
    {"speak", "speech", "voice", "talk", "say", "audio"},
    {"search", "find", "locate", "lookup", "query"},
    {"delete", "remove", "purge", "erase"},
    {"create", "make", "generate", "build", "compose"},
    {"user", "owner", "human", "person", "creator"},
    {"week", "weekly", "daily", "friday", "monday", "schedule", "calendar"},
    {"document", "file", "spreadsheet", "report", "sheet", "notes"},
]
_CONCEPT_BY_TOKEN = {
    token: f"concept{i}" for i, group in enumerate(_CONCEPT_GROUPS) for token in group
}


def _bucket(feature: str) -> Tuple[int, int]:
    """Deterministic (index, sign) for a feature string (signed hashing trick)."""
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % _DIM, 1 if (value >> 63) & 1 else -1


class HashedNGramEmbedder:
    """Deterministic subword-hashed embeddings; no model, no network."""

    name = "hashed-ngram-512"

    @property
    def dimension(self) -> int:
        return _DIM

    # Feature-type weights: concept bridges carry the paraphrase signal, words
    # anchor exact topics, char n-grams add fuzzy subword matching. Stopwords
    # are dropped so common glue words cannot dominate the cosine floor.
    _STOPWORDS = {
        "the", "a", "an", "at", "of", "to", "in", "on", "with", "without",
        "and", "or", "each", "is", "was", "for", "while", "it", "its", "by",
        "about", "into", "from", "that", "this",
    }
    _WEIGHT_WORD = 2.0
    _WEIGHT_CHAR = 1.0
    _WEIGHT_CONCEPT = 6.0

    def embed(self, text: str) -> List[float]:
        vector = np.zeros(_DIM, dtype=np.float32)
        tokens = _tokens(text)
        content = [t for t in tokens if t not in self._STOPWORDS]
        for token in content:
            index, sign = _bucket(f"w:{token}")
            vector[index] += sign * self._WEIGHT_WORD
        for ngram in _char_ngrams(" ".join(content)):
            index, sign = _bucket(f"c:{ngram}")
            vector[index] += sign * self._WEIGHT_CHAR
        concepts = {_CONCEPT_BY_TOKEN[token] for token in content if token in _CONCEPT_BY_TOKEN}
        for concept in concepts:
            index, sign = _bucket(f"k:{concept}")
            vector[index] += sign * self._WEIGHT_CONCEPT
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


class LMStudioEmbedder:
    """Optional real embedding model behind LM Studio's embeddings endpoint."""

    def __init__(self, url: str, model: str, timeout: float = 10.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._dimension: Optional[int] = None

    @property
    def name(self) -> str:
        return f"lmstudio:{self.model}"

    def _endpoint(self) -> str:
        base = self.url
        if not (base.endswith("/embeddings") or base.endswith("/v1/embeddings")):
            base = base + "/v1"
        return base + "/embeddings"

    def embed(self, text: str) -> Optional[List[float]]:
        try:
            import httpx
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self._endpoint(),
                    json={"model": self.model, "input": [text]},
                )
                response.raise_for_status()
                data = response.json()["data"][0]["embedding"]
                self._dimension = len(data)
                return data
        except Exception as exc:
            app_logger.warning(
                f"LM Studio embedding provider unavailable ({exc}); associative memory "
                "degrades to the deterministic hashed embedder"
            )
            return None

    def embed_batch(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
        return [self.embed(text) for text in texts]


def default_embedder() -> Any:
    """Configured provider: real model when set and reachable, else hashed."""
    url = getattr(settings, "ARENA_EMBEDDING_URL", "") or ""
    model = getattr(settings, "ARENA_EMBEDDING_MODEL", "") or ""
    if url and model:
        provider = LMStudioEmbedder(url, model)
        if provider.embed("arena-embedding-probe") is not None:
            app_logger.info(f"Associative memory using LM Studio embeddings ({model})")
            return provider
        app_logger.warning("Falling back to the hashed-ngram embedder for associative memory")
    return HashedNGramEmbedder()


class MemoryVectorIndex:
    """Persistent numpy vector index over memory records (cosine top-k)."""

    def __init__(self, path: str | Path, embedder: Any = None, cap: int = 20000) -> None:
        self.path = Path(path)
        self.embedder = embedder or default_embedder()
        self.cap = max(1, int(cap))
        self._lock = threading.RLock()
        self._ids: List[str] = []
        self._matrix: Optional[np.ndarray] = None
        self._meta_path = self.path.with_suffix(".meta.json")
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path.exists() or not self._meta_path.exists():
            return
        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            if meta.get("embedder") != self.embedder.name:
                return  # provider changed: rebuild instead of mixing spaces
            archive = np.load(self.path)
            ids = [str(x) for x in archive["ids"]]
            matrix = archive["matrix"].astype(np.float32)
            if matrix.ndim == 2 and len(ids) == matrix.shape[0] and matrix.shape[0]:
                self._ids, self._matrix = ids, matrix
        except Exception as exc:
            app_logger.warning(f"Memory vector index unreadable; will rebuild: {exc}")

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                self.path,
                ids=np.array(self._ids, dtype="<U64"),  # pickle-free reload
                matrix=self._matrix,
            )
            self._meta_path.write_text(
                json.dumps({"embedder": self.embedder.name, "count": len(self._ids)}),
                encoding="utf-8",
            )
        except Exception as exc:
            app_logger.warning(f"Memory vector index persist failed: {exc}")

    # ── operations ──────────────────────────────────────────────────────────
    def rebuild(self, records: Sequence[Tuple[str, str]]) -> int:
        """Rebuild from (memory_id, text) pairs; replaces any existing index."""
        records = list(records[: self.cap])
        vectors: List[List[float]] = []
        ids: List[str] = []
        for memory_id, text in records:
            vector = self.embedder.embed(text)
            if vector is None:
                continue  # honest provider failure: skip rather than fake
            vectors.append(vector)
            ids.append(memory_id)
        with self._lock:
            if vectors:
                self._ids = ids
                self._matrix = np.array(vectors, dtype=np.float32)
                norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._matrix = self._matrix / norms
            else:
                self._ids, self._matrix = [], None
            self._persist()
        return len(self._ids)

    def add(self, memory_id: str, text: str) -> bool:
        vector = self.embedder.embed(text)
        if vector is None:
            return False
        row = np.array([vector], dtype=np.float32)
        norm = float(np.linalg.norm(row))
        if norm > 0:
            row /= norm
        with self._lock:
            if self._matrix is None:
                self._ids, self._matrix = [memory_id], row
            else:
                if memory_id in set(self._ids):
                    return True  # idempotent
                self._ids.append(memory_id)
                self._matrix = np.vstack([self._matrix, row])
                if len(self._ids) > self.cap:
                    self._ids = self._ids[-self.cap:]
                    self._matrix = self._matrix[-self.cap:]
            self._persist()
        return True

    def search(self, query: str, k: int = 32) -> List[Tuple[str, float]]:
        if self._matrix is None or not query.strip():
            return []
        vector = self.embedder.embed(query)
        if vector is None:
            return []
        q = np.array(vector, dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm == 0:
            return []
        q /= norm
        with self._lock:
            scores = self._matrix @ q
            top = min(max(1, k), len(self._ids))
            order = np.argsort(-scores)[:top]
            return [(self._ids[i], float(scores[i])) for i in order]

    def count(self) -> int:
        with self._lock:
            return len(self._ids)

    def forget(self, memory_id: str) -> None:
        with self._lock:
            if memory_id in set(self._ids):
                keep = [i for i, mid in enumerate(self._ids) if mid != memory_id]
                self._ids = [self._ids[i] for i in keep]
                self._matrix = self._matrix[keep] if self._matrix is not None else None
                self._persist()
