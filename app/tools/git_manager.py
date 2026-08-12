import subprocess
from pathlib import Path
from typing import Dict, Any, List
from app.config import settings
from app.utils.logger import app_logger, audit_logger

class GitManagerTool:
    @classmethod
    def run_git_cmd(cls, args: List[str]) -> Dict[str, Any]:
        """
        Executes git commands safely inside the workspace directory.
        """
        try:
            cmd = ["git"] + args
            res = subprocess.run(
                cmd,
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=15
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except Exception as e:
            app_logger.error(f"Error running git command {args}: {e}")
            return {"success": False, "stdout": "", "stderr": str(e)}

    @classmethod
    def create_checkpoint(cls, message: str) -> Dict[str, Any]:
        """
        Creates a Git working-tree checkpoint so any file edit can be safely rolled back.
        """
        message_clean = message.strip() or "Workspace checkpoint"
        
        # Stage workspace files
        cls.run_git_cmd(["add", "data/workspace/", "app/", "memory/"])
        res = cls.run_git_cmd(["commit", "-m", f"checkpoint: {message_clean}"])

        audit_logger.info(f"Created Git workspace checkpoint: '{message_clean}'")
        return {
            "success": res["success"],
            "message": message_clean,
            "git_output": res["stdout"] or res["stderr"]
        }

    @classmethod
    def list_checkpoints(cls, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Lists recent Git working-tree checkpoints.
        """
        res = cls.run_git_cmd(["log", "--oneline", f"-n{limit}"])
        checkpoints = []
        if res["success"] and res["stdout"]:
            for line in res["stdout"].split("\n"):
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    checkpoints.append({"hash": parts[0], "message": parts[1]})
        return checkpoints

    @classmethod
    def rollback_checkpoint(cls, checkpoint_hash: str) -> Dict[str, Any]:
        """
        Rolls back the workspace files to a previous Git checkpoint.
        """
        res = cls.run_git_cmd(["checkout", checkpoint_hash, "--", "data/workspace/"])
        audit_logger.info(f"Rolled back workspace to Git checkpoint '{checkpoint_hash}'")
        return {
            "success": res["success"],
            "checkpoint_hash": checkpoint_hash,
            "message": f"Rolled back workspace files to checkpoint {checkpoint_hash}." if res["success"] else f"Rollback failed: {res['stderr']}"
        }
