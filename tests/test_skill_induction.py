"""Skill induction: repeated successful sequences become owner-reviewed skills.

Mining measures completion honestly (failed contexts veto a pattern), payloads
are templated (varying values → {{params}}, constants stay concrete), and
nothing enters the taught-skills library until the owner accepts.
"""
import json
import sqlite3
from pathlib import Path

from app.cognition.skill_induction import SkillInductionEngine


def make_plans_db(tmp_path, plans):
    """plans: list of (plan_id, status, [(action_type, payload, step_status), ...])"""
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = str(tmp_path / "goal_execution.db")
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS execution_plans (
            plan_id TEXT PRIMARY KEY, goal_id TEXT, goal_title TEXT, steps TEXT,
            status TEXT, progress REAL, started_at TEXT, completed_at TEXT,
            outcome_summary TEXT, lessons_learned TEXT)""")
        for plan_id, status, steps in plans:
            steps_json = json.dumps([
                {"action_type": a, "payload": p, "status": s} for a, p, s in steps
            ])
            conn.execute("INSERT INTO execution_plans VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (plan_id, "g1", "goal", steps_json, status, 1.0, None, None, None, None))
        conn.commit()
    return db


RECIPE = [
    ("copy_file_verified", {"source": "varies", "destination": "/tmp/out"}, "completed"),
    ("compress_files", {"files": ["/tmp/out"], "archive": "/tmp/a.zip"}, "completed"),
]


def test_repeated_sequence_becomes_a_candidate_with_templated_payload(tmp_path):
    plans = make_plans_db(tmp_path, [
        (f"plan_{i}", "completed", [ (a, {**p, "source": f"src_{i}"}, s) for a, p, s in RECIPE ])
        for i in range(4)
    ])
    engine = SkillInductionEngine(tmp_path / "induced.db")
    result = engine.scan(plans)
    assert result["success"] is True and result["candidates_created"] == 1
    candidate = engine.list("pending")[0]
    assert candidate.action_sequence == ["copy_file_verified", "compress_files"]
    assert candidate.occurrences == 4 and candidate.context_success_rate == 1.0
    # Varying source became a parameter; constant destination stayed concrete.
    first_step = candidate.payload_template[0]
    assert first_step["source"] == "{{source}}" and first_step["destination"] == "/tmp/out"
    # Evidence names the plans.
    assert len(candidate.evidence_plan_ids) == 4

    # Re-scan is idempotent.
    again = engine.scan(plans)
    assert again["candidates_created"] == 0 and again["candidates_already_pending"] == 1


def test_failed_contexts_veto_the_pattern(tmp_path):
    # 4 completed + 2 failed containing plans → success rate 4/6 = 0.67 < 0.8.
    plans = make_plans_db(tmp_path, [
        *[(f"ok_{i}", "completed", RECIPE) for i in range(4)],
        *[(f"fail_{i}", "failed", RECIPE) for i in range(2)],
    ])
    engine = SkillInductionEngine(tmp_path / "induced.db")
    engine.scan(plans)
    assert engine.list("pending") == []


def test_two_occurrences_do_not_qualify(tmp_path):
    plans = make_plans_db(tmp_path, [
        (f"plan_{i}", "completed", RECIPE) for i in range(2)
    ])
    engine = SkillInductionEngine(tmp_path / "induced.db")
    engine.scan(plans)
    assert engine.list("pending") == []


def test_owner_accept_teaches_and_reject_is_final(tmp_path, monkeypatch):
    plans = make_plans_db(tmp_path, [
        (f"plan_{i}", "completed", RECIPE) for i in range(3)
    ])
    engine = SkillInductionEngine(tmp_path / "induced.db")
    engine.scan(plans)
    candidate = engine.list("pending")[0]

    rejected_first = engine.list("pending")[0]
    # Accept path: patch teach_skill to avoid touching the global DB.
    from app.tools import skill_teaching_engine as ste
    taught = []
    monkeypatch.setattr(ste.SkillTeachingEngine, "teach_skill",
                        classmethod(lambda cls, skill_name, **kw: taught.append(skill_name) or {"success": True}))
    accepted = engine.accept(candidate.candidate_id)
    assert accepted["success"] is True and taught == [candidate.skill_name]
    assert "still passes all gates" in accepted["note"]
    assert engine.get(candidate.candidate_id).status == "accepted"

    # Double decision is refused.
    assert engine.accept(candidate.candidate_id)["success"] is False

    # A second candidate can be rejected permanently.
    engine2 = SkillInductionEngine(tmp_path / "i2.db")
    engine2.scan(make_plans_db(tmp_path / "sub", [
        (f"p_{i}", "completed", RECIPE) for i in range(3)
    ]))
    other = engine2.list("pending")[0]
    assert engine2.reject(other.candidate_id)["success"] is True
    assert engine2.accept(other.candidate_id)["success"] is False
    assert engine2.get(other.candidate_id).status == "rejected"


def test_scan_survives_missing_plan_store(tmp_path):
    engine = SkillInductionEngine(tmp_path / "induced.db")
    result = engine.scan(tmp_path / "does_not_exist.db")
    assert result["success"] is True and result["plans_scanned"] == 0
    assert result["candidates_created"] == 0
