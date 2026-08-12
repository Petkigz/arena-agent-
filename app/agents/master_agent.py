import os
import re
import json
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.llm import llm_client
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.cognition import CognitiveState, CognitiveEvent, EventBus
from app.cognition.cognitive_router import CognitiveRouter
from app.runtime.resource_manager import ResourceManager

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


class MasterAgentOrchestrator:
    """Unified Master Agent with a lightweight Phase 1 cognitive boundary.

    Existing deterministic tools remain intact. The cognitive foundation adds
    shared state, routing, resource awareness, and events without replacing
    the existing tool layer.
    """

    cognitive_router = CognitiveRouter()
    resource_manager = ResourceManager()
    event_bus = EventBus()
    cognitive_state = CognitiveState()

    @classmethod
    def process_user_task(cls, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """Process a user request through the existing tools plus Phase 1 state."""
        text_lower = user_text.lower().strip()
        app_logger.info(f"MasterAgent processing user task: '{user_text[:80]}...'")

        # Phase 1: establish the shared cognitive context before acting.
        cls.cognitive_state.task.goal = user_text
        cls.cognitive_state.task.status = "running"
        cls.cognitive_state.attention.focus = user_text
        cls.cognitive_state.touch()

        route = cls.cognitive_router.route(user_text)
        resources = cls.resource_manager.snapshot()
        resource_policy = cls.resource_manager.execution_policy(resources)
        cls.cognitive_state.resources.cpu_percent = resources.cpu_percent
        cls.cognitive_state.resources.ram_percent = resources.ram_percent
        cls.cognitive_state.resources.ram_available_mb = resources.ram_available_mb
        cls.cognitive_state.resources.gpu_percent = resources.gpu_percent
        cls.cognitive_state.resources.vram_percent = resources.vram_percent
        cls.cognitive_state.resources.updated_at = cls.cognitive_state.updated_at

        cls.event_bus.publish(CognitiveEvent(
            event_type="user_message_received",
            data={"text": user_text, "route": route.to_dict()},
            source="master_agent",
        ))

        executed_actions = []

        # 1. APPLICATION LAUNCHING & OPERATING INTENT
        if any(k in text_lower for k in ["open ", "launch ", "start ", "run ", "search for ", "look up "]):
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
            PentestCompanyAssistant.draft_rules_of_engagement("Client Company", ["192.168.1.0/24"])
            executed_actions.append("Drafted Penetration Testing Rules of Engagement (RoE) document.")

        # 5. SCREENSHOT & VISION INTENT
        if any(k in text_lower for k in ["screenshot", "capture screen", "screen vision", "what is on my screen"]):
            cap_res = ScreenCaptureTool.capture_screen()
            executed_actions.append(f"Captured active desktop screen window ({cap_res.get('file_name')}).")

        # 6. DAILY BRIEFING INTENT
        if any(k in text_lower for k in ["daily briefing", "morning report", "executive briefing"]):
            DailyBriefingEngine.generate_briefing(generate_audio=False)
            executed_actions.append("Generated Daily Executive Briefing.")

        # Resource-aware model selection. Explicit caller complexity still wins
        # when supplied, but constrained hosts are allowed to force the fast tier.
        selected_complexity = complexity
        if resource_policy["mode"] != "normal":
            selected_complexity = "fast"
        elif route.model_tier:
            selected_complexity = route.model_tier

        system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=executed_actions)
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_text}
        ]

        llm_res = llm_client.generate_chat_completion(
            messages=messages,
            complexity=selected_complexity,
            max_tokens=150,
            temperature=0.7
        )

        assistant_reply = "Done."
        if llm_res.get("choices") and len(llm_res["choices"]) > 0:
            assistant_reply = llm_res["choices"][0]["message"]["content"].strip()

        cls.cognitive_state.execution.last_action = {"type": "user_task", "route": route.to_dict()}
        cls.cognitive_state.execution.last_result = {
            "success": bool(llm_res.get("choices")),
            "model": llm_res.get("model", ""),
            "executed_actions": executed_actions,
        }
        cls.cognitive_state.task.status = "completed"
        cls.cognitive_state.touch()

        cls.event_bus.publish(CognitiveEvent(
            event_type="task_completed",
            data={"success": bool(llm_res.get("choices")), "actions": executed_actions},
            source="master_agent",
        ))

        HumanNatureEngine.assimilate_human_experience(user_text, assistant_reply)

        return {
            "success": True,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "model_used": llm_res.get("model", ""),
            "cognitive_route": route.to_dict(),
            "resource_policy": resource_policy,
            "cognitive_state": cls.cognitive_state.to_dict(),
        }
