"""Provider-served LoRA behavior must pass held-out gates before routing."""

from __future__ import annotations

import json

from app.cognition.lora_evaluation import LoraEvaluationManager
from app.llm import llm_client
from app.tools.lora_manager import LoraManagerTool


def _setup(tmp_path, monkeypatch):
    import app.tools.lora_manager as lora_module

    loras = tmp_path / "loras"
    datasets = loras / "datasets"
    adapter = loras / "skill-adapter"
    adapter.mkdir(parents=True)
    (adapter / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "base-model"}), encoding="utf-8"
    )
    for skill, prompt, response in (
        ("skill", "special prompt", "alpha beta"),
        ("general", "ordinary prompt", "stable answer"),
    ):
        directory = datasets / skill
        directory.mkdir(parents=True)
        (directory / "eval.jsonl").write_text(
            "".join(
                json.dumps({"prompt": f"{prompt} {index}", "response": response}) + "\n"
                for index in range(3)
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(lora_module, "LORAS_DIR", loras)
    monkeypatch.setattr(lora_module, "DATASETS_DIR", datasets)
    monkeypatch.setattr(lora_module, "ACTIVE_FILE", loras / "active.json")
    monkeypatch.setattr(LoraEvaluationManager, "EVALUATIONS_DIR", loras / "evaluations")
    monkeypatch.setattr(LoraEvaluationManager, "_runtime_binding", None)
    llm_client.set_model_override(None)
    return loras


def _improved_inference(model: str, prompt: str):
    if prompt.startswith("special prompt"):
        text = "alpha" if model == "base-model" else "alpha beta"
    elif prompt.startswith("ordinary prompt"):
        text = "stable answer"
    else:
        text = "READY"
    return {"success": True, "text": text, "observed_model": model}


def test_held_out_improvement_and_regression_gate_provider_deployment(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    evaluated = LoraEvaluationManager.evaluate(
        adapter_name="skill-adapter",
        base_model="base-model",
        adapter_model="base-with-skill-adapter",
        skill_name="skill",
        unrelated_skill_name="general",
        inference=_improved_inference,
        minimum_improvement=0.1,
        maximum_regression=0.01,
    )

    assert evaluated["success"] is True
    report = evaluated["report"]
    assert report["provider_model_identity_verified"] is True
    assert report["skill_improvement"] > 0.1
    assert report["unrelated_regression"] == 0.0
    assert report["deployment_eligible"] is True
    assert report["runtime_applied"] is False
    assert "text" not in json.dumps(report["example_metrics"])

    deployed = LoraEvaluationManager.deploy(report["report_id"], _improved_inference)

    assert deployed["success"] is True
    assert deployed["runtime_applied"] is True
    assert llm_client.route_request("fast") == "base-with-skill-adapter"
    status = LoraManagerTool.get_active_adapter()
    assert status["runtime_applied"] is True
    assert status["runtime_binding"]["report_id"] == report["report_id"]

    deactivated = LoraManagerTool.deactivate_adapter()
    assert deactivated["runtime_applied"] is False
    assert llm_client.model_override is None


def test_model_identity_mismatch_blocks_deployment(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def mismatched(model: str, prompt: str):
        result = _improved_inference(model, prompt)
        if model == "base-with-skill-adapter":
            result["observed_model"] = "base-model"
        return result

    evaluated = LoraEvaluationManager.evaluate(
        adapter_name="skill-adapter",
        base_model="base-model",
        adapter_model="base-with-skill-adapter",
        skill_name="skill",
        unrelated_skill_name="general",
        inference=mismatched,
    )

    assert evaluated["success"] is False
    assert evaluated["report"]["provider_model_identity_verified"] is False
    assert evaluated["report"]["deployment_eligible"] is False
    deployed = LoraEvaluationManager.deploy(
        evaluated["report"]["report_id"], mismatched
    )
    assert deployed["success"] is False
    assert deployed["runtime_applied"] is False
    assert llm_client.model_override is None


def test_unrelated_domain_regression_blocks_deployment(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def regressing(model: str, prompt: str):
        result = _improved_inference(model, prompt)
        if model == "base-with-skill-adapter" and prompt.startswith("ordinary prompt"):
            result["text"] = "completely wrong"
        return result

    evaluated = LoraEvaluationManager.evaluate(
        adapter_name="skill-adapter",
        base_model="base-model",
        adapter_model="base-with-skill-adapter",
        skill_name="skill",
        unrelated_skill_name="general",
        inference=regressing,
        minimum_improvement=0.1,
        maximum_regression=0.05,
    )

    report = evaluated["report"]
    assert report["skill_improvement"] > 0.1
    assert report["unrelated_regression"] > 0.05
    assert report["deployment_eligible"] is False


def test_metadata_selection_of_different_adapter_clears_live_binding(tmp_path, monkeypatch):
    loras = _setup(tmp_path, monkeypatch)
    evaluated = LoraEvaluationManager.evaluate(
        adapter_name="skill-adapter",
        base_model="base-model",
        adapter_model="base-with-skill-adapter",
        skill_name="skill",
        unrelated_skill_name="general",
        inference=_improved_inference,
        minimum_improvement=0.1,
    )
    assert LoraEvaluationManager.deploy(
        evaluated["report"]["report_id"], _improved_inference
    )["runtime_applied"] is True
    other = loras / "other-adapter"
    other.mkdir()
    (other / "adapter_config.json").write_text("{}", encoding="utf-8")

    selected = LoraManagerTool.activate_adapter("other-adapter")

    assert selected["runtime_applied"] is False
    assert llm_client.model_override is None
    assert LoraEvaluationManager.runtime_binding() is None


def test_evaluation_rejects_too_small_holdout(tmp_path, monkeypatch):
    loras = _setup(tmp_path, monkeypatch)
    (loras / "datasets" / "skill" / "eval.jsonl").write_text(
        json.dumps({"prompt": "one", "response": "answer"}) + "\n",
        encoding="utf-8",
    )

    result = LoraEvaluationManager.evaluate(
        adapter_name="skill-adapter",
        base_model="base-model",
        adapter_model="base-with-skill-adapter",
        skill_name="skill",
        unrelated_skill_name="general",
        inference=_improved_inference,
    )

    assert result["success"] is False
    assert "at least 3" in result["error"]
    assert LoraEvaluationManager.runtime_binding() is None


def test_restart_does_not_claim_persisted_selection_is_runtime_applied(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert LoraManagerTool.activate_adapter("skill-adapter")["success"] is True

    # A process restart loses the in-memory verified provider binding by design.
    monkeypatch.setattr(LoraEvaluationManager, "_runtime_binding", None)
    llm_client.set_model_override(None)

    status = LoraManagerTool.get_active_adapter()
    assert status["active"] == "skill-adapter"
    assert status["runtime_applied"] is False
    assert "not attached" in status["note"]
