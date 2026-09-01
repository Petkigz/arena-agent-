"""F3a (DIAG D4): per-step success conditions for compound requests.

Live bug (owner machine, 2026-09-01): 'Find files matching requirements,
read the first one, summarize it, then check the tests still pass.' produced
ONE success condition ('file_path_identified = true') — step 1 only. The
other three steps were invisible to verification, so a run that finished
step 1 and replied anything verified as 'achieved'.

Contract under test (representation side):
  * a request with >= 2 recognizable sequential steps gets ONE typed
    success condition PER STEP (covering every step, not just the first);
  * every emitted condition is one the GoalVerifier actually classifies
    (a real condition type with a resolver — not free text that resolves
    to nothing);
  * single-step and conversational requests keep their existing
    conditions (no breadth regression).

This mirrors the owner diagnostic d4_compound_goal_conditions, which
measures step-keyword coverage ('path', 'read', 'summar', 'test') in the
emitted conditions.
"""

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier, GoalConditionType


D4_TASK = (
    "Find files matching requirements, read the first one, "
    "summarize it, then check the tests still pass."
)


def _conditions_for(text: str):
    rep = SemanticGoalInterpreter.interpret_goal(text)
    return [str(c) for c in rep.success_conditions]


def _step_coverage(conditions):
    kws = ["path", "read", "summar", "test"]
    return sum(1 for kw in kws if any(kw in c.lower() for c in conditions))


def test_d4_compound_request_covers_every_step():
    """The exact live D4 input: all four steps must appear in conditions."""
    conditions = _conditions_for(D4_TASK)
    covered = _step_coverage(conditions)
    assert covered == 4, (
        f"Compound request covers {covered}/4 steps; conditions: {conditions}"
    )


def test_d4_compound_conditions_are_verifier_classifiable():
    """Each per-step condition must classify to a REAL GoalConditionType —
    conditions that resolve to nothing would be representation theater."""
    conditions = _conditions_for(D4_TASK)
    rep = SemanticGoalInterpreter.interpret_goal(D4_TASK)
    for cond in conditions:
        ctype = GoalVerifier.classify_condition_type(
            cond, rep.primary_intent_type, rep.target_domain
        )
        assert isinstance(ctype, GoalConditionType), (
            f"condition {cond!r} does not classify to a condition type"
        )
    # The find-step condition is the established ARTIFACT-typed one.
    assert "file_path_identified = true" in conditions


def test_compound_conditions_are_distinct_per_step():
    conditions = _conditions_for(D4_TASK)
    assert len(conditions) == len(set(conditions)), (
        f"duplicate step conditions: {conditions}"
    )
    # One condition per step, not one global blob.
    assert len(conditions) >= 4


def test_semicolon_then_first_finally_markers_also_split():
    """Step markers beyond the D4 comma/then phrasing."""
    conditions = _conditions_for(
        "First find the config file; then read it. Finally summarize it."
    )
    covered = _step_coverage(conditions)
    assert covered >= 3, f"marker variants cover {covered}/3; got {conditions}"


def test_single_step_request_not_overridden():
    """A plain single-step find keeps its existing filesystem condition —
    the compound override must not fire (no false breadth)."""
    conditions = _conditions_for("Find files matching requirements")
    assert conditions == ["file_path_identified = true"]


def test_conversational_request_unchanged():
    """Plain chat keeps the response-delivered criterion."""
    conditions = _conditions_for("hello there, how are you doing")
    assert conditions == ["response_delivered = true"]


def test_unrecognized_clauses_contribute_nothing():
    """Fragments without a recognizable step verb add no conditions, so a
    comma-heavy conversational request is not overridden."""
    conditions = _conditions_for("tell me about paris, rome, and madrid")
    assert conditions == ["response_delivered = true"]
