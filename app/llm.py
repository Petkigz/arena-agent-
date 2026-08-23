import httpx
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger

class LocalLLMClient:
    def __init__(self, base_url: str = settings.LM_STUDIO_URL):
        self.base_url = base_url.rstrip('/')
        self.provider = "lm_studio"  # "lm_studio", "ollama", "openai"
        self.client = httpx.Client(timeout=settings.DEFAULT_TIMEOUT)

    def route_request(self, request_complexity: str) -> str:
        """
        Routes the request to the appropriate model based on complexity or direct model ID.
        'fast' -> settings.FAST_MODEL
        'main' -> settings.MAIN_MODEL
        Otherwise -> uses the direct model ID passed
        """
        if request_complexity == "fast":
            return settings.FAST_MODEL
        elif request_complexity == "main":
            return settings.MAIN_MODEL
        return request_complexity

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
            response = self.client.post(url, json=payload, timeout=settings.DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response.json()
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
