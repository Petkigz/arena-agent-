"""F6 (DIAG D8): 'run code' must reach a tool that RUNS the code.

Live bug (owner machine, 2026-09-01): 'Run this Python code and tell me
the output: print(sum(range(1, 101)))' — the router matched a code-RUNNING
tool but the payload arrived EMPTY (no code extracted), the run failed on
a missing command, and the replanner's Plan-B fell to code_explain — the
agent EXPLAINED the code instead of running it (ground truth 5050 never
appeared).

Findings from recon (2026-09-01):
  * manifest 'sandbox_run' wraps run_in_sandbox(sandbox_id, ...) — the
    REQUIRED sandbox_id is un-providable by any chat caller, so the action
    is un-callable for fresh runs (same N2 class of payload-contract gap);
  * 'local_execute' (LocalExecutor) wraps the create-sandbox + run dance
    itself and takes a CODE SNIPPET directly — the correct target, per the
    owner's prescription;
  * local_execute is Level 3 (sensitive): the gate routes it to the 1-click
    owner-approval flow (WAITING_FOR_USER + approval_store) instead of
    running arbitrary code autonomously. That is the designed safety path:
    the agent must ASK to run code, never pretend an explanation was the
    execution.

Contract under test:
  * the router vocabulary maps run-code phrasings to local_execute
    deterministically (and never lets code_explain win them);
  * the code snippet is extracted into the payload (action=python, code);
  * code fences and colon-introduced snippets are both extracted; no code
    in the message means no fabricated code;
  * explain-phrasings still route to code_explain (guard);
  * LocalExecutor actually runs the snippet (post-approval path);
  * end to end, the exact live D8 question: SUPERSEDED by owner review
    item 6 (Option B, 2026-09-01) — a PURE computation is evaluated
    deterministically at Level 0 (the calculator's risk class) and never
    demands approval; IMPURE snippets keep the local_execute + Level-3
    approval contract unchanged (the gate is not weakened).
"""

from unittest.mock import patch

from app.cognition.tool_matcher import match_control_tool


D8_TEXT = ("Run this Python code and tell me the output: "
           "print(sum(range(1, 101)))")


# ── router vocabulary ───────────────────────────────────────────────────

def test_run_code_routes_to_local_execute():
    m = match_control_tool(D8_TEXT)
    assert m is not None
    assert m.action_type == "local_execute", \
        f"run-code must route to the code-RUNNING tool, got {m.action_type}"


def test_run_code_phrasing_variants_route_to_local_execute():
    for text in (
        "run this code: print('hi')",
        "execute this code and tell me the output: print(2 + 2)",
        "run the python code: sum([1, 2, 3])",
        "execute python for me: print(7 * 6)",
        "run this script: print('done')",
    ):
        m = match_control_tool(text)
        assert m is not None and m.action_type == "local_execute", \
            f"{text!r} -> {m.action_type if m else None}"


def test_explain_code_still_routes_to_code_explain():
    """Guard: explaining is a different verb — the fix must not steal it
    ('print' is a control verb, so the matcher fires and must pick the
    EXPLAIN tool, not the runner)."""
    m = match_control_tool("Explain this code: print(sum(range(10)))")
    assert m is not None
    assert m.action_type == "code_explain"


def test_explain_request_never_asks_approval_to_run():
    """End-to-end guard: an EXPLAIN request must not be converted into a
    run-code approval request by the new vocabulary."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    def _fake_llm(**kwargs):
        return {"success": True, "id": "chat-real",
                "choices": [{"message": {"content": "This code prints the sum."}}]}

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm):
        res = CognitivePipeline.process_chat(
            user_text="Explain this code: print(sum(range(10)))")
    assert res.get("recommendation", {}).get("action_type") != "local_execute"
    assert res.get("requires_approval") is not True


# ── payload extraction ──────────────────────────────────────────────────

def test_code_snippet_extracted_from_colon():
    m = match_control_tool(D8_TEXT)
    assert m.payload.get("action") == "python"
    assert m.payload.get("code") == "print(sum(range(1, 101)))"


def test_code_snippet_extracted_from_fence():
    text = "Run this python code and tell me the output:\n```python\nprint(sum(range(1, 101)))\n```"
    m = match_control_tool(text)
    assert m is not None and m.action_type == "local_execute"
    assert m.payload.get("code") == "print(sum(range(1, 101)))"
    assert m.payload.get("action") == "python"


def test_no_code_in_message_means_no_fabricated_code():
    m = match_control_tool("run the code I sent you yesterday")
    assert m is None or "code" not in (m.payload or {}), \
        "no snippet in the message -> no fabricated code in the payload"


def test_sandbox_run_payload_carries_a_runnable_command():
    """If a run-code request routes to sandbox_run (explicit 'disposable
    sandbox' phrasing), the payload must carry the built command,
    not an empty dict."""
    m = match_control_tool(
        "run this code in a disposable sandbox: print(2 + 2)")
    assert m is not None and m.action_type == "sandbox_run"
    assert "python -c" in str(m.payload.get("command", ""))
    assert m.payload.get("code") == "print(2 + 2)"


# ── the executor actually runs snippets (post-approval path) ────────────

def test_local_executor_runs_the_d8_snippet():
    from app.tools.local_executor import LocalExecutor
    res = LocalExecutor.execute(action="python",
                                code="print(sum(range(1, 101)))")
    assert res.get("success") is True, res
    assert "5050" in str(res.get("stdout", ""))


# ── end to end: the exact live D8 question ──────────────────────────────

def test_d8_e2e_asks_to_run_code_never_explains_it():
    """Owner review item 6 (2026-09-01, Option B): a PURE computation
    ('print(sum(range(1, 101)))' — no I/O by AST construction) is the
    calculator's class of risk, NOT arbitrary execution. The old contract
    (Level-3 approval for this exact text) is superseded: the observation
    router evaluates it deterministically at Level 0 and the answer must
    come from that verified evidence — never code_explain, never a
    fabricated guess, and never an approval demand for arithmetic.
    (Impure snippets keep the local_execute + approval contract — pinned
    by test_impure_code_e2e_still_demands_approval below.)"""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    def _fake_llm(**kwargs):
        # Obedient brain: echoes the verified computation it was given.
        content = ("The output is 5050."
                   if "VERIFIED COMPUTATION" in str(kwargs.get("messages", ""))
                   else "placeholder")
        return {"success": True, "id": "chat-real",
                "choices": [{"message": {"content": content}}]}

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm):
        res = CognitivePipeline.process_chat(user_text=D8_TEXT)

    # The pure computation was ANSWERED from verified evidence — no
    # Level-3 approval flow for arithmetic.
    assert res.get("reasoning_action") == "answer"
    assert res.get("requires_approval") is not True
    assert res.get("approval_request") is None
    assert res.get("goal_lifecycle_state") == "achieved"
    assert "5050" in str(res.get("assistant_reply", ""))
    # And the misroute is dead:
    assert "code_explain" not in [
        str(a) for a in (res.get("executed_actions") or [])]
    assert "code_explain" not in str(res.get("assistant_reply", ""))


def test_d8_e2e_stubborn_model_fails_verification():
    """F3c enforcement: the deterministic evaluation is ground truth. A
    brain that explains instead of stating the output FAILS the goal —
    the pipeline must not mark a non-answer as achieved."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    def _stubborn_llm(**kwargs):
        return {"success": True, "id": "chat-real",
                "choices": [{"message": {
                    "content": "This code prints a sum of numbers."}}]}

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_stubborn_llm):
        res = CognitivePipeline.process_chat(user_text=D8_TEXT)

    assert res.get("goal_lifecycle_state") == "failed", \
        "a reply that never states the verified output must not pass"
    assert res.get("goal_verified") is False


def test_impure_code_e2e_still_demands_approval():
    """The gate is NOT weakened (item 6 constraint): a snippet that can
    touch the file system (open().read()) keeps the F6 contract —
    local_execute proposal, Level 3, one-click owner approval."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    def _fake_llm(**kwargs):
        return {"success": True, "id": "chat-real",
                "choices": [{"message": {"content": "placeholder"}}]}

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm):
        res = CognitivePipeline.process_chat(
            user_text="Run this Python code and tell me the output: "
                      "print(open('/tmp/x.txt').read())")

    assert res.get("recommendation", {}).get("action_type") == "local_execute"
    assert res.get("requires_approval") is True
    assert res.get("goal_lifecycle_state") == "waiting_for_user"
    assert res.get("approval_request") is not None
