"""Owner-controlled encrypted vault API.

Fernet (AES-128-CBC + HMAC-SHA256) via the `cryptography` package; master key
derived per operation with scrypt from the owner's passphrase and never stored.
Passphrases travel in request bodies exactly like every other credential-based
tool — owner-only surfaces, HTTPS/localhost assumed.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.tools.crypto_vault import crypto_vault

router = APIRouter()


class VaultInitializeRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=1024)


class VaultItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    plaintext: str = Field(min_length=1)
    passphrase: str = Field(min_length=8, max_length=1024)
    overwrite: bool = False


class VaultPassphraseRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=1024)


class VaultRotateRequest(BaseModel):
    old_passphrase: str = Field(min_length=8, max_length=1024)
    new_passphrase: str = Field(min_length=8, max_length=1024)


class VaultMessageRequest(BaseModel):
    plaintext: Optional[str] = None
    armored: Optional[str] = None
    passphrase: str = Field(min_length=8, max_length=1024)


@router.post("/vault/initialize")
def vault_initialize_endpoint(req: VaultInitializeRequest):
    return crypto_vault.initialize(req.passphrase)


@router.get("/vault/status")
def vault_status_endpoint():
    return crypto_vault.status()


@router.post("/vault/items")
def vault_store_item_endpoint(req: VaultItemRequest):
    return crypto_vault.encrypt_item(req.name, req.plaintext, req.passphrase, overwrite=req.overwrite)


@router.get("/vault/items")
def vault_list_items_endpoint():
    return crypto_vault.list_items()


@router.post("/vault/items/{name}/decrypt")
def vault_decrypt_item_endpoint(name: str, req: VaultPassphraseRequest):
    return crypto_vault.decrypt_item(name, req.passphrase)


@router.delete("/vault/items/{name}")
def vault_delete_item_endpoint(name: str):
    result = crypto_vault.delete_item(name)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Item not found"))
    return result


@router.post("/vault/rotate")
def vault_rotate_endpoint(req: VaultRotateRequest):
    return crypto_vault.rotate_passphrase(req.old_passphrase, req.new_passphrase)


@router.post("/vault/message/encrypt")
def vault_encrypt_message_endpoint(req: VaultMessageRequest):
    if req.plaintext is None:
        return {"success": False, "error": "plaintext is required"}
    return crypto_vault.encrypt_message(req.plaintext, req.passphrase)


@router.post("/vault/message/decrypt")
def vault_decrypt_message_endpoint(req: VaultMessageRequest):
    if req.armored is None:
        return {"success": False, "error": "armored is required"}
    return crypto_vault.decrypt_message(req.armored, req.passphrase)
