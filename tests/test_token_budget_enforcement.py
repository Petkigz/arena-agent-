"""P0 review #10: the reasoning token budget is REAL.

ReasoningBudget.max_tokens used to be carried but never enforced — a
component could request max_tokens=8192 under a 2048 budget. Now every
LLM call under an active reasoning_token_budget scope is clamped at the
ONE choke point (llm_client.generate_chat_completion), with cumulative
spend settled against the provider-reported real usage.
"""

from unittest.mock import patch

from app.llm import (
    active_token_budget_status,
    llm_client,
    reasoning_token_budget,
)


class _FakeResp:
    def __init__(self, completion_tokens=None):
        self._tokens = completion_tokens

    def raise_for_status(self):
        return None

    def json(self):
        result = {"choices": [{"message": {"content": "ok"}}], "model": "test"}
        if self._tokens is not None:
            result["usage"] = {"completion_tokens": self._tokens}
        return result


def _call(max_tokens, completion_tokens=None, budget=None):
    """One LLM call through the real client with a fake HTTP layer.
    Returns the payload that would have hit the provider."""
    payloads = []

    def fake_post(url, json=None, timeout=None):
        payloads.append(json)
        return _FakeResp(completion_tokens)

    with patch.object(llm_client.client, "post", side_effect=fake_post):
        if budget is not None:
            with reasoning_token_budget(budget):
                llm_client.generate_chat_completion(
                    messages=[{"role": "user", "content": "hi"}], max_tokens=max_tokens)
        else:
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "hi"}], max_tokens=max_tokens)
    return payloads[0]


def test_component_cannot_exceed_the_budget():
    """THE review case: budget 2048, a component requests 8192 — the wire
    request carries 2048."""
    payload = _call(max_tokens=8192, completion_tokens=100, budget=2048)
    assert payload["max_tokens"] == 2048


def test_requests_within_budget_pass_unchanged():
    payload = _call(max_tokens=500, completion_tokens=50, budget=2048)
    assert payload["max_tokens"] == 500


def test_cumulative_spend_settles_to_real_usage():
    """Reserved optimistically, settled to provider usage: a 2000-token
    request that USED only 200 leaves 2048 - 200 = 1848 for the next call
    (the unused reservation is refunded — the ledger tracks REAL spend)."""
    payloads = []

    def fake_post(url, json=None, timeout=None):
        payloads.append(json)
        return _FakeResp(200 if len(payloads) == 1 else None)

    with patch.object(llm_client.client, "post", side_effect=fake_post):
        with reasoning_token_budget(2048):
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "a"}], max_tokens=2000)
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "b"}], max_tokens=8192)
    assert payloads[0]["max_tokens"] == 2000
    assert payloads[1]["max_tokens"] == 1848  # 2048 - 200 actually used


def test_exhausted_budget_runs_at_floor_never_unlimited():
    payloads = []

    def fake_post(url, json=None, timeout=None):
        payloads.append(json)
        return _FakeResp(None)

    with patch.object(llm_client.client, "post", side_effect=fake_post):
        with reasoning_token_budget(100):
            # No usage reported -> nothing refunded -> the budget is spent.
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "a"}], max_tokens=100)
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "b"}], max_tokens=8192)
    assert payloads[0]["max_tokens"] == 100
    assert payloads[1]["max_tokens"] == 128  # floor: degraded, honest, visible


def test_outside_any_scope_behavior_is_unchanged():
    payload = _call(max_tokens=8192, completion_tokens=10)
    assert payload["max_tokens"] == 8192


def test_generate_text_is_enforced_too():
    payloads = []

    def fake_post(url, json=None, timeout=None):
        payloads.append(json)
        return _FakeResp(10)

    with patch.object(llm_client.client, "post", side_effect=fake_post):
        with reasoning_token_budget(256):
            llm_client.generate_text(
                messages=[{"role": "user", "content": "hi"}], max_tokens=4096)
    assert payloads[0]["max_tokens"] == 256


def test_runtime_cycle_activates_the_budget():
    """End-to-end: the public cognitive cycle entry wraps the whole cycle
    in the token budget scope — an inner component's oversized request is
    clamped on the wire."""
    from app.cognition.runtime import CognitiveRuntime

    payloads = []

    def fake_post(url, json=None, timeout=None):
        payloads.append(json)
        return _FakeResp(10)

    runtime = CognitiveRuntime.__new__(CognitiveRuntime)
    with patch.object(llm_client.client, "post", side_effect=fake_post), \
         patch.object(CognitiveRuntime, "_process_cognitive_cycle_impl") as impl:

        def side_effect(**kwargs):
            # A component deep inside the cycle requests 8192 tokens.
            llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": "inner"}], max_tokens=8192)
            return {"success": True}

        impl.side_effect = side_effect
        runtime.process_cognitive_cycle("hello", complexity="fast")
    assert payloads
    assert all(p["max_tokens"] <= 2048 for p in payloads)  # fast tier ceiling
