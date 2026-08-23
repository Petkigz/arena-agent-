"""Verified dynamic capability synthesis.

CapabilityFactory is a thin compatibility facade over SelfEvolvingAgent. It
must never write or register model-generated code until sandbox verification
passes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.logger import app_logger


class CapabilityFactory:
    """Synthesize, sandbox-test, and register a dynamic capability."""

    @classmethod
    def synthesize_capability(
        cls,
        capability_name: str,
        description: str,
        sample_params: Optional[Dict[str, Any]] = None,
        world_model: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if not capability_name or not capability_name.strip():
            return {"success": False, "verified": False, "error": "Capability name is required"}
        if not description or not description.strip():
            return {"success": False, "verified": False, "error": "Capability description is required"}

        from app.agents.self_evolving_agent import SelfEvolvingAgent

        objective = description.strip()
        if sample_params:
            objective += f"\nExpected sample parameters: {sample_params}"
        result = SelfEvolvingAgent.synthesize_and_hotload_tool(
            task_objective=objective,
            tool_name_query=capability_name,
        )
        if not result.get("success") or not result.get("verified"):
            return {
                **result,
                "success": False,
                "verified": False,
                "capability_name": capability_name,
            }

        safe_name = SelfEvolvingAgent._safe_name(capability_name)
        if world_model is not None:
            try:
                world_model.add_entity(
                    entity_id=f"cap_{safe_name}",
                    entity_type="capability",
                    name=capability_name,
                    properties={
                        "description": description,
                        "verified": True,
                        "module_file": result.get("tool_module_name"),
                    },
                )
            except Exception as exc:
                app_logger.warning(f"Verified capability world-model registration failed: {exc}")

        return {
            **result,
            "success": True,
            "verified": True,
            "capability_name": capability_name,
            "description": description,
        }
