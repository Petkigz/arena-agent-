"""P0 review #9: the typed condition language.

Condition AST -> observation query -> typed value -> predicate ->
PASS / FAIL / UNKNOWN. One parser (parse_condition), one AST, two
consumers (StepVerifier criteria via criterion_evaluator, goal conditions
via GoalVerifier's provenance environment).

The flagship case: 'CPU usage dropped by at least 20%' — a MEASURED
CHANGE that needs a typed baseline, not a string heuristic.
"""

from app.cognition.condition_language import (
    FAIL,
    PASS,
    UNKNOWN,
    CountAtLeast,
    FlagCondition,
    MetricDelta,
    NumericThreshold,
    ObservationEnvironment,
    ObservedValue,
    ResponseDelivered,
    StateCondition,
    condition_from_dict,
    parse_condition,
)
from app.cognition.criterion_evaluator import evaluate_criteria


class FakeEnv(ObservationEnvironment):
    def __init__(self, metrics=None, baselines=None, states=None, counts=None,
                 duration=None, response=None, flags=None):
        self._metrics = metrics or {}
        self._baselines = baselines or {}
        self._states = states or {}
        self._counts = counts or {}
        self._duration = duration
        self._response = response
        self._flags = flags or {}

    def metric(self, name):
        return self._metrics.get(name)

    def baseline(self, metric):
        return self._baselines.get(metric)

    def entity_state(self, entity):
        return self._states.get(entity)

    def count(self, what):
        return self._counts.get(what)

    def duration_seconds(self):
        return self._duration

    def response_delivered(self):
        return self._response

    def flag(self, name):
        v = self._flags.get(name)
        return ObservedValue(v, "boolean", True, source=f"test:{name}") if v is not None else None


# --- parsing into the AST -----------------------------------------------------

def test_flag_conditions_parse_to_typed_nodes():
    node = parse_condition("response_delivered = true")
    assert isinstance(node, FlagCondition) and node.expected is True
    node = parse_condition("app_process_running = true")
    assert isinstance(node, FlagCondition) and node.name == "app_process_running"
    node = parse_condition("network_available = false")
    assert isinstance(node, FlagCondition) and node.expected is False
    node = parse_condition("cpu_idle")
    assert isinstance(node, FlagCondition)  # bare snake_case flag


def test_entity_sentences_are_not_flags():
    """'Chrome is running' is an entity state — the flag grammar must not
    steal it (the copula is restricted to strict true/false)."""
    assert isinstance(parse_condition("Chrome is running"), StateCondition)
    assert isinstance(parse_condition("report.pdf exists"), StateCondition)
    assert isinstance(parse_condition("The file is saved"), StateCondition)


def test_metric_delta_parses_with_unit_and_at_least():
    node = parse_condition("CPU usage dropped by at least 20%")
    assert isinstance(node, MetricDelta)
    assert node.metric == "cpu usage"
    assert node.direction == "dropped"
    assert node.value == 20.0
    assert node.unit == "percent"
    node = parse_condition("CPU usage decreased by 20%")
    assert isinstance(node, MetricDelta)
    node = parse_condition("load average rose by 1.5 points")
    assert isinstance(node, MetricDelta) and node.unit == "points"


def test_ast_round_trips_through_the_predicate_dict():
    for text in ["CPU usage dropped by at least 20%", "Chrome is running",
                 "response_delivered = true", "completes within 5 seconds",
                 "at least 3 results", "CPU above 90%"]:
        node = condition_from_dict(node_dict := parse_condition(text).to_dict())
        assert node.to_dict() == node_dict, text


# --- THE example: measured deltas ----------------------------------------------

def test_cpu_drop_evaluates_pass_with_baseline():
    """CPU 80% -> 60% is a 25% drop: 'dropped by at least 20%' PASSES, with
    the measured numbers in the basis."""
    node = parse_condition("CPU usage dropped by at least 20%")
    verdict = node.evaluate(FakeEnv(metrics={"cpu usage": 60.0},
                                    baselines={"cpu usage": 80.0}))
    assert verdict.status == PASS
    assert "80" in verdict.basis and "60" in verdict.basis


def test_cpu_drop_evaluates_fail_when_change_too_small():
    node = parse_condition("CPU usage dropped by at least 20%")
    verdict = node.evaluate(FakeEnv(metrics={"cpu usage": 70.0},   # 12.5% drop
                                    baselines={"cpu usage": 80.0}))
    assert verdict.status == FAIL


def test_cpu_drop_without_baseline_is_unknown_with_reason():
    node = parse_condition("CPU usage dropped by at least 20%")
    verdict = node.evaluate(FakeEnv(metrics={"cpu usage": 60.0}))
    assert verdict.status == UNKNOWN
    assert "baseline" in verdict.basis


def test_cpu_drop_without_any_measurement_is_unknown():
    node = parse_condition("CPU usage dropped by at least 20%")
    verdict = node.evaluate(FakeEnv())
    assert verdict.status == UNKNOWN
    assert "before-and-after" in verdict.basis


def test_points_deltas_are_absolute():
    node = parse_condition("CPU usage dropped by at least 20 points")
    assert node.evaluate(FakeEnv(metrics={"cpu usage": 55.0},
                                 baselines={"cpu usage": 80.0})).status == PASS
    assert node.evaluate(FakeEnv(metrics={"cpu usage": 65.0},   # 15 points
                                 baselines={"cpu usage": 80.0})).status == FAIL


def test_rising_deltas():
    node = parse_condition("throughput rose by at least 50%")
    assert node.evaluate(FakeEnv(metrics={"throughput": 30.0},
                                 baselines={"throughput": 20.0})).status == PASS
    assert node.evaluate(FakeEnv(metrics={"throughput": 25.0},
                                 baselines={"throughput": 20.0})).status == FAIL


# --- flags: typed values + predicates ------------------------------------------

def test_flag_passes_on_authorized_true():
    node = FlagCondition(name="response_delivered", expected=True)
    verdict = node.evaluate(FakeEnv(flags={"response_delivered": True}))
    assert verdict.status == PASS


def test_flag_fails_on_refuted_value_regardless_of_provenance():
    node = FlagCondition(name="app_process_running", expected=True,
                         satisfied_by=("running", "active"),
                         refuted_by=("crashed", "failed", "terminated", "error"))
    verdict = node.evaluate(FakeEnv(flags={"app_process_running": "crashed"}))
    assert verdict.status == FAIL


def test_unauthorized_evidence_is_unknown_not_pass():
    class UnauthEnv(FakeEnv):
        def flag(self, name):
            v = self._flags.get(name)
            return ObservedValue(v, "state", authorized=False, source="self_reported") if v is not None else None

    node = FlagCondition(name="app_process_running", expected=True,
                         satisfied_by=("running", "active"))
    verdict = node.evaluate(UnauthEnv(flags={"app_process_running": "running"}))
    assert verdict.status == UNKNOWN
    assert "provenance" in verdict.basis


def test_response_delivered_node():
    assert ResponseDelivered().evaluate(FakeEnv(response=True)).status == PASS
    assert ResponseDelivered().evaluate(FakeEnv(response=False)).status == FAIL


# --- typed thresholds -----------------------------------------------------------

def test_numeric_threshold_typed_comparison():
    node = NumericThreshold(subject="cpu", op="above", value=90.0)
    assert node.evaluate(FakeEnv(metrics={"cpu": 95.0})).status == PASS
    assert node.evaluate(FakeEnv(metrics={"cpu": 80.0})).status == FAIL
    assert node.evaluate(FakeEnv()).status == UNKNOWN


# --- the StepVerifier pipeline now evaluates deltas end-to-end ------------------

def test_evaluate_criteria_computes_delta_from_cycle_baselines():
    """criterion_evaluator feeds the AST from cycle facts: baselines arrive
    via metric_baselines; 'dropped by at least 20%' is computed, not
    string-matched."""
    results = evaluate_criteria(["CPU usage dropped by at least 20%"], {
        "verification_observed_state": {
            "observations": {"cpu_usage": 60.0},
            "verified_entity_states": {},
        },
        "metric_baselines": {"cpu_usage": 80.0},
    })
    assert results[0].status == "pass"
    assert "before-and-after" not in results[0].basis


def test_evaluate_criteria_delta_without_baseline_stays_unknown():
    results = evaluate_criteria(["CPU usage dropped by at least 20%"], {
        "verification_observed_state": {
            "observations": {"cpu_usage": 60.0},
            "verified_entity_states": {},
        },
    })
    assert results[0].status == "unknown"
    assert "baseline" in results[0].basis
