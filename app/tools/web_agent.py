from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.tools.browser_automation import BrowserAutomation
from app.tools.knowledge_indexer import KnowledgeIndexer
from app.utils.logger import app_logger, audit_logger

class WebAgent:
    @classmethod
    def execute_web_workflow(
        cls, 
        objective: str, 
        target_url: str,
        complexity: str = "main",
        auto_save_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Autonomous Web Agent Workflow:
        1. Navigates to target URL using Playwright.
        2. Extracts page content & screenshot.
        3. Uses Qwen local LLM to plan and summarize next actions for the objective.
        4. Saves findings into SQLite Memory Vault with source URL citation.
        """
        app_logger.info(f"WebAgent starting workflow for objective '{objective}' on '{target_url}'")

        # Step 1: Playwright Browser Navigation & Extraction
        browser_res = BrowserAutomation.navigate_and_extract(target_url)
        if not browser_res.get("success"):
            return browser_res

        page_title = browser_res.get("title", target_url)
        page_content = browser_res.get("content_snippet", "")[:10000]

        system_prompt = (
            "You are an autonomous Web Agent. Your task is to analyze the extracted "
            "web page text for a user's objective and formulate a structured workflow result."
        )

        user_prompt = f"""
Web Objective: "{objective}"
Target URL: {target_url} (Page Title: "{page_title}")

Extracted Web Page Content:
\"\"\"
{page_content}
\"\"\"

Please provide:
1. **Objective Execution Result**: Did the web page contain the required information for the objective?
2. **Key Data & Technical Findings**: Core data points, links, facts, or instructions found.
3. **Recommended Next Step**: Next action for the user or persistent task.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=800
            )

            agent_summary = "No workflow summary generated."
            if llm_res.get("choices") and len(llm_res["choices"]) > 0:
                agent_summary = llm_res["choices"][0]["message"]["content"]

            result = {
                "success": True,
                "objective": objective,
                "target_url": target_url,
                "page_title": page_title,
                "agent_summary": agent_summary,
                "screenshot_path": browser_res.get("screenshot_path", ""),
                "image_url": browser_res.get("image_url", "")
            }

            if auto_save_memory and agent_summary:
                mem_id = KnowledgeIndexer.index_web_knowledge({
                    "success": True,
                    "title": f"Web Workflow: {objective}",
                    "url": target_url,
                    "domain": browser_res.get("url", target_url),
                    "ai_summary": agent_summary
                }, category="web_workflow")
                result["memory_id"] = mem_id

            audit_logger.info(f"Completed web agent workflow for '{objective}' on {target_url}")
            return result

        except Exception as e:
            app_logger.error(f"Error in web agent workflow: {e}")
            return {
                "success": False,
                "error": f"Web agent execution error: {str(e)}",
                "objective": objective,
                "target_url": target_url
            }
