import os
import math
import time
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger

class SecurityCanaryTrap:
    """
    Digital Defense Canary Honeypot & Clipboard Entropy Trap.
    Spawns decoy file canaries on disk, monitors access, and winks high-entropy keys/passwords from system clipboard.
    """

    CANARY_DIR = settings.DATA_DIR / "canaries"

    @classmethod
    def spawn_canary_honeypots(cls) -> Dict[str, Any]:
        """
        Creates decoy security canary files (synthetic API keys, passwords.txt) to trap rogue background processes or malware.
        """
        cls.CANARY_DIR.mkdir(parents=True, exist_ok=True)
        canary_files = [
            ("decoy_passwords.txt", "API_KEY=decoy_canary_key_token_992184128941248\nDB_PASS=DecoyHoneypotSecret123!"),
            ("decoy_aws_credentials.csv", "AccessKeyId,SecretAccessKey\nCANARYKEYID,CANARYSECRETKEY")
        ]

        created = []
        for fname, content in canary_files:
            fpath = cls.CANARY_DIR / fname
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            created.append(str(fpath))

        db.create_audit_log("spawn_canary_honeypots", "success", f"Created {len(created)} security canary honeypots", level=1)

        return {
            "success": True,
            "canary_files_count": len(created),
            "canary_paths": created
        }

    @classmethod
    def calculate_entropy(cls, text: str) -> float:
        """
        Calculates Shannon entropy of text to detect high-entropy keys/passwords.
        """
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in set(text)]
        return -sum([p * math.log(p, 2) for p in prob])

    @classmethod
    def inspect_clipboard_entropy(cls, clear_sensitive: bool = False) -> Dict[str, Any]:
        """Inspect clipboard; clearing is a separate Level-3 exact action."""
        try:
            import pyperclip
            clip_text = pyperclip.paste() if hasattr(pyperclip, 'paste') else ""

            if not clip_text:
                return {"success": True, "clipboard_cleared": False, "note": "Clipboard empty."}

            entropy = cls.calculate_entropy(clip_text)
            is_sensitive = entropy > 4.2 and len(clip_text) > 16

            if is_sensitive:
                if not clear_sensitive:
                    return {
                        "success": True, "clipboard_cleared": False,
                        "sensitive_detected": True, "requires_approval": True,
                        "entropy_score": round(entropy, 2),
                        "note": "Sensitive-looking clipboard content detected; no change made. Clearing requires an exact Level-3 action."
                    }
                if not hasattr(pyperclip, 'copy'):
                    return {"success": False, "error": "Clipboard clear operation unavailable"}
                pyperclip.copy("")
                verified_empty = not (pyperclip.paste() if hasattr(pyperclip, 'paste') else None)
                if not verified_empty:
                    return {"success": False, "error": "Clipboard clear command was not independently observed", "side_effects": True}
                db.create_audit_log("clear_sensitive_clipboard", "success", f"Owner-authorized wipe of high-entropy clipboard string ({len(clip_text)} chars, entropy {entropy:.2f})", level=3)
                return {
                    "success": True, "clipboard_cleared": True,
                    "sensitive_detected": True, "environment_verified": True,
                    "entropy_score": round(entropy, 2), "side_effects": True,
                    "rollback_supported": False,
                    "rollback_reason": "Previous clipboard contents are intentionally not retained and cannot be restored.",
                    "note": "Sensitive-looking clipboard content cleared and empty clipboard observed."
                }

            return {
                "success": True,
                "clipboard_cleared": False,
                "entropy_score": round(entropy, 2),
                "note": "Clipboard content inspected; safe entropy level."
            }
        except Exception as e:
            app_logger.warning(f"Clipboard entropy inspection notice: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def clear_sensitive_clipboard(cls) -> Dict[str, Any]:
        return cls.inspect_clipboard_entropy(clear_sensitive=True)
