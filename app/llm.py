import httpx
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger

class LocalLLMClient:
    def __init__(self, base_url: str = settings.LM_STUDIO_URL):
        self.base_url = base_url.rstrip('/')
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
        Generates a chat completion from the local LM Studio server.
        Requests LM Studio to auto-load the target model if it is not currently active in VRAM.
        Falls back to a polite mock response if the local server is unreachable or fails.
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
            app_logger.info(f"Sending request to LM Studio for model '{model}' (Auto-loading into VRAM if needed): {url}")
            response = self.client.post(url, json=payload, timeout=settings.DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            app_logger.warning(f"LM Studio local server returned error or timed out while loading/generating with '{model}': {e}. Falling back to simulation.")
            # Return a simulated response representing the Qwen model when offline
            last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return {
                "id": "chat-simulated",
                "object": "chat.completion",
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[Simulated Response - Local LM Studio Offline or Model Loading Error]\n\n"
                                   f"I received your message: \"{last_user_msg}\"\n\n"
                                   f"Target LLM brain ({model}) is not loaded. "
                                   f"Please ensure LM Studio is running on {self.base_url} and JIT Model Auto-Loading is enabled in LM Studio settings."
                    },
                    "finish_reason": "stop"
                }]
            }

    def close(self):
        self.client.close()

llm_client = LocalLLMClient()
