#!/usr/bin/env python3
"""
Train a LoRA adapter for continual learning (P2 AGI).

This script enables the agent to get better at tasks it has seen before
without catastrophic forgetting — a key human intelligence capability.

Usage (on your PC with GPU, not in sandbox):

1. Prepare dataset via API or tool:
   POST /loras/dataset with {skill_name, examples: [{prompt, response}]}

2. Create training job:
   POST /loras/train-job with {adapter_name, base_model, skill_name}

3. Run training:
   python scripts/train_lora.py --adapter my_skill_adapter --base Qwen/Qwen2.5-3B-Instruct --skill coding

Or directly via tool:
   from app.tools.lora_manager import LoraManagerTool
   LoraManagerTool.train("my_adapter", "Qwen/Qwen2.5-3B-Instruct", "coding")

Requirements (owner machine):
   pip install transformers peft accelerate datasets torch

The adapter will be saved to data/loras/<adapter_name>/. Selecting it via
POST /loras/activate updates metadata only. To affect default model routing, run
POST /loras/evaluations with distinct provider base/adapter model identifiers,
review the held-out and unrelated-domain metrics, then separately call
POST /loras/deploy-evaluated with the passing report id.
"""

import argparse
import sys
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.lora_manager import LoraManagerTool


def main():
    parser = argparse.ArgumentParser(description="Train LoRA adapter for continual learning")
    parser.add_argument("--adapter", required=True, help="Adapter name (e.g., my_coding_skill)")
    parser.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct", help="Base model id")
    parser.add_argument("--skill", default="general", help="Skill name (dataset folder)")
    parser.add_argument("--r", type=int, default=8, help="LoRA r")
    parser.add_argument("--alpha", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--epochs", type=int, default=3, help="Epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")

    args = parser.parse_args()

    print(f"=== LoRA Training ===")
    print(f"Adapter: {args.adapter}")
    print(f"Base: {args.base}")
    print(f"Skill: {args.skill}")
    print(f"r={args.r}, alpha={args.alpha}, epochs={args.epochs}, lr={args.lr}")
    print()

    # Check status first
    status = LoraManagerTool.get_status()
    print(f"LoRA dir: {status.get('loras_dir')}")
    print(f"Existing adapters: {status.get('adapters_count')}")
    print(f"Active: {status.get('active')}")
    print(f"Datasets: {status.get('datasets')}")
    print()

    # Create job config
    job = LoraManagerTool.create_training_job(
        adapter_name=args.adapter,
        base_model=args.base,
        skill_name=args.skill,
        r=args.r,
        lora_alpha=args.alpha,
        epochs=args.epochs,
        learning_rate=args.lr,
    )

    if not job.get("success"):
        print(f"❌ Could not create training job: {job.get('error')}")
        print(f"\nInstructions:\n{job.get('instructions','')}")
        print(f"\nConfig:\n{job.get('config','')}")
        return 1

    print(f"✅ Job config created:")
    print(f"  Dataset: {job['config']['dataset_path']}")
    print(f"  Output: {job['config']['output_dir']}")
    print()

    # Run training
    print(f"Starting training (this may take a while on GPU)...")
    result = LoraManagerTool.train(args.adapter, args.base, args.skill)

    if result.get("success"):
        print(f"\n✅ Training completed!")
        print(f"  Adapter: {result.get('adapter_name')}")
        print(f"  Path: {result.get('path')}")
        print(f"  Info: {result.get('training_info')}")
        print(f"\nNext steps (selection alone does not change behavior):")
        print("  1. Make the provider expose distinct base and adapter/merged model IDs.")
        print("  2. POST /loras/evaluations with this adapter, both model IDs, the skill dataset, and an unrelated dataset.")
        print("  3. Review the report, then separately POST /loras/deploy-evaluated only if deployment_eligible=true.")
        return 0
    else:
        print(f"\n❌ Training failed: {result.get('error')}")
        print(f"\nConfig: {result.get('config')}")
        print(f"\nInstructions: {result.get('instructions','')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
