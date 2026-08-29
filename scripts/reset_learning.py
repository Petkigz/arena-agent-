#!/usr/bin/env python3
"""
reset_learning.py — clear Arena's learned experience (the polluted learning).

WHY THIS EXISTS
---------------
Before the launch-honesty fixes (commits 81cdfe4 and 6b11799), failed
launches were recorded as VERIFIED SUCCESSES. Every false success poisoned
the learning systems downstream:

  * memories / structured_lessons / self_reflections   ("Lesson saved",
    "successfully executed without any issues" — Memory #1338/#1340)
  * planning_patterns / execution_patterns             ("Pattern
    ['open_application'] succeeded 4x (100% rate)")
  * strategy_outcomes / task_signatures                (analogical memory:
    "Previously succeeded using 'open_application' x3")
  * self_model                                          ("Capability
    'open_application' is expert (success_rate=1.00)")
  * causal_graphs                                       ("open_application ->
    Launched application 'Now In Contrrol Panel Open User Accoun'")
  * cognitive_traces / calibration_records / bayesian_updates (false
    verified_success, miscalibrated confidence)
  * training_examples.db                                (LoRA training
    candidates proposed FROM the false outcomes)
  * memory_vectors.npz                                  (vector embeddings of
    the polluted memories — 81 vectors)

Those records keep nudging future planning toward open_application with
inflated confidence even after the code is fixed. This script removes them.

WHAT IS KEPT (default mode)
---------------------------
  * conversations, agent_messages, tasks        — your chat & task history
  * audit_logs                                  — forensic record of what ran
  * installed_apps                              — the app inventory cache
  * owner-control / autonomy / settings DBs     — your authority records
  * inference_profile.json, settings, projects, notes, workspace

Use --full for a complete fresh brain (also wipes chat/task history and
audit logs — everything in assistant.db).

USAGE
-----
    # 1. Stop the server first (Ctrl+C in the uvicorn terminal).

    # 2. Preview what would be cleared (default is a safe dry run):
    python scripts/reset_learning.py

    # 3. Apply:
    python scripts/reset_learning.py --apply

    # Optional: wipe EVERYTHING learned + history:
    python scripts/reset_learning.py --apply --full

    # Data dir not at <repo>/data? Point at it:
    python scripts/reset_learning.py --apply --data-dir F:\\ai\\arena\\arena-agent-\\data

A timestamped backup of everything removed is written to <data>/backups/
before anything is deleted. Restore = copy the files back and restart.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

# ── what gets cleared ────────────────────────────────────────────────────────

# Tables inside assistant.db that learn from execution outcomes. Ordered so
# dependents are cleared before their parents (best effort; FKs are typically
# off in this codebase, but this stays correct either way).
LEARNING_TABLES = [
    "memory_consolidation_links",
    "memories",
    "cognitive_memory",
    "structured_lessons",
    "self_reflections",
    "planning_patterns",
    "execution_patterns",
    "strategy_outcomes",
    "task_signatures",
    "causal_graphs",
    "causal_queries",
    "bayesian_updates",
    "calibration_records",
    "self_model",
    "observed_behaviors",
    "persistent_beliefs",
    "cognitive_traces",
    "cognitive_processes",
    "cognitive_optimizations",
    "contextual_meanings",
    "knowledge_graph",
    "knowledge_claims",
    "synthesized_knowledge",
    "social_interactions",
    "emotional_states",
    "subjective_experiences",
    "conscious_states",
    "mental_states",
    "world_entities",
    "world_observations",
    "world_relationships",
]

# Standalone files that persist learned state. Deleted (after backup) — the
# owning stores recreate them on next startup.
LEARNING_FILES = [
    "memory_vectors.npz",
    "memory_vectors.meta.json",
    "training_examples.db",
    "action_outcomes.db",
    "continual_learning.db",
]

# Tables that are deliberately KEPT in default mode.
KEPT_TABLES = [
    "conversations",
    "agent_messages",
    "agents",
    "tasks",
    "audit_logs",
    "installed_apps",
    "taught_skills",
]


def _server_is_running(host: str = "127.0.0.1", port: int = 8000, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _backup(src: Path, backup_dir: Path) -> Path | None:
    if not src.exists():
        return None
    dst = backup_dir / src.name
    shutil.copy2(src, dst)
    return dst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clear Arena's learned experience (dry-run by default)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually delete (default is a dry run).")
    parser.add_argument("--full", action="store_true",
                        help="Also wipe chat/task history and audit logs "
                             "(everything in assistant.db). Learning-only by default.")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Path to the data directory (default: <repo>/data).")
    parser.add_argument("--force", action="store_true",
                        help="Run even if the server appears to be running "
                             "(NOT recommended — the server can rewrite rows as it shuts down).")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    data_dir = (args.data_dir or repo_root / "data").resolve()
    db_path = data_dir / "assistant.db"

    print("=" * 72)
    print("Arena learning reset")
    print("=" * 72)
    print(f"data dir : {data_dir}")
    print(f"database : {db_path}")
    print(f"mode     : {'FULL WIPE' if args.full else 'learning-only'}"
          f"{' [APPLY]' if args.apply else ' [DRY RUN — nothing will be deleted]'}")
    print()

    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}")
        return 2

    if not args.force and _server_is_running():
        print("ERROR: the Arena server appears to be running on port 8000.")
        print("       Stop it first (Ctrl+C in the uvicorn terminal), then re-run.")
        print("       If you are sure it is stopped, re-run with --force.")
        return 2

    if not args.apply:
        print("Dry run — counts of learned records that WOULD be cleared:")
    else:
        print("Clearing learned records...")

    backup_dir = data_dir / "backups" / time.strftime("%Y%m%d-%H%M%S")
    made_backup = False

    if args.apply:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if _backup(db_path, backup_dir):
            made_backup = True
            print(f"  backup : {backup_dir / db_path.name}")
        # Sidecar WAL/SHM files, if any.
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                _backup(sidecar, backup_dir)

    # ── assistant.db ────────────────────────────────────────────────────────
    cleared_rows = 0
    cleared_tables = 0
    if args.full:
        if args.apply:
            db_path.unlink()
            # Remove sidecars too so a stale WAL can't resurrect old rows.
            for suffix in ("-wal", "-shm"):
                sidecar = db_path.with_name(db_path.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            print(f"  deleted database (full wipe): {db_path.name}")
        else:
            print("  [full] the ENTIRE assistant.db would be deleted")
    else:
        conn = sqlite3.connect(db_path)
        try:
            for table in LEARNING_TABLES:
                if not _table_exists(conn, table):
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count == 0:
                    continue
                if args.apply:
                    conn.execute(f"DELETE FROM {table}")
                print(f"  {'cleared' if args.apply else 'would clear'} {table:<32} {count:>6} rows")
                cleared_rows += count
                cleared_tables += 1
            if args.apply:
                conn.commit()
                conn.execute("VACUUM")
                conn.commit()
        finally:
            conn.close()
        print(f"  {'cleared' if args.apply else 'would clear'} {cleared_tables} learning tables, "
              f"{cleared_rows} rows total")

    # ── standalone learning files ───────────────────────────────────────────
    removed_files = []
    for name in LEARNING_FILES:
        f = data_dir / name
        if not f.exists():
            continue
        if args.apply:
            _backup(f, backup_dir)
            made_backup = made_backup or True
            f.unlink()
            print(f"  deleted {name}")
        else:
            print(f"  would delete {name}")
        removed_files.append(name)

    print()
    print("KEPT (default mode): " + ", ".join(KEPT_TABLES) +
          " + owner-control/autonomy/settings DBs")
    if args.full:
        print("KEPT: owner-control/autonomy/settings DBs and files outside assistant.db")
    if made_backup:
        print(f"Backups written to: {backup_dir}")
    if not args.apply:
        print()
        print("This was a DRY RUN. To actually clear the learning, run:")
        print(f"    python {Path(__file__).name} --apply")
    else:
        print()
        print("Done. Restart the server — it will rebuild the memory vector index")
        print("and re-learn from clean ground truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
