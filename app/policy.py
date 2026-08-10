import re
from typing import Dict, Any, Tuple
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger

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
        if action_type in ["read_file", "search_notes", "capture_screen", "browser_read", "web_search"]:
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
