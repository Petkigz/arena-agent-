"""Cooperative cancellation, persistent execution history, and rollback receipts."""

import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_control import (
    ExecutionCancelled,
    ExecutionControlRegistry,
)
from app.cognition.runtime import CognitiveRuntime
from app.tools.disposable_sandbox import DisposableSandbox


def test_cancellation_checkpoint_is_persistent(tmp_path):
    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    record = registry.begin("proposal-1", "long_task")
    registry.request_cancel(record.execution_id)

    with registry.scope(record.execution_id):
        with pytest.raises(ExecutionCancelled):
            registry.checkpoint("before_work")

    registry.complete(record.execution_id, status="cancelled")
    restored = ExecutionControlRegistry(tmp_path / "executions.db").get(record.execution_id)
    assert restored.cancel_requested is True
    assert restored.cancellation_observed is True
    assert restored.status == "cancelled"


def test_restart_marks_orphaned_running_execution_interrupted(tmp_path):
    path = tmp_path / "executions.db"
    first = ExecutionControlRegistry(path)
    record = first.begin("proposal-1", "task")

    restored = ExecutionControlRegistry(path).get(record.execution_id)

    assert restored.status == "interrupted"
    assert restored.completed_at is not None


def test_rollback_receipts_are_truthful_and_compensation_is_not_auto_executed(tmp_path):
    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    supported_record = registry.begin("proposal-lora", "activate_lora")
    supported = registry.create_rollback_receipt(
        supported_record.execution_id, "activate_lora", {"adapter_name": "x"}, {"success": True}
    )
    unsupported_record = registry.begin("proposal-email", "send_email")
    unsupported = registry.create_rollback_receipt(
        unsupported_record.execution_id, "send_email", {"to": "x"}, {"success": True}
    )

    assert supported.supported is True
    assert supported.compensation_action == "deactivate_lora"
    assert supported.requires_approval is True
    assert unsupported.supported is False
    assert unsupported.compensation_action is None


def test_runtime_controlled_execution_emits_id_and_receipt(tmp_path):
    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    runtime = object.__new__(CognitiveRuntime)
    runtime.execution_control = registry
    runtime.world = object()
    execute = Mock(return_value={
        "success": True,
        "executed_actions": ["Selected adapter"],
        "assistant_reply": "Selected",
    })
    fake_agent_module = SimpleNamespace(
        MasterAgentOrchestrator=SimpleNamespace(execute_proposal=execute)
    )
    proposal = ActionProposal(
        action_type="activate_lora",
        payload={"adapter_name": "test"},
    )

    with patch.dict(sys.modules, {"app.agents.master_agent": fake_agent_module}):
        result = runtime._execute_capability_controlled(proposal, "Select adapter", "fast")

    assert result["success"] is True
    assert result["controlled_execution_id"].startswith("exec_")
    assert result["rollback_receipt"]["supported"] is True
    persisted = registry.get(result["controlled_execution_id"])
    assert persisted.status == "completed"
    assert persisted.rollback_receipt.compensation_action == "deactivate_lora"


def test_cancellable_sandbox_terminates_process_group(tmp_path):
    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    sandbox_root = tmp_path / "data"
    sandbox_id = "sandbox_cancel"
    sandbox_dir = sandbox_root / "sandboxes" / sandbox_id
    sandbox_dir.mkdir(parents=True)
    record = registry.begin("proposal-sandbox", "run_command")
    result_holder = {}

    def run():
        with registry.scope(record.execution_id):
            result_holder["result"] = DisposableSandbox.run_in_sandbox(
                sandbox_id,
                f"{sys.executable} -c \"import time; time.sleep(10)\"",
                timeout_seconds=20,
            )

    with (
        patch("app.tools.disposable_sandbox.settings.DATA_DIR", sandbox_root),
        patch("app.cognition.execution_control.execution_control_registry", registry),
    ):
        thread = threading.Thread(target=run)
        started = time.monotonic()
        thread.start()
        time.sleep(0.2)
        registry.request_cancel(record.execution_id)
        thread.join(timeout=5)
        elapsed = time.monotonic() - started

    assert not thread.is_alive()
    assert elapsed < 5
    assert result_holder["result"]["success"] is False
    assert result_holder["result"]["cancelled"] is True
