"""Owner-managed local inference profile with measured recommendations.

The hardware self-model recommends a context budget and model size from
installed RAM, but until now those were metadata: `settings.MAIN_MODEL` and
friends were only changed ad hoc through `/models/config`, with no persistence,
no recommendation comparison, and no live provider evidence.

This module makes the inference configuration a single owner-managed artifact:

  * `InferenceProfile.recommended()` derives context window + fast/main models
    from the measured hardware tier (not hard-coded 16GB-era assumptions).
  * `InferenceProfileStore` persists the owner's profile atomically at
    `data/inference_profile.json` with revisions. A malformed file fails safe
    to the measured recommendation, never to an arbitrary model.
  * `apply_profile()` pushes the profile into the live runtime (settings +
    shared llm_client) — one write path, no dual sources of truth.
  * `probe_provider()` gathers *measured* evidence from the running provider:
    online state, loaded models, whether the configured models are loaded, and
    a small completion latency measurement. Offline or unprobed states stay
    honestly `unknown`; no claim is made from configuration alone.

Owner authority: the owner may configure any model/context window; the store
only records honest divergence flags (`exceeds_measured_budget`,
`recommendation_match`) — observation, never falsified capability. Whether a
model actually fits in RAM is proven only by a successful load/completion,
which is what the probe and the benchmark script measure.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hardware_tier() -> Dict[str, Any]:
    from app.utils.hardware_governor import HardwareGovernor
    return HardwareGovernor.detect_hardware_tier()


@dataclass
class InferenceProfile:
    main_model: str = ""
    fast_model: str = ""
    provider_url: str = ""
    context_window_tokens: int = 2048
    revision: int = 0
    updated_at: str = ""

    @classmethod
    def recommended(cls) -> "InferenceProfile":
        """Derive the profile from the measured hardware tier."""
        tier = _hardware_tier()
        context = int(tier.get("max_context_budget_tokens") or 2048)
        ram_gb = float(tier.get("total_ram_gb") or 0)
        level = int(tier.get("tier_level") or 3)
        if level == 1 and ram_gb >= 40:
            main = "qwen2.5-14b-instruct"
            fast = "qwen2.5-3b-instruct"
        elif level == 2 or ram_gb >= 24:
            main = "qwen2.5-9b-instruct"
            fast = "qwen2.5-3b-instruct"
        else:
            main = "qwen2.5-3b-instruct"
            fast = "qwen2.5-1.5b-instruct"
        return cls(
            main_model=main,
            fast_model=fast,
            provider_url=settings.LM_STUDIO_URL,
            context_window_tokens=context,
            revision=0,
            updated_at="",
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InferenceProfileStore:
    """Atomic, thread-safe persistence for the owner's inference profile."""

    min_context_tokens = 512
    max_context_tokens = 32768

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path is not None else settings.DATA_DIR / "inference_profile.json"
        self._lock = threading.RLock()
        self._profile: InferenceProfile = self._load()

    def _load(self) -> InferenceProfile:
        recommended = InferenceProfile.recommended()
        if not self.path.exists():
            return recommended
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            profile = InferenceProfile(
                main_model=str(raw.get("main_model") or recommended.main_model).strip(),
                fast_model=str(raw.get("fast_model") or recommended.fast_model).strip(),
                provider_url=str(raw.get("provider_url") or recommended.provider_url).strip().rstrip("/"),
                context_window_tokens=int(raw.get("context_window_tokens") or recommended.context_window_tokens),
                revision=max(0, int(raw.get("revision", 0))),
                updated_at=str(raw.get("updated_at", "")),
            )
            return self._validated(profile, recommended)
        except Exception as exc:
            # Malformed profile fails safe to the measured recommendation.
            app_logger.warning(f"Inference profile file unreadable ({exc}); using measured recommendation.")
            return recommended

    def _validated(self, profile: InferenceProfile, recommended: InferenceProfile) -> InferenceProfile:
        profile.context_window_tokens = max(
            self.min_context_tokens, min(self.max_context_tokens, int(profile.context_window_tokens))
        )
        if not profile.main_model:
            profile.main_model = recommended.main_model
        if not profile.fast_model:
            profile.fast_model = recommended.fast_model
        parsed = urlparse(profile.provider_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            profile.provider_url = recommended.provider_url
        return profile

    def _persist(self, profile: InferenceProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self) -> InferenceProfile:
        with self._lock:
            return InferenceProfile(**self._profile.to_dict())

    def recommendation(self) -> InferenceProfile:
        return InferenceProfile.recommended()

    def divergence(self, profile: Optional[InferenceProfile] = None) -> Dict[str, Any]:
        """Honest comparison of the configured profile against the measured recommendation."""
        configured = profile or self.get()
        recommended = self.recommendation()
        return {
            "recommendation_match": (
                configured.main_model == recommended.main_model
                and configured.fast_model == recommended.fast_model
            ),
            "recommended_main_model": recommended.main_model,
            "recommended_fast_model": recommended.fast_model,
            "recommended_context_window_tokens": recommended.context_window_tokens,
            "exceeds_measured_budget": configured.context_window_tokens > recommended.context_window_tokens,
            "note": "Divergence is recorded, not blocked: only a successful provider load/completion proves real capability.",
        }

    def update(self, patch: Dict[str, Any]) -> InferenceProfile:
        unknown = set(patch) - {"main_model", "fast_model", "provider_url", "context_window_tokens"}
        if unknown:
            raise ValueError(f"Unknown inference profile field(s): {', '.join(sorted(unknown))}")
        for key in ("main_model", "fast_model", "provider_url"):
            if key in patch and patch[key] is not None and not str(patch[key]).strip():
                raise ValueError(f"{key} must be a non-empty string")
        if "provider_url" in patch and patch["provider_url"] is not None:
            parsed = urlparse(str(patch["provider_url"]).strip().rstrip("/"))
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("provider_url must be an absolute http(s) URL")
        if "context_window_tokens" in patch and patch["context_window_tokens"] is not None:
            value = patch["context_window_tokens"]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("context_window_tokens must be an integer")
            if not (self.min_context_tokens <= value <= self.max_context_tokens):
                raise ValueError(f"context_window_tokens must be within [{self.min_context_tokens}, {self.max_context_tokens}]")
        with self._lock:
            current = self._profile.to_dict()
            current.update({k: v for k, v in patch.items() if v is not None})
            merged = InferenceProfile(
                main_model=str(current["main_model"]).strip(),
                fast_model=str(current["fast_model"]).strip(),
                provider_url=str(current["provider_url"]).strip().rstrip("/"),
                context_window_tokens=int(current["context_window_tokens"]),
                revision=self._profile.revision + 1,
                updated_at=_now(),
            )
            merged = self._validated(merged, InferenceProfile.recommended())
            self._persist(merged)
            self._profile = merged
            audit_logger.info(
                f"Owner inference profile updated: main={merged.main_model}, fast={merged.fast_model}, "
                f"context={merged.context_window_tokens}, url={merged.provider_url}, revision={merged.revision}"
            )
            return self.get()


# Module-level singleton mirroring the other owner stores.
inference_profile_store = InferenceProfileStore()


def apply_profile(profile: InferenceProfile) -> Dict[str, Any]:
    """Push the profile into the live runtime. The single write path."""
    from app.llm import llm_client

    settings.MAIN_MODEL = profile.main_model
    settings.FAST_MODEL = profile.fast_model
    settings.LM_STUDIO_URL = profile.provider_url
    llm_client.base_url = profile.provider_url.rstrip("/")
    return {
        "applied": True,
        "main_model": settings.MAIN_MODEL,
        "fast_model": settings.FAST_MODEL,
        "lm_studio_url": settings.LM_STUDIO_URL,
        "context_window_tokens": profile.context_window_tokens,
    }


def apply_persisted_profile() -> Optional[InferenceProfile]:
    """Load the persisted profile at startup so model ids survive restarts.

    Without this, every boot reverted to tier-derived defaults (e.g.
    qwen2.5-9b-instruct) even after the owner set their real loaded models,
    producing HTTP 400s on live machines. Best-effort: never blocks startup.
    """
    try:
        profile = inference_profile_store.get()
        apply_profile(profile)
        app_logger.info(
            "Inference profile applied at startup (main=%s, fast=%s)",
            profile.main_model, profile.fast_model,
        )
        # Silent-degradation guard (live incident: main quietly became the
        # 3b, so 'Evidence-grounded answer routed to the main model' still
        # hit the small model that fumbles evidence). Warn loudly when the
        # persisted MAIN equals FAST while the measured hardware tier
        # recommends a bigger main — evidence answers and the OS planner
        # both depend on MAIN.
        try:
            recommended = InferenceProfile.recommended()
            if (
                profile.main_model
                and profile.main_model == profile.fast_model
                and recommended.main_model != profile.main_model
            ):
                app_logger.warning(
                    "Inference profile: MAIN model '%s' equals the FAST model — "
                    "evidence-grounded answers and the OS planner will run on the "
                    "small model. The measured hardware tier recommends '%s' for "
                    "main. Load it in LM Studio and set it via the Model Settings "
                    "page or POST /models/config {\"main_model\": \"%s\"}.",
                    profile.main_model, recommended.main_model, recommended.main_model,
                )
        except Exception:
            pass
        return profile
    except Exception as exc:
        app_logger.warning(f"Could not apply persisted inference profile: {exc}")
        return None


def probe_provider(
    profile: Optional[InferenceProfile] = None,
    *,
    client: Optional[httpx.Client] = None,
    timeout: float = 5.0,
    completion_probe: bool = True,
) -> Dict[str, Any]:
    """Gather measured provider evidence. Offline stays honestly unknown."""
    prof = profile or inference_profile_store.get()
    base = prof.provider_url.rstrip("/")
    owned_client = client is None
    http = client or httpx.Client(timeout=timeout)
    evidence: Dict[str, Any] = {
        "probed_at": _now(),
        "provider_url": base,
        "provider_online": False,
        "loaded_models": [],
        "main_model_loaded": None,   # unknown until observed online
        "fast_model_loaded": None,
        "completion_probe": None,    # unknown until measured
        "latency_ms": None,
        "error": None,
    }
    try:
        response = http.get(f"{base}/models", timeout=timeout)
        if response.status_code != 200:
            evidence["error"] = f"provider returned HTTP {response.status_code}"
            return evidence
        evidence["provider_online"] = True
        data = response.json() or {}
        models = [str(m.get("id")) for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
        evidence["loaded_models"] = models
        evidence["main_model_loaded"] = prof.main_model in models
        evidence["fast_model_loaded"] = prof.fast_model in models
        if completion_probe and models:
            # Probe ONLY a configured model that is actually loaded — starting
            # with the cheap fast model. Never an arbitrary models[0]: a
            # randomly-picked reasoning model can burn a minute producing an
            # empty visible channel (observed live: 50.8s, verified=false).
            if prof.fast_model in models:
                probe_model = prof.fast_model
            elif prof.main_model in models:
                probe_model = prof.main_model
            else:
                evidence["completion_probe"] = {
                    "success": False, "verified": False,
                    "reason": "neither configured model is loaded; refusing to probe an arbitrary one",
                    "loaded_models": models,
                }
                probe_model = None
            payload = {
                "model": probe_model,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
                "temperature": 0.0,
                "max_tokens": 8,
                "stream": False,
            } if probe_model else None
            if payload is None:
                return evidence
            started = time.perf_counter()
            completion = http.post(f"{base}/chat/completions", json=payload, timeout=max(timeout, 60.0))
            evidence["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            if completion.status_code == 200:
                body = completion.json() or {}
                reply = ""
                try:
                    reply = str(body["choices"][0]["message"]["content"])
                except Exception:
                    reply = ""
                # Served-model honesty: providers may loosely resolve the
                # requested id to a different model — record what ACTUALLY
                # served the response, because a probe of X answered by Y is
                # not evidence about X.
                served = str(body.get("model") or payload["model"])
                evidence["completion_probe"] = {
                    "success": bool(reply.strip()),
                    "model": payload["model"],
                    "served_model": served,
                    "resolved_differently": served != payload["model"],
                    "reply_preview": reply.strip()[:80],
                    "usage": body.get("usage"),
                    "verified": bool(reply.strip()) and served == payload["model"],
                }
            elif payload is not None:
                evidence["completion_probe"] = {
                    "success": False,
                    "verified": False,
                    "http_status": completion.status_code,
                }
    except httpx.HTTPError as exc:
        evidence["error"] = f"provider unreachable: {exc}"
    except Exception as exc:  # Probe must never crash callers.
        evidence["error"] = f"probe failed: {exc}"
    finally:
        if owned_client:
            http.close()
    return evidence
