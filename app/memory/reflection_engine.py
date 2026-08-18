from typing import Dict, Any, Optional
from app.database import db
from app.llm import llm_client
from app.utils.logger import app_logger, audit_logger

class ReflectionEngine:
    @classmethod
    def reflect_on_task_execution(
        cls, 
        task_title: str, 
        task_goal: str, 
        outcome_summary: str,
        user_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs an AI self-reflection post-mortem on completed tasks to extract lessons learned,
        correct mistakes, and save improved preferences into SQLite permanent memory.
        """
        system_prompt = (
            "You are an AI self-reflection evaluator. Analyze completed task execution "
            "and user feedback to extract lessons learned and permanent preference rules."
        )

        feedback_str = f"User Feedback: '{user_feedback}'" if user_feedback else "User Feedback: Task completed normally."

        user_prompt = f"""
Task Title: "{task_title}"
Task Goal: "{task_goal}"
Execution Outcome:
\"\"\"
{outcome_summary}
\"\"\"
{feedback_str}

Reflect on this execution and summarize:
1. **Successes & Efficient Strategies**: What worked well?
2. **Mistakes, Delays, or Misunderstandings**: What failed or could be improved?
3. **Permanent Lesson Learned / Preference Rule**: A 1-2 sentence rule or learned preference to remember for future similar tasks.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=600
            )

            reflection_text = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Reflection completed."

            # Save lesson learned to SQLite permanent memory
            mem_content = f"🧠 [SELF-REFLECTION :: {task_title}]\n{reflection_text}"
            mem_id = db.create_memory({
                "content": mem_content,
                "category": "task_reflection",
                "source": "self_reflection_engine",
                "confidence": 0.95
            })

            audit_logger.info(f"Self-reflection logged for task '{task_title}' (Memory #{mem_id})")

            return {
                "success": True,
                "task_title": task_title,
                "reflection_text": reflection_text,
                "memory_id": mem_id
            }
        except Exception as e:
            app_logger.error(f"Error in task reflection: {e}")
            return {
                "success": False,
                "error": f"Reflection error: {str(e)}",
                "task_title": task_title
            }
