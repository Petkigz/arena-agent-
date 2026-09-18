"""The gated self-improvement loop (owner go-ahead 2026-09-13).

Owner's requirement, verbatim intent: the machine must DIFFERENTIATE
between choosing what to improve and improving its own code — and any
change it proves still waits for her. The architecture:

  * THE CHOOSER (meta-level): `rank_improvement_targets` ranks
    weaknesses from EVIDENCE ONLY — benchmark scoreboard failures and
    regressions, verified_failure clusters in the Phase 1 event ledger,
    and the Phase 20 organ's detected capability gaps. It proposes
    targets, never fixes.
  * THE EXPERIMENT SPINE: every improvement trial is one event on the
    Phase 1 ledger (source 'self_improvement'): hypothesis, variant,
    baseline-vs-variant scores, verdict — append-only receipts. A
    variant that fails to beat baseline (or regresses anything) is
    REJECTED BY MEASUREMENT immediately; only measured improvements
    reach the owner, as observation_pending.
  * THE OWNER GATE: approve/reject are the ONLY paths from
    observation_pending to verified_success — the machine proposes with
    evidence, the owner disposes. Nothing auto-applies. (Owner decision
    2026-09-13: the gate applies to EVERY accepted change.)
  * THE EVALUATOR IS SACRED: this organ only READS the benchmark
    scoreboard. The improver can never edit its own exam (Goodhart).
  * TRAINING READINESS: an honest report of how much verified evidence
    exists before model training is worth anything, with the recorded
    hardware constraint stated, never hidden.

Fail-open everywhere; kill switch ARENA_SELF_IMPROVEMENT=0.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger, audit_logger

MIN_VERIFIED_FOR_TRAINING = 25


def _enabled() -> bool:
    return os.environ.get("ARENA_SELF_IMPROVEMENT", "1") != "0"


# ── THE CHOOSER: evidence-only weakness ranking ────────────────────────────

def rank_improvement_targets(
    history_store: Any = None,
    limit: int = 10,
    include_capability_gaps: bool = False,
) -> List[Dict[str, Any]]:
    """Rank WHAT to improve from evidence alone. Never proposes fixes."""
    if not _enabled():
        return []
    targets: List[Dict[str, Any]] = []
    try:
        # Evidence 1: the benchmark scoreboard (read-only — sacred).
        try:
            if history_store is None:
                from app.cognition.intelligence_benchmark import (
                    BenchmarkHistoryStore,
                )
                history_store = BenchmarkHistoryStore()
            latest = history_store.latest()
            if latest is not None:
                if latest.regressions:
                    targets.append({
                        "target": "benchmark regressions",
                        "kind": "regression",
                        "weight": 100,
                        "evidence": [
                            f"regressed since previous run: {n}"
                            for n in latest.regressions],
                    })
                failed = [c.name for c in latest.checks if not c.passed]
                if failed:
                    targets.append({
                        "target": "failing benchmark checks",
                        "kind": "benchmark_failure",
                        "weight": 60 + min(len(failed), 20),
                        "evidence": [f"failing: {n}" for n in failed[:10]],
                    })
                categories: Dict[str, List[bool]] = {}
                for c in latest.checks:
                    categories.setdefault(c.category, []).append(c.passed)
                for cat, passes in sorted(categories.items()):
                    if not all(passes):
                        targets.append({
                            "target": f"weakest benchmark family: {cat}",
                            "kind": "weak_family",
                            "weight": 30,
                            "evidence": [
                                f"{sum(passes)}/{len(passes)} passing in '{cat}'"],
                        })
        except Exception as exc:
            app_logger.debug(f"Chooser: scoreboard evidence skipped: {exc}")

        # Evidence 2: verified_failure clusters in the Phase 1 ledger.
        for cluster in failure_clusters(limit=3):
            targets.append({
                "target": f"recurring verified failures: {cluster['reason']}",
                "kind": "ledger_failure_cluster",
                "weight": 30 + min(cluster["count"], 20),
                "evidence": [
                    f"{cluster['count']} verified_failure event(s) sharing "
                    f"reason '{cluster['reason']}'"],
            })

        # Evidence 3: the Phase 20 organ's detected capability gaps.
        if include_capability_gaps:
            try:
                from app.mind import BeanieMind
                gaps = BeanieMind.get_instance().improvement.detect_gaps()
                for gap in gaps[:3]:
                    targets.append({
                        "target": f"capability gap: {gap.get('capability', '?')}",
                        "kind": "capability_gap",
                        "weight": 20 + min(int(gap.get("count", 0)), 10),
                        "evidence": [str(gap.get("evidence", gap))[:160]],
                    })
            except Exception as exc:
                app_logger.debug(f"Chooser: capability gaps skipped: {exc}")

        targets.sort(key=lambda t: -t["weight"])
        return targets[:max(1, int(limit))]
    except Exception as exc:
        app_logger.debug(f"Chooser skipped: {exc}")
        return []


# ── failure clusters from the Phase 1 ledger ───────────────────────────────

def failure_clusters(limit: int = 3) -> List[Dict[str, Any]]:
    """Top reasons behind verified_failure events (evidence for the
    Chooser). Read-only."""
    if not _enabled():
        return []
    try:
        from app.database import db
        with db._get_connection() as conn:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='cognitive_events'").fetchone()
            if not exists:
                return []
            rows = conn.execute(
                "SELECT COALESCE(NULLIF(reason, ''), 'unspecified') AS r, "
                "       COUNT(*) AS n FROM cognitive_events "
                "WHERE state = 'verified_failure' "
                "GROUP BY r ORDER BY n DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [{"reason": str(r[0]), "count": int(r[1])} for r in rows]
    except Exception as exc:
        app_logger.debug(f"Failure-cluster read skipped: {exc}")
        return []


# ── THE EXPERIMENT SPINE (Phase 1 ledger, source 'self_improvement') ───────

_EXPERIMENT_CONVERSATION = "self-improvement"


def record_experiment(
    hypothesis: str,
    variant_summary: str,
    baseline_score: float,
    variant_score: float,
    regressions: Optional[List[str]] = None,
) -> Optional[str]:
    """Record one improvement trial. Measurement is the first gate: a
    variant that fails to beat baseline — or regresses anything — is
    rejected immediately and never spends owner attention. A measured
    improvement becomes observation_pending: the OWNER decides."""
    if not _enabled():
        return None
    try:
        from app.cognition import event_ledger as ledger
        hypothesis = str(hypothesis or "").strip()
        if not hypothesis:
            return None
        event_id = ledger.open_event(
            _EXPERIMENT_CONVERSATION, f"[experiment] {hypothesis}",
            source="self_improvement")
        if not event_id:
            return None
        ledger.attach_receipt(
            event_id, "experiment",
            f"hypothesis: {hypothesis[:120]} | variant: "
            f"{str(variant_summary)[:120]}", verified=None)
        regressions = [str(r) for r in (regressions or [])]
        improved = float(variant_score) > float(baseline_score)
        measurement = {
            "kind": "measurement",
            "detail": (f"baseline={float(baseline_score):.4f} "
                       f"variant={float(variant_score):.4f} "
                       f"regressions={len(regressions)}"),
            "verified": bool(improved and not regressions),
        }
        if regressions or not improved:
            ledger.transition_event(
                event_id, ledger.STATE_VERIFIED_FAILURE,
                reason=("regressed: " + ", ".join(regressions[:3])
                        if regressions else "no measured improvement"),
                receipt=measurement)
        else:
            ledger.transition_event(
                event_id, ledger.STATE_DISPATCHED,
                reason="measured improvement — owner approval required",
                receipt=measurement)
            ledger.transition_event(
                event_id, ledger.STATE_OBSERVATION_PENDING,
                reason="awaiting owner approval")
        return event_id
    except Exception as exc:
        app_logger.debug(f"Experiment record skipped: {exc}")
        return None


def _experiments(limit: int = 20, state: Optional[str] = None):
    from app.database import db
    with db._get_connection() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='cognitive_events'").fetchone()
        if not exists:
            return []
        query = ("SELECT event_id, request_text, state, reason, "
                 "receipt_json, created_at FROM cognitive_events "
                 "WHERE source = 'self_improvement' ")
        args: List[Any] = []
        if state:
            query += "AND state = ? "
            args.append(state)
        query += "ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        rows = conn.execute(query, args).fetchall()
    out = []
    for r in rows:
        try:
            receipts = json.loads(r[4] or "[]")
        except Exception:
            receipts = []
        out.append({
            "event_id": r[0], "hypothesis": r[1], "state": r[2],
            "reason": r[3], "receipts": receipts, "created_at": r[5],
        })
    return out


def pending_experiments(limit: int = 20) -> List[Dict[str, Any]]:
    """Measured improvements awaiting the owner's decision."""
    if not _enabled():
        return []
    try:
        from app.cognition import event_ledger as ledger
        return _experiments(limit=limit,
                            state=ledger.STATE_OBSERVATION_PENDING)
    except Exception as exc:
        app_logger.debug(f"Pending experiments read skipped: {exc}")
        return []


def recent_experiments(limit: int = 20) -> List[Dict[str, Any]]:
    if not _enabled():
        return []
    try:
        return _experiments(limit=limit)
    except Exception as exc:
        app_logger.debug(f"Experiment history read skipped: {exc}")
        return []


def approve_experiment(event_id: str) -> bool:
    """THE OWNER GATE: the only path from measured-improvement to
    verified_success. Recorded in the audit log — this is authority."""
    if not _enabled():
        return False
    try:
        from app.cognition import event_ledger as ledger
        ok = ledger.transition_event(
            str(event_id), ledger.STATE_VERIFIED_SUCCESS,
            reason="approved by the owner",
            receipt={"kind": "owner_decision", "detail": "approved",
                     "verified": True})
        if ok:
            audit_logger.info(
                f"Self-improvement experiment {event_id} APPROVED by owner")
        return ok
    except Exception as exc:
        app_logger.debug(f"Experiment approval skipped: {exc}")
        return False


def reject_experiment(event_id: str, reason: str = "") -> bool:
    if not _enabled():
        return False
    try:
        from app.cognition import event_ledger as ledger
        ok = ledger.transition_event(
            str(event_id), ledger.STATE_VERIFIED_FAILURE,
            reason=f"rejected by the owner: {str(reason)[:120]}"
            or "rejected by the owner",
            receipt={"kind": "owner_decision", "detail": "rejected",
                     "verified": False})
        if ok:
            audit_logger.info(
                f"Self-improvement experiment {event_id} REJECTED by owner")
        return ok
    except Exception as exc:
        app_logger.debug(f"Experiment rejection skipped: {exc}")
        return False


# ── TRAINING READINESS: honest evidence accounting ─────────────────────────

def training_readiness() -> Dict[str, Any]:
    """How much verified evidence exists before model training is worth
    anything — and the recorded hardware constraint, stated not hidden.
    This organ never trains anything."""
    if not _enabled():
        return {"available": False, "reason": "disabled"}
    try:
        from app.database import db
        verified = failures = experiments = 0
        with db._get_connection() as conn:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='cognitive_events'").fetchone()
            if exists:
                verified = conn.execute(
                    "SELECT COUNT(*) FROM cognitive_events "
                    "WHERE state = 'verified_success'").fetchone()[0]
                failures = conn.execute(
                    "SELECT COUNT(*) FROM cognitive_events "
                    "WHERE state = 'verified_failure'").fetchone()[0]
                experiments = conn.execute(
                    "SELECT COUNT(*) FROM cognitive_events "
                    "WHERE source = 'self_improvement'").fetchone()[0]
        evidence_count = int(verified) + int(failures)
        ready = evidence_count >= MIN_VERIFIED_FOR_TRAINING
        report: Dict[str, Any] = {
            "available": True,
            "verified_success": int(verified),
            "verified_failure": int(failures),
            "experiments_recorded": int(experiments),
            "evidence_count": evidence_count,
            "minimum_for_training": MIN_VERIFIED_FOR_TRAINING,
            "data_ready": ready,
            "verdict": (
                "enough verified evidence to justify a first adapter "
                "attempt" if ready else
                f"insufficient data — {MIN_VERIFIED_FOR_TRAINING - evidence_count} "
                "more verified outcomes needed before training means anything"),
        }
        try:
            from app.settings_store import get_hardware
            hw = get_hardware()
            vram = hw.get("vram_gb")
            if vram is not None and int(vram) < 16:
                report["hardware_note"] = (
                    f"recorded GPU has {vram}GB VRAM — serious adapter "
                    "training waits for the planned upgrade; small/slow "
                    "experiments only until then")
        except Exception:
            pass
        return report
    except Exception as exc:
        app_logger.debug(f"Training readiness skipped: {exc}")
        return {"available": False, "reason": str(exc)[:120]}
