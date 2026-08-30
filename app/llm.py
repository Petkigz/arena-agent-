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


def output_budget(kind: str, complexity: str = "fast") -> int:
    """Output token budget for a task kind at a complexity level.

    Unknown kind is a programming error and fails loudly (this is a static
    table); unknown complexity falls back to the 'main' column.
    """
    table = OUTPUT_TOKEN_BUDGETS.get(kind)
    if table is None:
        raise ValueError(f"unknown output budget kind: {kind!r}")
    return table.get(complexity, table["main"])


class LocalLLMClient:
    def __init__(self, base_url: str = settings.LM_STUDIO_URL):
        self.base_url = base_url.rstrip('/')
        self.provider = "lm_studio"  # "lm_studio", "ollama", "openai"
        self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)
        # In-memory only. It is set exclusively after held-out evaluation and a
        # fresh provider identity probe; restart intentionally clears it.
        self.model_override: Optional[str] = None

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
        Requests local server to auto-load target model if needed.
        Falls back to a polite mock response if local server is unreachable.
        """
        model = self.route_request(complexity)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        try:
            url = f"{self.base_url}/chat/completions"
            app_logger.info(f"Sending request to Provider '{self.provider}' for model '{model}': {url}")
            response = run_cancellable_blocking_call(
                lambda: self.client.post(
                    url, json=payload, timeout=settings.DEFAULT_TIMEOUT
                ),
                cancel=self.client.close,
                description="local model HTTP request",
            )
            response.raise_for_status()
            return response.json()
        except ExecutionCancelled:
            # The cancellation interrupt closes this request's transport.
            # Replace it so later, separately authorized requests can run.
            if self.client.is_closed:
                self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)
            raise
        except httpx.HTTPError as e:
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
