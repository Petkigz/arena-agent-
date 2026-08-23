"""Verified experience proposes LoRA examples, but only owner-approved data exports."""

from types import SimpleNamespace

from app.cognition.training_examples import TrainingExampleStatus, TrainingExampleStore
from app.tools.lora_manager import LoraManagerTool


def _verified(success=True):
    return SimpleNamespace(
        verified_success=success,
        met_conditions=["artifact_exists = true"] if success else [],
        verification_reason="Direct filesystem probe",
    )


def test_only_verified_non_simulated_outcomes_become_pending_candidates(tmp_path):
    store = TrainingExampleStore(tmp_path / "candidates.db")

    assert store.propose_verified(
        prompt="Do task",
        response="Not verified",
        action_type="search_files",
        verification_result=_verified(False),
    ) is None
    assert store.propose_verified(
        prompt="Do task",
        response="[Simulated Response - Local LLM Server Offline]",
        action_type="search_files",
        verification_result=_verified(True),
    ) is None

    candidate = store.propose_verified(
        prompt="Find the report",
        response="The verified report is at reports/q3.pdf",
        action_type="search_files",
        verification_result=_verified(True),
        source_session_id="session-1",
        source_trace_id="trace-1",
    )

    assert candidate is not None
    assert candidate.status == TrainingExampleStatus.PENDING
    assert candidate.source_type == "verified_outcome"
    assert candidate.evidence == ["artifact_exists = true"]


def test_redaction_and_deduplication_happen_before_review(tmp_path):
    store = TrainingExampleStore(tmp_path / "candidates.db")
    prompt = "Email owner@example.com using api_key=super-secret-value from /home/alice/project"
    response = "Bearer abcdefghijklmnop completed the task; call +256 700 123 456"

    first = store.propose_verified(
        prompt=prompt,
        response=response,
        action_type="send_email",
        verification_result=_verified(True),
    )
    second = store.propose_verified(
        prompt=prompt,
        response=response,
        action_type="send_email",
        verification_result=_verified(True),
    )

    assert first.candidate_id == second.candidate_id
    assert "super-secret-value" not in first.prompt
    assert "owner@example.com" not in first.prompt
    assert "/home/alice" not in first.prompt
    assert "abcdefghijklmnop" not in first.response
    assert first.redactions
    assert len(store.list()) == 1


def test_owner_can_edit_approve_or_reject_exact_candidate(tmp_path):
    store = TrainingExampleStore(tmp_path / "candidates.db")
    candidate = store.propose_owner_correction(
        prompt="Summarize this",
        response="Use a concise verified summary",
        skill_name="Writing Style",
    )
    edited = store.edit(
        candidate.candidate_id,
        prompt="Summarize this report",
        response="Return three concise verified bullets",
        skill_name="writing-style",
        note="Owner corrected format",
    )
    approved = store.decide(edited.candidate_id, approved=True, note="Approved")

    assert approved.status == TrainingExampleStatus.APPROVED
    assert approved.skill_name == "writing-style"
    assert approved.review_note == "Approved"

    rejected = store.propose_owner_correction(
        prompt="Another prompt",
        response="Another response",
        skill_name="writing-style",
    )
    rejected = store.decide(rejected.candidate_id, approved=False)
    assert rejected.status == TrainingExampleStatus.REJECTED


def test_export_requires_three_approved_examples_and_writes_manifest(tmp_path, monkeypatch):
    import app.tools.lora_manager as lora_module

    loras_dir = tmp_path / "loras"
    monkeypatch.setattr(lora_module, "LORAS_DIR", loras_dir)
    monkeypatch.setattr(lora_module, "DATASETS_DIR", loras_dir / "datasets")
    monkeypatch.setattr(lora_module, "ACTIVE_FILE", loras_dir / "active.json")
    store = TrainingExampleStore(tmp_path / "candidates.db")

    first = store.propose_owner_correction(
        prompt="Prompt 0", response="Response 0", skill_name="search"
    )
    store.decide(first.candidate_id, True)
    insufficient = store.export_approved("search")
    assert insufficient["success"] is False
    assert insufficient["approved_count"] == 1

    for index in range(1, 5):
        candidate = store.propose_owner_correction(
            prompt=f"Prompt {index}", response=f"Response {index}", skill_name="search"
        )
        store.decide(candidate.candidate_id, True)

    exported = store.export_approved("search")

    assert exported["success"] is True
    assert exported["count"] == 5
    assert exported["train_count"] == 4
    assert exported["eval_count"] == 1
    dataset_dir = loras_dir / "datasets" / "search"
    assert (dataset_dir / "train.jsonl").is_file()
    assert (dataset_dir / "eval.jsonl").is_file()
    assert (dataset_dir / "dataset_manifest.json").is_file()
    assert all(
        item.status == TrainingExampleStatus.EXPORTED
        for item in store.list(skill_name="search")
    )


def test_lora_dataset_counts_only_valid_unique_examples(tmp_path, monkeypatch):
    import app.tools.lora_manager as lora_module

    loras_dir = tmp_path / "loras"
    monkeypatch.setattr(lora_module, "LORAS_DIR", loras_dir)
    monkeypatch.setattr(lora_module, "DATASETS_DIR", loras_dir / "datasets")
    monkeypatch.setattr(lora_module, "ACTIVE_FILE", loras_dir / "active.json")

    result = LoraManagerTool.prepare_dataset("skill", [
        {"prompt": "Valid prompt", "response": "Valid response"},
        {"prompt": "Valid prompt", "response": "Valid response"},
        {"prompt": "", "response": "invalid"},
        {"not": "an example"},
    ])

    assert result["success"] is True
    assert result["count"] == 1
    assert result["train_count"] == 1


def test_adapter_selection_is_honest_about_external_runtime(tmp_path, monkeypatch):
    import json
    import app.tools.lora_manager as lora_module

    loras_dir = tmp_path / "loras"
    adapter_dir = loras_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "Qwen"}), encoding="utf-8"
    )
    monkeypatch.setattr(lora_module, "LORAS_DIR", loras_dir)
    monkeypatch.setattr(lora_module, "DATASETS_DIR", loras_dir / "datasets")
    monkeypatch.setattr(lora_module, "ACTIVE_FILE", loras_dir / "active.json")

    selected = LoraManagerTool.activate_adapter("adapter")
    status = LoraManagerTool.get_status()

    assert selected["success"] is True
    assert selected["runtime_applied"] is False
    assert status["active"] == "adapter"
    assert status["runtime_applied"] is False
    assert "external" in status["note"].lower()
