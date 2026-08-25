"""Encrypted vault: authenticated encryption for owner secrets and messages.

Fernet (AES-128-CBC + HMAC-SHA256); master key derived per operation via
scrypt from the owner's passphrase and never stored. Wrong passphrases fail
closed with typed errors; plaintext never appears in listings, stored files,
or logs.
"""
import json

import pytest

from app.tools.crypto_vault import CryptoVault


@pytest.fixture
def vault(tmp_path):
    v = CryptoVault(tmp_path / "vault")
    assert v.initialize("correct horse battery")["success"] is True
    return v


def test_initialize_is_one_time_and_requires_a_real_passphrase(tmp_path):
    v = CryptoVault(tmp_path / "vault")
    assert v.initialize("short")["success"] is False
    assert v.initialize("correct horse battery")["success"] is True
    assert v.initialize("another passphrase")["success"] is False  # already initialized


def test_item_roundtrip_and_wrong_passphrase_fails_closed(vault):
    vault.encrypt_item("email-password", "hunter2-but-long", "correct horse battery")
    good = vault.decrypt_item("email-password", "correct horse battery")
    assert good["success"] is True and good["plaintext"] == "hunter2-but-long"
    bad = vault.decrypt_item("email-password", "wrong passphrase")
    assert bad["success"] is False and "plaintext" not in bad
    assert bad["plaintext_released"] is False


def test_stored_files_and_listings_never_contain_plaintext(vault):
    vault.encrypt_item("api-key", "SUPER-SECRET-VALUE-9182", "correct horse battery")
    listing = vault.list_items()
    assert listing["items"][0]["name"] == "api-key"
    assert "plaintext" not in listing["items"][0]
    for path in vault.items_dir.glob("*.json"):
        blob = path.read_text(encoding="utf-8")
        assert "SUPER-SECRET-VALUE-9182" not in blob
        record = json.loads(blob)
        assert set(record) >= {"name", "ciphertext", "updated_at"}


def test_overwrite_requires_explicit_flag(vault):
    vault.encrypt_item("note", "first", "correct horse battery")
    assert vault.encrypt_item("note", "second", "correct horse battery")["success"] is False
    assert vault.encrypt_item("note", "second", "correct horse battery", overwrite=True)["success"] is True
    assert vault.decrypt_item("note", "correct horse battery")["plaintext"] == "second"


def test_invalid_names_are_refused_and_missing_items_report_not_found(vault):
    assert vault.encrypt_item("../escape", "x", "correct horse battery")["success"] is False
    assert vault.encrypt_item("ok-name_v2.0", "x", "correct horse battery")["success"] is True
    assert vault.decrypt_item("does-not-exist", "correct horse battery")["error"].startswith("No vault item")


def test_tampered_ciphertext_fails_hmac(vault):
    vault.encrypt_item("bank", "account-number-776", "correct horse battery")
    path = vault.items_dir / "bank.json"
    record = json.loads(path.read_text())
    token = bytearray(record["ciphertext"].encode())
    token[10] = token[10] ^ 0x01  # flip one bit
    record["ciphertext"] = token.decode()
    path.write_text(json.dumps(record))
    result = vault.decrypt_item("bank", "correct horse battery")
    assert result["success"] is False and "tampered" in result["error"]


def test_delete_is_permanent(vault):
    vault.encrypt_item("tmp", "value", "correct horse battery")
    assert vault.delete_item("tmp")["success"] is True
    assert vault.decrypt_item("tmp", "correct horse battery")["success"] is False
    assert vault.delete_item("tmp")["success"] is False


def test_passphrase_rotation_rekeys_every_item(vault):
    vault.encrypt_item("a", "1", "correct horse battery")
    vault.encrypt_item("b", "2", "correct horse battery")
    rotated = vault.rotate_passphrase("correct horse battery", "staple battery horse")
    assert rotated["success"] is True and rotated["rotated_items"] == 2
    assert vault.decrypt_item("a", "correct horse battery")["success"] is False  # old key dead
    assert vault.decrypt_item("a", "staple battery horse")["plaintext"] == "1"
    assert vault.decrypt_item("b", "staple battery horse")["plaintext"] == "2"
    # A wrong old passphrase leaves the vault untouched.
    failed = vault.rotate_passphrase("not the passphrase", "x" * 12)
    assert failed["success"] is False and "unchanged" in failed["error"]
    assert vault.decrypt_item("a", "staple battery horse")["plaintext"] == "1"


def test_message_roundtrip_is_stateless_and_tamper_evident(vault):
    encrypted = vault.encrypt_message("meet at 7", "correct horse battery")
    assert encrypted["success"] is True and encrypted["armored"].startswith("ARENA-V1:")
    decrypted = vault.decrypt_message(encrypted["armored"], "correct horse battery")
    assert decrypted["plaintext"] == "meet at 7"
    assert vault.list_items()["items"] == []  # nothing stored
    wrong = vault.decrypt_message(encrypted["armored"], "wrong passphrase")
    assert wrong["success"] is False and "plaintext" not in wrong
    tampered = vault.decrypt_message(encrypted["armored"][:-4] + "AAAA", "correct horse battery")
    assert tampered["success"] is False
    assert vault.decrypt_message("not-armored", "correct horse battery")["success"] is False


def test_uninitialized_vault_refuses_operations(tmp_path):
    v = CryptoVault(tmp_path / "fresh")
    assert v.encrypt_item("x", "y", "12345678")["success"] is False
    assert "not initialized" in v.encrypt_item("x", "y", "12345678")["error"]
    assert v.status()["initialized"] is False


def test_vault_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.tools import crypto_vault as vault_module
    from pathlib import Path

    test_vault = CryptoVault(tmp_path / "vault")
    monkeypatch.setattr(vault_module, "crypto_vault", test_vault)
    # The router imported the singleton by name; patch it there too.
    import app.api.vault as vault_api
    monkeypatch.setattr(vault_api, "crypto_vault", test_vault)
    monkeypatch.setenv("ARENA_API_KEY", "owner-key")
    client = TestClient(app)
    headers = {"X-API-Key": "owner-key"}

    assert client.get("/vault/status", headers=headers).json()["initialized"] is False
    init = client.post("/vault/initialize", headers=headers, json={"passphrase": "owner master key"})
    assert init.json()["success"] is True

    stored = client.post("/vault/items", headers=headers,
                         json={"name": "wifi", "plaintext": "home-wifi-pass", "passphrase": "owner master key"})
    assert stored.json()["success"] is True
    assert "plaintext" not in client.get("/vault/items", headers=headers).json()["items"][0]

    decrypted = client.post("/vault/items/wifi/decrypt", headers=headers,
                            json={"passphrase": "owner master key"})
    assert decrypted.json()["plaintext"] == "home-wifi-pass"
    wrong = client.post("/vault/items/wifi/decrypt", headers=headers, json={"passphrase": "nope-nope-nope"})
    assert wrong.json()["success"] is False

    message = client.post("/vault/message/encrypt", headers=headers,
                          json={"plaintext": "secret message", "passphrase": "owner master key"}).json()
    opened = client.post("/vault/message/decrypt", headers=headers,
                         json={"armored": message["armored"], "passphrase": "owner master key"}).json()
    assert opened["plaintext"] == "secret message"

    assert client.delete("/vault/items/wifi", headers=headers).json()["success"] is True
    assert client.delete("/vault/items/wifi", headers=headers).status_code == 404
