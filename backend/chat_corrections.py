"""In-chat owner corrections.

The owner should be able to correct the assistant in the conversation
itself — "no, you searched the wrong folder, search the whole pc" — and
have that understood AS a correction, not just as ordinary chatter.

This module is deliberately thin and conservative:

- Detection is deterministic explicit-marker matching. It prefers missing
  a casually phrased correction over fabricating a correction record from
  an ambiguous message; the Review-response form remains available for
  anything this misses.
- Recording reuses the EXISTING owner-correction path
  (``TrainingExampleStore.propose_owner_correction`` + the existing
  ``CorrectionMeasurementStore``). No parallel correction store exists.
- The candidate stays PENDING the existing owner review; nothing auto-trains.
- The corrected turn still runs as an ordinary message afterwards: the
  correction instruction ("search the whole pc") is executed by the normal
  cognitive path, not by this module.
"""

from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# Explicit opener markers: the message must START with one of these
# (whitespace-insensitive). Conservative by design — "no way, nice!"
# does not match because it is "no way", not "no," / "no." / "no!".
_OPENER_MARKERS = (
    "no,", "no.", "no!", "nope",
    "wrong", "incorrect",
    "that's wrong", "thats wrong", "that is wrong",
    "you're wrong", "youre wrong", "you are wrong",
    "you got it wrong", "you got that wrong",
    "that's not right", "thats not right", "that is not right",
    "not what i asked", "not what i meant", "not what i wanted",
    "that's not what", "thats not what", "that is not what",
    "i meant", "i didn't mean", "i did not mean", "i was asking",
    "you misunderstood", "you misread", "you searched the wrong",
    "you looked in the wrong", "you checked the wrong", "you used the wrong",
    "try again", "do it over",
    "don't do it that way", "do not do it that way", "not like that",
)

# Strong phrases that mark a correction anywhere in the message. Each is
# specific enough that ordinary questions are unlikely to contain them.
_STRONG_MARKERS = (
    "you're wrong", "youre wrong", "you are wrong",
    "that's wrong", "thats wrong", "that is wrong",
    "you searched the wrong", "you looked in the wrong",
    "you checked the wrong", "you used the wrong",
    "wrong folder", "wrong directory", "wrong place", "wrong location",
    "wrong file", "wrong drive",
    "search the whole", "whole pc", "whole computer", "entire pc",
    "entire computer", "all drives", "every drive",
    "i meant", "i didn't mean", "i did not mean",
    "not what i asked", "not what i meant",
    "you misunderstood",
    "don't use", "do not use", "should have used", "instead of",
    "next time", "from now on",
)

# Classification order matters: the most specific signal wins.
_TYPE_SIGNALS = (
    ("intent", (
        "i meant", "i didn't mean", "i did not mean",
        "not what i asked", "not what i meant", "not what i wanted",
        "i was asking", "you misunderstood", "you misread",
    )),
    ("retrieval", (
        "you searched the wrong", "you looked in the wrong",
        "you checked the wrong", "searched the wrong",
        "wrong folder", "wrong directory", "wrong place", "wrong location",
        "wrong file", "wrong drive",
        "search the whole", "whole pc", "whole computer", "entire pc",
        "entire computer", "all drives", "every drive",
    )),
    ("routing", (
        "you used the wrong", "used the wrong",
        "don't use", "do not use", "should have used", "instead of",
    )),
    ("procedural", (
        "do it that way", "not like that", "next time", "from now on",
        "do it over",
    )),
    ("factual", (
        "that's wrong", "thats wrong", "that is wrong",
        "you're wrong", "youre wrong", "you are wrong",
        "you got it wrong", "you got that wrong",
        "that's not right", "thats not right", "that is not right",
        "incorrect",
    )),
)

# Openers that alone signal a factual disagreement even without a strong
# phrase elsewhere in the message.
_FACTUAL_OPENERS = (
    "wrong", "incorrect", "nope",
    "that's wrong", "thats wrong", "that is wrong",
    "you're wrong", "youre wrong", "you are wrong",
    "that's not right", "thats not right", "that is not right",
)


def detect_chat_correction(content: str) -> Optional[Dict[str, str]]:
    """Return ``{"correction_type", "signal"}`` for an explicit in-chat
    correction, else ``None``.

    Conservative: an ambiguous message yields ``None`` rather than a guessed
    correction record. The Review-response form remains the precise path.
    """
    if not content or not content.strip():
        return None
    lowered = " ".join(content.lower().split())
    signal = None
    for marker in _OPENER_MARKERS:
        if lowered.startswith(marker):
            signal = marker
            break
    if signal is None:
        for marker in _STRONG_MARKERS:
            if marker in lowered:
                signal = marker
                break
    if signal is None:
        return None

    for correction_type, phrases in _TYPE_SIGNALS:
        if any(phrase in lowered for phrase in phrases):
            return {"correction_type": correction_type, "signal": signal}
    if lowered.startswith(_FACTUAL_OPENERS):
        return {"correction_type": "factual", "signal": signal}
    # An opener matched without any classifiable content — record it
    # honestly as unspecified rather than guessing a type.
    return {"correction_type": "unspecified", "signal": signal}


def resolve_target_trace(
    conversation_id: str, *, fetch=None,
) -> Optional[Dict[str, str]]:
    """Resolve the trace of the most recent assistant reply in a conversation.

    Uses the EXISTING persisted conversation rows (role == 'assistant' with a
    runtime-authored trace_id). Legacy rows without a trace link are skipped —
    they can never be correction targets. Returns
    ``{"trace_id", "reply_excerpt"}`` or ``None``.
    """
    if fetch is None:
        from app.database import db
        fetch = db.get_conversation_messages
    try:
        messages: List[Dict[str, Any]] = fetch(conversation_id, limit=50) or []
    except Exception as exc:  # store failure is not a correction failure
        app_logger.warning(f"Could not read conversation for correction link: {exc}")
        return None
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        trace_id = message.get("trace_id")
        if isinstance(trace_id, str) and trace_id.strip():
            return {
                "trace_id": trace_id.strip(),
                "reply_excerpt": str(message.get("content", ""))[:400],
            }
    return None


def record_chat_correction(
    runtime: Any, conversation_id: str, content: str, *, fetch=None,
) -> Optional[Dict[str, Any]]:
    """Detect and record an in-chat correction through the existing path.

    Returns the event payload for the conversation room, or ``None`` when the
    message is not an explicit correction or no prior trace is linkable.
    A duplicate correction (same trace + same redacted instruction) is
    reported with ``duplicate=True`` and does NOT record a second measurement.
    """
    detected = detect_chat_correction(content)
    if detected is None:
        return None
    target = resolve_target_trace(conversation_id, fetch=fetch)
    if target is None:
        # No linkable prior reply (new conversation, or legacy traceless rows):
        # an honest no-op — the Review form remains for manual targeting.
        app_logger.info(
            f"In-chat correction signal in {conversation_id} had no linkable "
            f"prior trace; not recorded ({detected['signal']})"
        )
        return None

    training = getattr(runtime, "training_examples", None)
    measurements = getattr(runtime, "correction_measurements", None)
    if training is None or measurements is None:
        app_logger.warning("Correction stores unavailable; in-chat correction skipped")
        return None

    from app.cognition.training_examples import redact_training_text

    response_clean, _ = redact_training_text(content)
    for existing in training.list():
        if (
            getattr(existing, "source_trace_id", "") == target["trace_id"]
            and getattr(existing, "action_type", "") == "owner_correction"
            and getattr(existing, "response", "") == response_clean
        ):
            app_logger.info(
                f"In-chat correction in {conversation_id} duplicates candidate "
                f"{existing.candidate_id}; not re-recorded"
            )
            return {
                "correction_type": detected["correction_type"],
                "signal": detected["signal"],
                "target_trace_id": target["trace_id"],
                "candidate_id": existing.candidate_id,
                "generalized": bool(
                    (existing.strategy_update or {}).get("generalized")
                ),
                "duplicate": True,
            }

    candidate = training.propose_owner_correction(
        prompt="",
        response=content,
        skill_name="general",
        note=(
            f"In-chat correction (type: {detected['correction_type']}, "
            f"signal: {detected['signal']}). The preferred response is not yet "
            "written; edit this candidate before approval."
        ),
        source_trace_id=target["trace_id"],
        action_type="owner_correction",
        strategy_store=getattr(runtime, "outcomes", None),
    )
    if candidate is None:
        app_logger.warning("In-chat correction candidate could not be created")
        return None

    strategy_update = candidate.strategy_update or {}
    generalized = bool(strategy_update.get("generalized"))
    measurement = measurements.record(
        trace_id=target["trace_id"],
        correction_type=detected["correction_type"],
        expected_effect=(
            "repeated evidence may adjust the linked strategy"
            if generalized
            else "keep the correction local until repeated evidence exists"
        ),
        strategy_update=strategy_update,
        evidence=list(candidate.evidence),
    )
    app_logger.info(
        f"In-chat correction recorded against {target['trace_id']} "
        f"(type={detected['correction_type']}, candidate={candidate.candidate_id}, "
        f"measurement={getattr(measurement, 'correction_id', 'n/a')})"
    )
    return {
        "correction_type": detected["correction_type"],
        "signal": detected["signal"],
        "target_trace_id": target["trace_id"],
        "candidate_id": candidate.candidate_id,
        "generalized": generalized,
        "duplicate": False,
    }
