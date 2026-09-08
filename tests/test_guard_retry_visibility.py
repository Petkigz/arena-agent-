"""Guard-refusal visibility in chat (owner vision charter §6 raw-input item).

RawInputGuard refusals were typed and retryable inside the execution payload
but invisible to the owner: the chat reply never mentioned them. Pins the
deterministic surfacing pass.
"""
import os

os.environ.setdefault("ARENA_ANNOUNCEMENT_GUARD", "0")

import pytest

from app.cognition.guard_visibility import guard_retry_note, surface_guard_retry


def _refusal(reason: str, error: str = "detail") -> dict:
    return {
        "success": False,
        "refused": True,
        "guard_passed": False,
        "attempted": False,
        "guard_reason": reason,
        "error": error,
    }


def test_topology_changed_refusal_becomes_owner_visible():
    result = {
        "assistant_reply": "Done with your request.",
        "outputs": {"manifest_res": _refusal("topology_changed")},
        "user_text": "click the delete button",
    }
    out = surface_guard_retry(result)
    assert "did NOT complete the screen input" in out["assistant_reply"]
    assert "display setup changed" in out["assistant_reply"]
    assert 'say "retry"' in out["assistant_reply"]
    assert out["guard_retry_surfaced"] == ["topology_changed"]


@pytest.mark.parametrize(
    "reason,expect_words",
    [
        ("process_gone", "has closed"),
        ("unknown_grounding", "gone or no longer active"),
        ("missing_grounding", "no verified window+process target"),
        ("stale_observation", "too old to trust"),
        ("point_outside_window", "outside the verified target window"),
    ],
)
def test_typed_reasons_get_plain_words(reason, expect_words):
    note = guard_retry_note(reason)
    assert expect_words in note
    assert "retry" in note


def test_unknown_reason_still_surfaced_with_raw_name():
    note = guard_retry_note("some_new_reason")
    assert "some_new_reason" in note
    assert "retry" in note


def test_nested_refusal_deep_in_payload_is_found():
    result = {
        "assistant_reply": "ok",
        "executed_actions": ["Raw click"],
        "outputs": {
            "step_results": [
                {"tool": "mouse_click", "result": _refusal("process_gone")}
            ]
        },
    }
    out = surface_guard_retry(result)
    assert out["guard_retry_surfaced"] == ["process_gone"]
    assert "has closed" in out["assistant_reply"]


def test_no_refusal_leaves_reply_untouched():
    result = {
        "assistant_reply": "All done, verified on screen.",
        "outputs": {"manifest_res": {"success": True}},
    }
    out = surface_guard_retry(result)
    assert out["assistant_reply"] == "All done, verified on screen."
    assert "guard_retry_surfaced" not in out


def test_duplicate_refusals_collapse_to_one_note():
    result = {
        "assistant_reply": "tried",
        "outputs": {
            "a": _refusal("topology_changed"),
            "b": _refusal("topology_changed"),
        },
    }
    out = surface_guard_retry(result)
    assert out["assistant_reply"].count("Guard note:") == 1


def test_reason_already_named_in_reply_is_not_repeated():
    # Suppression hook: the reply literally names the refusal reason in its
    # spoken form — no duplicate note. (A reply that explains a refusal in
    # other words still gets the note: it lacks the retry path.)
    reply = (
        "The click was refused — topology changed since the plan was made. "
        'Say "retry" to re-ground and try again.'
    )
    result = {
        "assistant_reply": reply,
        "outputs": {"a": _refusal("topology_changed")},
    }
    out = surface_guard_retry(result)
    assert out["assistant_reply"] == reply
    assert "guard_retry_surfaced" not in out


def test_distinct_refusals_each_surface():
    result = {
        "assistant_reply": "",
        "outputs": {
            "a": _refusal("topology_changed"),
            "b": _refusal("process_gone"),
            "c": _refusal("unknown_grounding"),
        },
    }
    out = surface_guard_retry(result)
    assert sorted(out["guard_retry_surfaced"]) == [
        "process_gone",
        "topology_changed",
        "unknown_grounding",
    ]
    assert out["assistant_reply"].count("Guard note:") == 3


def test_composes_with_completion_honesty_guard():
    """Honesty guard replaces a hollow promise; the refusal note still lands
    after it — the owner sees the truth AND the retry path."""
    from app.cognition.completion_honesty import enforce_completion_honesty

    result = {
        "assistant_reply": "I'm working on it now!",
        "executed_actions": [],
        "outputs": {"manifest_res": _refusal("topology_changed")},
        "user_text": "click save",
    }
    out = surface_guard_retry(enforce_completion_honesty(result))
    assert "Straight answer" in out["assistant_reply"]  # honesty replaced it
    assert "Guard note:" in out["assistant_reply"]      # visibility appended
    assert "display setup changed" in out["assistant_reply"]


def test_scan_depth_bounded_and_garbage_safe():
    # Cyclic + weird payloads must not hang or raise.
    cyc: dict = {}
    cyc["self"] = cyc
    result = {"assistant_reply": "x", "outputs": cyc}
    out = surface_guard_retry(result)
    assert out["assistant_reply"] == "x"
