"""P0 #16: success criteria are EVALUATED, not copied.

The pipeline under test:
    NL criterion -> structured predicate -> observation -> deterministic
    evaluation -> PASS / FAIL / UNKNOWN (with a basis trail)

The canonical example: "CPU usage decreased by 20%" must be parsed into a
metric-delta predicate, found to lack before/after measurements, and reported
UNKNOWN — blocking step COMPLETION — instead of being waved through on the
runtime's goal_verified.
"""

from app.cognition.criterion_evaluator import (
    ObservationFacts,
    evaluate_criteria,
    parse_criterion,
)
from app.cognition.step_verifier import StepVerifier


class _Step:
    def __init__(self, produces=None, requires=None, success=None, failure=None):
        self.produces_evidence = produces or []
        self.requires_evidence = requires or []
        self.success_criteria = success or []
        self.failure_conditions = failure or []


# ---------------------------------------------------------------------------
# Stage 1: parsing
# ---------------------------------------------------------------------------

def test_parse_metric_delta():
    p = parse_criterion("CPU usage decreased by 20%")
    assert p["type"] == "metric_delta"
    assert p["metric"] == "cpu usage"
    assert p["value"] == 20.0
    assert p["direction"] == "decreased"


def test_parse_entity_running():
    p = parse_criterion("Chrome is running")
    assert p["type"] == "entity_state"
    assert p["entity"] == "chrome"


def test_parse_exists():
    assert parse_criterion("report.pdf exists")["type"] == "entity_state"
    assert parse_criterion("The file is saved")["type"] == "entity_state"


def test_parse_duration_and_counts():
    assert parse_criterion("completes within 5 seconds")["type"] == "duration_max"
    assert parse_criterion("at least 3 results")["type"] == "count_at_least"
    assert parse_criterion("5 or more files")["type"] == "count_at_least"


def test_parse_opaque_is_opaque():
    p = parse_criterion("Knowledge integrated into belief system")
    assert p["type"] == "opaque"


# ---------------------------------------------------------------------------
# Stage 2-4: evaluation against observations
# ---------------------------------------------------------------------------

def test_cpu_delta_without_measurements_is_unknown_not_pass():
    """THE example: nothing was measured, so nothing can be calculated."""
    results = evaluate_criteria(["CPU usage decreased by 20%"], {
        "goal_verified": True,
        "executed_actions": [{"action_type": "optimize"}],
        "environment_observed": True,
    })
    assert results[0].status == "unknown"
    assert "before-and-after" in results[0].basis
    assert results[0].predicate["type"] == "metric_delta"


def test_entity_running_passes_via_os_grounding():
    results = evaluate_criteria(["Chrome is running"], {
        "os_grounding": {"success": True, "verified": True,
                         "grounding": {"app_name": "chrome"}},
    })
    assert results[0].status == "pass"
    assert "chrome" in results[0].basis


def test_entity_running_refuted_by_failed_grounding():
    results = evaluate_criteria(["Chrome is running"], {
        "os_grounding": {"success": False, "verified": False,
                         "error": "No matching running process observed"},
    })
    assert results[0].status == "fail"


def test_entity_state_via_verifier_observations():
    results = evaluate_criteria(["report.pdf exists"], {
        "verification_observed_state": {
            "observations": {},
            "verified_entity_states": {"report.pdf": "found"},
        },
    })
    assert results[0].status == "pass"


def test_entity_never_observed_is_unknown():
    results = evaluate_criteria(["Slack is running"], {"environment_observed": True})
    assert results[0].status == "unknown"
    assert "never observed" in results[0].basis


def test_count_at_least_with_count_observation():
    results = evaluate_criteria(["at least 3 results"], {
        "verification_observed_state": {
            "observations": {"search.results_count": 5, "search.query": "pdf"},
            "verified_entity_states": {},
        },
    })
    assert results[0].status == "pass"
    assert "5" in results[0].basis


def test_count_at_least_without_observation_is_unknown():
    results = evaluate_criteria(["at least 3 results"], {})
    assert results[0].status == "unknown"


def test_duration_evaluated_against_measured_latency():
    fast = evaluate_criteria(["completes within 5 seconds"], {"latency_ms": 812.0})
    slow = evaluate_criteria(["completes within 5 seconds"], {"latency_ms": 8000.0})
    assert fast[0].status == "pass"
    assert slow[0].status == "fail"
    assert "measured duration" in slow[0].basis


def test_numeric_threshold_observed_and_not():
    observed = evaluate_criteria(["Confidence level above 0.7"], {
        "verification_observed_state": {
            "observations": {"confidence_level": 0.82},
            "verified_entity_states": {},
        },
    })
    missing = evaluate_criteria(["Confidence level above 0.7"], {})
    assert observed[0].status == "pass"
    assert missing[0].status == "unknown"
    assert "not numerically observed" in missing[0].basis


def test_response_delivered_uses_reply_existence():
    ok = evaluate_criteria(["Response delivered"], {"assistant_reply": "here you go"})
    missing = evaluate_criteria(["Response delivered"], {"assistant_reply": ""})
    assert ok[0].status == "pass"
    assert missing[0].status == "fail"


def test_goal_verifier_condition_verdict_is_reused():
    results = evaluate_criteria(["App process running"], {
        "verification_met_conditions": ["app_process_running"],
    })
    assert results[0].status == "pass"
    assert "goal verifier" in results[0].basis


def test_reply_text_is_never_an_observation_for_state_criteria():
    """The reply SAYING chrome is running must not verify that chrome runs."""
    results = evaluate_criteria(["Chrome is running"], {
        "assistant_reply": "Chrome is definitely running now!",
    })
    assert results[0].status == "unknown"


# ---------------------------------------------------------------------------
# StepVerifier integration: criteria now drive the verdict
# ---------------------------------------------------------------------------

def _cycle(**kw):
    base = {
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "reasoning_action": "act",
        "executed_actions": [{"action_type": "launch_app"}],
        "environment_observed": True,
        "assistant_reply": "done",
    }
    base.update(kw)
    return base


def test_unevaluable_criterion_blocks_completion_despite_goal_verified():
    step = _Step(success=["CPU usage decreased by 20%"])
    v = StepVerifier.verify_step(step, _cycle())
    assert v.status == "unverified"
    assert v.postcondition_verified is False
    assert "criteria not verifiable" in v.explanation
    assert any(r.status == "unknown" for r in v.criterion_results)


def test_refuted_criterion_fails_step_despite_goal_verified():
    """A green runtime verdict cannot overwrite a refuted postcondition."""
    step = _Step(success=["Chrome is running"])
    v = StepVerifier.verify_step(step, _cycle(os_grounding={
        "success": False, "verified": False, "error": "No matching running process observed",
    }))
    assert v.status == "failed"
    assert v.confidence == 0.0
    assert "refuted by observation" in v.explanation
    assert "Chrome is running" in v.unmet_criteria


def test_all_criteria_pass_completes_step():
    step = _Step(success=["Chrome is running", "Response delivered"])
    v = StepVerifier.verify_step(step, _cycle(os_grounding={
        "success": True, "verified": True, "grounding": {"app_name": "chrome"},
    }))
    assert v.status == "verified"
    assert v.confidence == 0.9
    assert v.postcondition_verified is True
    assert v.met_criteria == ["Chrome is running", "Response delivered"]


def test_observed_failure_condition_triggers_failed():
    step = _Step(success=["System stable"], failure=["App crashed"])
    v = StepVerifier.verify_step(step, _cycle(os_grounding={
        "success": False, "verified": False, "error": "No matching running process observed",
    }))
    # "System stable" can't be evaluated; but the failure condition "App
    # crashed"... is entity-less, so also unevaluable — only an OBSERVED
    # failure condition triggers. Use an explicit one instead:
    assert v.status in ("failed", "unverified")


def test_observed_crash_failure_condition_fails_step():
    step = _Step(success=["Report saved"], failure=["process crashed"])
    facts_cycle = _cycle(
        verification_observed_state={
            "observations": {},
            "verified_entity_states": {"process": "crashed"},
        },
    )
    v = StepVerifier.verify_step(step, facts_cycle)
    assert v.status == "failed"
    assert "process crashed" in v.triggered_failure_conditions


def test_met_criteria_are_real_evaluations_not_copies():
    """met_criteria must contain only criteria that PASSED evaluation."""
    step = _Step(success=["Chrome is running", "CPU usage decreased by 20%"])
    v = StepVerifier.verify_step(step, _cycle(os_grounding={
        "success": True, "verified": True, "grounding": {"app_name": "chrome"},
    }))
    assert v.met_criteria == ["Chrome is running"]
    assert "CPU usage decreased by 20%" in v.unmet_criteria


def test_step_contract_override_beats_goal_level_failure():
    """The runtime's goal verdict is NOT the step verdict: observed-satisfied
    criteria complete the step even when goal_verified is False and the
    lifecycle says 'blocked' (e.g. a later stage was gated while the step's
    own work already succeeded and was observed)."""
    step = _Step(success=["at least 1 result found", "Response delivered"])
    cycle = {
        "goal_verified": False,
        "goal_lifecycle_state": "blocked",
        "reasoning_action": "act",
        "executed_actions": [{"action_type": "search_files"}],
        "environment_observed": True,
        "verification_observed_state": {
            "observations": {"filesystem.search_result_set": {"count": 5}},
            "verified_entity_states": {},
        },
        "assistant_reply": "Found 5 PDFs.",
    }
    v = StepVerifier.verify_step(step, cycle, available_evidence=None)
    assert v.status == "verified"
    assert v.confidence == 0.9
    assert v.postcondition_verified is True
    assert "all declared criteria observed satisfied" in v.explanation


def test_refutation_outranks_lifecycle_success():
    """A green runtime verdict cannot rescue a refuted postcondition."""
    step = _Step(success=["Chrome is running"])
    cycle = {
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "reasoning_action": "act",
        "executed_actions": [{"action_type": "launch_app"}],
        "environment_observed": True,
        "os_grounding": {"success": False, "verified": False,
                         "error": "No matching running process observed"},
        "assistant_reply": "Launched!",
    }
    v = StepVerifier.verify_step(step, cycle, available_evidence=None)
    assert v.status == "failed"
    assert "refuted by observation" in v.explanation
