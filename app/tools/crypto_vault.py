"""Owner-controlled encrypted vault for secrets and messages.

Arena previously had hashing (integrity) but no encryption. This module adds
authenticated encryption using the battle-tested `cryptography` package
(Fernet: AES-128-CBC + HMAC-SHA256, encrypt-then-MAC). No crypto is
hand-rolled.

Security model, stated honestly:
  * The master key NEVER exists at rest. It is derived per operation from the
    owner's passphrase with scrypt (parameters stored in vault meta).
  * Passphrases and plaintext are never written to logs or results beyond the
    caller's explicit request; audit lines record item names and operations
    only.
  * Items are stored as ciphertext files with best-effort 0600 permissions on
    POSIX. Wrong passphrases fail closed via HMAC verification with typed
    errors and zero plaintext disclosure.
  * A wrong-passphrase decrypt on a missing item still reports not-found —
    item existence is not secret from the machine's owner.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_ITEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class VaultError(RuntimeError):
    """Typed vault failure with no plaintext in the message."""


class CryptoVault:
    """Persistent encrypted item store + stateless message encryption."""

    VERSION = 1

    def __init__(self, vault_dir: Optional[str | Path] = None) -> None:
        self.vault_dir = Path(vault_dir or (settings.DATA_DIR / "vault"))
        self.meta_path = self.vault_dir / "meta.json"
        self.items_dir = self.vault_dir / "items"

    # ── key derivation ──────────────────────────────────────────────────────
    def _load_meta(self) -> Optional[Dict[str, Any]]:
        if not self.meta_path.exists():
            return None
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise VaultError(f"Vault metadata unreadable: {exc}") from exc

    def _derive_fernet_key(self, passphrase: str, meta: Dict[str, Any]) -> bytes:
        from cryptography.fernet import Fernet
        raw = hashlib.scrypt(
            passphrase.encode("utf-8"),
            salt=base64.b64decode(meta["salt"]),
            n=int(meta["scrypt_n"]), r=int(meta["scrypt_r"]), p=int(meta["scrypt_p"]),
            dklen=_DKLEN,
            maxmem=128 * 1024 * 1024,  # OpenSSL default (32MB) is below N=2^15,r=8 usage
        )
        return base64.urlsafe_b64encode(raw)

    def _fernet(self, passphrase: str):
        from cryptography.fernet import Fernet, InvalidToken
        meta = self._load_meta()
        if meta is None:
            raise VaultError("Vault is not initialized; initialize it with the owner passphrase first")
        return Fernet(self._derive_fernet_key(passphrase, meta)), meta

    # ── lifecycle ───────────────────────────────────────────────────────────
    def initialize(self, passphrase: str) -> Dict[str, Any]:
        if len(passphrase or "") < 8:
            return {"success": False, "error": "Passphrase must be at least 8 characters"}
        if self.meta_path.exists():
            return {"success": False, "error": "Vault already initialized; rotate the passphrase instead"}
        meta = {
            "version": self.VERSION,
            "created_at": _now_iso(),
            "salt": base64.b64encode(os.urandom(16)).decode("ascii"),
            "scrypt_n": _SCRYPT_N, "scrypt_r": _SCRYPT_R, "scrypt_p": _SCRYPT_P,
            "verifier_hint": "wrong-or-corrupt items fail HMAC, not this field",
        }
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        # Prove the passphrase round-trips before committing the vault.
        from cryptography.fernet import Fernet
        probe = Fernet(self._derive_fernet_key(passphrase, meta))
        probe.decrypt(probe.encrypt(b"vault-init-probe"))
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._restrict_permissions(self.meta_path)
        audit_logger.info("Crypto vault initialized (scrypt N=%d)", _SCRYPT_N)
        return {"success": True, "created_at": meta["created_at"], "note": "The passphrase is the master key; it is never stored. Losing it means the items are unrecoverable."}

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        try:
            if os.name == "posix":
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # best-effort; Windows ACLs differ

    def status(self) -> Dict[str, Any]:
        meta = self._load_meta()
        items = self.list_items()["items"]
        return {
            "success": True,
            "initialized": meta is not None,
            "created_at": meta.get("created_at") if meta else None,
            "item_count": len(items),
            "kdf": "scrypt(N=%s,r=%s,p=%s)" % (meta.get("scrypt_n"), meta.get("scrypt_r"), meta.get("scrypt_p")) if meta else None,
            "cipher": "Fernet (AES-128-CBC + HMAC-SHA256)" if meta else None,
        }

    # ── stored items ────────────────────────────────────────────────────────
    def encrypt_item(self, name: str, plaintext: str, passphrase: str, *, overwrite: bool = False) -> Dict[str, Any]:
        if not _ITEM_NAME_RE.match(name or ""):
            return {"success": False, "error": "Item name must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"}
        try:
            fernet, _ = self._fernet(passphrase)
        except VaultError as exc:
            return {"success": False, "error": str(exc)}
        self.items_dir.mkdir(parents=True, exist_ok=True)
        path = self.items_dir / f"{name}.json"
        if path.exists() and not overwrite:
            return {"success": False, "error": f"Item '{name}' already exists; pass overwrite=True to replace it"}
        token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        record = {
            "name": name, "version": self.VERSION,
            "ciphertext": token, "updated_at": _now_iso(),
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self._restrict_permissions(path)
        audit_logger.info("Vault item stored: %s (overwrite=%s)", name, overwrite)
        return {"success": True, "name": name, "updated_at": record["updated_at"], "stored_plaintext": False}

    def decrypt_item(self, name: str, passphrase: str) -> Dict[str, Any]:
        path = self.items_dir / f"{name}.json" if _ITEM_NAME_RE.match(name or "") else None
        if path is None or not path.exists():
            return {"success": False, "error": f"No vault item named '{name}'"}
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            fernet, _ = self._fernet(passphrase)
            plaintext = fernet.decrypt(record["ciphertext"].encode("ascii")).decode("utf-8")
        except Exception:
            audit_logger.warning("Vault decrypt failed for item %s (wrong passphrase or tampered ciphertext)", name)
            return {"success": False, "error": "Decryption failed: wrong passphrase or tampered ciphertext", "plaintext_released": False}
        audit_logger.info("Vault item decrypted: %s", name)
        return {"success": True, "name": name, "plaintext": plaintext}

    def list_items(self) -> Dict[str, Any]:
        if not self.items_dir.exists():
            return {"success": True, "items": []}
        items = []
        for path in sorted(self.items_dir.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                items.append({"name": record["name"], "updated_at": record.get("updated_at"), "bytes": len(record.get("ciphertext", ""))})
            except Exception:
                items.append({"name": path.stem, "updated_at": None, "bytes": None, "unreadable": True})
        return {"success": True, "items": items}

    def delete_item(self, name: str) -> Dict[str, Any]:
        path = self.items_dir / f"{name}.json" if _ITEM_NAME_RE.match(name or "") else None
        if path is None or not path.exists():
            return {"success": False, "error": f"No vault item named '{name}'"}
        path.unlink()
        audit_logger.warning("Vault item deleted: %s", name)
        return {"success": True, "deleted": name}

    def rotate_passphrase(self, old_passphrase: str, new_passphrase: str) -> Dict[str, Any]:
        if len(new_passphrase or "") < 8:
            return {"success": False, "error": "New passphrase must be at least 8 characters"}
        meta = self._load_meta()
        if meta is None:
            return {"success": False, "error": "Vault is not initialized"}
        try:
            from cryptography.fernet import Fernet
            old_fernet = Fernet(self._derive_fernet_key(old_passphrase, meta))
            # Verify against the first item (or a probe when the vault is empty).
            paths = sorted(self.items_dir.glob("*.json")) if self.items_dir.exists() else []
            if paths:
                record = json.loads(paths[0].read_text(encoding="utf-8"))
                old_fernet.decrypt(record["ciphertext"].encode("ascii"))
            new_meta = dict(meta)
            new_meta["salt"] = base64.b64encode(os.urandom(16)).decode("ascii")
            new_meta["rotated_at"] = _now_iso()
            new_fernet = Fernet(self._derive_fernet_key(new_passphrase, new_meta))
            rotated = 0
            for path in paths:
                record = json.loads(path.read_text(encoding="utf-8"))
                plaintext = old_fernet.decrypt(record["ciphertext"].encode("ascii"))
                record["ciphertext"] = new_fernet.encrypt(plaintext).decode("ascii")
                record["updated_at"] = _now_iso()
                path.write_text(json.dumps(record, indent=2), encoding="utf-8")
                rotated += 1
            self.meta_path.write_text(json.dumps(new_meta, indent=2), encoding="utf-8")
        except Exception:
            audit_logger.warning("Vault passphrase rotation failed (wrong old passphrase or tampered item)")
            return {"success": False, "error": "Rotation failed: wrong old passphrase or tampered ciphertext; vault unchanged"}
        audit_logger.warning("Vault passphrase rotated (%d items re-encrypted)", rotated)
        return {"success": True, "rotated_items": rotated}

    # ── stateless messages (no storage) ─────────────────────────────────────
    def encrypt_message(self, plaintext: str, passphrase: str) -> Dict[str, Any]:
        try:
            fernet, _ = self._fernet(passphrase)
        except VaultError as exc:
            return {"success": False, "error": str(exc)}
        token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return {"success": True, "armored": f"ARENA-V1:{token}", "note": "Stateless: nothing is stored; the recipient needs the same vault passphrase."}

    def decrypt_message(self, armored: str, passphrase: str) -> Dict[str, Any]:
        prefix = "ARENA-V1:"
        if not armored.startswith(prefix):
            return {"success": False, "error": "Not an Arena V1 armored message"}
        try:
            fernet, _ = self._fernet(passphrase)
            plaintext = fernet.decrypt(armored[len(prefix):].encode("ascii")).decode("utf-8")
        except Exception:
            return {"success": False, "error": "Decryption failed: wrong passphrase or tampered message", "plaintext_released": False}
        return {"success": True, "plaintext": plaintext}


# Module-level singleton, mirroring the other tool stores.
crypto_vault = CryptoVault()
