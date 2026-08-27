#!/usr/bin/env python3
"""Owner-machine LM Studio benchmark: measured latency/throughput/RAM per model.

Runs on the owner's machine against the real local provider. For each requested
model it issues timed completions across fixed prompts, records tokens/sec from
provider usage fields when available, samples RAM before/after, and writes a
JSON report to data/lm_benchmarks/. Offline providers are reported honestly as
failures; nothing is simulated.

Usage:
    python scripts/benchmark_lm_studio.py [model_id ...]
    # no args → benchmarks the configured fast and main models

Requirements: LM Studio (or any OpenAI-compatible server) running at the
configured provider URL with JIT loading enabled, or the models pre-loaded.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cognition.inference_profile import inference_profile_store, probe_provider  # noqa: E402

PROMPTS = [
    "Summarize the idea of feedback loops in two sentences.",
    "List three practical ways to reduce daily electricity use.",
    "Explain the difference between latency and throughput briefly.",
    "Write one cautious sentence about verifying claims with evidence.",
    "Translate 'good morning, the build passed' into Swahili.",
]
MAX_TOKENS = 256


def _ram_gb() -> dict:
    mem = psutil.virtual_memory()
    return {"used_gb": round(mem.used / (1024 ** 3), 2), "percent": mem.percent}


def benchmark_model(client: httpx.Client, base_url: str, model: str) -> dict:
    """Timed completions for one model. Failures are honest failures."""
    result = {
        "model": model,
        "requested": True,
        "completed_samples": 0,
        "errors": [],
        "wall_seconds": [],
        "latency_ms_first_token": None,
        "completion_tokens_per_second": [],
        "usage_reported": False,
        "served_models": [],
        "requested_model_served": True,
    }
    for prompt in PROMPTS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
        try:
            started = time.perf_counter()
            response = client.post(f"{base_url}/chat/completions", json=payload, timeout=600.0)
            elapsed = time.perf_counter() - started
            if response.status_code != 200:
                result["errors"].append(f"HTTP {response.status_code}: {response.text[:200]}")
                continue
            body = response.json()
            served = str(body.get("model") or model)
            if served not in result["served_models"]:
                result["served_models"].append(served)
            if served != model:
                # The provider loosely resolved our id to a DIFFERENT model:
                # these samples are not evidence about the requested model.
                result["requested_model_served"] = False
            content = ""
            message = {}
            try:
                message = body["choices"][0]["message"]
                content = str(message.get("content") or "")
            except Exception:
                pass
            reasoning = str(message.get("reasoning_content") or "") if isinstance(message, dict) else ""
            if reasoning.strip():
                # Reasoning model (e.g. Qwen3): thinking is real work. Record
                # it as evidence with the honest label; throughput counts.
                result["reasoning_model"] = True
            if not content.strip() and not reasoning.strip():
                result["errors"].append("empty completion (no content and no reasoning)")
                continue
            if not content.strip():
                # All budget consumed by thinking; note it but keep the sample.
                result.setdefault("reasoning_only_samples", 0)
                result["reasoning_only_samples"] += 1
            result["completed_samples"] += 1
            result["wall_seconds"].append(round(elapsed, 3))
            usage = body.get("usage") or {}
            completion_tokens = usage.get("completion_tokens")
            if isinstance(completion_tokens, (int, float)) and completion_tokens > 0:
                result["usage_reported"] = True
                result["completion_tokens_per_second"].append(round(completion_tokens / elapsed, 2))
        except httpx.HTTPError as exc:
            result["errors"].append(f"transport: {exc}")
    if result["wall_seconds"]:
        result["wall_seconds_mean"] = round(statistics.mean(result["wall_seconds"]), 3)
    if result["completion_tokens_per_second"]:
        result["completion_tokens_per_second_mean"] = round(
            statistics.mean(result["completion_tokens_per_second"]), 2
        )
    result["success"] = result["completed_samples"] == len(PROMPTS) and result["requested_model_served"]
    if result.get("reasoning_model"):
        result["note"] = (
            "Reasoning model: throughput includes thinking tokens; some samples "
            "may spend the entire budget on reasoning_content with empty visible content.")
    result["partial"] = 0 < result["completed_samples"] < len(PROMPTS)
    if not result["requested_model_served"]:
        result["resolution_warning"] = (
            f"Provider resolved '{model}' to {result['served_models']}; samples are NOT evidence "
            "about the requested model. Set the profile to the provider's exact model id." )
    return result


def run(models: list[str] | None = None, client_factory=httpx.Client) -> dict:
    profile = inference_profile_store.get()
    base_url = profile.provider_url.rstrip("/")
    targets = models or [profile.fast_model, profile.main_model]
    probe = probe_provider(profile, completion_probe=False)
    # Live-hardware lesson: the profile may still name models this provider
    # doesn't have (server down when PUT was attempted, defaults on a fresh
    # install). Refuse honestly instead of burning the run on 400s — and
    # suggest the loaded models that COULD be benchmarked.
    loaded = set(probe.get("loaded_models") or [])
    if loaded:
        missing = [m for m in targets if m not in loaded]
        if missing:
            report = {
                "benchmarked_at": datetime.now(timezone.utc).isoformat(),
                "provider_url": base_url,
                "success": False,
                "error": (
                    f"Requested models not loaded by the provider: {missing}. "
                    "Start the Arena server and PUT /owner-control/inference-profile "
                    "with exact loaded ids, or pass them as CLI arguments."
                ),
                "loaded_models": sorted(loaded),
                "suggestion": (
                    f"e.g. python scripts/benchmark_lm_studio.py {' '.join(sorted(loaded)[:2])}"
                ),
            }
            return report

    report = {
        "benchmarked_at": datetime.now(timezone.utc).isoformat(),
        "provider_url": base_url,
        "provider_online": probe["provider_online"],
        "loaded_models_at_start": probe["loaded_models"],
        "context_window_tokens": profile.context_window_tokens,
        "prompts_per_model": len(PROMPTS),
        "max_tokens_per_prompt": MAX_TOKENS,
        "ram_before": _ram_gb(),
        "results": [],
    }
    if not probe["provider_online"]:
        report["success"] = False
        report["error"] = f"provider offline: {probe.get('error')}"
        return report

    with client_factory(timeout=600.0) as client:
        for model in targets:
            report["results"].append(benchmark_model(client, base_url, model))

    report["ram_after"] = _ram_gb()
    report["success"] = bool(report["results"]) and all(r["success"] for r in report["results"])
    return report


def main() -> int:
    report = run(sys.argv[1:] or None)
    out_dir = Path("data/lm_benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"benchmark_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nreport written to {out_path}", file=sys.stderr)
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
