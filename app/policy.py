import re
from typing import Dict, Any, Tuple
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger

# ── D8 code-execution contract (owner review P1 #8, 2026-09-01) ─────────
# Level 0 for code execution is GRANTED BY VALIDATION, never by name:
# 'evaluate_pure_code' is Level 0 only when its payload passes the AST
# purity validation, re-derived HERE at the policy layer — the layer
# whose job is to answer "allowed without approval?" must not answer
# "unknown action" for a contract it owns. Anything else that runs code
# is a DECLARED Level 3 (the owner's 1-click approval flow), never the
# unknown-action fallback accident.
ARBITRARY_CODE_ACTIONS = (
    "local_execute",
    "sandbox_run",
    "run_code",
    "execute_code",
    "eval_code",
)


class PolicyEvaluator:
    @staticmethod
    def evaluate_action(action_type: str, details: Dict[str, Any]) -> Tuple[bool, str, int]:
        """
        Evaluates whether an action is allowed, draft-only, or requires explicit approval.
        Returns:
            Tuple[is_allowed: bool, reason: str, level: int]
        """
        # Level definitions
        # Level 0: Read/Observe (Fully Autonomous)
        # Level 1: Draft (Autonomous in Sandboxed Folders)
        # Level 2: Reversible Action (Autonomous with Active Log)
        # Level 3: Sensitive/Irreversible (Requires Approval)
        
        action_type = action_type.lower()
        
        # Read/Observe actions (Level 0)
        # Read-only NATIVE_EXECUTABLES (owner diagnostics F2, 2026-09): these
        # virtual actions have no manifest entry, so the ActionGate falls
        # through to this evaluator — and the unknown->Level-3 default was
        # blocking the GoalReplanner's OWN re-observation probe ('investigate')
        # on every unknown-evidence verdict. Execution handlers verified
        # read-only: investigate/diagnostic (filesystem search + hardware
        # stats read), formulate_answer/answer (compose a reply), observe
        # (no side effects). Unknown actions still fail closed at Level 3.
        if action_type in ["read_file", "search_notes", "capture_screen", "browser_read", "web_search", "master_task", "user_task", "chat",
                           "investigate", "diagnostic", "formulate_answer", "answer", "observe"]:
            db.create_audit_log(action_type, "allowed", f"Autonomous read execution: {details}", level=0)
            return True, "Autonomous execution allowed (Level 0: Read/Observe)", 0

        # Draft-only actions (Level 1)
        if action_type in ["write_draft", "browser_draft"]:
            # Check if write path is in a safe drafts folder or current working workspace
            path = details.get("path", "")
            if path and not ("draft" in path or "workspace" in path or "data/" in path or "memory/" in path or "tests/" in path or "app/" in path):
                audit_logger.warning(f"Draft attempted outside of designated workspace: {path}")
                db.create_audit_log(action_type, "rejected", f"Draft path violation: {path}", level=1)
                return False, "Drafting must be inside approved drafts/workspace directories", 1
                
            db.create_audit_log(action_type, "allowed", f"Autonomous draft execution: {details}", level=1)
            return True, "Autonomous draft execution allowed (Level 1: Draft)", 1

        # Reversible Actions (Level 2)
        if action_type in ["open_application", "organize_files"]:
            db.create_audit_log(action_type, "allowed", f"Autonomous reversible execution: {details}", level=2)
            return True, "Autonomous reversible execution allowed (Level 2: Reversible Action)", 2

        # ── D8 code-execution contract (owner review P1 #8) ─────────────
        # Pure computation: the calculator's risk class. The Level 0
        # grant is re-derived from the payload via the same AST
        # validation the evaluator enforces — impure, empty, or missing
        # code never gets it and routes to the approval flow instead.
        if action_type == "evaluate_pure_code":
            code = details.get("code")
            pure = False
            if isinstance(code, str) and code.strip():
                try:
                    from app.tools.pure_code import is_pure_code
                    pure = bool(is_pure_code(code))
                except Exception as e:
                    app_logger.warning(
                        f"Pure-code validation unavailable at policy gate: {e}")
                    pure = False
            if pure:
                db.create_audit_log(action_type, "allowed",
                                    f"Pure computation (AST-validated): {details}", level=0)
                return True, ("Autonomous execution allowed (Level 0: pure "
                              "computation — AST-validated, no imports, no "
                              "I/O by construction)"), 0
            db.create_audit_log(action_type, "pending_approval",
                                f"Code failed pure-computation validation: {details}", level=3)
            return False, ("Code failed pure-computation validation — "
                           "arbitrary code execution requires explicit user "
                           "approval (Level 3)"), 3

        # Arbitrary code execution: a DECLARED Level 3 (D8 contract) —
        # the reason names code execution, not 'unknown action'.
        if action_type in ARBITRARY_CODE_ACTIONS:
            audit_logger.warning(f"Arbitrary code execution requested: {action_type} - requires approval. Details: {details}")
            db.create_audit_log(action_type, "pending_approval",
                                f"Arbitrary code execution: {details}", level=3)
            return False, ("Arbitrary code execution requires explicit user "
                           "approval (Level 3)"), 3

        # Level 3 Actions (Sensitive/Irreversible)
        if action_type in ["submit_form", "send_email", "delete_file", "shell_command", "trade_action", "publish_post"]:
            audit_logger.warning(f"Level 3 action requested: {action_type} - requires approval. Details: {details}")
            db.create_audit_log(action_type, "pending_approval", f"Sensitive action: {details}", level=3)
            return False, f"Action requires explicit user approval (Level 3: Sensitive/Irreversible Action)", 3

        # Fallback/Unknown actions default to requiring approval
        audit_logger.warning(f"Unknown action requested: {action_type} - defaulting to Level 3 approval requirement.")
        db.create_audit_log(action_type, "pending_approval", f"Unknown action: {details}", level=3)
        return False, "Unknown action: requires explicit user approval by default", 3

    @staticmethod
    def check_network_scope(target_ip_or_domain: str) -> bool:
        """
        Check if the target target_ip_or_domain is within the allowed pentesting lab/scopes.
        """
        # For simplicity in V0, allow local/private ranges and reject anything else
        # E.g., 127.0.0.1, localhost, 192.168.*, 10.*, .local
        private_patterns = [
            r"^localhost$",
            r"^127\.0\.0\.1$",
            r"^192\.168\.\d{1,3}\.\d{1,3}$",
            r"^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
            r".*\.local$"
        ]
        
        for pattern in private_patterns:
            if re.match(pattern, target_ip_or_domain):
                return True
        return False
