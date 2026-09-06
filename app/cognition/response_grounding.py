"""Reconcile generated responses with authoritative evidence.

This is intentionally conservative. It does not attempt to prove every
natural-language sentence. It handles the high-value, structured cases that
already have authoritative runtime evidence: deterministic answers and an
observation that explicitly returned no result.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ResponseGrounding:
    status: str  # verified | contradicted | unsupported | unknown
    supported: bool
    unsupported_claims: List[str] = field(default_factory=list)
    authoritative_facts: List[str] = field(default_factory=list)
    recovery_applied: bool = False
    replacement_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _value_mentions(reply: str, value: Any, value_str: Optional[str] = None) -> bool:
    text = str(reply or "")
    candidates = [str(value_str or "").strip(), str(value).strip()]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = None

    for candidate in candidates:
        if not candidate:
            continue
        if numeric is None:
            if candidate in text:
                return True
            continue
        # Numeric values need token boundaries: value "4" must not match
        # the unrelated value "41". Accept the supplied display form and a
        # normalized decimal form, including comma-free text.
        numeric_forms = {candidate, str(numeric).rstrip("0").rstrip(".")}
        for form in numeric_forms:
            if not form:
                continue
            number_pattern = rf"(?<![\d.]){re.escape(form.replace(',', ''))}(?!\d|\.\d)"
            if re.search(number_pattern, text.replace(",", "")):
                return True
    return False


def reconcile_response(
    reply: str,
    *,
    deterministic_answers: Optional[Iterable[Dict[str, Any]]] = None,
    observation_evidence: str = "",
) -> tuple[str, ResponseGrounding]:
    """Return a safe response and the evidence reconciliation result.

    A deterministic mismatch is corrected using the authoritative computed
    value. An explicitly empty observation cannot be narrated as a positive
    discovery. Other prose is left unchanged and receives a conservative
    status rather than a fabricated rewrite.
    """
    reply = str(reply or "")
    facts: List[str] = []
    mismatches: List[str] = []
    answers = [item for item in (deterministic_answers or []) if isinstance(item, dict)]
    for answer in answers:
        value = answer.get("value")
        if value is None:
            continue
        expression = str(answer.get("expression") or "computed result")
        value_str = str(answer.get("value_str") or value)
        fact = f"{expression} = {value_str}"
        facts.append(fact)
        if not _value_mentions(reply, value, value_str):
            mismatches.append(fact)

    if mismatches:
        replacement = (
            "I could not verify the generated answer as written. "
            "The authoritative result is: " + "; ".join(mismatches) + "."
        )
        return replacement, ResponseGrounding(
            status="contradicted",
            supported=False,
            unsupported_claims=["generated answer omitted or contradicted an authoritative result"],
            authoritative_facts=facts,
            recovery_applied=True,
            replacement_reason="deterministic evidence contradicted the generated response",
        )

    observation_fact = str(observation_evidence or "").strip()
    evidence = observation_fact.lower()
    empty_observation = (
        "[]" in evidence
        or re.search(r"(?<!\d)0\s+(?:hit(?:s)?|result(?:s)?)\b", evidence) is not None
        or re.search(r"\b(?:no matches|no results|nothing found)\b", evidence) is not None
    )
    normalized_reply = reply.lower()
    # Negated reports are not positive discoveries. Strip the common negative
    # constructions before looking for a positive claim so an honest response
    # such as "I found no matching files" is not rewritten again.
    normalized_reply = re.sub(
        r"\b(?:did not|didn't|not|never|no longer)\s+"
        r"(?:find|found|locate|located|create|created|open|opened|run|running|complete|completed)\b",
        "",
        normalized_reply,
    )
    normalized_reply = re.sub(
        r"\b(?:no|none|nothing)\s+(?:was\s+)?(?:found|located|created|opened)\b",
        "",
        normalized_reply,
    )
    normalized_reply = re.sub(
        r"\b(?:found|located|created|opened)\s+(?:no|none|nothing)\b",
        "",
        normalized_reply,
    )
    normalized_reply = re.sub(
        r"\bthere\s+(?:are|is)\s+no\b",
        "",
        normalized_reply,
    )
    positive_claim = re.search(
        r"\b(found|located|created|opened|there are|there is|running|completed successfully)\b",
        normalized_reply,
    ) is not None
    if empty_observation and positive_claim:
        replacement = (
            "I could not verify that discovery. The authoritative observation "
            "returned no matching results."
        )
        return replacement, ResponseGrounding(
            status="contradicted",
            supported=False,
            unsupported_claims=["positive discovery claim conflicts with an empty observation"],
            authoritative_facts=["the observation returned no matching results"],
            recovery_applied=True,
            replacement_reason="empty observation contradicted a positive discovery claim",
        )

    if answers:
        return reply, ResponseGrounding(
            status="verified",
            supported=True,
            authoritative_facts=facts,
        )
    if observation_fact:
        return reply, ResponseGrounding(
            status="supported",
            supported=True,
            authoritative_facts=[observation_fact[:500]],
        )
    return reply, ResponseGrounding(
        status="unknown",
        supported=False,
        unsupported_claims=["no authoritative response evidence was available"],
    )
