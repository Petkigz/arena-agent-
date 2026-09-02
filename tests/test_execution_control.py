"""Cooperative cancellation, persistent execution history, and rollback receipts."""

import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.cognition.action_proposal import ActionProposal


@pytest.fixture(autouse=True)
def _real_llm_transport(monkeypatch):
    """These tests exercise the REAL HTTP/cancellation path (blocking
    clients, interrupted transports) — remove the suite's hermeticity
    guard (tests/conftest.py sets ARENA_LLM_DISABLED) so the mocked
    transports are actually reached."""
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)

from app.cognition.execution_control import (
    ExecutionCancelled,
    ExecutionControlRegistry,
    run_cancellable_blocking_call,
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


def test_execution_result_evidence_persists_for_reconciliation(tmp_path):
 registry=ExecutionControlRegistry(tmp_path/'executions.db');record=registry.begin('p','move_file')
 result={'success':True,'new_path':'/tmp/x','environment_verified':False}
 registry.record_result(record.execution_id,result)
 assert ExecutionControlRegistry(tmp_path/'executions.db').get_result(record.execution_id)==result

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


def test_blocking_library_call_is_interrupted_cooperatively(tmp_path):
    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    record = registry.begin("proposal-http", "web_search")
    release = threading.Event()
    interrupt_called = threading.Event()
    result_holder = {}

    def blocking_operation():
        release.wait(10)
        return "late response"

    def interrupt():
        interrupt_called.set()
        release.set()

    def run():
        with registry.scope(record.execution_id):
            try:
                run_cancellable_blocking_call(
                    blocking_operation,
                    cancel=interrupt,
                    description="test HTTP request",
                )
            except Exception as exc:
                result_holder["error"] = exc

    with patch("app.cognition.execution_control.execution_control_registry", registry):
        thread = threading.Thread(target=run)
        started = time.monotonic()
        thread.start()
        time.sleep(0.15)
        registry.request_cancel(record.execution_id)
        thread.join(timeout=3)
        elapsed = time.monotonic() - started

    assert not thread.is_alive()
    assert elapsed < 3
    assert interrupt_called.is_set()
    assert isinstance(result_holder["error"], ExecutionCancelled)
    assert "remote side effects may already have occurred" in str(result_holder["error"])
    assert registry.get(record.execution_id).cancellation_observed is True


def test_blocking_call_runs_inline_outside_controlled_execution():
    caller_thread = threading.get_ident()
    observed_thread = run_cancellable_blocking_call(
        threading.get_ident,
        description="uncontrolled test call",
    )
    assert observed_thread == caller_thread


def test_tool_registry_does_not_downgrade_cancellation_to_tool_error(tmp_path):
    from app.cognition.tool_registry import ToolRegistry

    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    record = registry.begin("proposal-tool-http", "web_search")
    release = threading.Event()
    result_holder = {}
    tools = ToolRegistry()
    tools.register_tool(
        "web_search",
        "test",
        lambda payload: run_cancellable_blocking_call(
            lambda: release.wait(10),
            cancel=release.set,
            description="registry HTTP test",
        ),
    )

    def run():
        with registry.scope(record.execution_id):
            try:
                tools.execute_registered_tool("web_search", {})
            except Exception as exc:
                result_holder["error"] = exc

    with patch("app.cognition.execution_control.execution_control_registry", registry):
        thread = threading.Thread(target=run)
        thread.start()
        time.sleep(0.15)
        registry.request_cancel(record.execution_id)
        thread.join(timeout=3)

    assert not thread.is_alive()
    assert isinstance(result_holder["error"], ExecutionCancelled)


def test_local_model_http_cancellation_is_not_converted_to_offline_fallback(tmp_path):
    import httpx
    from app.llm import LocalLLMClient

    registry = ExecutionControlRegistry(tmp_path / "executions.db")
    record = registry.begin("proposal-model", "answer")
    request_started = threading.Event()
    release = threading.Event()
    result_holder = {}

    class BlockingClient:
        is_closed = False

        def post(self, *args, **kwargs):
            request_started.set()
            release.wait(10)
            raise httpx.ReadError("transport interrupted")

        def close(self):
            self.is_closed = True
            release.set()

    model_client = LocalLLMClient(base_url="http://127.0.0.1:1/v1")
    model_client.client.close()
    blocking_client = BlockingClient()
    model_client.client = blocking_client

    def run():
        with registry.scope(record.execution_id):
            try:
                model_client.generate_chat_completion(
                    [{"role": "user", "content": "hello"}]
                )
            except Exception as exc:
                result_holder["error"] = exc

    with patch("app.cognition.execution_control.execution_control_registry", registry):
        thread = threading.Thread(target=run)
        thread.start()
        assert request_started.wait(2)
        registry.request_cancel(record.execution_id)
        thread.join(timeout=3)

    assert not thread.is_alive()
    assert blocking_client.is_closed is True
    assert isinstance(result_holder["error"], ExecutionCancelled)
    # Cancellation must propagate, never become a simulated/offline answer.
    assert "result" not in result_holder
    model_client.close()


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
