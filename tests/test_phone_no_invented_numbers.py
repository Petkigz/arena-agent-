"""P0 bottleneck #10: phone operations must NEVER invent a number.
The old '555-0199' fallback could text a real wrong person — a
correctness bug, not just a safety one. Resolution order: explicit
payload number > dialable number in the recipient slot > REAL contacts
lookup; unknown/ambiguous names become clarifications, never guesses."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.execution_result import ExecutionStatus
from app.tools.android_adb_controller import AndroidADBController

OFFLINE = {"success": False, "error": "Model provider is unavailable", "choices": []}

CONTACTS = [
    {"name": "John Mukasa", "phone": "+256700111222"},
    {"name": "John B.", "phone": "+256700333444"},
    {"name": "Mom", "phone": "+256777000111"},
    {"name": "No Phone", "phone": ""},
]


def _fake_list(query=""):
    q = (query or "").strip().lower()
    return [c for c in CONTACTS if q in c.get("name", "").lower()]


def _run(user_text, payload=None):
    prop = SimpleNamespace(action_type="phone_command", payload=payload or {},
                           proposal_id="prop_test")
    with patch("app.agents.master_agent.llm_client.generate_chat_completion",
               return_value=OFFLINE), \
         patch("app.tools.contacts.ContactsTool.list_contacts", side_effect=_fake_list):
        return MasterAgentOrchestrator.execute_proposal(prop, user_text)


def test_unknown_contact_asks_instead_of_inventing():
    with patch.object(AndroidADBController, "send_sms",
                      side_effect=AssertionError("MUST NOT SEND")):
        res = _run("text Sarah I'm running late")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "don't have a contact named 'sarah'" in res.executed_actions[0].lower()
    assert "which number" in res.executed_actions[0].lower()
    assert res.outputs["phone_res"]["clarification_required"] is True


def test_ambiguous_contact_lists_candidates_and_stops():
    with patch.object(AndroidADBController, "send_sms",
                      side_effect=AssertionError("MUST NOT SEND")):
        res = _run("text John I'm running late")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "multiple contacts match 'john'" in res.executed_actions[0].lower()
    assert "John Mukasa" in res.executed_actions[0] and "John B." in res.executed_actions[0]


def test_single_contact_match_texts_the_real_number_with_provenance():
    with patch.object(AndroidADBController, "send_sms",
                      return_value={"success": True}) as mock_sms:
        res = _run("text Mom I'm running late")
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    args, _ = mock_sms.call_args
    assert args[0] == "+256777000111"          # the REAL number
    assert args[1] == "I'm running late"       # body split from the sentence
    assert "resolved from contact 'Mom'" in res.executed_actions[0]


def test_contact_without_number_is_honest():
    with patch.object(AndroidADBController, "send_sms",
                      side_effect=AssertionError("MUST NOT SEND")):
        res = _run("text No Phone a message")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "no phone number stored" in res.executed_actions[0].lower()


def test_explicit_number_in_recipient_slot_is_used():
    with patch.object(AndroidADBController, "send_sms",
                      return_value={"success": True}) as mock_sms:
        res = _run("text 0771234567 that I'm running late")
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    assert mock_sms.call_args[0][0] == "0771234567"


def test_payload_number_takes_precedence():
    with patch.object(AndroidADBController, "send_sms",
                      return_value={"success": True}) as mock_sms:
        res = _run("text whoever something", payload={"phone_number": "+256999888777"})
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    assert mock_sms.call_args[0][0] == "+256999888777"


def test_body_digits_are_never_assembled_into_a_number():
    """'text John I'm 30 minutes late' — the 30 is a quantity in the body,
    not a dialable recipient."""
    with patch.object(AndroidADBController, "send_sms",
                      side_effect=AssertionError("MUST NOT SEND")):
        res = _run("text Sarah I'm 30 minutes late")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "30" != res.outputs["phone_res"].get("error", "x")[:2]


def test_bare_text_with_no_target_asks():
    with patch.object(AndroidADBController, "send_sms",
                      side_effect=AssertionError("MUST NOT SEND")):
        res = _run("send a text message")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "no phone number or contact name" in res.executed_actions[0].lower()


def test_call_path_never_invents_either():
    with patch.object(AndroidADBController, "make_phone_call",
                      side_effect=AssertionError("MUST NOT DIAL")):
        res = _run("call Sarah")
    assert res.execution_status is ExecutionStatus.FAILED
    assert "call not placed" in res.executed_actions[0].lower()

    with patch.object(AndroidADBController, "make_phone_call",
                      return_value={"success": True}) as mock_call:
        res = _run("call Mom")
    assert res.execution_status is ExecutionStatus.SUCCEEDED
    assert mock_call.call_args[0][0] == "+256777000111"


def test_no_fake_number_literal_remains():
    src = open("app/agents/master_agent.py", encoding="utf-8").read()
    assert "555-0199" not in src
