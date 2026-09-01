"""Read-only native actions pass the policy gate (owner diagnostics F2).

The owner's live run blocked the GoalReplanner's OWN re-observation probe
three times (D4, D7, D9):

    Unknown action requested: investigate - defaulting to Level 3
    ActionGate BLOCKED proposal 'investigate' at Policy Gate: Unknown
    action: requires explicit user approval by default

'investigate' is a NATIVE_EXECUTABLES virtual action (not a manifest
tool), so the ActionGate falls back to PolicyEvaluator — whose allowlist
predates the native-action vocabulary. The replanner's unknown-evidence
branch can therefore NEVER run: it proposes its probe, the gate bins it.

The read-only native actions (verified against their execution handlers
in MasterAgentOrchestrator): investigate / diagnostic (filesystem search
+ hardware stats read), formulate_answer / answer (compose a reply),
observe (no side effects). They are Level 0. Unknown actions still fail
closed at Level 3 — that default is the safety floor, not the bug.
"""

from app.cognition.action_proposal import ActionGate, ActionProposal
from app.policy import PolicyEvaluator

READ_ONLY_NATIVE_ACTIONS = ["investigate", "diagnostic",
                            "formulate_answer", "answer", "observe"]


def test_read_only_native_actions_are_level_0():
    for action in READ_ONLY_NATIVE_ACTIONS:
        allowed, reason, level = PolicyEvaluator.evaluate_action(action, {})
        assert allowed is True, (action, reason)
        assert level == 0, (action, level)


def test_unknown_actions_still_fail_closed():
    """The fix must not open the default: unknown names stay Level 3."""
    for action in ["definitely_not_an_action", "rm_rf_everything", ""]:
        allowed, _, level = PolicyEvaluator.evaluate_action(action, {})
        assert allowed is False, action
        assert level == 3, (action, level)


def test_replan_reobservation_probe_passes_the_action_gate():
    """The exact blocked path from the live run: an 'investigate' proposal
    must now clear the gate."""
    proposal = ActionProposal(
        action_type="investigate",
        payload={"query": "re-observe environment for unknown conditions",
                 "action_type": "investigate"},
    )
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.allowed is True, (gate.gate_name, gate.reason)


def test_conversational_answer_passes_the_gate():
    proposal = ActionProposal(action_type="formulate_answer",
                              payload={"query": "what can you do?"})
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.allowed is True, (gate.gate_name, gate.reason)
