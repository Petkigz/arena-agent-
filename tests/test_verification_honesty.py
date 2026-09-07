"""F3c (DIAG D1/D2/D6): a reply existing is not an answer being verified.

Live bugs (owner machine, 2026-09-01), all three verified 'achieved':
  * D1 'What is 17 * 24?' — the 3B model answered 396 (ground truth 408,
    computed by the agent's own deterministic calculator in evidence);
  * D2 'Analyze the CSV ... tell me the average of the amount column' —
    the mean was never stated in the reply;
  * D6 'Create a new tool called reverse_words ... install it' — a plan
    document was produced, no tool was installed.

Contract under test:
  * GoalVerifier: a DETERMINISTIC computation recorded in observed_state
    is ground truth — a reply that does not state the computed value has
    not delivered the answer, whatever the goal conditions say (FAILED,
    not achieved);
  * typed ANSWER_CONTENT conditions ('computed_answer_in_reply',
    'answer_value_in_reply'): with ground truth they are PASS/FAIL on the
    reply's content; WITHOUT ground truth they are UNKNOWN — delivery
    alone cannot verify correctness (WAITING_FOR_EVIDENCE, not achieved);
  * the interpreter emits the honest condition for each shape:
    arithmetic -> computed_answer_in_reply, statistic asks ->
    answer_value_in_reply, capability creation -> capability_installed +
    capability_executes_correctly;
  * end to end: the exact live D1 question with a wrong model reply is
    NOT achieved; with the computed value it is.
"""

from unittest.mock import patch

from app.cognition.condition_language import (
    AnswerContainsVerifiedValue,
    ObservationEnvironment,
    PASS,
    FAIL,
    UNKNOWN,
)
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.goal_verifier import GoalVerifier, GoalConditionType


D1_TEXT = "What is 17 * 24?"
D2_TEXT = ("Analyze the CSV file at C:/data/sales.csv and tell me the "
           "average of the amount column.")
D6_TEXT = ("Create a new tool called reverse_words that takes a "
           "string and returns the words in reverse order. Write it, "
           "test it, and install it as a permanent capability.")


def _verify(user_text, reply, observed_state=None, conditions=None):
    goal_rep = SemanticGoalInterpreter.interpret_goal(user_text)
    if conditions is not None:
        goal_rep.success_conditions = list(conditions)
    return GoalVerifier.verify_goal_achievement(
        goal_rep, [], reply, observed_state=observed_state
    )


def _arithmetic_observed_state():
    """The state the runtime records after the calculator ran (D1)."""
    return {
        "deterministic_answers": [
            {"expression": "17 * 24", "value": 408, "value_str": "408"},
        ],
    }


# ── D1: deterministic ground truth beats a confident wrong reply ────────

def test_reply_contradicting_deterministic_answer_fails():
    """The exact live failure: model says 396, ground truth 408."""
    res = _verify(
        D1_TEXT, "17 * 24 is 396.",
        observed_state=_arithmetic_observed_state(),
        conditions=["computed_answer_in_reply = true"],
    )
    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
    assert any("408" in str(fc) for fc in res.failed_conditions), (
        "the failed condition must name the computed ground truth"
    )


def test_reply_stating_deterministic_answer_verifies():
    res = _verify(
        D1_TEXT, "17 * 24 = 408",
        observed_state=_arithmetic_observed_state(),
        conditions=["computed_answer_in_reply = true"],
    )
    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
    assert "computed_answer_in_reply = true" in res.met_conditions


def test_deterministic_ground_truth_enforced_even_with_weak_conditions():
    """The unconditional check: even if the representation only says
    'response_delivered' (the interpreter missed the arithmetic shape),
    a recorded deterministic answer must still block false achievement."""
    res = _verify(
        D1_TEXT, "17 * 24 is 396.",
        observed_state=_arithmetic_observed_state(),
        conditions=["response_delivered = true"],
    )
    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED


# ── D2/D6: without ground truth, delivery is NOT verification ──────────

def test_answer_value_condition_without_ground_truth_is_unknown():
    """D2 shape: the mean is not stated and nothing computed it — the
    honest verdict is WAITING_FOR_EVIDENCE, never achieved."""
    res = _verify(
        D2_TEXT, "I analyzed the CSV file for you.",
        conditions=["answer_value_in_reply = true"],
    )
    assert res.verified_success is False
    assert res.is_unknown is True
    assert res.final_state == GoalLifecycleState.WAITING_FOR_EVIDENCE


def test_capability_creation_conditions_are_about_the_artifact():
    """D6 shape: creating a capability is verified by the capability
    existing and executing — not by a plan document being replied."""
    rep = SemanticGoalInterpreter.interpret_goal(D6_TEXT)
    assert "capability_installed = true" in rep.success_conditions
    assert "capability_executes_correctly = true" in rep.success_conditions
    assert "response_delivered = true" not in rep.success_conditions


def test_capability_plan_document_reply_is_not_achieved(monkeypatch):
    """The exact live failure: a plan document in the reply verified as
    achieved. With artifact-typed conditions it must not.

    Hermeticity (owner machine, live 2026-09-05 20:44): the property
    under test is 'plan document + capability NOT installed -> not
    achieved'. But a previous successful live D6 run had REALLY
    installed reverse_words to data/plugins/, the manifest discovers it
    from disk in every new process, and the verifier CORRECTLY probed
    it installed — the test was asserting machine state, not the
    property. The precondition is now controlled explicitly: the probe
    reports not-installed for this test regardless of what the machine
    has (a genuinely installed capability achieving the goal is the
    OTHER test's job, in the capability-chain file, with a unique
    name)."""
    from app.cognition.tool_registry import get_shared_registry
    registry = get_shared_registry()
    real_lookup = registry.effective_capability

    def _not_installed_for_this_test(name):
        if str(name or "").lower() == "reverse_words":
            return None
        return real_lookup(name)

    monkeypatch.setattr(registry, "effective_capability",
                        _not_installed_for_this_test)
    rep = SemanticGoalInterpreter.interpret_goal(D6_TEXT)
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "Here is my plan for the reverse_words tool: step 1 write "
                 "the code, step 2 test it, step 3 install it."
    )
    assert res.verified_success is False
    assert res.final_state != GoalLifecycleState.ACHIEVED


# ── interpreter: honest conditions per request shape ────────────────────

def test_interpreter_arithmetic_condition():
    rep = SemanticGoalInterpreter.interpret_goal(D1_TEXT)
    assert rep.success_conditions == ["computed_answer_in_reply = true"]


def test_interpreter_statistic_ask_condition():
    rep = SemanticGoalInterpreter.interpret_goal(D2_TEXT)
    assert rep.success_conditions == ["answer_value_in_reply = true"]


def test_interpreter_conversational_questions_unchanged():
    """Guard: ordinary knowledge/conversational questions keep the
    delivery criterion — this fix must not make every chat answer
    unverifiable."""
    rep = SemanticGoalInterpreter.interpret_goal(
        "What is the capital of France?")
    assert rep.success_conditions == ["response_delivered = true"]
    rep = SemanticGoalInterpreter.interpret_goal("hello, how are you?")
    assert rep.success_conditions == ["response_delivered = true"]


# ── classification + condition language node ────────────────────────────

def test_classify_answer_content_conditions():
    for cond in ("computed_answer_in_reply = true", "answer_value_in_reply = true"):
        ctype = GoalVerifier.classify_condition_type(
            cond, "knowledge_query", "conversation")
        assert ctype == GoalConditionType.ANSWER_CONTENT


class _FakeEnv(ObservationEnvironment):
    def __init__(self, values, reply):
        self._values = values
        self._reply = reply

    def verified_answer_values(self):
        return self._values

    def response_text(self):
        return self._reply


def test_answer_contains_verified_value_node_verdicts():
    node = AnswerContainsVerifiedValue()
    # No ground truth -> UNKNOWN (delivery is not verifiable correctness).
    v = node.evaluate(_FakeEnv([], "some answer"))
    assert v.status == UNKNOWN
    # Ground truth present and stated -> PASS.
    v = node.evaluate(_FakeEnv([408], "17 * 24 = 408"))
    assert v.status == PASS
    # Ground truth present and contradicted -> FAIL.
    v = node.evaluate(_FakeEnv([408], "17 * 24 is 396"))
    assert v.status == FAIL


# ── end to end: the exact live D1 question through process_chat ─────────

def _llm_replying(content):
    def _fake(**kwargs):
        return {
            "success": True,
            "id": "chat-real",
            "choices": [{"message": {"content": content}}],
        }
    return _fake


def test_d1_e2e_wrong_model_reply_is_not_achieved():
    """RED proof of the live bug: the model ignores the verified
    calculation evidence and answers 396 — the goal must FAIL."""
    from app.cognition.cognitive_pipeline import CognitivePipeline
    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_llm_replying("17 * 24 is 396.")):
        res = CognitivePipeline.process_chat(user_text=D1_TEXT)
    assert res["goal_lifecycle_state"] == "failed"
    assert res["goal_verified"] is False
    assert res["assistant_reply"].startswith("17 * 24 is 396.")
    assert "Epistemic status:" in res["assistant_reply"]
    assert res["epistemic_presentation"]["confidence_label"] in {"Tentative", "Unknown"}


def test_d1_e2e_correct_reply_from_evidence_achieves():
    from app.cognition.cognitive_pipeline import CognitivePipeline
    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_llm_replying("17 * 24 = 408")):
        res = CognitivePipeline.process_chat(user_text=D1_TEXT)
    assert res["goal_lifecycle_state"] == "achieved"
    assert res["goal_verified"] is True
    assert res["assistant_reply"].startswith("17 * 24 = 408")
    assert "Epistemic status:" in res["assistant_reply"]
    assert res["epistemic_presentation"]["confidence_label"] in {"Highly confident", "Moderately confident"}
