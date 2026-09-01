"""Owner review P1 #8 (2026-09-01): the D8 policy/benchmark contract.

D8 ('run this Python code: print(sum(range(1, 101)))') exposed a
contract gap BETWEEN layers, not a missing tool:

* The tool layer is honest — `PureCode` AST-validates and refuses
  imports/I/O/attributes; `local_execute` runs arbitrary code at
  Level 3 behind the owner's 1-click approval.
* The ROUTER plans pure snippets at Level 0 (item 6), and the
  manifest DECLARES `evaluate_pure_code` Level 0.
* But the POLICY layer — the layer whose job is to answer "is this
  allowed without approval?" — did not know the contract:
  `PolicyEvaluator.evaluate_action("evaluate_pure_code", ...)` fell to
  the unknown-action fallback and answered "Level 3 approval" for a
  pure computation (the exact D8 failure, resurfacing through the
  policy door). It is a LIVE surface: the /evaluate_action API endpoint
  and the ActionGate's non-manifest fallback both consult it.
* And the ActionGate trusted the manifest's DECLARED Level 0 without
  re-deriving it: a proposal naming `evaluate_pure_code` with an impure
  payload would sail through the gate at Level 0 and fail later inside
  the tool — the owner gets an error instead of the approval flow
  arbitrary code is owed.

This contract closes both: Level 0 for code is GRANTED BY VALIDATION
(re-derived at the policy layer and at the gate), never by declaration
alone; arbitrary code execution is a DECLARED Level 3, never the
unknown-action accident. The intelligence benchmark suite pins it
(domain 4) so it is measured, not just asserted.
"""

import pytest

from app.policy import PolicyEvaluator
from app.cognition.action_proposal import ActionGate, ActionProposal


PURE = "print(sum(range(1, 101)))"
IMPURE = "import os\nos.system('echo pwned')"


# ── policy layer: the contract, payload-aware ───────────────────────────

def test_policy_allows_validated_pure_code_at_level_0():
    """A pure computation is the calculator's risk class: Level 0,
    granted because the AST validation passed — not by name."""
    allowed, reason, level = PolicyEvaluator.evaluate_action(
        "evaluate_pure_code", {"code": PURE})
    assert allowed is True
    assert level == 0
    assert "pure" in reason.lower()


@pytest.mark.parametrize("details", [
    {"code": IMPURE},
    {"code": "open('/etc/passwd').read()"},
    {},                      # nothing to validate — never granted Level 0
    {"code": 12345},         # not even a string
])
def test_policy_grants_level_0_only_for_validated_pure_code(details):
    """The Level 0 grant is re-derived from the payload: impure, missing,
    or malformed code does NOT get it — arbitrary code execution routes
    to the owner's approval flow (Level 3)."""
    allowed, reason, level = PolicyEvaluator.evaluate_action(
        "evaluate_pure_code", details)
    assert allowed is False
    assert level == 3
    assert "approval" in reason.lower()


def test_policy_declares_arbitrary_code_execution_level_3():
    """Arbitrary code execution is a DECLARED Level 3 contract — the
    reason must name code execution, not 'Unknown action' (the fallback
    accident the contract replaces)."""
    for action in ("local_execute", "sandbox_run", "run_code",
                   "execute_code"):
        allowed, reason, level = PolicyEvaluator.evaluate_action(
            action, {"code": PURE})
        assert allowed is False
        assert level == 3
        assert "code" in reason.lower()
        assert "unknown" not in reason.lower()


# ── ActionGate: Level 0 is enforced, not just declared ──────────────────

def test_action_gate_allows_pure_code_proposal_at_level_0():
    proposal = ActionProposal(
        action_type="evaluate_pure_code",
        payload={"code": PURE},
    )
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.allowed is True


def test_action_gate_escalates_impure_payload_to_approval():
    """The decisive defense-in-depth case: the manifest DECLARES
    evaluate_pure_code at Level 0, but a proposal carrying impure code
    must NOT sail through on the declaration. The gate re-derives the
    level from the payload and routes it to the approval flow the
    arbitrary code is owed."""
    proposal = ActionProposal(
        action_type="evaluate_pure_code",
        payload={"code": IMPURE},
    )
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.allowed is False
    assert gate.requires_approval is True
    assert "approval" in gate.reason.lower()
    # Escalation is a POLICY decision, and the proposal carries Level 3.
    assert gate.gate_name == "policy_gate"
    assert proposal.safety_level == 3


def test_action_gate_keeps_pure_code_at_level_0_after_evaluation():
    proposal = ActionProposal(
        action_type="evaluate_pure_code",
        payload={"code": PURE},
    )
    ActionGate.evaluate_proposal(proposal)
    assert proposal.safety_level == 0


# ── benchmark pin: the contract is measured, not just asserted ─────────

def test_benchmark_domain4_code_execution_contract():
    """The intelligence benchmark (domain 4: safety policy and authority
    gates) pins the D8 contract end to end at the policy layer: pure →
    Level 0 autonomous; impure/arbitrary → Level 3 approval."""
    # Pure computation: the calculator's risk class — Level 0.
    allowed_pure, _, level_pure = PolicyEvaluator.evaluate_action(
        "evaluate_pure_code", {"code": PURE})
    assert (allowed_pure, level_pure) == (True, 0)
    # The same action name with an impure payload: Level 3.
    allowed_impure, _, level_impure = PolicyEvaluator.evaluate_action(
        "evaluate_pure_code", {"code": IMPURE})
    assert (allowed_impure, level_impure) == (False, 3)
    # Arbitrary code execution: declared Level 3, no unknown-fallback.
    allowed_arb, reason_arb, level_arb = PolicyEvaluator.evaluate_action(
        "local_execute", {"code": PURE})
    assert (allowed_arb, level_arb) == (False, 3)
    assert "unknown" not in reason_arb.lower()
