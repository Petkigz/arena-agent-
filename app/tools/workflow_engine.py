import os
import time
from typing import Dict, Any, List, Optional
from app.database import db
from app.utils.logger import app_logger

class WorkflowEngine:
    """
    Automated Multi-Step Local Workflow Engine.
    Executes sequential or trigger-based automation workflows using local tools.
    """

    @staticmethod
    def execute_workflow(workflow_name: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes a sequence of workflow steps.
        Each step format: {"action": "daily_briefing" | "web_search" | "rag_search" | "log_memory", "params": {...}}
        """
        app_logger.info(f"Executing workflow '{workflow_name}' with {len(steps)} steps.")
        step_results = []
        overall_success = True

        for idx, step in enumerate(steps, 1):
            action = step.get("action", "")
            params = step.get("params", {})
            step_entry = {"step": idx, "action": action, "status": "pending", "result": None}

            try:
                if action == "daily_briefing":
                    from app.tools.daily_briefing import DailyBriefingEngine

                    res = DailyBriefingEngine.generate_briefing(
                        custom_topics=params.get("topics"),
                        generate_audio=params.get("generate_audio", True)
                    )
                    step_entry["status"] = "success" if res.get("success") else "failed"
                    step_entry["result"] = res

                elif action == "web_search":
                    from app.tools.web_research import WebResearcher

                    query = params.get("query", "")
                    res = WebResearcher.search_and_scrape(query, max_results=params.get("max_results", 3))
                    step_entry["status"] = "success" if res.get("success") else "failed"
                    step_entry["result"] = res

                elif action == "rag_search":
                    from app.memory.semantic_rag import SemanticRAGEngine

                    query = params.get("query", "")
                    res = SemanticRAGEngine.search_memories(query, limit=params.get("limit", 5))
                    step_entry["status"] = "success"
                    step_entry["result"] = {"results": res, "count": len(res)}

                elif action == "log_memory":
                    content = params.get("content", "")
                    category = params.get("category", "workflow")
                    mem_id = db.create_memory({"content": content, "category": category, "source": "workflow_engine"})
                    step_entry["status"] = "success"
                    step_entry["result"] = {"memory_id": mem_id, "content": content}

                else:
                    step_entry["status"] = "failed"
                    step_entry["result"] = {"error": f"Unknown action: {action}"}
                    overall_success = False

            except Exception as e:
                app_logger.error(f"Error in workflow step {idx} ({action}): {e}")
                step_entry["status"] = "error"
                step_entry["result"] = {"error": str(e)}
                overall_success = False

            step_results.append(step_entry)

        db.create_audit_log(
            "execute_workflow",
            "success" if overall_success else "partial_failure",
            f"Executed workflow '{workflow_name}' ({len(steps)} steps)",
            level=1
        )

        return {
            "workflow_name": workflow_name,
            "overall_success": overall_success,
            "total_steps": len(steps),
            "step_results": step_results
        }
