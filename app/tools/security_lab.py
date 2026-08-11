import socket
from typing import Dict, Any, List, Optional
from app.policy import PolicyEvaluator
from app.database import db
from app.utils.logger import app_logger, audit_logger

class SecurityLabTool:
    # Authorized local target scopes
    AUTHORIZED_SCOPES = ["127.0.0.1", "localhost", "192.168.1.", "172.17.0.", "10.0.0."]

    @classmethod
    def is_scope_authorized(cls, target: str) -> bool:
        target_clean = target.strip().lower()
        return any(scope in target_clean for scope in cls.AUTHORIZED_SCOPES)

    @classmethod
    def scan_lab_target(cls, target: str, ports: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Scans authorized home lab / Docker IPs for open ports and services.
        Enforces scope authorization rules from memory/rules.md.
        """
        target = target.strip()
        if not cls.is_scope_authorized(target):
            audit_logger.warning(f"UNAUTHORIZED SECURITY SCAN ATTEMPTED on '{target}'")
            return {
                "success": False,
                "error": f"Security Scope Violation: '{target}' is not in your authorized lab scope (127.0.0.1, 192.168.1.x, Docker 172.17.0.x). See memory/rules.md.",
                "target": target,
                "open_ports": []
            }

        # Policy Evaluation
        allowed, reason, level = PolicyEvaluator.evaluate_action("network_scan", {"target": target})
        if not allowed:
            return {"success": False, "error": f"Policy Blocked: {reason}", "authority_level": level}

        if not ports:
            ports = [21, 22, 80, 443, 1234, 3000, 3306, 5432, 8000, 8080]

        open_ports = []
        app_logger.info(f"Scanning lab target '{target}' across ports {ports}...")

        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.8)
                res = s.connect_ex((target, port))
                if res == 0:
                    open_ports.append(port)
                s.close()
            except Exception:
                pass

        audit_logger.info(f"Completed lab scan for '{target}'. Found open ports: {open_ports}")

        return {
            "success": True,
            "target": target,
            "scanned_ports": ports,
            "open_ports": open_ports,
            "security_note": "Laboratory assessment completed within authorized scope."
        }
