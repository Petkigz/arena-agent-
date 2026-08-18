import os
import re
import json
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.llm import llm_client
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

from app.tools.app_inventory import SystemAppInventory
from app.tools.desktop_control import DesktopControl
from app.tools.universal_filesystem import UniversalFilesystem
from app.tools.screen_capture import ScreenCaptureTool
from app.tools.vision_analyzer import VisionAnalyzerTool
from app.tools.web_research import WebResearcher
from app.tools.youtube_learner import YouTubeLearner
from app.tools.universal_media_learner import UniversalMediaLearner
from app.tools.cybersecurity_brain import CybersecurityBrainTool
from app.tools.security_lab import SecurityLabTool
from app.tools.pentest_company_assistant import PentestCompanyAssistant
from app.tools.opsec_manager import OpSecManagerTool
from app.tools.data_analyzer import DataAnalysisEngine
from app.tools.disposable_sandbox import DisposableSandbox
from app.tools.skill_teaching_engine import SkillTeachingEngine
from app.tools.daily_briefing import DailyBriefingEngine
from app.tools.workflow_engine import WorkflowEngine
from app.memory.semantic_rag import SemanticRAGEngine
from app.memory.human_nature_engine import HumanNatureEngine
from app.memory.coworker_brain import CoworkerBrain
from app.cognition.reasoning_cycle import ReasoningCycle, ReasoningAction, ReasoningDecision
from app.cognition.belief_engine import BeliefEngine

class MasterAgentOrchestrator:
    """
    Unified Master Agent & All-in-One Autonomous Router.
    Merates ALL domain tools (OS control, app launching, file search, vision, web research,
    cybersecurity/pentesting, OpSec, data analysis, sandboxes, and taught skills) into a single
    intelligent human-like agent.
    """

    @classmethod
    def execute_proposal(cls, proposal: Any, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """
        P0 Fix: Executes a specific ActionProposal directly through capability resolver,
        ensuring that counterfactual-selected proposals are executed without re-routing.
        Normalized to check tool success flags before recording action records or WorldModel observations.
        """
        action_type = getattr(proposal, "action_type", str(proposal)).lower().strip()
        payload = getattr(proposal, "payload", {}) if hasattr(proposal, "payload") else {}
        executed_actions = []
        execution_success = True

        if action_type in ["open_application", "launch_app"]:
            app_name = payload.get("app_name") or payload.get("app") or payload.get("app_query") or payload.get("query")
            if not app_name:
                match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', user_text.lower())
                app_name = match.group(1).strip() if match else "explorer"
            res = SystemAppInventory.launch_any_app(app_name)
            if res.get("success"):
                executed_actions.append(f"Launched application '{res.get('app_name', app_name).title()}' on your PC.")
            else:
                execution_success = False
                executed_actions.append(f"Failed to launch application '{app_name}': {res.get('error', 'Launch error')}")

        elif action_type == "web_search":
            query_term = payload.get("query_term") or payload.get("query") or user_text
            url = f"https://www.youtube.com/results?search_query={str(query_term).replace(' ', '+')}" if "youtube" in str(query_term).lower() or "youtube" in user_text.lower() else f"https://www.google.com/search?q={str(query_term).replace(' ', '+')}"
            d_res = DesktopControl.launch_application("firefox")
            DesktopControl.open_url(url)
            if d_res.get("success", True):
                executed_actions.append(f"Opened web browser and launched search for '{query_term}'.")
                try:
                    from app.cognition.world_model import WorldModel, Observation
                    wm = WorldModel(str(settings.DB_PATH))
                    wm.observe(Observation(
                        id=f"obs_web_{os.urandom(4).hex()}", subject="web_search", predicate="search_results", value=url, source="web_researcher"
                    ))
                except Exception as e:
                    app_logger.warning(f"WorldModel web_search observation note: {e}")
            else:
                execution_success = False
                executed_actions.append(f"Failed to open web browser for search '{query_term}'.")

        elif action_type == "search_files":
            search_query = payload.get("query") or payload.get("file_name") or payload.get("search_term") or user_text
            matched = UniversalFilesystem.search_filesystem(search_query, max_results=5)
            if matched:
                executed_actions.append(f"Found local file '{matched[0]['file_name']}' at {matched[0]['file_path']}.")
                try:
                    from app.cognition.world_model import WorldModel, Observation
                    wm = WorldModel(str(settings.DB_PATH))
                    wm.upsert_entity(name=matched[0]['file_name'], entity_type="file", attributes={"file_path": matched[0]['file_path'], "status": "identified"})
                    wm.observe(Observation(
                        id=f"obs_fs_{os.urandom(4).hex()}", subject="filesystem", predicate="file_path", value=matched[0]['file_path'], source="universal_filesystem"
                    ))
                except Exception as e:
                    app_logger.warning(f"WorldModel search_files observation note: {e}")
            else:
                executed_actions.append(f"Searched local filesystem for '{search_query}' (no matching files found).")

        elif action_type == "phone_command":
            from app.tools.android_adb_controller import AndroidADBController
            bat_res = AndroidADBController.get_battery_status()
            if bat_res.get("success"):
                executed_actions.append(bat_res.get("message", "Executed ADB command successfully."))
                try:
                    from app.cognition.world_model import WorldModel, Observation
                    wm = WorldModel(str(settings.DB_PATH))
                    wm.observe(Observation(
                        id=f"obs_adb_{os.urandom(4).hex()}", subject="phone", predicate="adb_status", value="succeeded", source="android_adb"
                    ))
                except Exception as e:
                    app_logger.warning(f"WorldModel phone_command observation note: {e}")
            else:
                execution_success = False
                executed_actions.append(f"Failed to execute phone command: {bat_res.get('error', 'Device offline or ADB error')}")

        elif action_type == "screen_capture":
            cap_res = ScreenCaptureTool.capture_screen()
            if cap_res.get("success"):
                executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")
                try:
                    from app.cognition.world_model import WorldModel, Observation
                    wm = WorldModel(str(settings.DB_PATH))
                    wm.observe(Observation(
                        id=f"obs_screen_{os.urandom(4).hex()}", subject="screen_capture", predicate="screenshot", value=cap_res.get("file_name"), source="screen_capture_tool"
                    ))
                except Exception as e:
                    app_logger.warning(f"WorldModel screen_capture observation note: {e}")
            else:
                execution_success = False
                executed_actions.append(f"Failed to capture desktop screen window: {cap_res.get('error', 'Capture error')}")

        elif action_type == "opsec_audit":
            audit_res = OpSecManagerTool.audit_digital_footprint("user@example.com")
            if audit_res.get("success", True):
                executed_actions.append(f"Audited OpSec footprint: {audit_res.get('total_exposures_found', 0)} findings.")
            else:
                execution_success = False
                executed_actions.append(f"OpSec audit failed: {audit_res.get('error', 'Audit failed')}")

        elif action_type == "daily_briefing":
            brief_res = DailyBriefingEngine.generate_briefing(generate_audio=False)
            if brief_res.get("success", True):
                executed_actions.append("Generated Daily Executive Briefing.")
            else:
                execution_success = False
                executed_actions.append("Failed to generate Daily Executive Briefing.")

        elif action_type in ["investigate", "diagnostic"]:
            executed_actions.append(f"Executed diagnostic investigation probe for '{user_text[:50]}'.")
            try:
                from app.cognition.world_model import WorldModel, Observation
                wm = WorldModel(str(settings.DB_PATH))
                wm.observe(Observation(
                    id=f"obs_diag_{os.urandom(4).hex()}", subject="diagnostic", predicate="evidence", value=user_text[:50], source="investigation_probe"
                ))
            except Exception as e:
                app_logger.warning(f"WorldModel investigation observation note: {e}")

        elif action_type in ["formulate_answer", "answer"]:
            executed_actions.append("Formulated direct conversational answer.")

        elif action_type == "workflow_execute":
            wf_res = WorkflowEngine.execute_workflow(payload.get("workflow_name", "Task Workflow"), payload.get("steps", []))
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
                    if tr_res.get("success"):
                        executed_actions.append(f"Executed registered tool '{action_type}'.")
                    else:
                        return {
                            "success": False,
                            "user_text": user_text,
                            "assistant_reply": f"Registered tool '{action_type}' execution failed: {tr_res.get('error')}",
                            "executed_actions": [],
                            "unsupported_capability": action_type,
                            "error": tr_res.get("error")
                        }
                else:
                    # CapabilityResolver: Unsupported capability proposal -> Structured Failure
                    app_logger.warning(f"CapabilityResolver: Proposal action_type '{action_type}' is unsupported.")
                    return {
                        "success": False,
                        "user_text": user_text,
                        "assistant_reply": f"Capability execution failed: Action proposal type '{action_type}' is unsupported by capability resolvers.",
                        "executed_actions": [],
                        "unsupported_capability": action_type,
                        "error": f"Unsupported proposal action_type '{action_type}'"
                    }
            except Exception as e:
                app_logger.warning(f"CapabilityResolver lookup exception for '{action_type}': {e}")
                return {
                    "success": False,
                    "user_text": user_text,
                    "assistant_reply": f"Capability execution failed: Action proposal type '{action_type}' is unsupported.",
                    "executed_actions": [],
                    "unsupported_capability": action_type,
                    "error": str(e)
                }

        system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=executed_actions)
        messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
        llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
        assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", "Done.").strip()

        HumanNatureEngine.assimilate_human_experience(user_text, assistant_reply)

        return {
            "success": execution_success,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "model_used": llm_res.get("model", "")
        }

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
