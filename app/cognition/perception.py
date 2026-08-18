"""Perception & Observation Collector Layer.

Separates Tool Execution (ExecutionResult) from Environmental Observations (WorldModel).
Tool execution functions execute tool commands and return ExecutionResult data without directly writing
observations into WorldModel. The Perception Layer (ObservationCollector) receives ExecutionResults,
performs real environmental state probes, and ingests EnvironmentalObservation records into WorldModel.
"""

from __future__ import annotations
import os
import psutil
from typing import Dict, Any, List, Optional
from app.cognition.world_model import WorldModel, Observation
from app.utils.logger import app_logger

class ObservationCollector:
    """
    Perception & Environmental Observation Ingestion Engine.
    Receives ExecutionResult payloads from capability resolvers/MasterAgent, collects raw execution
    facts, performs real environmental topology probes, and ingests structured EnvironmentalObservations
    into WorldModel prior to Goal Verification.
    """

    @classmethod
    def collect_and_ingest_observations(
        cls,
        proposal: Any,
        execution_result: Any,
        world_model: Optional[WorldModel] = None,
        event_bus: Optional[Any] = None
    ) -> List[Observation]:
        """
        Ingests execution facts and environmental observations from an ExecutionResult into WorldModel.
        """
        if not world_model:
            from app.config import settings
            world_model = WorldModel(str(settings.DB_PATH))

        ingested_observations: List[Observation] = []
        action_type = getattr(proposal, "action_type", str(proposal)).lower().strip()
        payload = getattr(proposal, "payload", {}) if hasattr(proposal, "payload") else {}
        
        # Support dict or ExecutionResult object
        if hasattr(execution_result, "execution_facts"):
            execution_facts = getattr(execution_result, "execution_facts", [])
            raw_output = getattr(execution_result, "outputs", {})
            exec_success = getattr(execution_result, "success", False)
        elif isinstance(execution_result, dict):
            execution_facts = execution_result.get("execution_facts", [])
            raw_output = execution_result.get("raw_output", {})
            exec_success = bool(execution_result.get("success", False))
        else:
            execution_facts = []
            raw_output = {}
            exec_success = False
        for fact in execution_facts:
            try:
                if fact.get("entity_type") and fact.get("attributes"):
                    world_model.upsert_entity(
                        name=fact.get("subject", "entity"),
                        entity_type=fact["entity_type"],
                        attributes=fact["attributes"]
                    )

                obs = Observation(
                    id=f"obs_exec_{os.urandom(4).hex()}",
                    subject=fact.get("subject", "system"),
                    predicate=fact.get("predicate", "action_execution"),
                    value=fact.get("value", "executed"),
                    source=fact.get("source", "execution_result"),
                    confidence=fact.get("confidence", 0.5),
                    observation_type="self_reported"
                )
                world_model.observe(obs)
                ingested_observations.append(obs)
            except Exception as e:
                app_logger.warning(f"ObservationCollector: Could not ingest execution fact: {e}")

        # 2. Real Environmental State Probes (Perception grounding)
        if action_type in ["open_application", "launch_app"]:
            app_name = (payload.get("app_name") or payload.get("app") or payload.get("query") or "app").lower().strip()

            # Process Probe: Check if process is running in host OS
            process_running = False
            try:
                for proc in psutil.process_iter(['name']):
                    try:
                        p_name = proc.info['name'].lower() if proc.info['name'] else ""
                        if app_name in p_name or p_name in app_name:
                            process_running = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            except Exception as e:
                app_logger.warning(f"ObservationCollector process probe warning for '{app_name}': {e}")

            # P0 Fix: Process probe strictly establishes 'running' or 'not_running' for direct environmental state.
            # "Launch command succeeded" belongs strictly to self_reported execution facts.
            real_status = "running" if process_running else "not_running"

            world_model.upsert_entity(
                name=app_name,
                entity_type="process",
                attributes={"status": real_status, "source": "os_process_probe", "observation_type": "direct"}
            )
            obs = Observation(
                id=f"obs_env_proc_{os.urandom(4).hex()}",
                subject=app_name,
                predicate="status",
                value=real_status,
                source="os_process_probe",
                confidence=1.0,
                observation_type="direct"
            )
            world_model.observe(obs)
            ingested_observations.append(obs)

        elif action_type == "search_files":
            raw_output = execution_result.get("raw_output", {}) if isinstance(execution_result, dict) else getattr(execution_result, "outputs", {})
            matched = raw_output.get("matched_files", []) if isinstance(raw_output, dict) else []
            has_fs_fact = any(f.get("subject") == "filesystem" and f.get("predicate") == "file_path" for f in execution_facts)

            if matched and isinstance(matched, list):
                first_file = matched[0]
                if isinstance(first_file, dict) and first_file.get("file_path"):
                    world_model.upsert_entity(
                        name=first_file.get("file_name", "file"),
                        entity_type="file",
                        attributes={"file_path": first_file["file_path"], "status": "identified"}
                    )
                    obs = Observation(
                        id=f"obs_env_fs_{os.urandom(4).hex()}",
                        subject="filesystem",
                        predicate="file_path",
                        value=first_file["file_path"],
                        source="filesystem_probe",
                        confidence=1.0,
                        observation_type="direct"
                    )
                    world_model.observe(obs)
                    ingested_observations.append(obs)
            elif not has_fs_fact and raw_output.get("result_found") is False:
                obs = Observation(
                    id=f"obs_env_fs_{os.urandom(4).hex()}",
                    subject="filesystem",
                    predicate="file_path",
                    value="not_found",
                    source="filesystem_probe",
                    confidence=1.0,
                    observation_type="direct"
                )
                world_model.observe(obs)
                ingested_observations.append(obs)

        if hasattr(execution_result, "observations") and isinstance(execution_result.observations, list):
            execution_result.observations.extend(ingested_observations)

        return ingested_observations
