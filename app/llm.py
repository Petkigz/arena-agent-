import httpx
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger
from app.cognition.execution_control import (
    ExecutionCancelled,
    run_cancellable_blocking_call,
)

# ---------------------------------------------------------------------------
# Task-dependent output token budgets (P0 #19)
#
# A fixed max_tokens=150 on the main conversational/action paths made the
# model LOOK stupid: replies truncated mid-sentence, plans and structured
# reasoning cut off, entity resolution dying silently — the classic
# "the model doesn't understand" that was really "the planner gave it a
# tiny budget". Budgets now scale with task KIND (what the output IS) and
# complexity (fast/main/deep).
#
# These are OUTPUT budgets per single completion. The reasoning loop's
# ReasoningBudget.max_tokens remains the per-cycle ceiling, so every budget
# below stays under it (fast 2048 / main 8192 / deep 32768).
# ---------------------------------------------------------------------------
OUTPUT_TOKEN_BUDGETS = {
    # Plain conversational reply — enough for a real answer, not an essay.
    "conversational":  {"fast": 300, "main": 800,  "deep": 1600},
    # Read evidence/data from the context and answer (search results, probes,
    # documents). Understanding + reconciling evidence takes more room.
    "evidence_answer": {"fast": 500, "main": 1200, "deep": 2400},
    # What I just did, briefly — action confirmations.
    "action_summary":  {"fast": 200, "main": 500,  "deep": 900},
    # Structured reasoning: goal interpretation JSON, OS command plans,
    # entity resolution, multi-step planning. The "understand ambiguity"
    # step — starved at 150/300 tokens before.
    "structured":      {"fast": 600, "main": 1500, "deep": 3000},
}


def llm_forced_offline() -> bool:
    """Test/hermeticity guard: ARENA_LLM_DISABLED makes every provider
    call behave EXACTLY as if the server were unreachable — the honest
    offline path (simulation with success=False, embedding local
    fallback), never a silent success. The owner runs the suite with LM
    Studio UP (it is the machine's natural state); without this guard
    ~20 tests assert offline shapes and flip on live-LLM variance (the
    2026-09-02 owner run: interpreter variance, embedding backend,
    'provider unavailable' error shapes). Set by tests/conftest.py."""
    return bool(os.environ.get("ARENA_LLM_DISABLED"))


def output_budget(kind: str, complexity: str = "fast") -> int:
    """Output token budget for a task kind at a complexity level.

    Unknown kind is a programming error and fails loudly (this is a static
    table); unknown complexity falls back to the 'main' column.
    """
    table = OUTPUT_TOKEN_BUDGETS.get(kind)
    if table is None:
        raise ValueError(f"unknown output budget kind: {kind!r}")
    return table.get(complexity, table["main"])


# ---------------------------------------------------------------------------
# Reasoning token budget enforcement (P0 review #10)
#
# ReasoningBudget.max_tokens used to be CARRIED but never ENFORCED: a
# component could request max_tokens=8192 under a 2048 budget and the
# budget was not real. The budget is now enforced at the ONE choke point
# every LLM call passes through — llm_client.generate_chat_completion:
#   * an active reasoning_token_budget scope clamps every request to the
#     remaining budget (a component can never exceed the cycle's ceiling)
#   * granted tokens are reserved optimistically and settled to the REAL
#     usage reported by the provider, so cumulative spend is tracked
#   * when the budget is exhausted, calls run at a minimal floor with a
#     warning — degraded, but honest and visible, never silently unlimited
# ---------------------------------------------------------------------------

import contextlib
import contextvars
import os
import re
import threading
import time

# Floor for calls made after exhaustion: enough for a short honest reply,
# never a full generation. The alternative (0 tokens) produces garbage.
_TOKEN_FLOOR_WHEN_EXHAUSTED = 128


class _TokenBudgetLedger:
    """Tracks one cycle's token budget: grants, clamps, settles real usage."""

    def __init__(self, max_tokens: int):
        self.max_tokens = int(max_tokens)
        self.remaining = float(self.max_tokens)
        self.granted_total = 0
        self.used_total = 0.0
        self.clamped_calls = 0
        self.exhausted_calls = 0
        self._lock = threading.Lock()

    def grant(self, requested: int) -> int:
        """Clamp a request to the remaining budget. Returns effective tokens."""
        with self._lock:
            if self.remaining <= 0:
                self.exhausted_calls += 1
                return _TOKEN_FLOOR_WHEN_EXHAUSTED
            effective = int(min(int(requested), self.remaining))
            if effective < requested:
                self.clamped_calls += 1
            self.remaining -= effective
            self.granted_total += effective
            return max(1, effective)

    def settle(self, reserved: int, actual_usage: Optional[int]) -> None:
        """Reconcile an optimistic reservation with the provider-reported
        usage; refunds the difference so the ledger tracks real spend."""
        if actual_usage is None:
            return
        try:
            actual = max(0, int(actual_usage))
        except (TypeError, ValueError):
            return
        with self._lock:
            refund = max(0, reserved - actual)
            self.remaining += refund
            self.used_total += actual

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "budget_max_tokens": self.max_tokens,
                "tokens_granted": self.granted_total,
                "tokens_used": round(self.used_total, 1),
                "remaining": max(0.0, round(self.remaining, 1)),
                "clamped_calls": self.clamped_calls,
                "exhausted_calls": self.exhausted_calls,
            }


_active_token_budget: "contextvars.ContextVar[Optional[_TokenBudgetLedger]]" = (
    contextvars.ContextVar("arena_active_token_budget", default=None)
)


@contextlib.contextmanager
def reasoning_token_budget(max_tokens: Optional[int]):
    """Activate the per-cycle token budget for every LLM call in scope.

    All generate_chat_completion / generate_text calls inside the scope are
    clamped to the remaining budget and their real usage is tracked. Outside
    any scope, behavior is unchanged (component-requested budgets apply).
    """
    if max_tokens is None:
        yield None
        return
    ledger = _TokenBudgetLedger(max_tokens)
    token = _active_token_budget.set(ledger)
    try:
        yield ledger
    finally:
        _active_token_budget.reset(token)
        s = ledger.summary()
        app_logger.info(
            f"Reasoning token budget: {s['tokens_used']}/{s['budget_max_tokens']} tokens used, "
            f"{s['clamped_calls']} call(s) clamped, {s['exhausted_calls']} at exhaustion floor")


def active_token_budget_status() -> Optional[Dict[str, Any]]:
    """The active budget's live status, or None outside a budget scope."""
    ledger = _active_token_budget.get()
    return ledger.summary() if ledger is not None else None


class LocalLLMClient:
    # Model-availability routing (P1, live 2026-09-01): a request for a
    # model that is not loaded used to go straight to HTTP 400 and then to
    # a SIMULATED reply — while perfectly good models sat loaded on the
    # same server. The ladder is now:
    #   requested model -> actually loaded? -> use it
    #                                      -> closest LOADED fallback (loud)
    #                                      -> simulation (last resort:
    #                                         server unreachable / nothing
    #                                         loaded — honest, and visible)
    # The fallback is intentional and observable: a WARNING naming both
    # models, a `model_fallback` tag on the response dict, and an entry in
    # `fallback_events` for inspection.
    _MODELS_CACHE_TTL_S = 15.0
    # Provider error texts that mean 'that model is not available here'
    # (LM Studio/Ollama phrasings). A 400 that is NOT about the model
    # (e.g. context overflow) must not trigger the model retry. NOTE: the
    # gap must allow periods INSIDE model ids ('qwen2.5-9b-instruct').
    _MODEL_NOT_FOUND_RE = re.compile(
        r"model.{0,160}?(?:not\s+(?:be\s+)?(?:found|loaded)|"
        r"no\s+longer\s+loaded|does\s+not\s+exist|is\s+unavailable)|"
        r"no\s+model\s+found|model\s+not\s+found",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, base_url: str = settings.LM_STUDIO_URL):
        self.base_url = base_url.rstrip('/')
        self.provider = "lm_studio"  # "lm_studio", "ollama", "openai"
        self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)
        # In-memory only. It is set exclusively after held-out evaluation and a
        # fresh provider identity probe; restart intentionally clears it.
        self.model_override: Optional[str] = None
        self._models_cache: Optional[List[str]] = None
        self._models_cache_ts: float = 0.0
        self._models_cache_lock = threading.Lock()
        # Bounded ring of observable fallback decisions (last 50).
        self.fallback_events: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Model availability
    # ------------------------------------------------------------------
    def list_loaded_models(self, force: bool = False) -> Optional[List[str]]:
        """Model ids currently loaded on the provider (GET /models).

        Returns None when the server is unreachable — the caller keeps the
        requested model and lets the request path decide (that is the
        honest simulation case, not a selection). Cached for
        _MODELS_CACHE_TTL_S so steady-state completions pay no extra
        round-trip; `force=True` re-probes (used after a provider rejects
        a model, when the cache may be stale).
        """
        if llm_forced_offline():
            return None  # unreachable semantics — no selection is invented
        now = time.monotonic()
        with self._models_cache_lock:
            if (not force and self._models_cache is not None
                    and now - self._models_cache_ts < self._MODELS_CACHE_TTL_S):
                return self._models_cache
        try:
            response = self.client.get(
                f"{self.base_url}/models", timeout=5.0)
            response.raise_for_status()
            data = (response.json() or {}).get("data") or []
            models = sorted({str(m.get("id")) for m in data if m.get("id")})
        except Exception as exc:
            app_logger.info(
                f"Loaded-models probe failed ({exc}); keeping the requested "
                f"model and letting the request path decide.")
            return None
        with self._models_cache_lock:
            self._models_cache = models
            self._models_cache_ts = time.monotonic()
        return models

    @staticmethod
    def _fallback_score(requested: str, candidate: str) -> float:
        """Closeness heuristic between an unavailable requested model id
        and a loaded candidate: same letter-prefix family (qwen vs llama),
        explicit chat tuning ('instruct'/'chat'), similar parameter count,
        general-purpose rather than vision- or code-specialized. This is a
        PREFERENCE RANKING for picking the least-surprising stand-in — it
        is not a capability claim about either model."""
        def _tokens(s: str) -> List[str]:
            return re.split(r"[^a-z0-9.]+", str(s or "").lower()) or [""]
        def _family(s: str) -> str:
            m = re.match(r"[a-z]+", str(s or "").lower().strip())
            return m.group(0) if m else ""
        def _params(tokens: List[str]) -> Optional[float]:
            for t in tokens:
                m = re.fullmatch(r"(\d+(?:\.\d+)?)b", t)
                if m:
                    return float(m.group(1))
            return None
        score = 0.0
        if _family(requested) and _family(requested) == _family(candidate):
            score += 2.0
        cand_lower = str(candidate).lower()
        if "instruct" in cand_lower or "chat" in cand_lower:
            score += 2.0
        if "coder" in cand_lower or "-code" in cand_lower:
            score -= 1.0
        if "-vl" in cand_lower or "vision" in cand_lower:
            score -= 2.0
        req_params = _params(_tokens(requested))
        cand_params = _params(_tokens(candidate))
        if req_params is not None and cand_params is not None:
            score += max(0.0, 3.0 - abs(req_params - cand_params))
            if req_params == cand_params:
                score += 1.0
        return score

    def select_loaded_fallback(
        self, requested: str, loaded: Optional[List[str]],
        exclude=frozenset(),
    ) -> Optional[str]:
        """Pick the closest LOADED model for an unavailable `requested`
        id, or None when there is nothing else to pick (the requested id
        itself is never its own fallback). Deterministic: highest
        closeness score, ties broken by lexicographic id."""
        candidates = [m for m in (loaded or [])
                      if m != requested and m not in exclude]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda c: (-self._fallback_score(requested, c), c),
        )

    def _resolve_model(self, requested: str) -> "Tuple[str, Optional[Dict[str, Any]]]":
        """The routing decision: is the requested model actually loaded?
        YES -> use it. NO -> closest loaded fallback (or the requested
        model itself when the probe is unavailable/empty, so the request
        path can fail honestly rather than invent a selection)."""
        loaded = self.list_loaded_models()
        if loaded is None or requested in loaded:
            return requested, None
        fallback = self.select_loaded_fallback(requested, loaded)
        if fallback is None:
            return requested, None
        return fallback, {
            "requested": requested,
            "used": fallback,
            "reason": "requested model not loaded; selected the closest "
                      "loaded model (family/chat-tuning/size heuristic)",
        }

    def _record_fallback(self, info: Dict[str, Any]) -> None:
        self.fallback_events.append(dict(info))
        del self.fallback_events[:-50]  # bounded history

    def route_request(self, request_complexity: str) -> str:
        """
        Routes the request to the appropriate model based on complexity or direct model ID.
        'fast' -> settings.FAST_MODEL
        'main' -> settings.MAIN_MODEL
        Otherwise -> uses the direct model ID passed
        """
        if request_complexity in ("fast", "main") and self.model_override:
            return self.model_override
        if request_complexity == "fast":
            return settings.FAST_MODEL
        elif request_complexity == "main":
            return settings.MAIN_MODEL
        return request_complexity

    def set_model_override(self, model: Optional[str]) -> None:
        """Set a verified provider model for default routes, or clear it."""
        self.model_override = (model or "").strip() or None

    def _post_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /chat/completions and return the parsed JSON. Raises
        httpx errors (and re-raises cancellation) — error POLICY lives in
        generate_chat_completion."""
        if llm_forced_offline():
            # Same shape as a refused connection: flows through the honest
            # httpx.HTTPError policy in generate_chat_completion.
            raise httpx.ConnectError(
                "ARENA_LLM_DISABLED: provider treated as unreachable")
        url = f"{self.base_url}/chat/completions"
        response = run_cancellable_blocking_call(
            lambda: self.client.post(
                url, json=payload, timeout=settings.DEFAULT_TIMEOUT
            ),
            cancel=self.client.close,
            description="local model HTTP request",
        )
        response.raise_for_status()
        return response.json()

    def generate_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        complexity: str = "fast",
        temperature: float = 0.7,
        max_tokens: int = 512,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generates a chat completion from local LM Studio, Ollama, or OpenAI provider.
        Routes to the requested model only if it is actually loaded; otherwise
        selects the closest loaded fallback LOUDLY (see _resolve_model).
        Falls back to a polite mock response only if the local server is
        unreachable or nothing usable is loaded.
        """
        requested_model = self.route_request(complexity)
        model, fallback_info = self._resolve_model(requested_model)
        if fallback_info:
            self._record_fallback(fallback_info)
            app_logger.warning(
                f"LLM model '{fallback_info['requested']}' is not loaded; "
                f"using loaded model '{fallback_info['used']}' instead. "
                f"Load '{fallback_info['requested']}' in LM Studio or update "
                f"MAIN_MODEL/FAST_MODEL to remove this fallback.")
        # P0 review #10: the reasoning budget is REAL. Under an active
        # reasoning_token_budget scope no component may exceed the cycle's
        # remaining token budget — request 8192 under a 2048 budget and the
        # wire request carries 2048.
        ledger = _active_token_budget.get()
        reserved = 0
        if ledger is not None:
            effective = ledger.grant(max_tokens)
            if effective != max_tokens:
                app_logger.info(
                    f"Token budget clamp: requested max_tokens={max_tokens}, "
                    f"granted {effective} (remaining budget)")
            reserved = effective
            max_tokens = effective
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        try:
            app_logger.info(f"Sending request to Provider '{self.provider}' for model '{model}': {self.base_url}/chat/completions")
            result = self._post_completion(payload)
        except ExecutionCancelled:
            # The cancellation interrupt closes this request's transport.
            # Replace it so later, separately authorized requests can run.
            if self.client.is_closed:
                self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)
            raise
        except httpx.HTTPError as e:
            # The loaded-models cache can be stale (a model unloaded seconds
            # ago): when the provider explicitly rejects the MODEL, re-probe
            # once and retry ONCE with a loaded fallback — observably, never
            # looping. Any other error goes straight to the honest path.
            retry_model = None
            if (isinstance(e, httpx.HTTPStatusError)
                    and e.response is not None
                    and e.response.status_code in (400, 404)
                    and self._MODEL_NOT_FOUND_RE.search(
                        str(getattr(e.response, "text", "") or ""))):
                loaded = self.list_loaded_models(force=True)
                if loaded is not None:
                    if requested_model in loaded and requested_model != model:
                        retry_model = requested_model
                    else:
                        retry_model = self.select_loaded_fallback(
                            requested_model, loaded, exclude={model})
            if retry_model:
                app_logger.warning(
                    f"Provider rejected model '{model}'; retrying once with "
                    f"loaded model '{retry_model}'.")
                payload = {**payload, "model": retry_model}
                try:
                    result = self._post_completion(payload)
                except ExecutionCancelled:
                    if self.client.is_closed:
                        self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)
                    raise
                except httpx.HTTPError as retry_error:
                    e = retry_error  # fall through to simulation, honestly
                else:
                    if ledger is not None:
                        usage = (result or {}).get("usage") or {}
                        ledger.settle(reserved, usage.get("completion_tokens"))
                    info = {
                        "requested": requested_model,
                        "used": retry_model,
                        "reason": "provider rejected the requested model; "
                                  "retried once with the closest loaded model",
                    }
                    self._record_fallback(info)
                    result["model_fallback"] = info
                    return result
            app_logger.warning(f"Local LLM provider '{self.provider}' returned error or timed out with model '{model}': {e}. Falling back to simulation.")
            last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return {
                "id": "chat-simulated",
                "object": "chat.completion",
                "success": False,
                "simulated": True,
                "error": f"Local LLM provider unavailable: {e}",
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[Simulated Response - Local LLM Server Offline]\n\n"
                                   f"I received your message: \"{last_user_msg}\"\n\n"
                                   f"Target LLM brain ({model}) is not loaded. "
                                   f"Please ensure LM Studio or Ollama is running on {self.base_url}."
                    },
                    "finish_reason": "stop"
                }]
            }
        if ledger is not None:
            usage = (result or {}).get("usage") or {}
            ledger.settle(reserved, usage.get("completion_tokens"))
        if fallback_info:
            result["model_fallback"] = fallback_info
        return result

    def set_provider(self, provider_name: str, url: str):
        self.provider = provider_name.lower().strip()
        self.base_url = url.rstrip('/')
        app_logger.info(f"LLM Provider set to '{self.provider}' at {self.base_url}")

    def close(self):
        self.client.close()

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        complexity: str = "fast",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """
        Convenience wrapper that returns just the assistant reply text.

        Robustly extracts the content from the completion response, returning an
        empty string (never raising) if the provider returns an unexpected shape.
        """
        result = self.generate_chat_completion(
            messages=messages,
            complexity=complexity,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return extract_reply(result)


class ModelCompletionUnavailable(RuntimeError):
    """The provider did not produce a real, usable model completion."""


def require_real_completion(result: Any) -> str:
    """Return completion text only for an explicitly non-simulated response.

    Outcome-producing tools must use this instead of treating diagnostic offline
    text or success-sounding fallback strings as generated content.
    """
    if not isinstance(result, dict):
        raise ModelCompletionUnavailable("Model provider returned an invalid response")
    if result.get("simulated") is True or result.get("success") is False:
        raise ModelCompletionUnavailable(
            str(result.get("error") or "Model provider is unavailable")
        )
    text = extract_reply(result).strip()
    if not text:
        raise ModelCompletionUnavailable("Model provider returned no completion text")
    return text


def extract_reply(result: Any, fallback: str = "") -> str:
    """Safely extract assistant text from an OpenAI-style completion dict.

    Never raises: returns `fallback` (default "") for None, missing keys, empty
    choices, or non-dict payloads. Replaces the fragile, repeated
    `result["choices"][0]["message"]["content"]` accessor used across tools.
    """
    try:
        choices = result.get("choices") if isinstance(result, dict) else None
        if not choices:
            return fallback
        first = choices[0]
        if not isinstance(first, dict):
            return fallback
        message = first.get("message")
        if not isinstance(message, dict):
            return fallback
        content = message.get("content")
        return content if isinstance(content, str) else fallback
    except Exception:
        return fallback


llm_client = LocalLLMClient()
