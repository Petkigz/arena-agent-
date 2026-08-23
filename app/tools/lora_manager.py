"""LoRA manager — continual learning via LoRA adapters for Qwen.

P2 AGI: Tooling toward continual learning that can change behavior once deployed.
Human intelligence gets better at tasks it has seen before. Full fine-tuning on
local hardware risks catastrophic forgetting; LoRA provides skill-specific
adapter weights. Training an adapter here does not change the external LM Studio
runtime until the provider loads or merges it, and improvement must be measured.

This module is deterministic, typed, degradable, and safe for low-spec hardware:
- Discovers adapters in data/loras/ (each adapter is a folder with adapter_config.json)
- Lists adapters, their base model, training info, and which skill/domain they serve
- Creates training jobs (via transformers + peft) — best-effort, requires owner machine
- Activates adapter (writes to data/loras/active.json, or sets env ARENA_LORA_ACTIVE)
- Deactivates, deletes

All methods return {success: bool, ...} dict, never raise.

Owner setup (on your PC, not sandbox):
1. pip install transformers peft accelerate datasets
2. Prepare dataset: data/loras/datasets/<skill>/train.jsonl with {prompt, response}
3. Run training via this tool or via scripts/train_lora.py (future)
4. Adapter saved to data/loras/<adapter_name>/

If not set up, this tool degrades gracefully (lists empty, training returns error with instructions).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

LORAS_DIR = settings.DATA_DIR / "loras"
ACTIVE_FILE = LORAS_DIR / "active.json"
DATASETS_DIR = LORAS_DIR / "datasets"


class LoraManagerTool:
    """Manage LoRA adapters for continual learning."""

    @classmethod
    def _ensure_dirs(cls):
        try:
            LORAS_DIR.mkdir(parents=True, exist_ok=True)
            DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            app_logger.warning(f"Could not create loras dirs: {e}")

    @classmethod
    def list_adapters(cls) -> Dict[str, Any]:
        """List discovered LoRA adapters."""
        cls._ensure_dirs()
        adapters = []
        try:
            for p in LORAS_DIR.iterdir():
                if not p.is_dir():
                    continue
                if p.name == "datasets":
                    continue
                config_path = p / "adapter_config.json"
                if not config_path.exists():
                    continue
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    # Try to read training info if exists
                    info_path = p / "training_info.json"
                    training_info = {}
                    if info_path.exists():
                        try:
                            training_info = json.loads(info_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass

                    adapters.append({
                        "name": p.name,
                        "path": str(p),
                        "base_model": config.get("base_model_name_or_path", "unknown"),
                        "r": config.get("r", 0),
                        "lora_alpha": config.get("lora_alpha", 0),
                        "target_modules": config.get("target_modules", []),
                        "training_info": training_info,
                        "size_mb": round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024, 2),
                    })
                except Exception as e:
                    app_logger.warning(f"Could not read adapter {p}: {e}")
                    continue

            return {
                "success": True,
                "adapters": adapters,
                "count": len(adapters),
                "active": cls.get_active_adapter().get("active"),
            }
        except Exception as e:
            app_logger.error(f"List adapters failed: {e}")
            return {"success": False, "error": str(e), "adapters": [], "count": 0}

    @classmethod
    def get_active_adapter(cls) -> Dict[str, Any]:
        """Get currently active adapter (if any)."""
        cls._ensure_dirs()
        try:
            if ACTIVE_FILE.exists():
                data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
                return {
                    "success": True,
                    "active": data.get("active"),
                    "runtime_applied": False,
                    "info": data,
                    "note": "Adapter is selected in Arena metadata but is not attached to the external LM Studio runtime.",
                }
            # Also check env var
            env_active = os.getenv("ARENA_LORA_ACTIVE", "").strip()
            if env_active:
                return {
                    "success": True,
                    "active": env_active,
                    "runtime_applied": False,
                    "info": {"source": "env"},
                    "note": "ARENA_LORA_ACTIVE is selection metadata; configure the inference provider separately.",
                }
            return {"success": True, "active": None, "runtime_applied": False, "info": {}}
        except Exception as e:
            return {"success": False, "error": str(e), "active": None}

    @classmethod
    def activate_adapter(cls, adapter_name: str) -> Dict[str, Any]:
        """Activate a LoRA adapter (writes to active.json)."""
        cls._ensure_dirs()
        if not adapter_name or not adapter_name.strip():
            return {"success": False, "error": "Adapter name required"}

        safe_name = "".join(c for c in adapter_name.strip() if c.isalnum() or c in ("_", "-", ".")).strip()
        adapter_path = LORAS_DIR / safe_name

        if not adapter_path.exists():
            return {"success": False, "error": f"Adapter not found: {adapter_path}"}

        if not (adapter_path / "adapter_config.json").exists():
            return {"success": False, "error": f"Not a valid LoRA adapter (missing adapter_config.json): {adapter_path}"}

        try:
            ACTIVE_FILE.write_text(json.dumps({"active": safe_name, "path": str(adapter_path)}, indent=2), encoding="utf-8")
            app_logger.info(f"Activated LoRA adapter: {safe_name}")

            # Also try to notify LLM client to reload? LLM is in LM Studio, not here — but we can set env for next run
            # For now, just return success with instructions

            return {
                "success": True,
                "active": safe_name,
                "path": str(adapter_path),
                "runtime_applied": False,
                "message": (
                    f"Selected adapter {safe_name} in Arena metadata. It will not change model output "
                    "until the adapter is merged/loaded by the external inference provider."
                ),
            }
        except Exception as e:
            app_logger.error(f"Activate adapter failed: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def deactivate_adapter(cls) -> Dict[str, Any]:
        """Deactivate current adapter."""
        cls._ensure_dirs()
        try:
            if ACTIVE_FILE.exists():
                ACTIVE_FILE.unlink()
            return {"success": True, "active": None, "message": "Deactivated LoRA adapter — using base model"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def delete_adapter(cls, adapter_name: str) -> Dict[str, Any]:
        """Delete an adapter (irreversible, requires approval)."""
        cls._ensure_dirs()
        if not adapter_name or not adapter_name.strip():
            return {"success": False, "error": "Adapter name required"}

        safe_name = "".join(c for c in adapter_name.strip() if c.isalnum() or c in ("_", "-", ".")).strip()
        adapter_path = LORAS_DIR / safe_name

        if not adapter_path.exists():
            return {"success": False, "error": f"Adapter not found: {adapter_path}"}

        # Check if it's the active one — deactivate first
        active = cls.get_active_adapter().get("active")
        if active == safe_name:
            cls.deactivate_adapter()

        try:
            shutil.rmtree(adapter_path)
            app_logger.info(f"Deleted LoRA adapter: {safe_name}")
            return {"success": True, "deleted": safe_name, "message": f"Deleted adapter {safe_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def prepare_dataset(cls, skill_name: str, examples: List[Dict[str, str]]) -> Dict[str, Any]:
        """Prepare a dataset for LoRA training from examples.

        examples: List of {prompt, response} dicts
        Saves to data/loras/datasets/<skill>/train.jsonl
        """
        cls._ensure_dirs()
        if not skill_name or not skill_name.strip():
            return {"success": False, "error": "Skill name required"}

        safe_skill = "".join(c for c in skill_name.strip().lower() if c.isalnum() or c in ("_", "-")).strip() or "general"
        skill_dir = DATASETS_DIR / safe_skill
        try:
            accepted: List[Dict[str, str]] = []
            seen = set()
            source_ids = []
            for ex in examples:
                if not isinstance(ex, dict):
                    continue
                prompt = str(ex.get("prompt", "")).strip()
                response = str(ex.get("response", "")).strip()
                if len(prompt) < 3 or len(response) < 3:
                    continue
                digest = hashlib.sha256(
                    json.dumps(
                        {"prompt": prompt, "response": response},
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                accepted.append({"prompt": prompt, "response": response})
                if ex.get("candidate_id"):
                    source_ids.append(str(ex["candidate_id"]))

            if not accepted:
                return {"success": False, "error": "No valid unique prompt/response examples supplied"}

            # Stable hash ordering makes train/eval splits reproducible.
            accepted.sort(key=lambda item: hashlib.sha256(
                f"{item['prompt']}\n{item['response']}".encode("utf-8")
            ).hexdigest())
            eval_count = max(1, round(len(accepted) * 0.2)) if len(accepted) >= 5 else 0
            eval_examples = accepted[:eval_count]
            train_examples = accepted[eval_count:]

            skill_dir.mkdir(parents=True, exist_ok=True)
            train_path = skill_dir / "train.jsonl"
            eval_path = skill_dir / "eval.jsonl"
            with open(train_path, "w", encoding="utf-8") as file:
                for example in train_examples:
                    file.write(json.dumps(example, ensure_ascii=False) + "\n")
            if eval_examples:
                with open(eval_path, "w", encoding="utf-8") as file:
                    for example in eval_examples:
                        file.write(json.dumps(example, ensure_ascii=False) + "\n")
            else:
                eval_path.unlink(missing_ok=True)

            dataset_hash = hashlib.sha256(
                "\n".join(
                    json.dumps(item, sort_keys=True, ensure_ascii=False)
                    for item in accepted
                ).encode("utf-8")
            ).hexdigest()
            manifest = {
                "skill": safe_skill,
                "total_count": len(accepted),
                "train_count": len(train_examples),
                "eval_count": len(eval_examples),
                "dataset_sha256": dataset_hash,
                "source_candidate_ids": sorted(set(source_ids)),
            }
            (skill_dir / "dataset_manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            return {
                "success": True,
                "skill": safe_skill,
                "path": str(train_path),
                "eval_path": str(eval_path) if eval_examples else None,
                "count": len(accepted),
                "train_count": len(train_examples),
                "eval_count": len(eval_examples),
                "dataset_sha256": dataset_hash,
                "message": f"Prepared reviewed dataset for skill {safe_skill} with {len(accepted)} unique examples",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def create_training_job(
        cls,
        adapter_name: str,
        base_model: str = "Qwen/Qwen2.5-3B-Instruct",
        skill_name: str = "general",
        r: int = 8,
        lora_alpha: int = 16,
        epochs: int = 3,
        learning_rate: float = 2e-4,
    ) -> Dict[str, Any]:
        """Create a LoRA training job (scaffolding, runs on owner machine).

        This does not run training in sandbox (no GPU, no deps), but creates a config
        and returns instructions. On owner machine with transformers+peft, it can run.

        Returns {success, config, instructions} — always typed dict.
        """
        cls._ensure_dirs()
        if not adapter_name or not adapter_name.strip():
            return {"success": False, "error": "Adapter name required"}

        safe_name = "".join(c for c in adapter_name.strip() if c.isalnum() or c in ("_", "-", ".")).strip()
        dataset_path = DATASETS_DIR / skill_name / "train.jsonl"

        if not dataset_path.exists():
            return {
                "success": False,
                "error": f"Dataset not found: {dataset_path}. Run prepare_dataset() first or create train.jsonl manually.",
                "instructions": f"Create {dataset_path} with JSONL lines {{\"prompt\": ..., \"response\": ...}}",
            }

        config = {
            "adapter_name": safe_name,
            "base_model": base_model,
            "skill_name": skill_name,
            "dataset_path": str(dataset_path),
            "output_dir": str(LORAS_DIR / safe_name),
            "r": r,
            "lora_alpha": lora_alpha,
            "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            "epochs": epochs,
            "learning_rate": learning_rate,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 4,
        }

        # Try to check if peft/transformers available — if not, return config with instructions (degradable)
        try:
            import transformers  # noqa: F401
            import peft  # noqa: F401
            peft_available = True
        except ImportError:
            peft_available = False

        if not peft_available:
            return {
                "success": False,
                "error": "peft/transformers not installed (pip install transformers peft accelerate datasets)",
                "config": config,
                "instructions": (
                    f"On your PC with GPU, run:\n"
                    f"pip install transformers peft accelerate datasets\n"
                    f"Then use scripts/train_lora.py or run training via:\n"
                    f"python -c \"from app.tools.lora_manager import LoraManagerTool; "
                    f"LoraManagerTool.train('{safe_name}', '{base_model}', '{skill_name}')\"\n"
                    f"Dataset: {dataset_path}\n"
                    f"Output: {LORAS_DIR / safe_name}\n"
                ),
            }

        # If available, we could run training here, but we don't auto-run in this method
        # (training is heavy, should be explicit). Return config for manual run.

        return {
            "success": True,
            "config": config,
            "peft_available": peft_available,
            "message": f"Training job config created for adapter {safe_name} (skill: {skill_name}). Run train() to execute.",
            "instructions": f"Dataset: {dataset_path} → Output: {LORAS_DIR / safe_name}",
        }

    @classmethod
    def train(
        cls,
        adapter_name: str,
        base_model: str = "Qwen/Qwen2.5-3B-Instruct",
        skill_name: str = "general",
    ) -> Dict[str, Any]:
        """Run LoRA training (heavy, owner machine only, best-effort).

        This will attempt to train using transformers+peft. In sandbox it will fail gracefully
        with instructions. On owner machine with GPU, it will train and save adapter.
        """
        cls._ensure_dirs()
        job = cls.create_training_job(adapter_name, base_model, skill_name)
        if not job.get("success"):
            return job

        config = job.get("config", {})
        dataset_path = Path(config.get("dataset_path", ""))
        output_dir = Path(config.get("output_dir", ""))

        try:
            from datasets import load_dataset  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer, DataCollatorForLanguageModeling  # type: ignore
            from peft import LoraConfig, get_peft_model, TaskType  # type: ignore

            app_logger.info(f"Starting LoRA training for {adapter_name} (skill: {skill_name})")

            # Load dataset
            dataset = load_dataset("json", data_files=str(dataset_path), split="train")

            # Load model and tokenizer
            model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)
            tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Prepare LoRA config
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=config.get("r", 8),
                lora_alpha=config.get("lora_alpha", 16),
                target_modules=config.get("target_modules"),
                lora_dropout=0.05,
                bias="none",
            )
            model = get_peft_model(model, lora_config)

            # Tokenize dataset
            def tokenize_function(examples):
                # Combine prompt + response
                texts = [f"{p}\n{r}" for p, r in zip(examples["prompt"], examples["response"])]
                return tokenizer(texts, truncation=True, max_length=512)

            tokenized = dataset.map(tokenize_function, batched=True)

            # Training args
            training_args = TrainingArguments(
                output_dir=str(output_dir),
                per_device_train_batch_size=config.get("per_device_train_batch_size", 1),
                gradient_accumulation_steps=config.get("gradient_accumulation_steps", 4),
                num_train_epochs=config.get("epochs", 3),
                learning_rate=config.get("learning_rate", 2e-4),
                logging_steps=10,
                save_steps=100,
                save_total_limit=2,
            )

            data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized,
                data_collator=data_collator,
            )

            trainer.train()

            # Save adapter
            model.save_pretrained(str(output_dir))
            tokenizer.save_pretrained(str(output_dir))

            # Save training info
            training_info = {
                "adapter_name": adapter_name,
                "base_model": base_model,
                "skill_name": skill_name,
                "dataset_path": str(dataset_path),
                "epochs": config.get("epochs", 3),
                "learning_rate": config.get("learning_rate", 2e-4),
                "trained_at": str(__import__("datetime").datetime.now().isoformat()),
            }
            (output_dir / "training_info.json").write_text(json.dumps(training_info, indent=2), encoding="utf-8")

            app_logger.info(f"LoRA training completed: {adapter_name} saved to {output_dir}")

            return {
                "success": True,
                "adapter_name": adapter_name,
                "path": str(output_dir),
                "training_info": training_info,
                "message": f"Trained adapter {adapter_name} for skill {skill_name} at {output_dir}",
            }

        except Exception as e:
            app_logger.error(f"LoRA training failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "config": config,
                "instructions": "Install transformers peft accelerate datasets and ensure dataset exists",
            }

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get LoRA system status."""
        cls._ensure_dirs()
        adapters = cls.list_adapters()
        active = cls.get_active_adapter()
        return {
            "success": True,
            "loras_dir": str(LORAS_DIR),
            "adapters_count": adapters.get("count", 0),
            "adapters": adapters.get("adapters", [])[:10],
            "active": active.get("active"),
            "runtime_applied": active.get("runtime_applied", False),
            "datasets": [p.name for p in DATASETS_DIR.iterdir() if p.is_dir()] if DATASETS_DIR.exists() else [],
            "note": (
                "Reviewed datasets and PEFT training are supported. Adapter selection is metadata only; "
                "the external LM Studio/inference provider must load or merge the adapter before behavior changes."
            ),
        }
