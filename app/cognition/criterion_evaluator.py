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

# P0 review #9: the predicate grammar and the typed evaluation logic live in
# ONE place — the condition language AST. This module keeps the observation
# FACTS pipeline (cycle result -> ObservationFacts) and adapts it to the
# language's environment interface. There are no second interpretations
# here: parse_criterion serializes the AST node; evaluate_predicate runs it.
from app.cognition.condition_language import (
    ObservationEnvironment,
    PASS,
    FAIL,
    UNKNOWN,
    condition_from_dict,
    parse_condition,
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
    """NL criterion -> serialized AST predicate. Unparseable -> {'type': 'opaque'}.

    The grammar lives in app.cognition.condition_language.parse_condition —
    the ONE parser (P0 review #9); this is its serialization for callers
    that speak predicate dicts.
    """
    return parse_condition(criterion).to_dict()


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
    metric_baselines: Dict[str, float] = field(default_factory=dict)
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

        # (g) Baseline (before) measurements for metric-delta criteria — from
        #     an explicit baselines map or before.* / *_before / baseline.*
        #     observation keys (P0 review #9: 'CPU usage dropped by 20%'
        #     needs a typed baseline to be evaluable at all).
        baselines_raw = cycle_result.get("metric_baselines")
        if isinstance(baselines_raw, dict):
            obs.metric_baselines = {
                str(k).lower(): float(v) for k, v in baselines_raw.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
        if not obs.metric_baselines:
            for key, value in list(obs.observation_values.items()):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                k = key.lower()
                if k.startswith("before.") or k.startswith("baseline."):
                    obs.metric_baselines[k.split(".", 1)[1]] = float(value)
                elif k.endswith("_before") or k.endswith("_pre") or k.endswith(".before"):
                    obs.metric_baselines[k.rsplit("_", 1)[0] if "_" in k else k] = float(value)

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

class FactsEnv(ObservationEnvironment):
    """Observation queries answered from what the cycle actually observed.

    The typed adapter between ObservationFacts and the condition language:
    a node asks for a metric / entity state / count / flag, and gets a
    typed value or None (never a guess).
    """

    def __init__(self, facts: "ObservationFacts"):
        self.facts = facts

    def metric(self, name: str) -> Optional[float]:
        return _lookup_metric(name, self.facts.numeric_metrics)

    def baseline(self, metric: str) -> Optional[float]:
        direct = _lookup_metric(metric, self.facts.metric_baselines)
        if direct is not None:
            return direct
        # before.*/baseline.* keys may still live in the numeric metrics
        m = _norm(metric)
        for key, value in self.facts.numeric_metrics.items():
            k = _norm(key)
            for prefix in ("before ", "baseline "):
                if k.startswith(prefix) and _norm(k[len(prefix):]) == m:
                    return value
            for suffix in (" before", " pre", ".before"):
                if k.endswith(suffix) and _norm(k[: -len(suffix)]) == m:
                    return value
        return None

    def entity_state(self, entity: str) -> Optional[str]:
        return _entity_observed(entity, self.facts.entity_states)

    def process_probe(self):
        return (self.facts.process_verified, self.facts.process_app)

    def count(self, what: str) -> Optional[float]:
        if not self.facts.counts:
            return None
        if what:
            words = [w for w in _norm(what).split() if len(w) > 2]
            relevant = {k: v for k, v in self.facts.counts.items()
                        if any(w in k for w in words)}
            relevant = relevant or self.facts.counts
        else:
            relevant = self.facts.counts
        return max(relevant.values())

    def duration_seconds(self) -> Optional[float]:
        if self.facts.duration_ms is None:
            return None
        return self.facts.duration_ms / 1000.0

    def response_delivered(self) -> Optional[bool]:
        return self.facts.response_delivered

    def error_states(self) -> List[str]:
        return [k for k, s in self.facts.entity_states.items() if s in _NEGATIVE_STATES]

    def any_observations(self) -> bool:
        return bool(self.facts.observation_values or self.facts.entity_states
                    or self.facts.process_verified is True)

    def flag(self, name: str):
        from app.cognition.condition_language import ObservedValue
        target = _norm(name)
        for key, value in self.facts.observation_values.items():
            if _norm(key) == target:
                if isinstance(value, bool):
                    return ObservedValue(value, "boolean", True, source=key)
                return ObservedValue(value, "text", True, source=key)
        return None


def evaluate_predicate(predicate: Dict[str, Any], facts: ObservationFacts) -> CriterionResult:
    """Serialized predicate + observed facts -> PASS / FAIL / UNKNOWN.

    The typed logic lives in the AST node (condition_from_dict); the facts
    supply the typed observations. One interpretation, no heuristics
    duplicated here (P0 review #9).
    """
    node = condition_from_dict(predicate)
    verdict = node.evaluate(FactsEnv(facts))
    return CriterionResult(criterion="", predicate=predicate,
                           status=verdict.status, basis=verdict.basis)


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
