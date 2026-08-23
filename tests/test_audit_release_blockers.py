"""Regression tests for release blockers found by the 2026-08-23 audit."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cognition.approval_store import ApprovalStore
from app.llm import ModelCompletionUnavailable, require_real_completion
from app.main import OwnerControlUpdate
from app.tools.translator import TranslatorTool


SIMULATED = {
    "id": "chat-simulated",
    "success": False,
    "simulated": True,
    "error": "provider offline",
    "choices": [{"message": {"content": "[Simulated Response - Local LLM Server Offline]"}}],
}


def test_server_and_singleton_are_the_same_brain():
    import app.server as server
    from app.cognition.runtime import CognitiveRuntime

    assert server.runtime is CognitiveRuntime.get_instance()


def test_native_safety_ceiling_payload_matches_backend_schema():
    update = OwnerControlUpdate.model_validate({"max_autonomous_level": 1})
    assert update.model_dump(exclude_none=True) == {"max_autonomous_level": 1}

    root = Path(__file__).resolve().parents[1]
    desktop = (root / "desktop/pages/owner_control.py").read_text()
    android_api = (
        root / "android/app/src/main/java/com/arena/voice/api/ApiClient.kt"
    ).read_text()
    android_ui = (
        root / "android/app/src/main/java/com/arena/voice/ui/screens/SettingsScreen.kt"
    ).read_text()
    assert "max_autonomous_safety_level" not in desktop + android_api + android_ui
    assert '"max_autonomous_level"' in desktop
    assert '"max_autonomous_level"' in android_api


def test_simulated_completion_is_never_real_content():
    with pytest.raises(ModelCompletionUnavailable):
        require_real_completion(SIMULATED)

    with patch(
        "app.tools.translator.llm_client.generate_chat_completion",
        return_value=SIMULATED,
    ):
        result = TranslatorTool.translate("hello", "French")
    assert result["success"] is False
    assert "Simulated Response" not in json.dumps(result)


def test_every_model_call_site_explicitly_handles_simulation():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "generate_chat_completion" not in text or path.name == "llm.py":
            continue
        if "require_real_completion" not in text and "simulated" not in text:
            offenders.append(str(path.relative_to(root.parent)))
    assert offenders == []


def test_approval_review_ledger_survives_restart_without_restoring_authority(tmp_path):
    path = tmp_path / "approvals.json"
    first = ApprovalStore(path)
    payload = {"title": "Exact", "nested": {"body": "Reviewed"}}
    request = first.add("conversation", "create_note", payload, "Owner review")
    payload["nested"]["body"] = "Mutated after review"

    restored = ApprovalStore(path)
    loaded = restored.get(request.action_id)

    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.payload == {"title": "Exact", "nested": {"body": "Reviewed"}}
    # Loading the review ledger never creates an execution grant.
    assert loaded.authorization_id is None
