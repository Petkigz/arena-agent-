"""Perception & Observation Collector Layer.

Separates Tool Execution (ExecutionResult) from Environmental Observations (WorldModel).
Tool execution functions execute tool commands and return ExecutionResult data without directly writing
observations into WorldModel. The Perception Layer (ObservationCollector) receives ExecutionResults,
performs real environmental state probes, and ingests EnvironmentalObservation records into WorldModel.

Phase 1: Uses canonical SourceType enum for all observation sources.
"""

from __future__ import annotations
import os
import psutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.cognition.world_model import WorldModel, Observation
from app.cognition.source_types import SourceType
from app.utils.logger import app_logger
from app.cognition.execution_control import run_cancellable_subprocess


class ObservationCollector:
    """
    Perception & Environmental Observation Ingestion Engine.
    Receives ExecutionResult payloads from capability resolvers/MasterAgent, collects raw execution
    facts, performs real environmental topology probes, and ingests structured EnvironmentalObservations
    into WorldModel prior to Goal Verification.
    """

    @classmethod
    def _make_obs(cls, subject: str, predicate: str, value: Any, source: str,
                  confidence: float = 1.0, observation_type: str = "direct") -> Observation:
        """Helper to create a structured Observation with a unique id."""
        return Observation(
            id=f"obs_{source[:8]}_{os.urandom(4).hex()}",
            subject=subject,
            predicate=predicate,
            value=value,
            source=source,
            confidence=confidence,
            observation_type=observation_type
        )

    @classmethod
    def _extract_raw_output(cls, execution_result: Any) -> Dict[str, Any]:
        """Extract raw_output dict from ExecutionResult or dict."""
        if isinstance(execution_result, dict):
            return execution_result.get("raw_output", {})
        return getattr(execution_result, "outputs", {}) or {}

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

        # 1. Execution facts are NOT ingested into WorldModel.
        #    They belong in ExecutionTrace (preserved in ExecutionResult.execution_facts
        #    and capture_observed_world_state().execution_trace), NOT in WorldModel.
        #    WorldModel entities and observations are established exclusively by
        #    capability-specific environmental probes below.

        # 2. Capability-Specific Environmental Observation Strategies
        # Each strategy independently probes the environment AFTER execution.
        # Execution success is NOT used as evidence — only direct environmental probes.

        if action_type in ["open_application", "launch_app"]:
            cls._observe_open_application(payload, world_model, ingested_observations)

        elif action_type == "search_files":
            cls._observe_search_files(execution_result, raw_output,
                                      world_model, ingested_observations)

        elif action_type == "web_search":
            cls._observe_web_search(payload, raw_output, world_model, ingested_observations)

        elif action_type == "screen_capture":
            cls._observe_screen_capture(raw_output, world_model, ingested_observations)

        elif action_type in ["phone_command", "make_phone_call", "send_sms"]:
            cls._observe_phone_command(payload, raw_output, world_model, ingested_observations)

        elif action_type == "run_command":
            cls._observe_run_command(payload, world_model, ingested_observations)

        elif action_type in ["investigate", "diagnostic"]:
            cls._observe_diagnostic(payload, raw_output, world_model, ingested_observations)

        if hasattr(execution_result, "observations") and isinstance(execution_result.observations, list):
            execution_result.observations.extend(ingested_observations)

        return ingested_observations

    # ── Capability-Specific Observation Strategies ────────────────────────

    @classmethod
    def _observe_open_application(cls, payload: Dict, world_model: WorldModel,
                                   ingested: List[Observation]) -> None:
        """Process probe: strictly establishes running or not_running."""
        app_name = (payload.get("app_name") or payload.get("app") or payload.get("query") or "app").lower().strip()

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

        real_status = "running" if process_running else "not_running"

        world_model.upsert_entity(
            name=app_name,
            entity_type="process",
            attributes={"status": real_status, "source": "os_process_probe", "observation_type": "direct"}
        )
        obs = cls._make_obs(
            subject=app_name, predicate="status", value=real_status,
            source=SourceType.OS_PROCESS_PROBE, confidence=1.0, observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

    @classmethod
    def _observe_search_files(cls, execution_result: Any,
                               raw_output: Dict, world_model: WorldModel,
                               ingested: List[Observation]) -> None:
        """Filesystem probe: observes first match and complete result set.

        The environmental probe owns the answer based solely on the actual
        result set — execution facts do not influence observation generation.
        """
        raw_out = cls._extract_raw_output(execution_result)
        matched = raw_out.get("matched_files", []) if isinstance(raw_out, dict) else []
        ts = datetime.now(timezone.utc).isoformat()

        if matched and isinstance(matched, list):
            # First-result compatibility observation
            first_file = matched[0]
            if isinstance(first_file, dict) and first_file.get("file_path"):
                world_model.upsert_entity(
                    name=first_file.get("file_name", "file"),
                    entity_type="file",
                    attributes={"file_path": first_file["file_path"], "status": "identified"}
                )
                obs = cls._make_obs(
                    subject="filesystem", predicate="file_path",
                    value=first_file["file_path"],
                    source=SourceType.FILESYSTEM_PROBE, confidence=1.0, observation_type="direct"
                )
                world_model.observe(obs)
                ingested.append(obs)

            # Complete result-set observation
            seen_paths = set()
            result_items = []
            for i, f in enumerate(matched):
                if isinstance(f, dict) and f.get("file_path"):
                    fp = f["file_path"]
                    if fp not in seen_paths:
                        seen_paths.add(fp)
                        result_items.append({
                            "file_name": f.get("file_name", ""),
                            "file_path": fp,
                            "size_bytes": f.get("size_bytes", 0),
                            "extension": f.get("extension", ""),
                            "rank": i + 1
                        })
                    # Add entity for each result
                    world_model.upsert_entity(
                        name=f.get("file_name", "file"),
                        entity_type="file",
                        attributes={"file_path": fp, "status": "identified",
                                    "source": "filesystem_probe", "observation_type": "direct"}
                    )

            result_set = {
                "query": raw_out.get("query", ""),
                "count": len(result_items),
                "items": result_items,
                "timestamp": ts,
                "complete": not raw_out.get("truncated", False),
                "limit": raw_out.get("max_results", 5),
                "status": "observed"
            }
            obs_set = cls._make_obs(
                subject="filesystem", predicate="search_result_set",
                value=result_set, source=SourceType.FILESYSTEM_PROBE,
                confidence=1.0, observation_type="direct"
            )
            world_model.observe(obs_set)
            ingested.append(obs_set)

        elif raw_out.get("result_found") is False:
            # Explicit empty result set — only when result_found is explicitly False
            result_set = {
                "query": raw_out.get("query", ""),
                "count": 0,
                "items": [],
                "timestamp": ts,
                "complete": True,
                "limit": raw_out.get("max_results", 5),
                "status": "observed"
            }
            obs_nf = cls._make_obs(
                subject="filesystem", predicate="file_path",
                value="not_found", source=SourceType.FILESYSTEM_PROBE,
                confidence=1.0, observation_type="direct"
            )
            world_model.observe(obs_nf)
            ingested.append(obs_nf)

            obs_set = cls._make_obs(
                subject="filesystem", predicate="search_result_set",
                value=result_set, source=SourceType.FILESYSTEM_PROBE,
                confidence=1.0, observation_type="direct"
            )
            world_model.observe(obs_set)
            ingested.append(obs_set)

    @classmethod
    def _observe_web_search(cls, payload: Dict, raw_output: Dict,
                             world_model: WorldModel, ingested: List[Observation]) -> None:
        """
        Fresh independent web search probe — execution output is not evidence.
        Extracts actual result URLs and titles, validates query correspondence.
        """
        query = payload.get("query_term") or payload.get("query") or ""
        results = []

        if query:
            try:
                import urllib.request
                import urllib.parse
                import re

                search_url = f"https://www.google.com/search?q={urllib.parse.quote(str(query))}"
                req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode("utf-8", errors="replace")

                    # Extract search result links — Google wraps results in <a href="/url?q=ACTUAL_URL&...">
                    # Pattern: href="/url?q=<encoded_url>&sa=...
                    url_pattern = re.compile(r'href="/url\?q=(https?://[^&"]+)&amp;sa=')
                    raw_urls = url_pattern.findall(body)

                    # Fallback: try direct href extraction for non-Google responses
                    if not raw_urls:
                        direct_pattern = re.compile(r'href="(https?://(?!www\.google\.|google\.|accounts\.google|play\.google)[^"]+)"')
                        raw_urls = direct_pattern.findall(body)

                    # Extract titles from <h3> tags (Google's result title markup)
                    title_pattern = re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL)
                    raw_titles = title_pattern.findall(body)
                    # Strip HTML tags from titles
                    clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in raw_titles[:10]]

                    # Filter and deduplicate URLs (skip Google-owned domains)
                    google_domains = {"google.com", "google.co", "gstatic.com", "ggpht.com",
                                      "youtube.com", "accounts.google"}
                    seen = set()
                    for url in raw_urls:
                        try:
                            domain = urllib.parse.urlparse(url).netloc.lower()
                            if not any(gd in domain for gd in google_domains) and url not in seen:
                                seen.add(url)
                                title = clean_titles[len(results)] if len(results) < len(clean_titles) else ""
                                results.append({"url": url, "title": title})
                        except Exception:
                            continue
                        if len(results) >= 10:
                            break

            except Exception as e:
                app_logger.warning(f"Web search probe failed for '{query}': {e}")

        # Query relevance: check if result titles/URLs contain query terms
        query_terms = set(str(query).lower().split())
        relevance_hits = 0
        if results and query_terms:
            for r in results:
                text = f"{r.get('title', '')} {r.get('url', '')}".lower()
                if any(term in text for term in query_terms if len(term) > 2):
                    relevance_hits += 1

        results_found = len(results) > 0
        obs_value = {
            "query": query,
            "results_found": results_found,
            "result_count": len(results),
            "results": results[:10],
            "query_relevance_hits": relevance_hits,
            "timestamp": datetime.now(timezone.utc).isoformat()
        } if results_found else {
            "query": query,
            "results_found": False,
            "result_count": 0,
            "results": [],
            "query_relevance_hits": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        confidence = 1.0 if results_found else 0.0
        obs = cls._make_obs(
            subject="web_search", predicate="search_results_retrieved",
            value=obs_value, source=SourceType.WEB_SEARCH_PROBE,
            confidence=confidence, observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

        if results_found:
            world_model.upsert_entity(
                name=f"web_search:{query[:40]}",
                entity_type="search_result",
                attributes={"status": "results_found", "result_count": len(results),
                            "query_relevance_hits": relevance_hits,
                            "source": "web_search_probe", "observation_type": "direct"}
            )

    @classmethod
    def _observe_screen_capture(cls, raw_output: Dict, world_model: WorldModel,
                                 ingested: List[Observation]) -> None:
        """Independent artifact verification: check the screenshot file exists and is valid."""
        raw_out = raw_output if isinstance(raw_output, dict) else {}
        cap_res = raw_out.get("cap_res", {})
        file_path = cap_res.get("file_path", "") if isinstance(cap_res, dict) else ""
        file_name = cap_res.get("file_name", "") if isinstance(cap_res, dict) else ""

        artifact_valid = False
        artifact_reason = "no_file_path_provided"

        if file_path:
            try:
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 0:
                        # Try Pillow validation if available
                        try:
                            from PIL import Image
                            with Image.open(file_path) as img:
                                img.verify()
                            artifact_valid = True
                            artifact_reason = "pillow_verified"
                        except ImportError:
                            # No Pillow — accept non-empty file as best effort
                            artifact_valid = True
                            artifact_reason = "file_exists_nonempty"
                        except Exception:
                            artifact_reason = "pillow_verify_failed"
                    else:
                        artifact_reason = "file_empty"
                else:
                    artifact_reason = "file_not_found"
            except Exception as e:
                artifact_reason = f"probe_error: {e}"

        obs = cls._make_obs(
            subject="screen_capture", predicate="screen_capture_saved",
            value="true" if artifact_valid else "false",
            source=SourceType.SCREEN_CAPTURE_FILE_PROBE,
            confidence=1.0 if artifact_valid else 0.0,
            observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

        if artifact_valid:
            world_model.upsert_entity(
                name=file_name or "screenshot",
                entity_type="image_artifact",
                attributes={"file_path": file_path, "status": "saved",
                            "validation": artifact_reason,
                            "source": "screen_capture_file_probe", "observation_type": "direct"}
            )

            # Vision loop OBSERVE step: understand the screen CONTENT, not just
            # confirm the file exists. Deterministic OCR-based observation so the
            # loop can reason about what is on screen (and GoalVerifier can use
            # actual observed content as evidence).
            try:
                from app.cognition.visual_observer import VisualObserver
                vobs = VisualObserver.observe_screenshot(file_path)
                content_obs = cls._make_obs(
                    subject="screen_capture", predicate="screen_content",
                    value=vobs.visible_text[:500] if vobs.has_content else "(no readable text observed)",
                    source=SourceType.SCREEN_CAPTURE_FILE_PROBE,
                    confidence=1.0 if vobs.has_content else 0.5,
                    observation_type="direct"
                )
                world_model.observe(content_obs)
                ingested.append(content_obs)
            except Exception as e:
                app_logger.warning(f"Visual content observation failed (non-fatal): {e}")

    @classmethod
    def _observe_phone_command(cls, payload: Dict, raw_output: Dict,
                                world_model: WorldModel, ingested: List[Observation]) -> None:
        """Action-specific ADB state probes. SMS/tap/camera remain UNKNOWN."""
        phone_query = (payload.get("query") or payload.get("command") or
                       payload.get("action") or "").lower()

        # Battery status probe — measurable postcondition
        if any(k in phone_query for k in ["battery", "charge", "power", "level"]):
            try:
                result = run_cancellable_subprocess(
                    ["adb", "shell", "dumpsys", "battery"],
                    capture_output=True, text=True, timeout=10
                )
                battery_output = result.stdout.strip()
                if result.returncode == 0 and battery_output:
                    level = "unknown"
                    for line in battery_output.splitlines():
                        if "level:" in line.lower():
                            level = line.split(":")[-1].strip()
                            break
                    obs = cls._make_obs(
                        subject="phone", predicate="battery_status",
                        value={"level": level, "raw": battery_output[:200]},
                        source=SourceType.ADB_BATTERY_PROBE, confidence=1.0, observation_type="direct"
                    )
                else:
                    obs = cls._make_obs(
                        subject="phone", predicate="battery_status",
                        value="probe_failed", source=SourceType.ADB_BATTERY_PROBE,
                        confidence=0.0, observation_type="direct"
                    )
            except Exception:
                obs = cls._make_obs(
                    subject="phone", predicate="battery_status",
                    value="adb_unavailable", source=SourceType.ADB_BATTERY_PROBE,
                    confidence=0.0, observation_type="direct"
                )
            world_model.observe(obs)
            ingested.append(obs)
            return

        # Phone call state probe — check telephony registry
        if any(k in phone_query for k in ["call", "dial"]) or "call" in str(payload.get("action_type", "")):
            try:
                result = run_cancellable_subprocess(
                    ["adb", "shell", "dumpsys", "telephony.registry"],
                    capture_output=True, text=True, timeout=10
                )
                telephony_output = result.stdout.strip()
                call_state = "unknown"
                if result.returncode == 0:
                    for line in telephony_output.splitlines():
                        if "mCallState" in line or "mForegroundCallState" in line:
                            call_state = line.split("=")[-1].strip() if "=" in line else line.strip()
                            break
                    obs = cls._make_obs(
                        subject="phone", predicate="call_state",
                        value={"state": call_state, "raw": telephony_output[:200]},
                        source=SourceType.ADB_TELEPHONY_PROBE, confidence=1.0, observation_type="direct"
                    )
                else:
                    obs = cls._make_obs(
                        subject="phone", predicate="call_state",
                        value="probe_failed", source=SourceType.ADB_TELEPHONY_PROBE,
                        confidence=0.0, observation_type="direct"
                    )
            except Exception:
                obs = cls._make_obs(
                    subject="phone", predicate="call_state",
                    value="adb_unavailable", source=SourceType.ADB_TELEPHONY_PROBE,
                    confidence=0.0, observation_type="direct"
                )
            world_model.observe(obs)
            ingested.append(obs)
            return

        # Android app launch probe — check foreground package
        if any(k in phone_query for k in ["open", "launch", "start"]):
            try:
                result = run_cancellable_subprocess(
                    ["adb", "shell", "dumpsys", "window", "displays"],
                    capture_output=True, text=True, timeout=10
                )
                window_output = result.stdout.strip()
                foreground_pkg = "unknown"
                if result.returncode == 0:
                    for line in window_output.splitlines():
                        if "mCurrentFocus" in line or "mFocusedApp" in line:
                            foreground_pkg = line.strip()
                            break
                    obs = cls._make_obs(
                        subject="phone", predicate="foreground_app",
                        value={"package": foreground_pkg},
                        source=SourceType.ADB_WINDOW_PROBE, confidence=1.0, observation_type="direct"
                    )
                else:
                    obs = cls._make_obs(
                        subject="phone", predicate="foreground_app",
                        value="probe_failed", source=SourceType.ADB_WINDOW_PROBE,
                        confidence=0.0, observation_type="direct"
                    )
            except Exception:
                obs = cls._make_obs(
                    subject="phone", predicate="foreground_app",
                    value="adb_unavailable", source=SourceType.ADB_WINDOW_PROBE,
                    confidence=0.0, observation_type="direct"
                )
            world_model.observe(obs)
            ingested.append(obs)
            return

        # Device availability probe (generic fallback)
        try:
            result = run_cancellable_subprocess(
                ["adb", "get-state"], capture_output=True, text=True, timeout=5
            )
            device_state = result.stdout.strip() if result.returncode == 0 else "offline"
        except Exception:
            device_state = "adb_unavailable"

        # SMS, tap, camera, and other actions have no reliable postcondition sensor.
        # Record explicit UNKNOWN rather than claiming success.
        obs = cls._make_obs(
            subject="phone", predicate="adb_command_postcondition",
            value="unknown_no_postcondition_sensor",
            source=SourceType.ADB_DEVICE_PROBE, confidence=0.0, observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

    @classmethod
    def _observe_run_command(cls, payload: Dict, world_model: WorldModel,
                              ingested: List[Observation]) -> None:
        """
        Generic command observation: requires a declared postcondition probe.
        Exit code alone never verifies a goal.
        """
        verification = payload.get("verification", {})
        if not verification:
            # Support compatibility aliases
            if payload.get("expected_file"):
                verification = {"type": "file_exists", "path": payload["expected_file"]}
            elif payload.get("output_path"):
                verification = {"type": "file_exists", "path": payload["output_path"]}
            elif payload.get("expected_process"):
                verification = {"type": "process_running", "name": payload["expected_process"]}

        if not verification:
            obs = cls._make_obs(
                subject="run_command", predicate="command_postcondition_satisfied",
                value="unknown_no_postcondition_declared",
                source=SourceType.RUN_COMMAND_PROBE, confidence=0.0, observation_type="direct"
            )
            world_model.observe(obs)
            ingested.append(obs)
            return

        probe_type = verification.get("type", "")
        probe_passed = False

        if probe_type == "file_exists":
            check_path = verification.get("path", "")
            if check_path and os.path.isfile(check_path):
                probe_passed = True
        elif probe_type == "process_running":
            proc_name = (verification.get("name") or verification.get("process") or "").lower()
            if proc_name:
                try:
                    for proc in psutil.process_iter(['name']):
                        try:
                            if proc_name in (proc.info['name'] or "").lower():
                                probe_passed = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception:
                    pass
        elif probe_type == "tcp_port_open":
            port = verification.get("port")
            host = verification.get("host", "127.0.0.1")
            if port:
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    result = s.connect_ex((host, int(port)))
                    s.close()
                    probe_passed = (result == 0)
                except Exception:
                    pass

        obs = cls._make_obs(
            subject="run_command", predicate="command_postcondition_satisfied",
            value="true" if probe_passed else "false",
            source=SourceType.RUN_COMMAND_PROBE,
            confidence=1.0 if probe_passed else 0.0,
            observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

    @classmethod
    def _observe_diagnostic(cls, payload: Dict, raw_output: Dict,
                             world_model: WorldModel, ingested: List[Observation]) -> None:
        """Independent diagnostic probe: reruns bounded filesystem and hardware checks."""
        probe_query = payload.get("query") or ""
        evidence_gathered = False
        details = {}

        # Independent filesystem probe
        if probe_query:
            try:
                from app.tools.universal_filesystem import UniversalFilesystem
                matched = UniversalFilesystem.search_filesystem(probe_query, max_results=3)
                details["filesystem_matches"] = len(matched) if matched else 0
                if matched:
                    evidence_gathered = True
            except Exception as e:
                details["filesystem_error"] = str(e)[:100]

        # Independent hardware probe
        try:
            details["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            details["ram_percent"] = mem.percent
            details["ram_available_mb"] = round(mem.available / (1024 * 1024))
            evidence_gathered = True
        except Exception as e:
            details["hardware_error"] = str(e)[:100]

        obs = cls._make_obs(
            subject="diagnostic", predicate="diagnostic_evidence_gathered",
            value="true" if evidence_gathered else "false",
            source=SourceType.DIAGNOSTIC_SYSTEM_PROBE,
            confidence=1.0 if evidence_gathered else 0.0,
            observation_type="direct"
        )
        world_model.observe(obs)
        ingested.append(obs)

        if details:
            obs_details = cls._make_obs(
                subject="diagnostic", predicate="system_state",
                value=details, source=SourceType.DIAGNOSTIC_SYSTEM_PROBE,
                confidence=1.0 if evidence_gathered else 0.0,
                observation_type="direct"
            )
            world_model.observe(obs_details)
            ingested.append(obs_details)
