"""Held-out LoRA evaluation and evidence-gated provider deployment.

An adapter is never considered applied merely because weights exist or Arena
metadata selected it. Evaluation compares externally served base and adapter
model identifiers on held-out reviewed examples and an unrelated-domain
regression set. Deployment remains in-memory and requires a fresh provider
probe; process restart returns to an unverified state.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.config import settings

InferenceFn = Callable[[str, str], Dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    return "".join(c for c in (value or "").strip() if c.isalnum() or c in "_-." )


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _token_f1(actual: str, expected: str) -> float:
    actual_tokens = _tokens(actual)
    expected_tokens = _tokens(expected)
    if not actual_tokens or not expected_tokens:
        return 0.0
    actual_counts: Dict[str, int] = {}
    expected_counts: Dict[str, int] = {}
    for token in actual_tokens:
        actual_counts[token] = actual_counts.get(token, 0) + 1
    for token in expected_tokens:
        expected_counts[token] = expected_counts.get(token, 0) + 1
    overlap = sum(
        min(count, expected_counts.get(token, 0))
        for token, count in actual_counts.items()
    )
    if overlap == 0:
        return 0.0
    precision = overlap / len(actual_tokens)
    recall = overlap / len(expected_tokens)
    return round(2 * precision * recall / (precision + recall), 6)


class LoraEvaluationManager:
    EVALUATIONS_DIR = settings.DATA_DIR / "loras" / "evaluations"
    MINIMUM_EXAMPLES_PER_DOMAIN = 3
    _runtime_binding: Optional[Dict[str, Any]] = None

    @classmethod
    def _load_examples(cls, path: Path) -> List[Dict[str, str]]:
        examples: List[Dict[str, str]] = []
        if not path.is_file():
            return examples
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            prompt = str(item.get("prompt", "")).strip()
            response = str(item.get("response", "")).strip()
            if prompt and response:
                examples.append({"prompt": prompt, "response": response})
        return examples

    @staticmethod
    def _provider_inference(model: str, prompt: str) -> Dict[str, Any]:
        from app.llm import llm_client, extract_reply

        result = llm_client.generate_chat_completion(
            [{"role": "user", "content": prompt}],
            complexity=model,
            temperature=0.0,
            max_tokens=512,
        )
        if not isinstance(result, dict) or result.get("success") is False or result.get("simulated"):
            return {
                "success": False,
                "error": (result or {}).get("error", "Provider returned no verified response")
                if isinstance(result, dict) else "Provider returned an invalid response",
            }
        text = extract_reply(result)
        if not text:
            return {"success": False, "error": "Provider response contained no text"}
        return {
            "success": True,
            "text": text,
            "observed_model": str(result.get("model", "")),
        }

    @classmethod
    def evaluate(
        cls,
        *,
        adapter_name: str,
        base_model: str,
        adapter_model: str,
        skill_name: str,
        unrelated_skill_name: str,
        inference: Optional[InferenceFn] = None,
        minimum_improvement: float = 0.02,
        maximum_regression: float = 0.03,
    ) -> Dict[str, Any]:
        """Compare provider-served models and persist metrics without raw outputs."""
        from app.tools import lora_manager as lora_module

        adapter_name = _safe_name(adapter_name)
        skill_name = _safe_name(skill_name)
        unrelated_skill_name = _safe_name(unrelated_skill_name)
        if not adapter_name or not base_model.strip() or not adapter_model.strip():
            return {"success": False, "error": "Adapter, base model, and adapter model are required"}
        if base_model.strip() == adapter_model.strip():
            return {"success": False, "error": "Base and adapter provider model identifiers must differ"}
        adapter_path = lora_module.LORAS_DIR / adapter_name
        if not (adapter_path / "adapter_config.json").is_file():
            return {"success": False, "error": f"Adapter weights/config not found: {adapter_path}"}

        skill_path = lora_module.DATASETS_DIR / skill_name / "eval.jsonl"
        unrelated_path = lora_module.DATASETS_DIR / unrelated_skill_name / "eval.jsonl"
        skill_examples = cls._load_examples(skill_path)
        unrelated_examples = cls._load_examples(unrelated_path)
        minimum = cls.MINIMUM_EXAMPLES_PER_DOMAIN
        if len(skill_examples) < minimum:
            return {
                "success": False,
                "error": f"Held-out skill evaluation requires at least {minimum} examples; found {len(skill_examples)} in {skill_path}",
            }
        if len(unrelated_examples) < minimum:
            return {
                "success": False,
                "error": f"Unrelated-domain regression requires at least {minimum} examples; found {len(unrelated_examples)} in {unrelated_path}",
            }

        infer = inference or cls._provider_inference
        rows: List[Dict[str, Any]] = []
        provider_verified = True
        errors: List[str] = []
        for domain, examples in (("skill", skill_examples), ("unrelated", unrelated_examples)):
            for index, example in enumerate(examples):
                outputs: Dict[str, Dict[str, Any]] = {}
                for label, model in (("base", base_model.strip()), ("adapter", adapter_model.strip())):
                    result = infer(model, example["prompt"])
                    if not result.get("success"):
                        errors.append(f"{domain}[{index}] {label}: {result.get('error', 'provider failure')}")
                        provider_verified = False
                        outputs[label] = {"score": None, "observed_model": result.get("observed_model")}
                        continue
                    observed = str(result.get("observed_model", ""))
                    if observed != model:
                        provider_verified = False
                        errors.append(f"{domain}[{index}] requested {model!r}, provider reported {observed!r}")
                    outputs[label] = {
                        "score": _token_f1(str(result.get("text", "")), example["response"]),
                        "observed_model": observed,
                    }
                rows.append({
                    "domain": domain,
                    "example_sha256": hashlib.sha256(
                        json.dumps(example, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "base_score": outputs.get("base", {}).get("score"),
                    "adapter_score": outputs.get("adapter", {}).get("score"),
                })

        def average(domain: str, field: str) -> Optional[float]:
            values = [row[field] for row in rows if row["domain"] == domain and row[field] is not None]
            return round(sum(values) / len(values), 6) if values else None

        skill_base = average("skill", "base_score")
        skill_adapter = average("skill", "adapter_score")
        unrelated_base = average("unrelated", "base_score")
        unrelated_adapter = average("unrelated", "adapter_score")
        improvement = round(skill_adapter - skill_base, 6) if skill_base is not None and skill_adapter is not None else None
        regression = round(unrelated_base - unrelated_adapter, 6) if unrelated_base is not None and unrelated_adapter is not None else None
        eligible = bool(
            provider_verified
            and improvement is not None
            and regression is not None
            and improvement >= max(0.0, float(minimum_improvement))
            and regression <= max(0.0, float(maximum_regression))
        )
        report_id = f"lora_eval_{uuid4().hex[:16]}"
        report = {
            "report_id": report_id,
            "created_at": _now(),
            "adapter_name": adapter_name,
            "base_model": base_model.strip(),
            "adapter_model": adapter_model.strip(),
            "skill_name": skill_name,
            "unrelated_skill_name": unrelated_skill_name,
            "skill_examples": len(skill_examples),
            "unrelated_examples": len(unrelated_examples),
            "skill_base_score": skill_base,
            "skill_adapter_score": skill_adapter,
            "skill_improvement": improvement,
            "unrelated_base_score": unrelated_base,
            "unrelated_adapter_score": unrelated_adapter,
            "unrelated_regression": regression,
            "minimum_improvement": max(0.0, float(minimum_improvement)),
            "maximum_regression": max(0.0, float(maximum_regression)),
            "provider_model_identity_verified": provider_verified,
            "deployment_eligible": eligible,
            "errors": errors,
            "example_metrics": rows,
            "runtime_applied": False,
        }
        report_dir = cls.EVALUATIONS_DIR / adapter_name
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{report_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return {"success": provider_verified, "report": report}

    @classmethod
    def get_report(cls, report_id: str) -> Optional[Dict[str, Any]]:
        safe_id = _safe_name(report_id)
        for path in cls.EVALUATIONS_DIR.glob(f"*/{safe_id}.json"):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    @classmethod
    def deploy(cls, report_id: str, inference: Optional[InferenceFn] = None) -> Dict[str, Any]:
        """Route future default requests only after a fresh provider identity probe."""
        report = cls.get_report(report_id)
        if not report:
            return {"success": False, "runtime_applied": False, "error": "Evaluation report not found"}
        if not report.get("deployment_eligible"):
            return {"success": False, "runtime_applied": False, "error": "Evaluation did not pass deployment gates", "report": report}
        infer = inference or cls._provider_inference
        probe = infer(report["adapter_model"], "Reply with the single word READY.")
        if not probe.get("success") or probe.get("observed_model") != report["adapter_model"]:
            return {
                "success": False,
                "runtime_applied": False,
                "error": "Fresh provider probe did not verify the evaluated adapter model identifier",
                "observed_model": probe.get("observed_model"),
            }
        from app.tools.lora_manager import LoraManagerTool
        selected = LoraManagerTool.activate_adapter(report["adapter_name"])
        if not selected.get("success"):
            return {
                "success": False,
                "runtime_applied": False,
                "error": selected.get("error", "Could not select evaluated adapter"),
            }
        from app.llm import llm_client

        llm_client.set_model_override(report["adapter_model"])
        cls._runtime_binding = {
            "adapter_name": report["adapter_name"],
            "provider_model": report["adapter_model"],
            "report_id": report_id,
            "applied_at": _now(),
            "provider_probe_verified": True,
        }
        return {"success": True, "runtime_applied": True, "binding": dict(cls._runtime_binding)}

    @classmethod
    def deactivate_runtime(cls) -> None:
        from app.llm import llm_client

        llm_client.set_model_override(None)
        cls._runtime_binding = None

    @classmethod
    def runtime_binding(cls) -> Optional[Dict[str, Any]]:
        return dict(cls._runtime_binding) if cls._runtime_binding else None
