"""Measured worker concurrency derived from live RAM/CPU pressure and owner override.

The governor turns the hardware recommendation (advisory until now) into a
granted worker budget with typed reasons, owner authority within physical
bounds, an absolute critical-pressure gate, and persisted execution receipts.
"""
import json

from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.utils.concurrency_governor import (
    ConcurrencyGovernor,
    ConcurrencyOverride,
    ConcurrencyOverrideStore,
)


def stats(ram_gb=48.0, ram_pct=30.0, cpu_pct=20.0):
    return {"ram_total_gb": ram_gb, "ram_percent": ram_pct, "cpu_percent": cpu_pct}


def test_measured_budget_scales_with_installed_ram(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    high = ConcurrencyGovernor.measure(stats=stats(ram_gb=48.0), cpu_threads=32, store=store)
    mid = ConcurrencyGovernor.measure(stats=stats(ram_gb=24.0), cpu_threads=8, store=store)
    low = ConcurrencyGovernor.measure(stats=stats(ram_gb=8.0), cpu_threads=4, store=store)
    # 48GB/32-thread machine: recommendation 6 fits the half-thread headroom cap.
    assert high["workers_granted"] == 6 and high["physical_thread_cap"] == 32
    # 24GB/8-thread: recommendation 3 clamped to headroom cap 4 → 3.
    assert mid["workers_granted"] == 3
    assert low["workers_granted"] == 1


def test_recommendation_never_exceeds_cpu_headroom(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    # 48GB but only 4 logical threads: half-thread headroom cap is 2.
    result = ConcurrencyGovernor.measure(stats=stats(ram_gb=48.0), cpu_threads=4, store=store)
    assert result["workers_granted"] == 2


def test_live_pressure_scales_budget_down_with_reasons(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    moderate = ConcurrencyGovernor.measure(stats=stats(ram_pct=70.0), cpu_threads=32, store=store)
    high = ConcurrencyGovernor.measure(stats=stats(ram_pct=82.0), cpu_threads=32, store=store)
    critical = ConcurrencyGovernor.measure(stats=stats(ram_pct=93.0), cpu_threads=32, store=store)
    cpu_critical = ConcurrencyGovernor.measure(stats=stats(cpu_pct=97.0), cpu_threads=32, store=store)
    assert moderate["workers_granted"] == 5 and "moderate_ram_pressure_scaled" in moderate["reasons"]
    assert high["workers_granted"] == 3 and "high_ram_pressure_halved" in high["reasons"]
    assert critical["workers_granted"] == 1 and "critical_ram_pressure_serial_only" in critical["reasons"]
    assert cpu_critical["workers_granted"] == 1 and "critical_cpu_pressure_serial_only" in cpu_critical["reasons"]


def test_owner_override_raises_budget_within_physical_threads(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    store.update({"max_workers": 12})
    result = ConcurrencyGovernor.measure(stats=stats(), cpu_threads=8, store=store)
    # Owner authority is real but cannot exceed physical threads: 8, not 12.
    assert result["workers_granted"] == 8
    assert result["configured_budget"] == 8
    assert "owner_max_workers_clamped_to_physical_8" in result["reasons"]


def test_owner_override_cannot_bypass_critical_pressure(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    store.update({"max_workers": 12})
    result = ConcurrencyGovernor.measure(stats=stats(ram_pct=95.0), cpu_threads=8, store=store)
    assert result["workers_granted"] == 1
    assert "critical_ram_pressure_serial_only" in result["reasons"]


def test_owner_can_disable_parallelism(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    store.update({"enabled": False})
    result = ConcurrencyGovernor.measure(stats=stats(), cpu_threads=32, store=store)
    assert result["workers_granted"] == 1 and "owner_disabled_parallelism" in result["reasons"]


def test_override_store_is_atomic_and_fail_safe(tmp_path):
    path = tmp_path / "cb.json"
    store = ConcurrencyOverrideStore(path)
    store.update({"max_workers": 4})
    assert json.loads(path.read_text())["max_workers"] == 4
    store.update({"max_workers": None})  # explicit reset to measured defaults
    assert json.loads(path.read_text())["max_workers"] is None
    path.write_text("{ not json")
    reloaded = ConcurrencyOverrideStore(path)
    assert reloaded.get().max_workers is None and reloaded.get().enabled is True


def test_override_store_rejects_unknown_or_invalid_fields(tmp_path):
    store = ConcurrencyOverrideStore(tmp_path / "cb.json")
    for bad in ({"nonsense": 1}, {"max_workers": "many"}, {"enabled": "yes"}):
        try:
            store.update(bad)
            raised = False
        except ValueError:
            raised = True
        assert raised


def _measurement(workers):
    return {
        "success": True,
        "workers_granted": workers,
        "configured_budget": workers,
        "base_recommendation": workers,
        "physical_thread_cap": 32,
        "reasons": [],
        "measured": {"cpu_threads": 32, "ram_total_gb": 48.0, "ram_percent": 30.0, "cpu_percent": 20.0},
        "owner_override": ConcurrencyOverride().to_dict(),
    }


def test_run_parallel_preserves_order_and_matches_serial(tmp_path):
    items = list(range(100))
    receipt_path = tmp_path / "receipts.jsonl"
    parallel_results, receipt = ConcurrencyGovernor.run_parallel(
        lambda n: n * n, items, label="test_parallel",
        measurement=_measurement(4), receipts_path=receipt_path,
    )
    assert parallel_results == [n * n for n in items]  # identical to serial
    assert receipt["parallel_executed"] is True
    assert receipt["workers_granted"] == 4 and receipt["items"] == 100
    assert receipt["duration_seconds"] >= 0
    persisted = json.loads(receipt_path.read_text().splitlines()[-1])
    assert persisted["receipt_id"] == receipt["receipt_id"]


def test_run_parallel_serial_when_budget_is_one(tmp_path):
    receipt_path = tmp_path / "receipts.jsonl"
    measurement = _measurement(1)
    measurement["reasons"] = ["critical_ram_pressure_serial_only"]
    results, receipt = ConcurrencyGovernor.run_parallel(
        lambda n: n + 1, [1, 2, 3], label="test_serial",
        measurement=measurement, receipts_path=receipt_path,
    )
    assert results == [2, 3, 4]
    assert receipt["parallel_executed"] is False
    assert receipt["serial_reason"] == "critical_ram_pressure_serial_only"


def test_receipt_log_is_bounded(tmp_path):
    receipt_path = tmp_path / "receipts.jsonl"
    for _ in range(ConcurrencyGovernor.max_receipts + 25):
        ConcurrencyGovernor.run_parallel(
            lambda n: n, [1], label="bounded",
            measurement=_measurement(1), receipts_path=receipt_path,
        )
    lines = [ln for ln in receipt_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == ConcurrencyGovernor.max_receipts
    assert len(ConcurrencyGovernor.recent_receipts(limit=500, path=receipt_path)) == ConcurrencyGovernor.max_receipts


def test_counterfactual_simulation_uses_measured_workers(tmp_path, monkeypatch):
    monkeypatch.setattr(ConcurrencyGovernor, "receipts_path", tmp_path / "cf_receipts.jsonl")
    monkeypatch.setattr(
        ConcurrencyGovernor, "measure",
        classmethod(lambda cls, **kwargs: _measurement(3)),
    )
    candidates = [
        {"name": "search", "action_type": "web_search", "payload": {"query": "docs"}},
        {"name": "open", "action_type": "open_application", "payload": {"app": "editor"}},
        {"name": "find", "action_type": "search_files", "payload": {"pattern": "*.txt"}},
        {"name": "email", "action_type": "send_email", "payload": {"to": "a@b.c"}},
    ]
    result = CounterfactualSimulator.simulate_competing_branches("open and search documents", candidates)

    # Same branch set as serial computation, same winner by utility.
    manifest_levels = {}
    from app.tools.manifest import get_tool_manifest
    manifest_levels = {n: int(e.get("safety_level", 0)) for n, e in get_tool_manifest().items()}
    serial = [
        CounterfactualSimulator._simulate_one_branch(
            (i, act), target_goal="open and search documents", goal_type=None,
            outcome_store=None, lesson_store=None, skill_classifier=None,
            hardware_self_model=None, resource_manager=None, manifest_levels=manifest_levels,
        )
        for i, act in enumerate(candidates, 1)
    ]
    assert sorted(b.utility_score for b in result.competing_branches) == sorted(b.utility_score for b in serial)
    assert result.winning_branch.utility_score == max(b.utility_score for b in serial)

    # Authorization classification comes from the manifest snapshot, unchanged.
    by_name = {b.branch_name: b for b in result.competing_branches}
    assert by_name["email"].authorization_requirement == "explicit_owner_approval"
    assert by_name["search"].authorization_requirement == "delegated_policy"

    # Measured concurrency evidence is attached.
    evidence = result.execution_evidence
    assert evidence["workers_granted"] == 3 and evidence["parallel_executed"] is True
    assert evidence["items"] == 4 and evidence["label"] == "counterfactual_branches"


def test_owner_concurrency_budget_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.utils.concurrency_governor as cg

    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    monkeypatch.setattr(cg, "concurrency_override_store", cg.ConcurrencyOverrideStore(tmp_path / "cb.json"))
    monkeypatch.setattr(ConcurrencyGovernor, "receipts_path", tmp_path / "receipts.jsonl")
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    current = client.get("/owner-control/concurrency-budget", headers=headers)
    assert current.status_code == 200 and current.json()["budget"]["workers_granted"] >= 1

    updated = client.put(
        "/owner-control/concurrency-budget",
        headers=headers,
        json={"max_workers": 3},
    )
    body = updated.json()
    assert body["success"] is True
    assert body["override"]["max_workers"] == 3 and body["override"]["revision"] == 1
    # The owner-posed budget is honored but never exceeds physical threads.
    physical_cap = body["budget"]["physical_thread_cap"]
    assert body["budget"]["configured_budget"] == min(3, physical_cap)
    if physical_cap < 3:
        assert any("clamped_to_physical" in r for r in body["budget"]["reasons"])

    reset = client.put(
        "/owner-control/concurrency-budget",
        headers=headers,
        json={"max_workers": None},
    )
    assert reset.json()["override"]["max_workers"] is None  # back to measured defaults
    assert reset.json()["override"]["revision"] == 2

    receipts = client.get("/owner-control/concurrency-budget/receipts", headers=headers)
    assert receipts.status_code == 200 and receipts.json()["receipts"] == []

    bad = client.put(
        "/owner-control/concurrency-budget",
        headers=headers,
        json={"max_workers": 0},
    )
    assert bad.status_code == 422  # ge=1 enforced: no zero/negative worker budgets
