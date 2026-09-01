"""The typed condition language (P0 review #9).

Conditions like 'response_delivered = true' or 'CPU usage dropped by at
least 20%' used to be interpreted through string heuristics — keyword
lists and substring containment, duplicated per consumer. This module is
the proper language, with ONE parser, ONE AST, and predicates that hold
typed logic:

    Condition AST          parse_condition("CPU usage dropped by at least 20%")
        ↓                  -> MetricDelta(metric="cpu usage", direction="dropped",
    Observation query          value=20.0, unit="percent")
        ↓                  node asks the environment for typed evidence:
    typed value                baseline metric, post metric, entity state, flag…
        ↓                  the node's predicate compares typed values:
    predicate              drop >= 20% of baseline?
        ↓
    PASS / FAIL / UNKNOWN  Verdict(status, basis) — with the reason.

Environments (the observation query layer) are supplied by the consumer:
  * criterion_evaluator.FactsEnv      — step criteria vs the cycle's facts
  * goal_verifier._ProvenanceEnv      — goal conditions vs provenance-checked
                                        world-model observations
The AST never talks to the LLM and never guesses: missing evidence is
UNKNOWN with the reason, never promoted to PASS.

Back-compat: every node serializes via to_dict() to the predicate-dict
shape criterion_evaluator has always exposed; condition_from_dict()
rebuilds the node. The dict is the wire format, the node is the logic —
there are not two interpretations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Typed observation values and verdicts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservationQuery:
    """What evidence a condition needs, stated explicitly."""
    kind: str   # "metric" | "baseline" | "entity_state" | "count" | "duration" | "response" | "flag"
    key: str


@dataclass(frozen=True)
class ObservedValue:
    """A typed observed value, with provenance authorization and source."""
    value: Any
    kind: str                 # "state" | "number" | "boolean" | "text"
    authorized: bool = True   # carries authorized provenance?
    source: str = ""


@dataclass(frozen=True)
class Verdict:
    status: str   # PASS | FAIL | UNKNOWN
    basis: str


# ---------------------------------------------------------------------------
# The environment: typed observation queries resolve here
# ---------------------------------------------------------------------------

class ObservationEnvironment:
    """Duck-typed evidence resolver. Subclasses override what they can
    answer; unanswered queries return None -> the node reports UNKNOWN."""

    def metric(self, name: str) -> Optional[float]:
        return None

    def baseline(self, metric: str) -> Optional[float]:
        return None

    def entity_state(self, entity: str) -> Optional[str]:
        return None

    def process_probe(self) -> Tuple[Optional[bool], str]:
        """(verified_running, app_name) from a live OS process probe."""
        return (None, "")

    def count(self, what: str) -> Optional[float]:
        return None

    def duration_seconds(self) -> Optional[float]:
        return None

    def response_delivered(self) -> Optional[bool]:
        return None

    def verified_answer_values(self) -> List[Any]:
        """Values computed deterministically for this request (ground
        truth for answer-content conditions). Empty by default."""
        return []

    def response_text(self) -> str:
        """The assistant reply text (the deliverable to inspect)."""
        return ""

    def error_states(self) -> List[str]:
        return []

    def any_observations(self) -> bool:
        return False

    def flag(self, name: str) -> Optional[ObservedValue]:
        return None


# ---------------------------------------------------------------------------
# AST nodes — each holds a typed predicate
# ---------------------------------------------------------------------------

@dataclass
class Condition:
    kind: str = "condition"

    def queries(self) -> List[ObservationQuery]:
        return []

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.kind}

    def evaluate(self, env: ObservationEnvironment) -> Verdict:  # pragma: no cover
        raise NotImplementedError


@dataclass
class OpaqueCondition(Condition):
    reason: str = ""

    def __post_init__(self):
        self.kind = "opaque"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "opaque", "reason": self.reason}

    def evaluate(self, env: ObservationEnvironment) -> Verdict:
        return Verdict(UNKNOWN, f"cannot evaluate deterministically ({self.reason})")


@dataclass
class ResponseDelivered(Condition):
    def __post_init__(self):
        self.kind = "response_delivered"

    def queries(self):
        return [ObservationQuery("response", "assistant_reply")]

    def to_dict(self):
        return {"type": "response_delivered"}

    def evaluate(self, env):
        delivered = env.response_delivered()
        if delivered is True:
            return Verdict(PASS, "assistant reply exists — the deliverable itself")
        if delivered is False:
            return Verdict(FAIL, "no assistant reply was delivered")
        return Verdict(UNKNOWN, "response delivery was not observed")


@dataclass
class AnswerContainsVerifiedValue(Condition):
    """The reply must STATE a value the system computed deterministically.

    F3c (DIAG D1/D2/D6): a reply existing is not an answer being verified.
    For answer-content conditions the predicate is the reply's content
    against deterministic ground truth:
      * no ground truth was computed  -> UNKNOWN (delivery alone cannot
        verify correctness — the goal waits for evidence, never achieves);
      * ground truth stated in reply   -> PASS;
      * ground truth computed but the reply states something else -> FAIL.
    """

    def __post_init__(self):
        self.kind = "answer_contains_value"

    def queries(self):
        return [ObservationQuery("verified_answer", "deterministic_answers")]

    def to_dict(self):
        return {"type": "answer_contains_value"}

    def evaluate(self, env):
        values = env.verified_answer_values()
        if not values:
            return Verdict(
                UNKNOWN,
                "no deterministic ground truth was computed for the answer "
                "value — a delivered reply cannot be verified for content",
            )
        reply = env.response_text()
        # Lazy import: condition_language stays dependency-free; the
        # calculator module owns the numeric-match semantics (thousands
        # separators, float tolerance) in ONE place.
        from app.tools.calculator import DeterministicCalculator
        mentioned = [v for v in values
                     if DeterministicCalculator.reply_mentions_value(reply, v)]
        if mentioned:
            return Verdict(
                PASS, f"reply states the computed answer value(s): {mentioned}")
        return Verdict(
            FAIL,
            f"reply does not state the computed answer value(s): {values} — "
            f"the deterministic result is ground truth, so the answer is wrong"
        )


@dataclass
class StateCondition(Condition):
    entity: str = ""
    states: Tuple[str, ...] = ()

    def __post_init__(self):
        self.kind = "entity_state"

    def queries(self):
        return [ObservationQuery("entity_state", self.entity)]

    def to_dict(self):
        return {"type": "entity_state", "entity": self.entity, "states": self.states}

    def evaluate(self, env):
        state = env.entity_state(self.entity)
        wanted = set(self.states)
        positive = wanted & _POSITIVE_STATES
        if state is None:
            verified, app = env.process_probe()
            if verified is True and app and _norm_match(self.entity, app):
                return Verdict(PASS, f"process probe verified '{app}' running")
            if verified is False:
                return Verdict(FAIL, "post-action process probe found no matching running process")
            return Verdict(UNKNOWN, f"entity '{self.entity}' was never observed")
        if state in wanted or (state in _POSITIVE_STATES and positive):
            return Verdict(PASS, f"entity '{self.entity}' observed '{state}'")
        if state in _NEGATIVE_STATES:
            return Verdict(FAIL, f"entity '{self.entity}' observed '{state}'")
        return Verdict(UNKNOWN, f"entity '{self.entity}' observed '{state}' — not a decisive state")


@dataclass
class FlagCondition(Condition):
    """A named boolean-ish condition ('response_delivered = true').

    The environment resolves the flag to a typed ObservedValue (with
    provenance); the predicate here decides PASS/FAIL/UNKNOWN:
      mode="membership"   PASS iff authorized and value in satisfied_by
                          (empty satisfied_by: any authorized truthy value)
                          FAIL iff value in refuted_by
      mode="not_refuted"  PASS iff authorized and value not in refuted_by
                          FAIL iff value in refuted_by
      expected=False      inverts: the refuted outcome is the goal
    """
    name: str = ""
    expected: bool = True
    mode: str = "membership"
    satisfied_by: Tuple[str, ...] = ()
    refuted_by: Tuple[str, ...] = ()

    def __post_init__(self):
        self.kind = "flag"

    def queries(self):
        return [ObservationQuery("flag", self.name)]

    def to_dict(self):
        return {"type": "flag", "name": self.name, "expected": self.expected}

    def evaluate(self, env):
        observed = env.flag(self.name)
        if observed is None:
            return Verdict(UNKNOWN, f"'{self.name}' was never observed")
        value = _clean(observed.value)
        refuted = value in self.refuted_by
        if self.mode == "not_refuted":
            satisfied = observed.authorized and not refuted
        else:
            in_satisfied = (not self.satisfied_by and value not in ("", "false", "none")) \
                or value in self.satisfied_by
            satisfied = observed.authorized and in_satisfied
        if self.expected:
            if refuted:
                return Verdict(FAIL, f"'{self.name}' observed '{value}'{self._src(observed)}")
            if satisfied:
                return Verdict(PASS, f"'{self.name}' observed '{value}'{self._src(observed)}")
            if not observed.authorized:
                return Verdict(UNKNOWN,
                               f"'{self.name}' observed '{value}' but the evidence is not "
                               f"provenance-authorized{self._src(observed)}")
            return Verdict(UNKNOWN, f"'{self.name}' observed '{value}' — not a decisive value")
        # expected=False: the condition WANTS the refuted outcome
        if refuted:
            return Verdict(PASS, f"'{self.name}' observed '{value}'{self._src(observed)}")
        if observed.authorized and value not in ("", "false", "none"):
            return Verdict(FAIL, f"'{self.name}' observed '{value}'{self._src(observed)}")
        if not observed.authorized:
            return Verdict(UNKNOWN,
                           f"'{self.name}' observed '{value}' but the evidence is not "
                           f"provenance-authorized{self._src(observed)}")
        return Verdict(UNKNOWN, f"'{self.name}' observed '{value}' — not a decisive value")

    @staticmethod
    def _src(observed: ObservedValue) -> str:
        return f" (source: {observed.source})" if observed.source else ""


@dataclass
class NumericThreshold(Condition):
    subject: str = ""
    op: str = ""
    value: float = 0.0

    def __post_init__(self):
        self.kind = "numeric_threshold"

    def queries(self):
        return [ObservationQuery("metric", self.subject)]

    def to_dict(self):
        return {"type": "numeric_threshold", "subject": self.subject,
                "op": self.op, "value": self.value}

    def evaluate(self, env):
        observed = env.metric(self.subject)
        if observed is None:
            return Verdict(
                UNKNOWN,
                f"'{self.subject}' was not numerically observed — cannot compare against {self.value:g}")
        ok = _compare(observed, self.op, self.value)
        if ok:
            return Verdict(PASS, f"observed {self.subject} = {observed:g} ({self.op} {self.value:g}) holds")
        return Verdict(FAIL, f"observed {self.subject} = {observed:g} violates '{self.op} {self.value:g}'")


@dataclass
class MetricDelta(Condition):
    """A measured CHANGE in a metric — 'CPU usage dropped by at least 20%'.

    This needs TWO typed observations (baseline and post-action); with
    both it computes the change and compares it against the required
    delta. Relative deltas ('%') compare against the baseline; absolute
    deltas ('points') compare raw values.
    """
    metric: str = ""
    direction: str = "dropped"   # dropped|decreased|reduced|rose|increased|grew
    value: float = 0.0
    unit: str = "percent"        # percent | points

    def __post_init__(self):
        self.kind = "metric_delta"

    def queries(self):
        return [ObservationQuery("baseline", self.metric),
                ObservationQuery("metric", self.metric)]

    def to_dict(self):
        return {"type": "metric_delta", "metric": self.metric,
                "direction": self.direction, "value": self.value, "unit": self.unit}

    def evaluate(self, env):
        post = env.metric(self.metric)
        base = env.baseline(self.metric)
        if post is None and base is None:
            return Verdict(
                UNKNOWN,
                f"'{self.metric}' change requires before-and-after measurements; "
                f"neither baseline nor post-state was observed")
        if base is None:
            return Verdict(
                UNKNOWN,
                f"'{self.metric}' change requires before-and-after measurements; "
                f"no baseline (before) value was observed")
        if post is None:
            return Verdict(
                UNKNOWN,
                f"'{self.metric}' change requires before-and-after measurements; "
                f"no post-action value was observed")

        rising = self.direction in ("rose", "increased", "grew")
        if self.unit == "points":
            change = (post - base) if rising else (base - post)
            requirement = self.value
            detail = f"{self.metric}: {base:g} -> {post:g} ({change:g} points {self.direction})"
        else:
            if base == 0:
                return Verdict(
                    UNKNOWN,
                    f"'{self.metric}' baseline is 0 — a relative change cannot be computed "
                    f"(use points)")
            change = ((post - base) / base * 100.0) if rising else ((base - post) / base * 100.0)
            requirement = self.value
            detail = (f"{self.metric}: {base:g} -> {post:g} "
                      f"({change:.1f}% {self.direction}, required >= {requirement:g}%)")
        if change >= requirement:
            return Verdict(PASS, f"measured {detail}")
        return Verdict(FAIL, f"measured {detail} — the required change was not achieved")


@dataclass
class CountAtLeast(Condition):
    n: float = 0
    what: str = ""

    def __post_init__(self):
        self.kind = "count_at_least"

    def queries(self):
        return [ObservationQuery("count", self.what)]

    def to_dict(self):
        return {"type": "count_at_least", "n": self.n, "what": self.what}

    def evaluate(self, env):
        best = env.count(self.what)
        if best is None:
            return Verdict(UNKNOWN, "no count-like observation available")
        if best >= self.n:
            return Verdict(PASS, f"observed count {best:g} >= {self.n:g}")
        return Verdict(FAIL, f"observed count {best:g} < {self.n:g}")


@dataclass
class DurationMax(Condition):
    seconds: float = 0.0

    def __post_init__(self):
        self.kind = "duration_max"

    def queries(self):
        return [ObservationQuery("duration", "step_duration")]

    def to_dict(self):
        return {"type": "duration_max", "seconds": self.seconds}

    def evaluate(self, env):
        actual = env.duration_seconds()
        if actual is None:
            return Verdict(UNKNOWN, "no measured duration available")
        if actual <= self.seconds:
            return Verdict(PASS, f"measured duration {actual:.2f}s <= {self.seconds:g}s")
        return Verdict(FAIL, f"measured duration {actual:.2f}s exceeds {self.seconds:g}s")


@dataclass
class Contains(Condition):
    container: str = ""
    what: str = ""

    def __post_init__(self):
        self.kind = "contains"

    def queries(self):
        return [ObservationQuery("entity_state", self.container)]

    def to_dict(self):
        return {"type": "contains", "container": self.container, "what": self.what}

    def evaluate(self, env):
        return Verdict(UNKNOWN, "content inspection observation not available for this step")


@dataclass
class NoErrors(Condition):
    def __post_init__(self):
        self.kind = "no_errors"

    def to_dict(self):
        return {"type": "no_errors"}

    def evaluate(self, env):
        errors = env.error_states()
        if errors:
            return Verdict(FAIL, f"observed failure states: {', '.join(errors[:3])}")
        verified, _ = env.process_probe()
        if verified is False:
            return Verdict(FAIL, "post-action probe reported failure")
        if env.any_observations():
            return Verdict(PASS, "observations present, none report an error state")
        return Verdict(UNKNOWN,
                       "nothing was observed — absence of observed errors is not evidence of no errors")


# ---------------------------------------------------------------------------
# The ONE parser: natural language / flag conditions -> AST
# ---------------------------------------------------------------------------

_RE_METRIC_DELTA = re.compile(
    r"(?P<metric>[\w\s]+?)\s+(?P<direction>decreased|increased|reduced|dropped|rose|grew)"
    r"\s+by\s+(?:at least\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|points?)?",
    re.IGNORECASE,
)
_RE_WITHIN_SECONDS = re.compile(
    r"(?:within|faster than|less than|under)\s+(?P<n>\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)
_RE_AT_LEAST = re.compile(r"at least\s+(?P<n>\d+)\s*(?P<what>[\w\s]*)", re.IGNORECASE)
_RE_OR_MORE = re.compile(r"(?P<n>\d+)\s+or more\s*(?P<what>[\w\s]*)", re.IGNORECASE)
_RE_ABOVE_BELOW = re.compile(
    r"(?P<subject>[\w\s]+?)\s+(?P<op>above|below|higher than|lower than|greater than|"
    r"less than|at least)\s+(?P<n>\d+(?:\.\d+)?)\s*(?:%|percent)?",
    re.IGNORECASE,
)
_RE_CONTAINS = re.compile(r"(?P<container>[\w\s.\\/:\-]+?)\s+contains\s+(?P<what>.+)$", re.IGNORECASE)
_RE_EXISTS = re.compile(
    r"^(?:the\s+)?(?P<entity>.+?)\s+(?:is\s+|are\s+|was\s+|were\s+)?"
    r"(?:created|saved|installed|present|exists?|found)$",
    re.IGNORECASE,
)
_RE_IS_RUNNING = re.compile(
    r"^(?:the\s+)?(?P<entity>.+?)\s+(?:is\s+|was\s+)?(?:running|launched|active|open)$",
    re.IGNORECASE,
)
_RE_CRASHED = re.compile(
    r"^(?:the\s+)?(?P<entity>.+?)\s+(?:is\s+|was\s+|has\s+|did\s+)?"
    r"(?:crashed?|fail(?:ed|s|ure)?|not running|closed|stopped|killed|hung|froze|missing)$",
    re.IGNORECASE,
)
_RE_NO_ERRORS = re.compile(r"^(?:no|zero|without)\s+(?:errors?|failures?|crashes?)", re.IGNORECASE)
_RE_RESPONSE_DELIVERED = re.compile(
    r"^(?:a\s+)?(?:response|reply|answer|message|notification)[\w\s]*(?:delivered|provided|generated|sent|shown)$",
    re.IGNORECASE,
)
# Flag conditions: 'response_delivered = true', 'app_process_running = true',
# 'network_available = false', 'x = running', or a bare snake_case flag.
# The '=' operator (or a strict 'is true/false') distinguishes flags from
# entity sentences — 'Chrome is running' is an entity state, not a flag.
_RE_FLAG = re.compile(
    r"^(?P<name>[a-z0-9][a-z0-9_ ]*?)\s*(?:=|==)\s*(?P<value>[a-z0-9_.]+)$",
    re.IGNORECASE,
)
_RE_FLAG_IS_BOOL = re.compile(
    r"^(?P<name>[a-z0-9][a-z0-9_ ]*?)\s+(?:is|was|remains)\s+(?P<value>true|false|yes|no)$",
    re.IGNORECASE,
)
_RE_BARE_FLAG = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$", re.IGNORECASE)


def parse_condition(text: str) -> Condition:
    """NL / flag condition -> AST node. Unparseable -> OpaqueCondition."""
    raw = (text or "").strip()
    if not raw:
        return OpaqueCondition("empty criterion")

    m = _RE_METRIC_DELTA.search(raw)
    if m:
        unit = (m.group("unit") or "").lower()
        return MetricDelta(
            metric=m.group("metric").strip().lower(),
            direction=m.group("direction").lower(),
            value=float(m.group("value")),
            unit="points" if unit.startswith("point") else "percent",
        )
    m = _RE_WITHIN_SECONDS.search(raw)
    if m:
        return DurationMax(seconds=float(m.group("n")))
    m = _RE_AT_LEAST.search(raw)
    if m:
        return CountAtLeast(n=int(m.group("n")), what=m.group("what").strip().lower())
    m = _RE_OR_MORE.search(raw)
    if m:
        return CountAtLeast(n=int(m.group("n")), what=m.group("what").strip().lower())
    m = _RE_ABOVE_BELOW.search(raw)
    if m:
        return NumericThreshold(
            subject=m.group("subject").strip().lower(),
            op=m.group("op").lower(),
            value=float(m.group("n")),
        )
    m = _RE_CONTAINS.search(raw)
    if m:
        return Contains(container=m.group("container").strip().lower(),
                        what=m.group("what").strip().lower())
    if _RE_RESPONSE_DELIVERED.match(raw):
        return ResponseDelivered()
    if _RE_NO_ERRORS.match(raw):
        return NoErrors()
    m = _RE_FLAG_IS_BOOL.match(raw) or _RE_FLAG.match(raw)
    if m:
        name = m.group("name").strip().lower()
        value = m.group("value").strip().lower()
        if value in ("true", "yes", "1"):
            return FlagCondition(name=name, expected=True)
        if value in ("false", "no", "0"):
            return FlagCondition(name=name, expected=False)
        # 'x = running' style: a state expectation on a named subject
        return FlagCondition(name=name, expected=True,
                             satisfied_by=(value,), mode="membership")
    if _RE_BARE_FLAG.match(raw):
        return FlagCondition(name=raw.lower(), expected=True)
    m = _RE_EXISTS.match(raw)
    if m:
        return StateCondition(entity=m.group("entity").strip().lower(),
                              states=("created", "saved", "installed", "present", "exists", "found"))
    m = _RE_IS_RUNNING.match(raw)
    if m:
        return StateCondition(entity=m.group("entity").strip().lower(),
                              states=("running", "open", "active"))
    m = _RE_CRASHED.match(raw)
    if m:
        return StateCondition(entity=m.group("entity").strip().lower(),
                              states=("crashed", "failed", "failure", "closed", "stopped",
                                      "killed", "hung", "froze", "missing", "not running"))
    return OpaqueCondition("no deterministic predicate grammar matches")


def condition_from_dict(data: Dict[str, Any]) -> Condition:
    """Rebuild the AST node from its serialized dict form."""
    ctype = str((data or {}).get("type") or "opaque")
    if ctype == "metric_delta":
        return MetricDelta(metric=data.get("metric", ""), direction=data.get("direction", "dropped"),
                           value=float(data.get("value", 0) or 0),
                           unit=data.get("unit", "percent") or "percent")
    if ctype == "duration_max":
        return DurationMax(seconds=float(data.get("seconds", 0) or 0))
    if ctype == "count_at_least":
        return CountAtLeast(n=float(data.get("n", 0) or 0), what=data.get("what", ""))
    if ctype == "numeric_threshold":
        return NumericThreshold(subject=data.get("subject", ""), op=data.get("op", ""),
                                value=float(data.get("value", 0) or 0))
    if ctype == "contains":
        return Contains(container=data.get("container", ""), what=data.get("what", ""))
    if ctype == "response_delivered":
        return ResponseDelivered()
    if ctype == "answer_contains_value":
        return AnswerContainsVerifiedValue()
    if ctype == "no_errors":
        return NoErrors()
    if ctype == "entity_state":
        states = data.get("states") or ()
        return StateCondition(entity=data.get("entity", ""), states=tuple(states))
    if ctype == "flag":
        return FlagCondition(name=data.get("name", ""), expected=bool(data.get("expected", True)))
    return OpaqueCondition(str(data.get("reason", "") or "unknown predicate type"))


# ---------------------------------------------------------------------------
# Shared vocabulary (typed state sets — used by nodes and environments)
# ---------------------------------------------------------------------------

_POSITIVE_STATES = {"running", "run", "open", "opened", "active", "found", "exists",
                    "exist", "created", "saved", "installed", "present", "success",
                    "succeeded", "verified", "ok", "true"}
_NEGATIVE_STATES = {"failed", "failure", "error", "crashed", "crash", "closed",
                    "not_found", "missing", "not running", "false", "killed", "timeout"}


def _clean(value: Any) -> str:
    return str(value if value is not None else "").lower().strip()


def _norm_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return bool(na) and bool(nb) and (na == nb or na.endswith(nb) or nb.endswith(na)
                                      or na in nb or nb in na)


def _norm(text: str) -> str:
    lowered = (text or "").lower().replace("_", " ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _compare(observed: float, op: str, value: float) -> bool:
    if op in ("above", "higher than", "greater than"):
        return observed > value
    if op in ("below", "lower than", "less than"):
        return observed < value
    if op == "at least":
        return observed >= value
    return False
