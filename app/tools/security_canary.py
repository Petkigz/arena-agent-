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
    def inspect_clipboard_entropy(cls) -> Dict[str, Any]:
        """
        Inspects system clipboard for exposed API keys, secret hashes, or passwords and clears them if high entropy.
        """
        try:
            import pyperclip
            clip_text = pyperclip.paste() if hasattr(pyperclip, 'paste') else ""

            if not clip_text:
                return {"success": True, "clipboard_cleared": False, "note": "Clipboard empty."}

            entropy = cls.calculate_entropy(clip_text)
            is_sensitive = entropy > 4.2 and len(clip_text) > 16

            if is_sensitive:
                if hasattr(pyperclip, 'copy'):
                    pyperclip.copy("")
                db.create_audit_log("inspect_clipboard_entropy", "success", f"Wiped high-entropy clipboard string ({len(clip_text)} chars, entropy {entropy:.2f})", level=1)
                return {
                    "success": True,
                    "clipboard_cleared": True,
                    "entropy_score": round(entropy, 2),
                    "note": "High-entropy API key or password detected on clipboard and safely wiped."
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
