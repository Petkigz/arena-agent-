"""Local semantic matching for capability discovery (P0 review #4).

Deterministic keyword/synonym scoring knows WHAT TOOLS EXIST; it does not
understand WHAT CAPABILITY IS CONCEPTUALLY APPROPRIATE. "Make the photo
take less disk space" shares no tokens with compress_files, so the lexical
funnel never proposes it.

This module adds the semantic slot of the discovery pipeline — still fully
local, no cloud services:

    goal embedding  ->  tool/capability embeddings  ->  semantic similarity
        (constraints / availability / risk / historical success stay
         downstream: the planner funnel, the gates, memory lessons)

Two backends, best available, degrading NEVER breaks discovery:

  embeddings  LM Studio /v1/embeddings (env ARENA_EMBED_BASE_URL, default
              http://localhost:1234/v1; model via ARENA_EMBED_MODEL or
              auto-picked from /v1/models preferring ids containing
              "embed" — a chat model is never fed 170 texts). Model
              discovery is cached WITH A TTL, never forever: a miss (no
              model loaded yet) expires in ~30s so a model loaded later in
              LM Studio is picked up WITHOUT a process restart; a hit
              revalidates in ~5min. Tool embeddings are cached per
              manifest AND per model (switching models invalidates them —
              vectors from two models live in different spaces); goal
              embeddings are cached per text. Unreachable/misconfigured ->
              fallback.
  local       In-process TF-IDF over tool DESCRIPTIONS: word unigrams
              plus character 4-grams, so morphological variants match
              ("compression"~"compress"). This is fuzzy LEXICAL matching —
              true synonymy ("shrink"~"compress") needs the embedding
              model. Honest about that.

Scores leave this module calibrated to [0, 1]:
    cal = clamp((cosine - 0.15) / 0.45, 0, 1)
a dead zone under 0.15 kills noise; cosine >= 0.6 saturates. Consumers fuse
the calibrated score with their lexical score; they own the weighting.
"""
from __future__ import annotations

import hashlib
import math
import re
import time

import httpx
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from app.utils.logger import app_logger

# --- configuration -----------------------------------------------------------

_DEFAULT_EMBED_BASE_URL = "http://localhost:1234/v1"
_EMBED_TIMEOUT_SECONDS = 4.0

# --- calibration -------------------------------------------------------------

_COS_DEAD_ZONE = 0.15
_COS_SATURATION = 0.60


def _calibrate(cosine: float) -> float:
    if cosine <= _COS_DEAD_ZONE:
        return 0.0
    if cosine >= _COS_SATURATION:
        return 1.0
    return (cosine - _COS_DEAD_ZONE) / (_COS_SATURATION - _COS_DEAD_ZONE)


# --- embedding backend (LM Studio, local) ------------------------------------

# A cached MISS (no embedding model loaded) expires quickly: the owner can
# load a model in LM Studio at any moment and semantic matching must
# notice without a process restart (P1 review — the old forever-cache kept
# the fallback long after a model appeared). A cached HIT is stable but
# still revalidates occasionally (models get switched or unloaded).
_EMBED_MODEL_TTL_MISS_S = 30.0
_EMBED_MODEL_TTL_HIT_S = 300.0

# base_url -> (model_or_None, expires_at_monotonic)
_embed_model_cache: Dict[str, Tuple[Optional[str], float]] = {}

# The model the vector caches were built with (see _invalidate_...).
_embeddings_cache_model: Optional[str] = None

_backend_state: Dict[str, Optional[str]] = {"current": None}


def _embed_base_url() -> str:
    import os

    return os.environ.get("ARENA_EMBED_BASE_URL", _DEFAULT_EMBED_BASE_URL).rstrip("/")


def _invalidate_vector_caches_if_model_changed(model: Optional[str]) -> None:
    """The vector caches belong to ONE model: embeddings from two different
    models live in different spaces (often different dimensions), so mixing
    them produces meaningless cosines. When discovery notices a different
    model, every cached vector is stale and is dropped."""
    global _embeddings_cache_model
    if model != _embeddings_cache_model:
        if _embeddings_cache_model is not None:
            app_logger.info(
                f"Semantic matching: embedding model changed "
                f"({_embeddings_cache_model!r} -> {model!r}); "
                f"dropping cached vectors from the old model")
        _tool_embedding_cache.clear()
        _embed_goal_cached.cache_clear()
        _embeddings_cache_model = model


def _pick_embedding_model(client) -> Optional[str]:
    """Prefer an explicitly configured model, else the first loaded model
    whose id looks like an embedding model. Chat models are never used.

    Discovery is cached WITH A TTL, never forever: a miss expires after
    _EMBED_MODEL_TTL_MISS_S (a model loaded later in LM Studio is picked
    up without a restart), a hit after _EMBED_MODEL_TTL_HIT_S (a switched
    or unloaded model is eventually noticed). Vector caches are rebound to
    the resolved model on every call."""
    import os

    configured = os.environ.get("ARENA_EMBED_MODEL", "").strip()
    if configured:
        _invalidate_vector_caches_if_model_changed(configured)
        return configured
    base = _embed_base_url()
    now = time.monotonic()
    cached = _embed_model_cache.get(base)
    if cached is not None and cached[1] > now:
        _invalidate_vector_caches_if_model_changed(cached[0])
        return cached[0]
    model: Optional[str] = None
    try:
        response = client.get(f"{base}/models", timeout=_EMBED_TIMEOUT_SECONDS)
        response.raise_for_status()
        ids = [m.get("id", "") for m in response.json().get("data", [])]
        embedding_ids = [i for i in ids if "embed" in i.lower()]
        model = embedding_ids[0] if embedding_ids else None
    except Exception:
        model = None
    ttl = _EMBED_MODEL_TTL_HIT_S if model else _EMBED_MODEL_TTL_MISS_S
    _embed_model_cache[base] = (model, time.monotonic() + ttl)
    _invalidate_vector_caches_if_model_changed(model)
    return model


def embed_texts(texts: Sequence[str]) -> Optional[List[List[float]]]:
    """Embed a batch of texts with the local embedding server, or None.

    None is the honest 'backend unavailable' answer — callers fall back,
    they never fail discovery because a server was down.
    """
    if not texts:
        return []
    try:
        with httpx.Client() as client:
            model = _pick_embedding_model(client)
            if not model:
                _log_backend_transition("fallback",
                          "Semantic matching: no embedding model loaded "
                          "(load one in LM Studio to enable it); using local fuzzy matching")
                return None
            response = client.post(
                f"{_embed_base_url()}/embeddings",
                json={"model": model, "input": list(texts)},
                timeout=_EMBED_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            vectors = [item.get("embedding") for item in data]
            if len(vectors) != len(texts) or not all(vectors):
                return None
            _log_backend_transition("embeddings",
                      f"Semantic matching: embedding backend active (model={model})")
            return vectors
    except Exception as exc:
        _log_backend_transition("fallback",
                  f"Semantic matching: embedding backend unavailable ({exc}); using local fuzzy matching")
        return None


def _log_backend_transition(state: str, message: str) -> None:
    """Log backend state TRANSITIONS, not just the first occurrence
    (P1 review): with TTL-based rediscovery the backend can recover
    mid-process (a model loaded in LM Studio) or degrade (server stopped)
    — once-only logging would hide the flip. Each transition is one line,
    so the volume stays bounded by real state changes."""
    if _backend_state["current"] != state:
        _backend_state["current"] = state
        app_logger.info(message)


# Tool embeddings depend only on the tool text set: cache per content hash.
_tool_embedding_cache: Dict[str, Dict[str, List[float]]] = {}


@lru_cache(maxsize=128)
def _embed_goal_cached(text: str) -> Optional[Tuple[float, ...]]:
    vectors = embed_texts([text])
    if not vectors:
        return None
    return tuple(vectors[0])


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


# --- local fuzzy backend (TF-IDF, no dependencies) ---------------------------

# Request/function words users type but tool descriptions don't focus on.
# Without these, 'make' (rare in descriptions, high idf) matched every
# "Make a ..." description and fabricated false positives.
_LOCAL_STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "that", "this", "your",
    "you", "are", "can", "use", "using", "get", "set", "any", "all", "new",
    "one", "two", "not", "but", "out", "may", "will", "shall",
    "make", "made", "take", "put", "turn", "keep", "let", "want", "need",
    "like", "please", "just", "also", "show", "tell", "give", "them",
    "there", "here", "have", "has", "had", "was", "were", "been", "does",
    "did", "than", "then", "when", "where", "what", "which", "how", "why",
}

_local_index_cache: Dict[str, Tuple[Dict[str, Dict[str, float]], Dict[str, float]]] = {}


def _word_grams(text: str) -> List[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower())
             if len(w) > 2 and w not in _LOCAL_STOPWORDS]
    return words + [f"w:{w}" for w in words]


def _char_grams(text: str) -> List[str]:
    """4-grams, not 3-grams: trigrams made short unrelated words look
    related ('photo' and 'phone' share 2 of 5). Morphological variants
    ('compression'/'compress') still share most of their grams."""
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3]
    grams: List[str] = []
    for word in words:
        padded = f"^{word}$"
        grams.extend(f"c:{padded[i:i + 4]}" for i in range(len(padded) - 3))
    return grams


def _vectorize(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for gram in _word_grams(text) + _char_grams(text):
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def _build_local_index(tool_texts: Dict[str, str]):
    """TF-IDF index over the tool corpus; cached by content hash."""
    key = hashlib.sha1(
        "\x00".join(f"{k}\x01{v}" for k, v in sorted(tool_texts.items())).encode("utf-8")
    ).hexdigest()
    cached = _local_index_cache.get(key)
    if cached:
        return cached
    doc_counts = {name: _vectorize(text) for name, text in tool_texts.items()}
    n_docs = max(1, len(doc_counts))
    df: Dict[str, int] = {}
    for counts in doc_counts.values():
        for gram in counts:
            df[gram] = df.get(gram, 0) + 1
    idf = {gram: math.log((n_docs + 1) / (d + 1)) + 1.0 for gram, d in df.items()}
    vectors = {
        name: _normalize({gram: count * idf[gram] for gram, count in counts.items()})
        for name, counts in doc_counts.items()
    }
    entry = (vectors, idf)
    _local_index_cache[key] = entry
    return entry


def _normalize(vector: Dict[str, float]) -> Dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vector.values()))
    if norm == 0.0:
        return {}
    return {gram: v / norm for gram, v in vector.items()}


def _local_scores(user_text: str, tool_texts: Dict[str, str]) -> Dict[str, float]:
    vectors, idf = _build_local_index(tool_texts)
    query = _normalize({
        gram: count * idf.get(gram, 1.0)
        for gram, count in _vectorize(user_text).items()
    })
    scores: Dict[str, float] = {}
    for name, vec in vectors.items():
        dot = sum(v * vec.get(gram, 0.0) for gram, v in query.items())
        scores[name] = _calibrate(dot)
    return scores


# --- public interface ---------------------------------------------------------

def semantic_scores(
    user_text: str,
    tool_texts: Dict[str, str],
) -> Tuple[Dict[str, float], str]:
    """Calibrated semantic relevance of each tool text to the goal.

    Returns ({tool_name: calibrated 0..1}, backend) where backend is
    "embeddings", "local", or "none". Never raises.
    """
    if not user_text or not tool_texts:
        return {}, "none"
    try:
        # Resolve the ACTIVE model BEFORE reading any vector cache (P1
        # review): _pick's TTL discovery and model-change invalidation
        # must run even when the goal embedding is an lru HIT — otherwise
        # a None cached during the no-model era (or vectors from a model
        # that was since switched away) would be served forever. The TTL
        # makes this cheap: no HTTP unless the discovery entry expired.
        with httpx.Client() as client:
            current_model = _pick_embedding_model(client)
        if current_model is not None:
            goal = _embed_goal_cached(user_text)
            if goal is not None:
                cache_key = hashlib.sha1(
                    "\x00".join(f"{k}\x01{v}" for k, v in sorted(tool_texts.items())).encode("utf-8")
                ).hexdigest()
                tool_vectors = _tool_embedding_cache.get(cache_key)
                if tool_vectors is None:
                    vectors = embed_texts(list(tool_texts.values()))
                    if vectors is None:
                        tool_vectors = None
                    else:
                        tool_vectors = dict(zip(tool_texts.keys(), vectors))
                        _tool_embedding_cache[cache_key] = tool_vectors
                if tool_vectors is not None:
                    return (
                        {
                            name: _calibrate(_cosine(goal, vec))
                            for name, vec in tool_vectors.items()
                        },
                        "embeddings",
                    )
    except Exception as exc:
        app_logger.warning(f"Semantic embedding path failed, falling back local: {exc}")
    try:
        return _local_scores(user_text, tool_texts), "local"
    except Exception as exc:
        app_logger.warning(f"Local semantic matching failed: {exc}")
        return {}, "none"
