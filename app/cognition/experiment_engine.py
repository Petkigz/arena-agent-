"""Phase C: Experimentation & Self-Play Sandbox Exploration Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.tools.disposable_sandbox import DisposableSandbox
from app.database import db
from app.utils.logger import app_logger

@dataclass
class ExperimentResult:
    experiment_id: str
    hypothesis_name: str
    command_executed: str
    exit_code: int
    success: bool
    output_summary: str
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExperimentEngine:
    """Executes speculative code and self-play exploration inside DisposableSandbox to test tool boundaries safely."""

    @classmethod
    def test_hypothesis_in_sandbox(
        cls,
        hypothesis_name: str,
        command_or_script: str,
        target_guest_os: str = "auto"
    ) -> ExperimentResult:
        app_logger.info(f"ExperimentEngine testing hypothesis '{hypothesis_name}': {command_or_script[:60]}")

        sb = DisposableSandbox.create_sandbox(f"sb_exp_{hypothesis_name[:8]}")
        sandbox_id = sb["sandbox_id"]

        run_res = DisposableSandbox.run_in_sandbox(
            sandbox_id,
            command_or_script,
            target_guest_os=target_guest_os
        )

        DisposableSandbox.destroy_sandbox(sandbox_id)

        return ExperimentResult(
            experiment_id=sandbox_id,
            hypothesis_name=hypothesis_name,
            command_executed=command_or_script,
            exit_code=run_res.get("exit_code", 1),
            success=run_res.get("success", False),
            output_summary=run_res.get("stdout", "") or run_res.get("stderr", "") or run_res.get("error", "")
        )

    @classmethod
    def run_self_play_sandbox_exploration(cls) -> Dict[str, Any]:
        """
        Generates mock edge-case inputs and runs speculative tool boundary exploration inside DisposableSandbox.
        """
        app_logger.info("[EXPERIMENT ENGINE] Launching self-play sandbox exploration loop...")

        mock_experiments = [
            ("Edge Case File Search", "python -c \"import os; print(os.listdir('.'))\""),
            ("Edge Case Data Parsing", "python -c \"import json; print(json.dumps({'test': 123}))\"")
        ]

        results = []
        for name, cmd in mock_experiments:
            res = cls.test_hypothesis_in_sandbox(name, cmd)
            results.append({
                "hypothesis_name": name,
                "success": res.success,
                "output": res.output_summary[:100]
            })

        db.create_audit_log("run_self_play_sandbox_exploration", "success", f"Explored {len(results)} self-play experiments", level=1)

        return {
            "success": True,
            "total_experiments_run": len(results),
            "results": results
        }
