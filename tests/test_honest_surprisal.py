"""P0 bottleneck #14: the counterfactual simulator's surprisal term must
DISCRIMINATE branches. The old hardcoded 0.15 made the uncertainty
component of the utility purely decorative. Now it is estimated from
Arena's verified execution history (action_outcomes: dispersion + Wilson
interval width), with honest priors when there is no history."""
from types import SimpleNamespace
from unittest.mock import patch

import app.cognition.action_outcomes as ao
from app.cognition.counterfactual_simulator import CounterfactualSimulator


def _store(**per_action):
    """Fake outcome store: per_action maps action_type -> estimate dict;
    anything else has no history (n=0)."""
    store = SimpleNamespace()

    def estimate(action_type, **kw):
        if action_type in per_action:
            return SimpleNamespace(**per_action[action_type])
        return SimpleNamespace(n=0, smoothed_success_rate=0.5, wilson_low=0.0, wilson_high=1.0)

    store.estimate = estimate
    return store


def _candidates(*pairs):
    return [{"name": n, "action_type": t, "payload": {}} for n, t in pairs]


def _branches(goal, candidates):
    res = CounterfactualSimulator.simulate_competing_branches(goal, candidates)
    return {b.hypothetical_action: b for b in res.competing_branches
            if b.branch_name != "Default Fallback"}


def test_surprisal_discriminates_branches():
    store = _store(
        search_files=dict(n=20, smoothed_success_rate=0.95, wilson_low=0.76, wilson_high=0.99),
        run_data_analysis=dict(n=10, smoothed_success_rate=0.5, wilson_low=0.24, wilson_high=0.76),
    )
    with patch.object(ao, "action_outcome_store", store):
        branches = _branches("do the thing", _candidates(
            ("File search", "search_files"), ("Data analysis", "run_data_analysis"),
            ("Mystery", "quantum_widget")))
    assert branches["search_files"].estimated_surprisal < \
           branches["run_data_analysis"].estimated_surprisal < \
           branches["quantum_widget"].estimated_surprisal
    # And it moves the utility, not just the label.
    assert branches["search_files"].utility_score > branches["run_data_analysis"].utility_score


def test_utility_gap_equals_the_surprisal_gap():
    """With equal goal-fit and risk, the utility difference must be exactly
    0.2 x the surprisal difference (the term's weight in the formula)."""
    store = _store(
        tool_a=dict(n=30, smoothed_success_rate=1.0, wilson_low=0.89, wilson_high=1.0),
        tool_b=dict(n=10, smoothed_success_rate=0.5, wilson_low=0.24, wilson_high=0.76),
    )
    with patch.object(ao, "action_outcome_store", store):
        branches = _branches("do the thing", _candidates(
            ("A", "tool_a"), ("B", "tool_b")))
    sa, sb = branches["tool_a"], branches["tool_b"]
    expected_gap = round(0.2 * (sb.estimated_surprisal - sa.estimated_surprisal), 4)
    # a has LOWER surprisal -> HIGHER utility; the gap is exactly the term's weight
    assert abs((sa.utility_score - sb.utility_score) - expected_gap) < 1e-3


def test_no_history_is_an_honest_prior_not_fake_confidence():
    """Untested actions get the coin-flip prior (0.5), labeled as a prior —
    never the old fake-confident 0.15."""
    with patch.object(ao, "action_outcome_store", _store()):
        branches = _branches("do the thing", _candidates(("Search", "search_files")))
    b = branches["search_files"]
    assert b.estimated_surprisal == 0.5
    assert b.consequences["uncertainty_source"] == "prior (no execution history)"


def test_unregistered_actions_are_more_uncertain_than_registered():
    with patch.object(ao, "action_outcome_store", _store()):
        branches = _branches("do the thing", _candidates(
            ("Search", "search_files"), ("Mystery", "quantum_widget")))
    assert branches["quantum_widget"].estimated_surprisal == 0.7
    assert branches["quantum_widget"].consequences["uncertainty_source"] == \
        "prior (unregistered action)"


def test_consistent_history_is_predictable_coinflip_history_is_not():
    store = _store(
        consistent=dict(n=30, smoothed_success_rate=1.0, wilson_low=0.89, wilson_high=1.0),
        coinflip=dict(n=30, smoothed_success_rate=0.5, wilson_low=0.34, wilson_high=0.66),
    )
    with patch.object(ao, "action_outcome_store", store):
        branches = _branches("do the thing", _candidates(
            ("Consistent", "consistent"), ("CoinFlip", "coinflip")))
    assert branches["consistent"].estimated_surprisal < 0.2
    assert branches["coinflip"].estimated_surprisal > 0.40


def test_thin_evidence_stays_uncertain():
    """Two perfect successes are NOT knowledge: the Wilson interval stays
    wide, so surprisal must not collapse toward zero."""
    store = _store(thin=dict(n=2, smoothed_success_rate=1.0, wilson_low=0.34, wilson_high=1.0))
    with patch.object(ao, "action_outcome_store", store):
        branches = _branches("do the thing", _candidates(("Thin", "thin")))
    assert branches["thin"].estimated_surprisal > 0.25
    assert "n=2" in branches["thin"].consequences["uncertainty_source"]
