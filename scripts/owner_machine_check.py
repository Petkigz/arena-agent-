#!/usr/bin/env python3
"""One-shot owner-machine readiness check: hardware, OS grounding, providers.

Run this ON THE OWNER MACHINE from the repo root:

    python scripts/owner_machine_check.py

It composes every existing probe into one JSON block — paste the whole
output back so failures can be diagnosed precisely. Every check reports
honestly: unavailable hardware, offline providers, and unknown states are
labeled, never simulated.
"""
import json
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def probe_hardware() -> dict:
    from app.utils.hardware_governor import HardwareGovernor
    model = HardwareGovernor.build_self_model()
    budget = model.get("measured_worker_budget", {})
    return {
        "cpu": model.get("cpu_model"),
        "threads": model.get("cpu_logical_threads"),
        "ram_total_gb": model.get("ram_total_gb"),
        "high_memory_profile": model.get("high_memory_profile"),
        "gpu": model.get("gpu_model"),
        "gpu_acceleration": model.get("gpu_acceleration"),
        "worker_budget": {
            "granted": budget.get("workers_granted"),
            "physical_cap": budget.get("physical_thread_cap"),
            "reasons": budget.get("reasons", []),
        },
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
    }


def probe_os_control() -> dict:
    from scripts.validate_os_control import run as run_validation
    return run_validation()


def probe_display() -> dict:
    from app.tools.display_topology import DisplayTopologyTool
    return DisplayTopologyTool.capture()


def probe_accessibility() -> dict:
    from app.tools.accessibility_control import AccessibilityControlTool
    return AccessibilityControlTool.status()


def probe_inference() -> dict:
    try:
        from app.cognition.inference_profile import inference_profile_store, probe_provider
        profile = inference_profile_store.get()
        return {"profile": profile.to_dict(), "probe": probe_provider(profile, timeout=8.0)}
    except Exception as exc:
        return {"error": f"inference probe failed: {exc}"}


def probe_embeddings() -> dict:
    from app.config import settings
    url = getattr(settings, "ARENA_EMBEDDING_URL", "")
    model = getattr(settings, "ARENA_EMBEDDING_MODEL", "")
    result = {"configured_url": url or None, "configured_model": model or None,
              "provider_reachable": None, "dimension": None, "error": None}
    if not (url and model):
        result["note"] = "Not configured; associative memory uses the deterministic hashed embedder."
        return result
    try:
        import httpx
        base = url.rstrip("/")
        if not base.endswith("/embeddings"):
            base = (base + "/v1").rstrip("/") + "/embeddings"
        with httpx.Client(timeout=8.0) as client:
            response = client.post(base, json={"model": model, "input": ["arena owner check"]})
            response.raise_for_status()
            data = response.json()["data"][0]["embedding"]
        result["provider_reachable"] = True
        result["dimension"] = len(data)
    except Exception as exc:
        result["provider_reachable"] = False
        result["error"] = str(exc)[:300]
    return result


def main() -> dict:
    report: dict = {}
    for name, probe in (
        ("hardware", probe_hardware),
        ("os_control_validation", probe_os_control),
        ("display_topology", probe_display),
        ("accessibility", probe_accessibility),
        ("inference_provider", probe_inference),
        ("embeddings", probe_embeddings),
    ):
        try:
            report[name] = probe()
        except Exception as exc:
            report[name] = {"error": f"probe crashed: {exc}"}
    report["next_steps_hint"] = {
        "if_lm_studio_offline": "Start LM Studio → load Qwen2.5-14B-Instruct Q4 → enable the local server (default http://127.0.0.1:1234) → re-run this check.",
        "if_accessibility_unavailable": "Windows: UIA is built-in. Linux: sudo apt install python3-atspi && ensure AT-SPI dbus is running.",
        "if_display_unavailable": "Headless session: run from a real desktop session (RDP/console), not a service context.",
    }
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, default=str))
