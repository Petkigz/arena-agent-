import pytest
from app.llm import LocalLLMClient
from app.config import settings

def test_llm_routing():
    client = LocalLLMClient()
    assert client.route_request("fast") == settings.FAST_MODEL
    assert client.route_request("main") == settings.MAIN_MODEL

def test_llm_graceful_fallback():
    # Use a dummy port that is definitely offline
    client = LocalLLMClient(base_url="http://localhost:59193/v1")
    messages = [{"role": "user", "content": "Hello LLM!"}]
    
    # generate completion should gracefully mock a response
    response = client.generate_chat_completion(messages, complexity="fast")
    assert response["id"] == "chat-simulated"
    assert "Simulated Response" in response["choices"][0]["message"]["content"]
    assert "Hello LLM!" in response["choices"][0]["message"]["content"]
