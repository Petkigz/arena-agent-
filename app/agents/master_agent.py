import os
import re
import json
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.llm import llm_client, ModelCompletionUnavailable, require_real_completion
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_monitor import HardwareMonitor

# Tool modules are imported inside the branch that invokes them.  Importing the
# orchestrator must not require every optional tool dependency to be installed.
from app.memory.human_nature_engine import HumanNatureEngine
from app.memory.coworker_brain import CoworkerBrain
from app.cognition.reasoning_cycle import ReasoningCycle, ReasoningAction, ReasoningDecision
from app.cognition.belief_engine import BeliefEngine
from app.cognition.execution_result import ExecutionResult, ExecutionStatus

class MasterAgentOrchestrator:
    """
    Unified Master Agent & All-in-One Autonomous Router.
    Merates ALL domain tools (OS control, app launching, file search, vision, web research,
    cybersecurity/pentesting, OpSec, data analysis, sandboxes, and taught skills) into a single
    intelligent human-like agent.
    """

    @classmethod
    def execute_proposal(
        cls,
        proposal: Any,
        user_text: str,
        complexity: str = "fast",
        world_model: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes a specific ActionProposal directly through capability resolvers,
        producing a structured ExecutionResult carrying raw execution facts and outputs.
        Uses the provided authoritative world_model instance if supplied.
        Does NOT directly write WorldModel observations; environmental observations are ingested
        downstream via the Perception Layer (ObservationCollector).
        """
        action_type = getattr(proposal, "action_type", str(proposal)).lower().strip()
        proposal_id = getattr(proposal, "proposal_id", f"prop_{os.urandom(4).hex()}")
        payload = getattr(proposal, "payload", {}) if hasattr(proposal, "payload") else {}
        executed_actions = []
        execution_facts: List[Dict[str, Any]] = []
        raw_output_data: Dict[str, Any] = {}
        execution_success = True

        if action_type in ["open_application", "launch_app"]:
            from app.tools.app_inventory import SystemAppInventory

            app_name = payload.get("app_name") or payload.get("app") or payload.get("app_query") or payload.get("query")
            if not app_name:
                match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', user_text.lower())
                app_name = match.group(1).strip() if match else "explorer"
            res = SystemAppInventory.launch_any_app(app_name)
            raw_output_data["launch_res"] = res
            if res.get("success"):
                executed_actions.append(f"Launched application '{res.get('app_name', app_name).title()}' on your PC.")
                execution_facts.append({
                    "subject": res.get("app_name", app_name).lower(),
                    "predicate": "launch_command",
                    "value": "succeeded",
                    "source": "system_app_inventory"
                })
            else:
                execution_success = False
                executed_actions.append(f"Failed to launch application '{app_name}': {res.get('error', 'Launch error')}")
                execution_facts.append({
                    "subject": app_name.lower(),
                    "predicate": "launch_command",
                    "value": "failed",
                    "source": "system_app_inventory"
                })

        elif action_type == "web_search":
            from app.tools.desktop_control import DesktopControl

            query_term = payload.get("query_term") or payload.get("query") or ""
            if not query_term:
                # Fall back to deterministic extraction before using the raw text.
                try:
                    from app.cognition.tool_matcher import _SEARCH_AFTER_RE
                    import re as _re
                    cleaned = _re.sub(r"(?:can\s+you\s+)?(?:open|launch|start|use)\s+\w+\s+(?:and|then|to)\s+", "", user_text, flags=_re.I)
                    search = _SEARCH_AFTER_RE.search(cleaned)
                    if search:
                        query_term = search.group(1).strip().rstrip("?.!")
                        query_term = _re.sub(r"^\s*(?:for\s+)?(?:me\s+|my\s+)", "", query_term, flags=_re.I).strip()
                except Exception:
                    pass
            if not query_term:
                query_term = user_text  # honest: couldn't extract a clean query
            url = f"https://www.youtube.com/results?search_query={str(query_term).replace(' ', '+')}" if "youtube" in str(query_term).lower() or "youtube" in user_text.lower() else f"https://www.google.com/search?q={str(query_term).replace(' ', '+')}"
            # Use the OS default browser — webbrowser.open() picks whatever
            # the owner has configured (Chrome, Edge, Firefox, Brave, ...).
            # Never hardcode a specific browser.
            d_res = DesktopControl.open_url(url)
            raw_output_data["url"] = url
            raw_output_data["query_term"] = query_term
            if d_res.get("success", False):
                executed_actions.append(f"Opened default browser and searched for '{query_term}'.")
                execution_facts.append({
                    "subject": "web_search",
                    "predicate": "search_results",
                    "value": url,
                    "source": "web_researcher"
                })
            else:
                execution_success = False
                executed_actions.append(f"Failed to open web browser for search '{query_term}'.")

        elif action_type == "search_files":
            from app.tools.universal_filesystem import UniversalFilesystem

            search_query = payload.get("query") or payload.get("file_name") or payload.get("search_term") or user_text

            # Determine search limit: normal=5, "all" or all_matches=up to 1000
            search_limit = 5
            all_matches = payload.get("all_matches", False)
            explicit_max = payload.get("max_results")

            if explicit_max is not None:
                search_limit = max(1, min(int(explicit_max), 1000))
            elif all_matches or "all" in str(search_query).lower().split():
                search_limit = 1000

            matched = UniversalFilesystem.search_filesystem(search_query, max_results=search_limit + 1)
            truncated = len(matched) > search_limit
            if truncated:
                matched = matched[:search_limit]
            result_found = bool(matched)
            raw_output_data["matched_files"] = matched
            raw_output_data["result_found"] = result_found
            raw_output_data["query"] = search_query
            raw_output_data["max_results"] = search_limit
            raw_output_data["truncated"] = truncated

            if result_found:
                executed_actions.append(f"Found local file '{matched[0]['file_name']}' at {matched[0]['file_path']}.")
                execution_facts.append({
                    "subject": "filesystem",
                    "predicate": "file_path",
                    "value": matched[0]['file_path'],
                    "source": "universal_filesystem"
                })
                execution_facts.append({
                    "subject": matched[0]['file_name'],
                    "predicate": "status",
                    "value": "identified",
                    "source": "universal_filesystem",
                    "entity_type": "file",
                    "attributes": {"file_path": matched[0]['file_path']}
                })
                # Add execution facts for additional results (beyond first)
                for extra_file in matched[1:]:
                    if isinstance(extra_file, dict) and extra_file.get("file_path"):
                        execution_facts.append({
                            "subject": extra_file.get("file_name", "file"),
                            "predicate": "status",
                            "value": "identified",
                            "source": "universal_filesystem",
                            "entity_type": "file",
                            "attributes": {"file_path": extra_file["file_path"]}
                        })
                if len(matched) > 1:
                    executed_actions.append(f"({len(matched)} total matches found, limit={search_limit})")
            else:
                executed_actions.append(f"Searched local filesystem for '{search_query}' (no matching files found).")
                execution_facts.append({
                    "subject": "filesystem",
                    "predicate": "file_search_result",
                    "value": "no_matching_files_found",
                    "source": "universal_filesystem"
                })

        elif action_type in ["phone_command", "make_phone_call", "send_sms"]:
            from app.tools.android_adb_controller import AndroidADBController
            phone_query = payload.get("query") or payload.get("command") or payload.get("action") or user_text
            phone_lower = str(phone_query).lower()

            if "sms" in phone_lower or "text" in phone_lower or payload.get("sms_body"):
                num = payload.get("phone_number") or payload.get("number") or "555-0199"
                sms_msg = payload.get("sms_body") or payload.get("message") or phone_query
                adb_res = AndroidADBController.send_sms(num, str(sms_msg))
                if adb_res.get("success"):
                    executed_actions.append(f"Sent SMS text to {num} via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to send SMS to {num}: {adb_res.get('error', 'Device offline')}")

            elif "call" in phone_lower or "dial" in phone_lower or action_type == "make_phone_call":
                num = payload.get("phone_number") or payload.get("number")
                if not num:
                    digits = "".join(c for c in str(phone_query) if c.isdigit() or c in "+*#")
                    num = digits if len(digits) >= 3 else "555-0199"
                adb_res = AndroidADBController.make_phone_call(num)
                if adb_res.get("success"):
                    executed_actions.append(f"Initiated phone call to {num} via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to make phone call to {num}: {adb_res.get('error', 'Device offline')}")

            elif "photo" in phone_lower or "camera" in phone_lower:
                adb_res = AndroidADBController.take_camera_photo()
                if adb_res.get("success"):
                    executed_actions.append("Captured camera photo via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to capture camera photo: {adb_res.get('error', 'Device offline')}")

            elif "tap" in phone_lower and payload.get("x") is not None and payload.get("y") is not None:
                adb_res = AndroidADBController.tap_screen(int(payload["x"]), int(payload["y"]))
                if adb_res.get("success"):
                    executed_actions.append(f"Tapped screen coordinates ({payload['x']}, {payload['y']}) via Android ADB.")
                else:
                    execution_success = False
                    executed_actions.append("Failed to tap screen coordinates via ADB.")

            elif any(k in phone_lower for k in ["battery", "charge", "power", "level"]):
                adb_res = AndroidADBController.get_battery_status()
                if adb_res.get("success"):
                    executed_actions.append(adb_res.get("message", "Queried phone battery level via Android ADB."))
                else:
                    execution_success = False
                    executed_actions.append("Failed to query phone status via Android ADB.")

            elif any(k in phone_lower for k in ["open", "launch", "start"]) and any(app_k in phone_lower for app_k in ["whatsapp", "chrome", "settings", "camera", "youtube"]):
                pkg = "com.whatsapp" if "whatsapp" in phone_lower else ("com.android.chrome" if "chrome" in phone_lower else "com.android.settings")
                adb_res = AndroidADBController.launch_android_app(pkg)
                if adb_res.get("success"):
                    executed_actions.append(f"Launched Android app package '{pkg}' via ADB.")
                else:
                    execution_success = False
                    executed_actions.append(f"Failed to launch Android app '{pkg}': Device offline or package missing")

            else:
                # P0 Fix: Eliminates dangerous fallback that substituted battery status for unrecognized phone commands.
                # Returns explicit structured capability failure to trigger Plan B replanning.
                app_logger.warning(f"AndroidADBController: Unsupported phone_command query '{phone_query}'")
                return ExecutionResult(
                    proposal_id=proposal_id,
                    action_type=action_type,
                    execution_status=ExecutionStatus.FAILED,
                    attempted=True,
                    executed_actions=[],
                    assistant_reply=f"Capability execution failed: Unrecognized or unsupported phone command '{phone_query}'.",
                    error=f"Unsupported phone_command query '{phone_query}'",
                    outputs={"unsupported_capability": "unsupported_phone_command"}
                )

            if execution_success:
                execution_facts.append({
                    "subject": "phone",
                    "predicate": "adb_status",
                    "value": "succeeded",
                    "source": "android_adb"
                })

        elif action_type == "screen_capture":
            from app.tools.screen_capture import ScreenCaptureTool

            cap_res = ScreenCaptureTool.capture_screen()
            raw_output_data["cap_res"] = cap_res
            if cap_res.get("success"):
                executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")
                execution_facts.append({
                    "subject": "screen_capture",
                    "predicate": "screenshot",
                    "value": cap_res.get("file_name"),
                    "source": "screen_capture_tool"
                })
            else:
                execution_success = False
                executed_actions.append(f"Failed to capture desktop screen window: {cap_res.get('error', 'Capture error')}")

        elif action_type == "opsec_audit":
            from app.tools.opsec_manager import OpSecManagerTool

            audit_res = OpSecManagerTool.audit_digital_footprint("user@example.com")
            raw_output_data["audit_res"] = audit_res
            if audit_res.get("success", True):
                executed_actions.append(f"Audited OpSec footprint: {audit_res.get('total_exposures_found', 0)} findings.")
            else:
                execution_success = False
                executed_actions.append(f"OpSec audit failed: {audit_res.get('error', 'Audit failed')}")

        elif action_type == "daily_briefing":
            from app.tools.daily_briefing import DailyBriefingEngine

            brief_res = DailyBriefingEngine.generate_briefing(generate_audio=False)
            raw_output_data["brief_res"] = brief_res
            if brief_res.get("success", True):
                executed_actions.append("Generated Daily Executive Briefing.")
            else:
                execution_success = False
                executed_actions.append("Failed to generate Daily Executive Briefing.")

        elif action_type in ["investigate", "diagnostic"]:
            from app.tools.universal_filesystem import UniversalFilesystem

            probe_query = payload.get("query") or user_text
            matched_evidence = UniversalFilesystem.search_filesystem(probe_query, max_results=3)
            hw_stats = HardwareMonitor.get_hardware_stats()

            diag_details = []
            if matched_evidence:
                diag_details.append(f"Located {len(matched_evidence)} relevant file/log path(s): {matched_evidence[0]['file_path']}")
            diag_details.append(f"System status: CPU {hw_stats.get('cpu_used_percent', 0)}%, RAM {hw_stats.get('ram_used_percent', 0)}%")

            probe_summary = f"Gathered diagnostic evidence for '{probe_query[:40]}': " + "; ".join(diag_details)
            executed_actions.append(probe_summary)
            execution_facts.append({
                "subject": "diagnostic",
                "predicate": "evidence",
                "value": probe_summary,
                "source": "investigation_probe"
            })
            raw_output_data["probe_summary"] = probe_summary

        elif action_type in ["formulate_answer", "answer"]:
            executed_actions.append("Formulated direct conversational answer.")

        elif action_type == "workflow_execute":
            from app.tools.workflow_engine import WorkflowEngine

            wf_res = WorkflowEngine.execute_workflow(payload.get("workflow_name", "Task Workflow"), payload.get("steps", []))
            raw_output_data["wf_res"] = wf_res
            if wf_res.get("overall_success", True):
                executed_actions.append(f"Executed workflow '{wf_res.get('workflow_name')}'.")
            else:
                execution_success = False
                executed_actions.append(f"Workflow execution failed: '{wf_res.get('workflow_name')}'.")

        else:
            # Check ToolRegistry for dynamically registered capabilities
            try:
                from app.cognition.tool_registry import ToolRegistry
                tr = ToolRegistry()
                if action_type in tr._registry:
                    tr_res = tr.execute_registered_tool(action_type, payload)
                    raw_output_data["tr_res"] = tr_res
                    if tr_res.get("success"):
                        executed_actions.append(f"Executed registered tool '{action_type}'.")
                    else:
                        return ExecutionResult(
                            proposal_id=proposal_id,
                            action_type=action_type,
                            execution_status=ExecutionStatus.FAILED,
                            attempted=True,
                            executed_actions=[],
                            assistant_reply=f"Registered tool '{action_type}' execution failed: {tr_res.get('error')}",
                            error=tr_res.get("error"),
                            outputs={"unsupported_capability": action_type}
                        )
                else:
                    # CapabilityResolver: Unsupported capability proposal -> Structured Failure
                    app_logger.warning(f"CapabilityResolver: Proposal action_type '{action_type}' is unsupported.")
                    return ExecutionResult(
                        proposal_id=proposal_id,
                        action_type=action_type,
                        execution_status=ExecutionStatus.FAILED,
                        attempted=True,
                        executed_actions=[],
                        assistant_reply=f"Capability execution failed: Action proposal type '{action_type}' is unsupported by capability resolvers.",
                        error=f"Unsupported proposal action_type '{action_type}'",
                        outputs={"unsupported_capability": action_type}
                    )
            except Exception as e:
                from app.cognition.execution_control import ExecutionCancelled

                if isinstance(e, ExecutionCancelled):
                    raise
                app_logger.warning(f"CapabilityResolver lookup exception for '{action_type}': {e}")
                return ExecutionResult(
                    proposal_id=proposal_id,
                    action_type=action_type,
                    execution_status=ExecutionStatus.FAILED,
                    attempted=True,
                    executed_actions=[],
                    assistant_reply=f"Capability execution failed: Action proposal type '{action_type}' is unsupported.",
                    error=str(e),
                    outputs={"unsupported_capability": action_type}
                )

        system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=executed_actions)
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
        llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
        try:
            assistant_reply = require_real_completion(llm_res)
            HumanNatureEngine.assimilate_human_experience(user_text, assistant_reply)
        except ModelCompletionUnavailable:
            # Preserve real action facts without laundering offline diagnostic
            # text into conversation, social learning, or memory.
            assistant_reply = (
                " ".join(executed_actions)
                if executed_actions else
                "Capability execution finished without a model-generated summary."
            )

        status = ExecutionStatus.SUCCEEDED if execution_success else ExecutionStatus.FAILED
        return ExecutionResult(
            proposal_id=proposal_id,
            action_type=action_type,
            execution_status=status,
            attempted=True,
            executed_actions=executed_actions,
            assistant_reply=assistant_reply,
            execution_facts=execution_facts,
            outputs=raw_output_data,
            model_used=llm_res.get("model", "")
        )

    @classmethod
    def process_user_task(cls, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """
        Adapter route wrapping canonical CognitivePipeline -> CognitiveRuntime.
        Ensures backwards compatibility for legacy callers while routing all processing
        through the single authoritative cognitive cycle.
        """
        app_logger.info(f"MasterAgentOrchestrator adapter delegating '{user_text[:60]}' to CognitivePipeline...")
        from app.cognition.pipeline import CognitivePipeline
        return CognitivePipeline.process_request(user_text, complexity=complexity)
