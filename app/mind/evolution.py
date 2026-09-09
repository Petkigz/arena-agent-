"""Evolution — Phase 21 (Beanie AGI roadmap): model evolution.

"Base model + memory + world model + self model + learned examples +
personality + optional LoRA. The model itself doesn't need to be
retrained after every interaction:
- Fast learning: memory/world-model updates.
- Medium-term learning: skill/concept consolidation.
- Long-term learning: dataset creation + evaluation + optional adapter
  training.
That prevents catastrophic forgetting and unnecessary retraining."

The three lanes, each honest about what it is:

- FAST (already live, reported — never duplicated): every experience
  already lands in the learning ledger / durable memory / world model /
  self model through the door. ``fast_state()`` reports that wiring from
  the real organs; it writes nothing.

- MEDIUM (consolidation): the WIRED ``ConsolidationCoordinator`` engine
  (conflict replay, gists from repeated verified success, calibration
  refresh — audited runs) is called by this organ when enough new
  learning has accumulated. The engine's telemetry is reported verbatim;
  consolidation APPENDS (gists/calibration), it never deletes raw
  experience — that is the forgetting guard.

- LONG (dataset + evaluation + optional adapter): her OWN verified
  ledger becomes a training dataset (JSONL with provenance), evaluated
  with deterministic sufficiency rules (volume + both outcome classes).
  The adapter layer (``LoraManagerTool`` / ``scripts/train_lora.py``)
  stays where the roadmap puts it — training runs on the owner's GPU
  machine, never here; this organ reports readiness, never claims a
  trained model.

The door consolidates automatically once enough new verified learning
accumulates; dataset export and evaluation are explicit surface acts.

Honesty rules:
- no consolidated claim without the engine's telemetry;
- no dataset row without a verified source event;
- sufficiency is arithmetic, never optimism;
- the adapter lane reports availability, never training.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

# Medium-term: consolidate after this much new learning accumulates.
CONSOLIDATION_THRESHOLD = 25
# Long-term: deterministic dataset-sufficiency floors.
MIN_DATASET_ROWS = 20
MIN_PER_OUTCOME_CLASS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Evolution:
    """The three lanes of model evolution: report the fast lane, delegate
    the medium lane to the wired consolidation engine, and build +
    evaluate the long lane from her own verified ledger."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_evolution (
                    evolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    op TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Evolution ledger unavailable: {exc}")

    # ── FAST lane: where learning already lands (report only) ───────────
    def fast_state(self) -> Dict[str, Any]:
        """The fast lane is ALREADY live at the door — this reports its
        real wiring from the actual organs. Nothing is written."""
        events: List[Dict[str, Any]] = []
        try:
            events = self.mind.learning.events(limit=10000)
        except Exception:
            events = []
        stored = sum(1 for e in events if e.get("stored_memory_id"))
        report: Dict[str, Any] = {
            "lane": "fast",
            "learning_events": len(events),
            "stored_memories": stored,
            "description": "every experience already lands here through "
                           "the door: learning ledger, durable memory, "
                           "world model, self model — no retraining "
                           "needed for fast learning",
        }
        def _memory_counts() -> Any:
            return self.mind.memory.counts()

        def _world() -> Any:
            return self.mind.world.stats()

        def _self_model() -> Any:
            caps = self.mind.self_model.capabilities()
            return {k: caps.get(k) for k in
                    ("capability_count", "wired", "unavailable")
                    if k in caps} or caps

        for key, getter in (("memory_counts", _memory_counts),
                            ("world", _world),
                            ("self_model", _self_model)):
            try:
                report[key] = getter()
            except Exception as exc:
                report[key] = f"unavailable ({exc})"
        return report

    # ── MEDIUM lane: consolidation via the wired engine ─────────────────
    def consolidate(self, max_tasks: int = 50) -> Dict[str, Any]:
        """Delegate to the audited ConsolidationCoordinator: conflict
        replay, gists from repeated VERIFIED success, calibration
        refresh. Appends; never deletes raw experience."""
        runtime = getattr(self.mind, "_runtime", None)
        memory_store = getattr(runtime, "memory", None)
        if memory_store is None:
            return {"success": False, "acted": False,
                    "reason": "no memory store wired — consolidation "
                              "unavailable (nothing was faked)"}
        coordinator = getattr(runtime, "consolidation", None)
        engine = "runtime.consolidation"
        if coordinator is None:
            try:
                from app.cognition.consolidation import ConsolidationCoordinator
                coordinator = ConsolidationCoordinator(
                    str(Path(self.db_path).with_name(
                        "beanie_evolution_consolidation.db")))
                engine = "standalone"
            except Exception as exc:
                return {"success": False, "acted": False,
                        "reason": f"consolidation engine unavailable: {exc}"}
        calibrator = getattr(runtime, "confidence_calibrator", None)
        try:
            telemetry = coordinator.run(memory_store, calibrator=calibrator,
                                        max_tasks=int(max_tasks))
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"consolidation run failed honestly: {exc}"}
        if not isinstance(telemetry, dict):
            return {"success": False, "acted": False,
                    "reason": "consolidation engine returned no typed "
                              "telemetry"}
        summary = {**telemetry, "engine": engine,
                   "max_tasks": int(max_tasks),
                   "events_total": self._events_total()}
        self._record("medium", "consolidate", summary, acted=True)
        return {"success": True, "acted": True,
                "epistemic_kind": "evolution_consolidation",
                "lane": "medium", "summary": summary,
                "statement": (
                    f"consolidation {telemetry.get('status')}: "
                    f"{telemetry.get('conflicts_replayed')} conflict(s) "
                    f"replayed, {telemetry.get('gists_created')} gist(s) "
                    f"from repeated verified success, calibration "
                    f"refreshed={bool(telemetry.get('calibration_refreshed'))}"
                    f" — raw experience untouched (the forgetting guard)")}

    def needs_consolidation(self) -> Dict[str, Any]:
        """Has enough new learning accumulated since the last medium-lane
        run? Deterministic; used by the door."""
        total = self._events_total()
        last = self._last_medium_total()
        return {"events_total": total, "since_last_consolidation":
                total - last if last is not None else total,
                "threshold": CONSOLIDATION_THRESHOLD,
                "needed": (total - (last or 0)) >= CONSOLIDATION_THRESHOLD}

    def consolidations(self, limit: int = 30) -> List[Dict[str, Any]]:
        return [r for r in self._rows(limit=200)
                if r["lane"] == "medium"][:int(limit)]

    # ── LONG lane: dataset from her own verified ledger ─────────────────
    def dataset(self, limit: int = 1000) -> Dict[str, Any]:
        """Export VERIFIED learning material as a training dataset (JSONL,
        provenance per row). No verified event, no row — the dataset is
        her real experience, never padded."""
        rows: List[Dict[str, Any]] = []
        try:
            for e in self.mind.learning.events(limit=int(limit)):
                if e.get("success") is not True and e.get("success") is not False:
                    continue  # unverified material never trains the model
                rows.append({
                    "event_id": e.get("event_id"),
                    "recorded_at": e.get("recorded_at"),
                    "kind": e.get("kind"), "content": e.get("content"),
                    "success": e.get("success"),
                    "verdict": e.get("verdict"),
                    "novelty": e.get("novelty"),
                    "provenance": "beanie_learning_events",
                })
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"dataset export could not read the "
                              f"learning ledger: {exc}"}
        by_success = {"true": sum(1 for r in rows if r["success"]),
                      "false": sum(1 for r in rows if not r["success"])}
        manifest: Dict[str, Any] = {
            "success": True, "lane": "long", "op": "dataset",
            "rows": len(rows), "by_success": by_success,
            "source": "verified learning events only",
        }
        if not rows:
            manifest["path"] = None
            manifest["statement"] = ("no verified material on record — "
                                     "nothing exported (a dataset is never "
                                     "padded)")
            self._record("long", "dataset", manifest, acted=False)
            return {**manifest, "acted": False,
                    "epistemic_kind": "evolution_dataset"}
        try:
            out_dir = Path(settings.DATA_DIR) / "evolution"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = out_dir / f"dataset_{stamp}_{len(rows)}.jsonl"
            blob = "\n".join(json.dumps(r, default=str) for r in rows) + "\n"
            path.write_text(blob, encoding="utf-8")
            manifest["path"] = str(path)
            manifest["sha256"] = hashlib.sha256(
                blob.encode("utf-8")).hexdigest()
        except Exception as exc:
            manifest["path"] = None
            manifest["statement"] = (f"dataset built ({len(rows)} rows) "
                                     f"but could not be written: {exc}")
            self._record("long", "dataset", manifest, acted=False)
            return {**manifest, "acted": False,
                    "epistemic_kind": "evolution_dataset"}
        manifest["statement"] = (f"{len(rows)} verified example(s) "
                                 f"exported with provenance — raw "
                                 f"experience, never padded")
        self._record("long", "dataset", manifest, acted=True)
        return {**manifest, "acted": True,
                "epistemic_kind": "evolution_dataset"}

    def evaluate_dataset(self, rows: Optional[List[Dict[str, Any]]] = None
                         ) -> Dict[str, Any]:
        """Deterministic sufficiency: volume floor + BOTH outcome classes
        present. Arithmetic, never optimism."""
        if rows is None:
            rows = []
            try:
                for e in self.mind.learning.events(limit=10000):
                    if e.get("success") in (True, False):
                        rows.append({"success": e.get("success")})
            except Exception:
                pass
        total = len(rows)
        successes = sum(1 for r in rows if r.get("success") is True)
        failures = total - successes
        gaps: List[str] = []
        if total < MIN_DATASET_ROWS:
            gaps.append(f"needs >= {MIN_DATASET_ROWS} verified examples "
                        f"(has {total})")
        if successes < MIN_PER_OUTCOME_CLASS:
            gaps.append(f"needs >= {MIN_PER_OUTCOME_CLASS} verified "
                        f"successes (has {successes})")
        if failures < MIN_PER_OUTCOME_CLASS:
            gaps.append(f"needs >= {MIN_PER_OUTCOME_CLASS} verified "
                        f"failures (has {failures})")
        sufficient = not gaps
        verdict = {
            "success": True, "acted": False,
            "epistemic_kind": "evolution_evaluation",
            "lane": "long", "op": "evaluate",
            "rows": total, "successes": successes, "failures": failures,
            "thresholds": {"min_rows": MIN_DATASET_ROWS,
                           "min_per_outcome_class": MIN_PER_OUTCOME_CLASS},
            "sufficient": sufficient,
            "gaps": gaps,
            "statement": ("dataset is sufficient to consider long-term "
                          "training" if sufficient else
                          "dataset is NOT sufficient yet: " +
                          "; ".join(gaps)),
        }
        self._record("long", "evaluate", verdict, acted=False)
        return verdict

    def adapter_status(self) -> Dict[str, Any]:
        """The OPTIONAL adapter lane. Training runs on the owner's GPU
        machine per the roadmap — this organ reports readiness, never
        claims a trained model."""
        import importlib.util
        tool_ok = importlib.util.find_spec("app.tools.lora_manager") is not None
        script_ok = (Path(settings.BASE_DIR) / "scripts" /
                     "train_lora.py").exists()
        loras_dir = Path(settings.DATA_DIR) / "loras"
        adapters = []
        try:
            if loras_dir.exists():
                adapters = sorted(p.name for p in loras_dir.iterdir()
                                  if p.is_dir())
        except Exception:
            pass
        return {"lane": "long", "op": "adapter_status", "acted": False,
                "lora_manager_available": tool_ok,
                "training_script_present": script_ok,
                "adapters_on_disk": adapters,
                "policy": "adapter training runs on the owner's GPU "
                          "machine (scripts/train_lora.py), never in the "
                          "sandbox; this organ reports readiness and "
                          "never claims a trained model"}

    # ── the door: consolidate when enough new learning accumulated ──────
    def maybe_consolidate(self) -> Optional[Dict[str, Any]]:
        """Door pass: deterministic threshold check, then consolidate.
        Never fails the task (callers keep it best-effort)."""
        if not self.needs_consolidation()["needed"]:
            return None
        return self.consolidate()

    # ── surfaces ────────────────────────────────────────────────────────
    def runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._rows(limit=int(limit))

    def stats(self) -> Dict[str, Any]:
        rows = self._rows(limit=10000)
        by_lane: Dict[str, int] = {}
        for r in rows:
            by_lane[r["lane"]] = by_lane.get(r["lane"], 0) + 1
        return {"runs": len(rows), "by_lane": by_lane,
                "consolidations": sum(1 for r in rows
                                      if r["lane"] == "medium"),
                "needs_consolidation": self.needs_consolidation()["needed"],
                "policy": "fast lane already live; medium lane appends, "
                          "never deletes (forgetting guard); long lane "
                          "exports verified material only — sufficiency "
                          "is arithmetic, adapter training stays on the "
                          "owner's machine"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "evolution", **self.stats(),
                "fast": self.fast_state(),
                "runs": self.runs(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _events_total(self) -> int:
        try:
            return len(self.mind.learning.events(limit=100000))
        except Exception:
            return 0

    def _last_medium_total(self) -> Optional[int]:
        for r in self._rows(limit=200):
            if r["lane"] != "medium":
                continue
            summary = r.get("summary") or {}
            if isinstance(summary, str):
                try:
                    summary = json.loads(summary)
                except Exception:
                    summary = {}
            total = summary.get("events_total")
            if isinstance(total, int):
                return total
        return None

    def _rows(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_evolution ORDER BY evolution_id "
                    "DESC LIMIT ?", (int(limit),))
                rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        for r in rows:
            try:
                r["summary"] = json.loads(r["summary"])
            except Exception:
                pass
            r["acted"] = bool(r.get("acted"))
        return rows

    def _record(self, lane: str, op: str, summary: Dict[str, Any],
                acted: bool) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "INSERT INTO beanie_evolution (created_at, lane, op,"
                    " summary, acted) VALUES (?,?,?,?,?)",
                    (_now_iso(), lane, op,
                     json.dumps(summary, default=str)[:8000],
                     1 if acted else 0))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Evolution record failed (non-fatal): {exc}")
