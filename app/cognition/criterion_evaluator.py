"""CriterionEvaluator — the step-level predicate pipeline (P0 #16).

StepVerifier used to accept success_criteria / failure_conditions and simply
COPY them into met_criteria / unmet_criteria while relying on the runtime's
goal_verified. "CPU usage decreased by 20%" caused no calculation because
nothing was ever parsed, bound to an observation, or evaluated.

This module implements the missing pipeline, deterministically and with no LLM:

    Natural language criterion
        -> structured predicate        (parse_criterion)
        -> observation                 (ObservationFacts.from_cycle_result)
        -> deterministic evaluation    (evaluate_predicate)
        -> PASS / FAIL / UNKNOWN       (CriterionResult, with a basis trail)

Honesty rules, matching the StepVerifier epistemic ladder (P0 #15):
  * PASS requires a real observation that entails the predicate.
  * FAIL requires a real observation that REFUTES it.
  * Anything else is UNKNOWN — unparseable criteria, missing observations,
    metrics that would need before-and-after measurements. UNKNOWN is
    reported with the reason; it is never silently promoted to PASS.
  * The assistant reply is a self-report, not an observation. The single
    exception is response-delivery criteria, where the reply IS the
    deliverable being verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Stage 1: natural language criterion -> structured predicate
# ---------------------------------------------------------------------------

# Ordered: most specific patterns first.
_RE_METRIC_DELTA = re.compile(
    r"(?P<metric>[\w\s]+?)\s+(?P<direction>decreased|increased|reduced|dropped|rose|grew)"
    r"\s+by\s+(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent|points?)?",
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

_POSITIVE_STATES = {"running", "run", "open", "opened", "active", "found", "exists",
                    "exist", "created", "saved", "installed", "present", "success",
                    "succeeded", "verified", "ok", "true"}
_NEGATIVE_STATES = {"failed", "failure", "error", "crashed", "crash", "closed",
                    "not_found", "missing", "not running", "false", "killed", "timeout"}
_COUNT_WORDS = ("count", "results", "result", "found", "matches", "match", "items",
                "item", "files", "file", "entries", "entry", "rows", "records")


@dataclass
class CriterionResult:
    """One criterion's journey through the pipeline, with its honesty trail."""
    criterion: str
    predicate: Dict[str, Any]
    status: str  # PASS | FAIL | UNKNOWN
    basis: str   # which observation decided it (or why nothing could)


def parse_criterion(criterion: str) -> Dict[str, Any]:
    """NL criterion -> structured predicate. Unparseable -> {'type': 'opaque'}."""
    text = (criterion or "").strip()
    if not text:
        return {"type": "opaque", "reason": "empty criterion"}

    m = _RE_METRIC_DELTA.search(text)
    if m:
        return {
            "type": "metric_delta",
            "metric": m.group("metric").strip().lower(),
            "direction": m.group("direction").lower(),
            "value": float(m.group("value")),
        }
    m = _RE_WITHIN_SECONDS.search(text)
    if m:
        return {"type": "duration_max", "seconds": float(m.group("n"))}
    m = _RE_AT_LEAST.search(text)
    if m:
        return {"type": "count_at_least", "n": int(m.group("n")), "what": m.group("what").strip().lower()}
    m = _RE_OR_MORE.search(text)
    if m:
        return {"type": "count_at_least", "n": int(m.group("n")), "what": m.group("what").strip().lower()}
    m = _RE_ABOVE_BELOW.search(text)
    if m:
        return {
            "type": "numeric_threshold",
            "subject": m.group("subject").strip().lower(),
            "op": m.group("op").lower(),
            "value": float(m.group("n")),
        }
    m = _RE_CONTAINS.search(text)
    if m:
        return {
            "type": "contains",
            "container": m.group("container").strip().lower(),
            "what": m.group("what").strip().lower(),
        }
    m = _RE_RESPONSE_DELIVERED.match(text)
    if m:
        return {"type": "response_delivered"}
    m = _RE_NO_ERRORS.match(text)
    if m:
        return {"type": "no_errors"}
    m = _RE_EXISTS.match(text)
    if m:
        return {"type": "entity_state", "entity": m.group("entity").strip().lower(),
                "states": ("created", "saved", "installed", "present", "exists", "found")}
    m = _RE_IS_RUNNING.match(text)
    if m:
        return {"type": "entity_state", "entity": m.group("entity").strip().lower(),
                "states": ("running", "open", "active")}
    m = _RE_CRASHED.match(text)
    if m:
        return {"type": "entity_state", "entity": m.group("entity").strip().lower(),
                "states": ("crashed", "failed", "failure", "closed", "stopped",
                           "killed", "hung", "froze", "missing", "not running")}
    return {"type": "opaque", "reason": "no deterministic predicate grammar matches"}


# ---------------------------------------------------------------------------
# Stage 2: cycle result -> observed facts (real signals only)
# ---------------------------------------------------------------------------

@dataclass
class ObservationFacts:
    """Everything the cycle actually observed, extracted from real signals.

    Deliberately excludes the assistant reply (self-report) and executed
    action descriptions (attempts) — per the P0 #15 epistemic ladder these
    are not observations.
    """
    entity_states: Dict[str, str] = field(default_factory=dict)
    observation_values: Dict[str, Any] = field(default_factory=dict)
    numeric_metrics: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, float] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    process_verified: Optional[bool] = None
    process_app: str = ""
    response_delivered: bool = False
    goal_met_conditions: List[str] = field(default_factory=list)
    goal_failed_conditions: List[str] = field(default_factory=list)

    @classmethod
    def from_cycle_result(cls, cycle_result: Dict[str, Any]) -> "ObservationFacts":
        obs = cls()

        # (a) The GoalVerifier's real observations (runtime only carries these
        #     when the world was actually probed — see P0 #15 wiring).
        vstate = cycle_result.get("verification_observed_state") or {}
        if isinstance(vstate, dict):
            observations = vstate.get("observations")
            entity_states = vstate.get("verified_entity_states")
            if isinstance(observations, dict) or isinstance(entity_states, dict):
                # structured form
                obs.observation_values = dict(observations or {})
                obs.entity_states = {
                    str(k).lower(): str(v).lower()
                    for k, v in (entity_states or {}).items()
                }
            else:
                # flat legacy form: the map itself
                obs.observation_values = dict(vstate)
                obs.entity_states = {
                    str(k).lower(): str(v).lower()
                    for k, v in vstate.items() if isinstance(v, str)
                }

        # (b) Live OS grounding: a post-action process/window probe.
        grounding = cycle_result.get("os_grounding")
        if isinstance(grounding, dict):
            g_app = str((grounding.get("grounding") or {}).get("app_name") or "")
            if grounding.get("verified") or grounding.get("success"):
                obs.process_verified = True
                obs.process_app = g_app
                if g_app:
                    obs.entity_states.setdefault(g_app.lower(), "running")
            elif "success" in grounding or "verified" in grounding:
                obs.process_verified = False
                if g_app:
                    obs.entity_states.setdefault(g_app.lower(), "failed")

        # (c) Measured latency (a real, instrumented observation).
        latency = cycle_result.get("latency_ms")
        if isinstance(latency, (int, float)):
            obs.duration_ms = float(latency)

        # (d) Response delivery: the reply is the deliverable, its existence
        #     is directly observable (not a claim about the world).
        obs.response_delivered = bool((cycle_result.get("assistant_reply") or "").strip())

        # (e) The GoalVerifier's own per-condition verdicts.
        obs.goal_met_conditions = list(cycle_result.get("verification_met_conditions") or [])
        obs.goal_failed_conditions = list(cycle_result.get("verification_failed_conditions") or [])

        # (f) Numeric leaves from the observation map: metrics + counts.
        obs.numeric_metrics, obs.counts = _extract_numeric(obs.observation_values)
        found_entities = sum(1 for s in obs.entity_states.values() if s in _POSITIVE_STATES)
        if found_entities:
            obs.counts.setdefault("__entities_observed__", float(found_entities))
        return obs


# Leaf keys that must NEVER be read as counts, even when their path mentions
# results/files (e.g. 'search_result_set.value.limit' is a page limit, not a
# result count — the live run caught exactly this misclassification).
_NON_COUNT_LEAVES = {"limit", "max", "min", "offset", "timeout", "threshold",
                     "confidence", "level", "size", "port", "pid", "id",
                     "revision", "version", "page", "index", "code", "ms"}


def _extract_numeric(values: Dict[str, Any]) -> tuple:
    """Collect numeric observation leaves, splitting count-ish leaves from
    metrics. Classification uses the LEAF key only, never the whole path."""
    metrics: Dict[str, float] = {}
    counts: Dict[str, float] = {}

    def _walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(v, f"{path}.{k}".strip("."))
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            key = path.lower()
            leaf = key.split(".")[-1]
            if leaf not in _NON_COUNT_LEAVES and any(w in leaf for w in _COUNT_WORDS):
                counts[key] = float(node)
            else:
                metrics[key] = float(node)

    _walk(values)
    return metrics, counts


def _norm(text: str) -> str:
    """Normalize for matching: underscores, punctuation and case collapse, so
    'app_process_running' == 'app process running'."""
    lowered = (text or "").lower().replace("_", " ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _entity_observed(entity: str, entity_states: Dict[str, str]) -> Optional[str]:
    """Find the observed state of an entity, or None if never observed."""
    e = _norm(entity)
    for key, state in entity_states.items():
        k = _norm(key)
        if not k:
            continue
        if e == k or e.endswith(k) or k.endswith(e) or e in k or k in e:
            return state
    return None


# ---------------------------------------------------------------------------
# Stage 3 + 4: deterministic evaluation -> PASS / FAIL / UNKNOWN
# ---------------------------------------------------------------------------

def evaluate_predicate(predicate: Dict[str, Any], facts: ObservationFacts) -> CriterionResult:
    ptype = predicate.get("type")
    basis_unknown = predicate.get("reason", "")

    if ptype == "opaque":
        return CriterionResult(
            criterion="", predicate=predicate, status=UNKNOWN,
            basis=f"cannot evaluate deterministically ({basis_unknown})",
        )

    if ptype == "response_delivered":
        if facts.response_delivered:
            return CriterionResult("", predicate, PASS, "assistant reply exists — the deliverable itself")
        return CriterionResult("", predicate, FAIL, "no assistant reply was delivered")

    if ptype == "entity_state":
        entity = predicate.get("entity", "")
        state = _entity_observed(entity, facts.entity_states)
        wanted = set(predicate.get("states", ()))
        if state is None:
            if facts.process_verified is True and _entity_observed(entity, {facts.process_app: "running"}):
                return CriterionResult("", predicate, PASS, f"process probe verified '{facts.process_app}' running")
            if facts.process_verified is False:
                return CriterionResult("", predicate, FAIL, "post-action process probe found no matching running process")
            return CriterionResult("", predicate, UNKNOWN, f"entity '{entity}' was never observed")
        if state in wanted or (state in _POSITIVE_STATES and (wanted & _POSITIVE_STATES)):
            return CriterionResult("", predicate, PASS, f"entity '{entity}' observed '{state}'")
        if state in _NEGATIVE_STATES:
            return CriterionResult("", predicate, FAIL, f"entity '{entity}' observed '{state}'")
        return CriterionResult("", predicate, UNKNOWN, f"entity '{entity}' observed '{state}' — not a decisive state")

    if ptype == "no_errors":
        if facts.process_verified is False:
            return CriterionResult("", predicate, FAIL, "post-action probe reported failure")
        error_states = [k for k, s in facts.entity_states.items() if s in _NEGATIVE_STATES]
        if error_states:
            return CriterionResult("", predicate, FAIL, f"observed failure states: {', '.join(error_states[:3])}")
        if facts.observation_values or facts.entity_states or facts.process_verified is True:
            return CriterionResult("", predicate, PASS, "observations present, none report an error state")
        return CriterionResult("", predicate, UNKNOWN, "nothing was observed — absence of observed errors is not evidence of no errors")

    if ptype == "count_at_least":
        n = float(predicate.get("n", 0))
        what = predicate.get("what", "")
        if not facts.counts:
            return CriterionResult("", predicate, UNKNOWN, "no count-like observation available")
        if what:
            words = [w for w in _norm(what).split() if len(w) > 2]
            relevant = {k: v for k, v in facts.counts.items()
                        if any(w in k for w in words)}
            relevant = relevant or facts.counts
        else:
            relevant = facts.counts
        best = max(relevant.values())
        if best >= n:
            return CriterionResult("", predicate, PASS, f"observed count {best:g} >= {n:g} ({'; '.join(list(relevant)[:2])})")
        return CriterionResult("", predicate, FAIL, f"observed count {best:g} < {n:g}")

    if ptype == "duration_max":
        seconds = float(predicate.get("seconds", 0))
        if facts.duration_ms is None:
            return CriterionResult("", predicate, UNKNOWN, "no measured duration available")
        actual = facts.duration_ms / 1000.0
        if actual <= seconds:
            return CriterionResult("", predicate, PASS, f"measured duration {actual:.2f}s <= {seconds:g}s")
        return CriterionResult("", predicate, FAIL, f"measured duration {actual:.2f}s exceeds {seconds:g}s")

    if ptype == "numeric_threshold":
        subject = predicate.get("subject", "")
        op = predicate.get("op", "")
        value = float(predicate.get("value", 0))
        observed = _lookup_metric(subject, facts.numeric_metrics)
        if observed is None:
            return CriterionResult(
                "", predicate, UNKNOWN,
                f"'{subject}' was not numerically observed — cannot compare against {value:g}",
            )
        ok = _compare(observed, op, value)
        if ok:
            return CriterionResult("", predicate, PASS, f"observed {subject} = {observed:g} ({op} {value:g}) holds")
        return CriterionResult("", predicate, FAIL, f"observed {subject} = {observed:g} violates '{op} {value:g}'")

    if ptype == "metric_delta":
        metric = predicate.get("metric", "")
        # A delta needs BOTH a before and an after measurement of the metric.
        # No step-level observation stream carries both today — so the honest
        # verdict is UNKNOWN, with the reason stated, instead of a fake PASS.
        return CriterionResult(
            "", predicate, UNKNOWN,
            f"'{metric}' change requires before-and-after measurements; "
            "neither baseline nor post-state was observed for this step",
        )

    if ptype == "contains":
        return CriterionResult(
            "", predicate, UNKNOWN,
            "content inspection observation not available for this step",
        )

    return CriterionResult("", predicate, UNKNOWN, f"unknown predicate type '{ptype}'")


def _lookup_metric(subject: str, metrics: Dict[str, float]) -> Optional[float]:
    s = _norm(subject)
    for key, value in metrics.items():
        k = _norm(key)
        if s and (s == k or s in k or k in s):
            return value
    return None


def _compare(observed: float, op: str, value: float) -> bool:
    if op in ("above", "higher than", "greater than"):
        return observed > value
    if op in ("below", "lower than", "less than"):
        return observed < value
    if op == "at least":
        return observed >= value
    return False


def _condition_in(criterion: str, conditions: List[str]) -> bool:
    """Does the criterion match one of the GoalVerifier's evaluated conditions?"""
    c = _norm(criterion)
    if not c:
        return False
    for cond in conditions:
        n = _norm(cond)
        if not n:
            continue
        if c == n or (len(n) > 6 and n in c) or (len(c) > 6 and c in n):
            return True
    return False


def evaluate_criterion(criterion: str, facts: ObservationFacts) -> CriterionResult:
    """The full pipeline for one criterion: parse -> bind -> evaluate."""
    predicate = parse_criterion(criterion)

    # The GoalVerifier may have already evaluated this exact condition against
    # its own observations — reuse that verdict, attributed to it.
    if _condition_in(criterion, facts.goal_met_conditions):
        return CriterionResult(criterion, predicate, PASS,
                               "goal verifier evaluated this condition as met")
    if _condition_in(criterion, facts.goal_failed_conditions):
        return CriterionResult(criterion, predicate, FAIL,
                               "goal verifier evaluated this condition as failed")

    result = evaluate_predicate(predicate, facts)
    result.criterion = criterion
    return result


def evaluate_criteria(criteria: List[str], cycle_result: Dict[str, Any]) -> List[CriterionResult]:
    """Evaluate every criterion against what the cycle actually observed."""
    facts = ObservationFacts.from_cycle_result(cycle_result)
    return [evaluate_criterion(c, facts) for c in (criteria or [])]
