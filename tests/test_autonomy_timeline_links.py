"""Commitment and recovery links on every autonomy timeline event.

attach_cycle_links is a read-time join over immutable stored events: plan
commitments appear on the events that reference the plan, and recovery
assessments raised during each event's OWN cycle window appear on that cycle's
events — per-cycle windows, labeled as temporal co-occurrence, never a
causation claim. Stored events are never rewritten.
"""
from types import SimpleNamespace

from app.cognition.autonomy_run_ledger import AutonomyRunLedger, attach_cycle_links


class FakeCommitmentLedger:
    def __init__(self, by_source):
        self.by_source = by_source
        self.queries = []

    def get_by_source(self, source_type, source_id):
        self.queries.append((source_type, source_id))
        return self.by_source.get((source_type, str(source_id)))


class FakeRecoveryStore:
    def __init__(self, assessments):
        self.assessments = assessments

    def list(self, limit=200, status_filter=None):
        return self.assessments


def commitment(cid, status="completed", verified=True):
    return SimpleNamespace(commitment_id=cid, status=status, completion_verified=verified)


def assessment(aid, created_at, status="pending"):
    return SimpleNamespace(assessment_id=aid, status=status, created_at=created_at)


def test_plan_commitments_attach_to_referencing_events(tmp_path):
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    ledger.record("c1", "execution_started", goal_id="g1", details={"plan_id": "plan_9", "allocation": {}})
    ledger.record("c1", "executed", goal_id="g1", details={"plan_id": "plan_9", "execution_links": []})
    ledger.record("c1", "considered", goal_id="g1", details={"title": "unrelated"})
    events = list(reversed(ledger.list(cycle_id="c1")))

    commitments = FakeCommitmentLedger({("approved_plan", "plan_9"): commitment("cm_1")})
    enriched = attach_cycle_links(events, commitment_ledger=commitments, recovery_store=FakeRecoveryStore([]))
    by_stage = {e["stage"]: e for e in enriched}

    assert by_stage["considered"]["commitment_links"] is None      # no plan reference
    assert by_stage["execution_started"]["commitment_links"][0]["commitment_id"] == "cm_1"
    assert by_stage["executed"]["commitment_links"][0]["source"] == "approved_plan:plan_9"
    assert by_stage["executed"]["commitment_links"][0]["completion_verified"] is True
    assert ("approved_plan", "plan_9") in commitments.queries


def test_missing_commitment_is_honest_null(tmp_path):
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    ledger.record("c1", "executed", goal_id="g1", details={"plan_id": "plan_none"})
    events = list(reversed(ledger.list(cycle_id="c1")))
    enriched = attach_cycle_links(events, commitment_ledger=FakeCommitmentLedger({}), recovery_store=FakeRecoveryStore([]))
    assert enriched[0]["commitment_links"] is None


def test_recovery_assessments_attach_per_cycle_window(tmp_path):
    import sqlite3
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    ledger.record("cA", "cycle_started", details={"started_at": "2026-01-01T08:00:00+00:00"})
    ledger.record("cA", "cycle_failed", reason="goal failed")
    ledger.record("cB", "cycle_started", details={"started_at": "2026-01-01T12:00:00+00:00"})
    ledger.record("cB", "cycle_completed", reason="ok")
    # Deterministic wall-clock windows: cA spans 08:00:00–08:00:10, cB 12:00:00–12:00:10.
    with sqlite3.connect(ledger.path) as conn:
        conn.execute("UPDATE autonomy_events SET created_at='2026-01-01T08:00:01+00:00' WHERE cycle_id='cA' AND stage='cycle_started'")
        conn.execute("UPDATE autonomy_events SET created_at='2026-01-01T08:00:10+00:00' WHERE cycle_id='cA' AND stage='cycle_failed'")
        conn.execute("UPDATE autonomy_events SET created_at='2026-01-01T12:00:01+00:00' WHERE cycle_id='cB' AND stage='cycle_started'")
        conn.execute("UPDATE autonomy_events SET created_at='2026-01-01T12:00:10+00:00' WHERE cycle_id='cB' AND stage='cycle_completed'")
        conn.commit()
    events = list(reversed(ledger.list(limit=10)))

    during_a = assessment("rec_1", "2026-01-01T08:00:05+00:00", status="decided")
    during_b = assessment("rec_2", "2026-01-01T12:00:05+00:00")
    before_all = assessment("rec_0", "2026-01-01T07:00:00+00:00")
    enriched = attach_cycle_links(events, recovery_store=FakeRecoveryStore([during_a, during_b, before_all]))

    by_cycle_stage = {(e["cycle_id"], e["stage"]): e for e in enriched}
    ids_a = [r["assessment_id"] for r in by_cycle_stage[("cA", "cycle_failed")]["recovery_assessment_ids"]]
    ids_b = [r["assessment_id"] for r in by_cycle_stage[("cB", "cycle_completed")]["recovery_assessment_ids"]]
    # Windows are per cycle: rec_1 only inside cA's 08:00–08:10 window, rec_2
    # only inside cB's, and rec_0 before both starts is never linked.
    assert ids_a == ["rec_1"]
    assert ids_b == ["rec_2"]
    link_a = by_cycle_stage[("cA", "cycle_failed")]["recovery_assessment_ids"][0]
    assert link_a["raised_during_cycle"] is True and link_a["status"] == "decided"


def test_every_event_carries_both_link_fields(tmp_path):
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    for stage in ("cycle_started", "observed", "considered", "recommended", "executed"):
        ledger.record("c1", stage, goal_id="g1", details={"plan_id": "p1"} if stage == "executed" else {})
    events = list(reversed(ledger.list(cycle_id="c1")))
    enriched = attach_cycle_links(
        events,
        commitment_ledger=FakeCommitmentLedger({("approved_plan", "p1"): commitment("cm_x", status="active", verified=False)}),
        recovery_store=FakeRecoveryStore([assessment("rec_9", "2099-01-01T00:00:00+00:00")]),  # far future: outside window
    )
    assert len(enriched) == 5
    for event in enriched:
        assert "commitment_links" in event and "recovery_assessment_ids" in event
        assert event["recovery_assessment_ids"] == []  # outside window stays empty
    # Stored rows are never rewritten by the join.
    assert all("commitment_links" not in (e.details or {}) for e in ledger.list(cycle_id="c1"))


def test_unparseable_window_disables_recovery_join(tmp_path):
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    ledger.record("c1", "cycle_started", details={"started_at": "not-a-timestamp"})
    ledger.record("c1", "cycle_completed", reason="ok")
    events = list(reversed(ledger.list(cycle_id="c1")))
    enriched = attach_cycle_links(events, recovery_store=FakeRecoveryStore([assessment("rec", "2026-08-24T10:05:00+00:00")]))
    assert enriched[0]["recovery_assessment_ids"] == []


def test_failing_ledgers_degrade_to_null_links(tmp_path):
    ledger = AutonomyRunLedger(tmp_path / "l.db")
    ledger.record("c1", "executed", goal_id="g1", details={"plan_id": "p1"})
    events = list(reversed(ledger.list(cycle_id="c1")))

    class Broken:
        def get_by_source(self, *a, **k):
            raise RuntimeError("db locked")

        def list(self, *a, **k):
            raise RuntimeError("db locked")

    enriched = attach_cycle_links(events, commitment_ledger=Broken(), recovery_store=Broken())
    assert enriched[0]["commitment_links"] is None
    assert enriched[0]["recovery_assessment_ids"] == []
