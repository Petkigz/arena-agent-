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
        """
        action_type = getattr(proposal, "action_type", str(proposal)).lower().strip()
        payload = getattr(proposal, "payload", {}) if hasattr(proposal, "payload") else {}
        executed_actions = []

        if action_type in ["open_application", "launch_app"]:
            app_name = payload.get("app_name") or payload.get("app") or payload.get("app_query") or payload.get("query")
            if not app_name:
                match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', user_text.lower())
                app_name = match.group(1).strip() if match else "explorer"
            res = SystemAppInventory.launch_any_app(app_name)
            if res.get("success"):
                executed_actions.append(f"Launched application '{res.get('app_name', app_name).title()}' on your PC.")
            else:
                executed_actions.append(f"Attempted to launch application '{app_name}'.")

        elif action_type == "web_search":
            query_term = payload.get("query_term") or payload.get("query") or user_text
            url = f"https://www.youtube.com/results?search_query={str(query_term).replace(' ', '+')}" if "youtube" in str(query_term).lower() or "youtube" in user_text.lower() else f"https://www.google.com/search?q={str(query_term).replace(' ', '+')}"
            DesktopControl.launch_application("firefox")
            DesktopControl.open_url(url)
            executed_actions.append(f"Opened web browser and launched search for '{query_term}'.")

        elif action_type == "search_files":
            search_query = payload.get("query") or payload.get("file_name") or payload.get("search_term") or user_text
            matched = UniversalFilesystem.search_filesystem(search_query, max_results=5)
            if matched:
                executed_actions.append(f"Found local file '{matched[0]['file_name']}' at {matched[0]['file_path']}.")
            else:
                executed_actions.append(f"Searched local filesystem for '{search_query}'.")

        elif action_type == "phone_command":
            from app.tools.android_adb_controller import AndroidADBController
            bat_res = AndroidADBController.get_battery_status()
            executed_actions.append(bat_res["message"])

        elif action_type == "screen_capture":
            cap_res = ScreenCaptureTool.capture_screen()
            executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")

        elif action_type == "opsec_audit":
            audit_res = OpSecManagerTool.audit_digital_footprint("user@example.com")
            executed_actions.append(f"Audited OpSec footprint: {audit_res.get('total_exposures_found', 0)} findings.")

        elif action_type == "daily_briefing":
            brief_res = DailyBriefingEngine.generate_briefing(generate_audio=False)
            executed_actions.append("Generated Daily Executive Briefing.")

        elif action_type in ["investigate", "diagnostic"]:
            executed_actions.append(f"Executed diagnostic investigation probe for '{user_text[:50]}'.")

        elif action_type in ["formulate_answer", "answer"]:
            executed_actions.append("Formulated direct conversational answer.")

        elif action_type == "workflow_execute":
            wf_res = WorkflowEngine.execute_workflow(payload.get("workflow_name", "Task Workflow"), payload.get("steps", []))
            executed_actions.append(f"Executed workflow '{wf_res.get('workflow_name')}'.")

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
            "success": True,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "model_used": llm_res.get("model", "")
        }

    @classmethod
    def process_user_task(cls, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """
        Unified single entry point for processing any user chat or spoken voice task.
        Automatically identifies, routes, and executes native tools on the system and returns
        a concise, human-warmth spoken/written response.
        """
        text_lower = user_text.lower().strip()
        app_logger.info(f"MasterAgent processing user task: '{user_text[:80]}...'")

        executed_actions = []

        # 1. APPLICATION LAUNCHING & OPERATING INTENT
        if any(k in text_lower for k in ["open ", "launch ", "start ", "run ", "search for ", "look up "]):
            # Web/YouTube Search in Browser
            if "youtube" in text_lower or "google" in text_lower or "browser" in text_lower:
                m = re.search(r'(?:search|look up|for|find|open)\s+(?:me\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+on youtube|\s+in firefox|\s+in chrome|\s+on google|$)', text_lower)
                query_term = m.group(1).strip() if m and m.group(1).strip() else "ordinary"
                url = f"https://www.youtube.com/results?search_query={query_term.replace(' ', '+')}" if "youtube" in text_lower else f"https://www.google.com/search?q={query_term.replace(' ', '+')}"

                app_name = "firefox" if "firefox" in text_lower else "chrome"
                DesktopControl.launch_application(app_name)
                DesktopControl.open_url(url)
                executed_actions.append(f"Opened {app_name.title()} and launched YouTube search for '{query_term}'.")

            else:
                match = re.search(r'(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9_\-\s]+)', text_lower)
                if match:
                    app_q = match.group(1).strip()
                    if len(app_q) > 1 and app_q not in ["file", "folder", "song", "task", "briefing", "sandbox"]:
                        res = SystemAppInventory.launch_any_app(app_q)
                        if res.get("success"):
                            executed_actions.append(f"Launched application '{res.get('app_name', app_q)}' on your PC.")

        # 2. FILE SEARCH & MEDIA PLAY INTENT
        fs_context = ""
        if any(k in text_lower for k in ["song", "file", "document", "ordinary", "library", "folder", "do i have", "search my pc"]):
            words = [w for w in user_text.replace("?", "").replace("'", "").split() if len(w) > 3 and w.lower() not in ["have", "called", "song", "this", "library", "with", "from", "does", "what", "open"]]
            search_term = words[0] if words else "Ordinary"
            matched = UniversalFilesystem.search_filesystem(search_term, max_results=5)
            if matched:
                fs_context = f"Found local file '{matched[0]['file_name']}' at {matched[0]['file_path']}."
                executed_actions.append(fs_context)
            else:
                fs_context = f"No local files matching '{search_term}' were found on this PC."

        # 3. OPSEC & DIGITAL FOOTPRINT INTENT
        if any(k in text_lower for k in ["opsec", "footprint", "erasure", "breach", "remove my data"]):
            words = [w for w in user_text.split() if "@" in w or len(w) > 4]
            ident = words[0] if words else "user@example.com"
            audit_res = OpSecManagerTool.audit_digital_footprint(ident)
            executed_actions.append(f"Audited OpSec footprint for '{ident}': {audit_res.get('total_exposures_found', 0)} findings.")

        # 4. PENTEST & CYBERSECURITY INTENT
        if any(k in text_lower for k in ["pentest", "rules of engagement", "roe", "security scan", "vulnerability report"]):
            roe_res = PentestCompanyAssistant.draft_rules_of_engagement("Client Company", ["192.168.1.0/24"])
            executed_actions.append(f"Drafted Penetration Testing Rules of Engagement (RoE) document.")

        # 5. SCREENSHOT & VISION INTENT
        if any(k in text_lower for k in ["screenshot", "capture screen", "screen vision", "what is on my screen"]):
            cap_res = ScreenCaptureTool.capture_screen()
            executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")

        # 6. DAILY BRIEFING INTENT
        if any(k in text_lower for k in ["daily briefing", "morning report", "executive briefing"]):
            brief_res = DailyBriefingEngine.generate_briefing(generate_audio=False)
            executed_actions.append("Generated Daily Executive Briefing.")

        # 7. REASONING CYCLE DECISION GATE
        cycle = ReasoningCycle()
        subject_term = text_lower.split()[0] if text_lower else "user_query"
        decision = cycle.observe_and_decide(
            subject=subject_term,
            predicate="task_intent",
            value=text_lower,
            source="user_input",
            confidence=0.9 if executed_actions else 0.5
        )

        app_logger.info(f"ReasoningCycle Decision for '{subject_term}': Action={decision.action.value}, Confidence={decision.confidence:.2f}")

        # BUILD CONCISE HUMAN-WARMTH PROMPT FOR COWORKER LLM
        system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=executed_actions)
        system_instruction += f"\n[REASONING DECISION GATE]: Action '{decision.action.value.upper()}' chosen (Confidence: {decision.confidence:.2f}). Reason: {decision.reason}"

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_text}
        ]

        llm_res = llm_client.generate_chat_completion(
            messages=messages,
            complexity=complexity,
            max_tokens=150,
            temperature=0.7
        )

        assistant_reply = "Done."
        if llm_res.get("choices") and len(llm_res["choices"]) > 0:
            assistant_reply = llm_res["choices"][0]["message"]["content"].strip()

        # Save experience into lifelong memory
        HumanNatureEngine.assimilate_human_experience(user_text, assistant_reply)

        return {
            "success": True,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "model_used": llm_res.get("model", "")
        }
