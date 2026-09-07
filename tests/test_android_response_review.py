"""Android response-review slice: protocol alignment without a toolchain.

The repo has no Android compile in CI (documented in docs/REPOSITORY_AUDIT.md),
so Kotlin structure is pinned the way test_android_design_tokens.py pins it:
Python asserts the exact wiring in the Kotlin sources. Combined with the
backend-frame tests, this proves the Android client consumes the SAME
cognitive_metadata frame and the SAME endpoints/stores as the web and desktop
review flows — no parallel feedback subsystem.

What is asserted here:
- VoiceWebSocketClient parses `cognitive_metadata` and per-message `trace_id`
  in hydrated history, and the listener interface carries both callbacks.
- ChatViewModel binds the trace to the exact message, keeps blank-trace
  replies unreviewable, and reuses submission ids until the backend receipt.
- ApiClient targets the exact backend paths (usefulness, task evaluations,
  grounded introspection).
- ChatScreen mounts the review bar only on finished, trace-linked replies.
- The value domains the Android client enforces equal the backend models'.

Real device/GUI behavior remains explicitly unverified in this environment.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KT = REPO / "android/app/src/main/java/com/arena/voice"

WS_KT = KT / "websocket/VoiceWebSocketClient.kt"
VIEWMODEL_KT = KT / "ui/chat/ChatViewModel.kt"
API_KT = KT / "api/ApiClient.kt"
CHAT_SCREEN_KT = KT / "ui/screens/ChatScreen.kt"
REVIEW_BAR_KT = KT / "ui/components/ResponseReviewBar.kt"


def _source(path: Path) -> str:
    assert path.exists(), f"missing Kotlin source: {path}"
    return path.read_text(encoding="utf-8")


# ── WebSocket protocol: the same frames web/desktop consume ──────────────────

def test_ws_client_parses_cognitive_metadata_frame():
    src = _source(WS_KT)
    assert '"cognitive_metadata"' in src
    block = src.split('"cognitive_metadata"')[1].split("}")[0]
    for field in ("conversation_id", "message_id", "trace_id"):
        assert f'optString("{field}"' in block, f"cognitive_metadata must read {field}"
    assert "onCognitiveMetadata(convId, msgId, traceId)" in src


def test_ws_client_history_carries_trace_ids():
    src = _source(WS_KT)
    assert "data class HistoryMessage(" in src
    assert "traceId = m?.optString(\"trace_id\", \"\") ?: \"\"" in src
    assert "Triple<String, String, String>" not in src, (
        "history must use the trace-carrying HistoryMessage type, not bare triples"
    )
    assert (
        "fun onConversationHistory(conversationId: String, messages: List<HistoryMessage>) {}"
        in src
    )
    assert "fun onCognitiveMetadata(conversationId: String, messageId: String, traceId: String) {}" in src


# ── ChatViewModel: exact-message binding + retry identity ────────────────────

def test_chat_message_has_trace_and_metadata_handler_binds_it():
    src = _source(VIEWMODEL_KT)
    assert "val traceId: String = \"\"" in src
    assert "override fun onCognitiveMetadata(conversationId: String, messageId: String, traceId: String)" in src
    # A blank trace never binds: unlinked replies stay unreviewable.
    assert "if (conversationId != this.conversationId || traceId.isBlank()) return" in src
    assert "messages[idx].copy(traceId = traceId)" in src
    # A miss must NOT guess a binding (next history pull carries the trace).
    assert "we never guess a binding" in src


def test_viewmodel_history_hydration_populates_trace():
    src = _source(VIEWMODEL_KT)
    assert "override fun onConversationHistory(conversationId: String, history: List<HistoryMessage>)" in src
    assert "traceId = m.traceId," in src


def test_submission_ids_are_retry_identities_reused_until_receipt():
    src = _source(VIEWMODEL_KT)
    assert '"android-${UUID.randomUUID()}"' in src
    # The id is only released after a durable receipt — a retry reuses it.
    assert "if (ok) usefulnessSubmissionIds.remove(traceId)" in src
    assert "if (ok) evaluationSubmissionIds.remove(traceId)" in src
    assert "Not saved — retry the same rating." in src
    assert "Not saved — retry the same submission." in src


def test_viewmodel_validates_domains_and_gates_unlinked_traces():
    src = _source(VIEWMODEL_KT)
    assert 'usefulnessLevels = listOf("helpful", "partially_helpful", "not_helpful")' in src
    assert 'taskOutcomes = listOf("success", "failure", "unknown")' in src
    assert src.count('if (traceId.isBlank()) {\n            onResult(false, "This reply carries no trace') >= 2, (
        "both review actions must refuse blank-trace reviews"
    )
    assert "A task key is required to record an evaluation." in src


def test_evaluation_payload_is_measurement_only_with_backend_defaults():
    src = _source(VIEWMODEL_KT)
    assert '.put("split", "held_out")' in src
    assert '.put("condition", "single")' in src
    assert '.put("usefulness", "unknown")' in src
    assert '.put("correction_received", correctionReceived)' in src
    assert '.put("evidence_ids", JSONArray())' in src


# ── ApiClient: exact backend paths, shared with web/desktop ──────────────────

def test_api_client_targets_exact_backend_endpoints():
    src = _source(API_KT)
    assert '"/cognition/traces/${segment(traceId)}/usefulness"' in src
    assert '"POST",' in src and '"submission_id", submissionId' in src
    assert '"/benchmarks/phase1/tasks/evaluations?trace_id=${segment(traceId)}' in src
    assert '"/benchmarks/phase1/tasks/evaluations", "POST"' in src
    assert '"/self-awareness/introspection/${segment(traceId)}"' in src


# ── UI: gated mounting + honest measurement-only language ────────────────────

def test_chat_screen_mounts_review_bar_only_on_linked_replies():
    src = _source(CHAT_SCREEN_KT)
    assert "ResponseReviewBar(" in src
    # The gate must be visible at the render site and include the trace check.
    gate = re.search(
        r"if \(msg\.role == \"assistant\" && !msg\.isStreaming && msg\.traceId\.isNotBlank\(\)\)",
        src,
    )
    assert gate, "review bar must mount only on finished, trace-linked replies"
    assert "we never guess identity" in src


def test_review_bar_states_the_measurement_only_boundary():
    src = _source(REVIEW_BAR_KT)
    assert "Measurement only" in src
    assert "does " in src and "not change runtime truth, authorize work, or approve training." in src
    assert "Why this response?" in src
    # No hardcoded hex colors — the design-token rule (theme roles only).
    assert not re.search(r"Color\(0xFF", src)


def test_android_domains_match_the_shared_contracts():
    """The three clients must enforce identical value domains."""
    from desktop.response_review import (
        EVALUATION_CONDITIONS,
        EVALUATION_SPLITS,
        TASK_OUTCOMES,
        USEFULNESS_LEVELS,
    )

    vm = _source(VIEWMODEL_KT)
    for level in USEFULNESS_LEVELS:
        assert f'"{level}"' in vm
    for outcome in TASK_OUTCOMES:
        assert f'"{outcome}"' in vm
    for split in EVALUATION_SPLITS:
        assert f'"{split}"' in vm or split == "contract", (
            "held_out must be recorded; contract is web/desktop/benchmark scope"
        )
    assert '.put("split", "held_out")' in vm
    assert '.put("condition", "single")' in vm
    for condition in EVALUATION_CONDITIONS:
        assert f'"{condition}"' in vm or condition != "single"
