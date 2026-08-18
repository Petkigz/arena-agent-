from app.cognition.action_planner import ActionPlanner
from app.cognition.action_proposal import ActionProposal


def test_action_planner_preserves_winning_candidate_payload():
    """
    P1/P0 Fix Verification:
    Verify that ActionPlanner constructs ActionProposal directly from the winning candidate,
    preserving 100% of custom candidate payload attributes (e.g. search_dir, memory_lesson, phone_number, sms_body)
    rather than discarding them and rebuilding a simplified payload.
    """
    custom_candidates = [
        {
            "name": "Local Filesystem Specific Search",
            "action_type": "search_files",
            "payload": {
                "query": "invoice_2026",
                "action_type": "search_files",
                "search_dir": "C:\\Documents\\Invoices",
                "memory_lesson": "invoices are stored in documents invoices folder"
            }
        },
        {
            "name": "Web Search Fallback",
            "action_type": "web_search",
            "payload": {
                "query": "invoice_2026",
                "action_type": "web_search"
            }
        }
    ]

    proposal = ActionPlanner.plan_and_evaluate_action(
        goal_text="Find invoice 2026",
        complexity="fast",
        candidates=custom_candidates
    )

    assert isinstance(proposal, ActionProposal)
    assert proposal.action_type == "search_files"

    # Custom payload attributes MUST be preserved in proposal.payload
    payload = proposal.payload
    assert payload.get("search_dir") == "C:\\Documents\\Invoices"
    assert payload.get("memory_lesson") == "invoices are stored in documents invoices folder"
    assert payload.get("query") == "invoice_2026" or payload.get("query") == "Find invoice 2026"


def test_action_proposal_from_candidate_preserves_custom_keys():
    """
    Verify ActionProposal.from_candidate constructs ActionProposal carrying all custom keys.
    """
    candidate = {
        "name": "Phone SMS Command",
        "action_type": "send_sms",
        "payload": {
            "phone_number": "555-1234",
            "sms_body": "Hello from Arena",
            "device_id": "adb_device_1"
        }
    }

    prop = ActionProposal.from_candidate(candidate, goal_text="Send SMS", complexity="fast")

    assert prop.action_type == "send_sms"
    assert prop.payload["phone_number"] == "555-1234"
    assert prop.payload["sms_body"] == "Hello from Arena"
    assert prop.payload["device_id"] == "adb_device_1"
