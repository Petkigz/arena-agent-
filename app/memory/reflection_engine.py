from typing import Dict, Any, Optional
from app.database import db
from app.llm import llm_client, require_real_completion
from app.utils.logger import app_logger, audit_logger

class ReflectionEngine:
    @classmethod
    def reflect_on_task_execution(
        cls, 
        task_title: str, 
        task_goal: str, 
        verification_result: Optional[Any] = None,
        user_feedback: Optional[str] = None,
        outcome_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs an AI self-reflection post-mortem on completed tasks to extract lessons learned,
        correct mistakes, and save improved preferences into SQLite permanent memory.
        
        Phase 4: Accepts GoalVerificationResult and derives confidence from verification quality.
        """
        # Build structured outcome from verification result
        if verification_result is not None:
            verified = getattr(verification_result, 'verified_success', False)
            lifecycle = getattr(verification_result, 'final_state', None)
            lifecycle_str = lifecycle.value if hasattr(lifecycle, 'value') else str(lifecycle)
            met = getattr(verification_result, 'met_conditions', [])
            failed = getattr(verification_result, 'failed_conditions', [])
            reason = getattr(verification_result, 'verification_reason', '')
            
            outcome_text = f"Verified: {verified} | State: {lifecycle_str} | Met: {len(met)} conditions | Failed: {len(failed)} conditions"
            if failed:
                outcome_text += f" | Failed details: {'; '.join(failed[:3])}"
            if reason:
                outcome_text += f" | Reason: {reason}"
            
            # Derive confidence from verification quality
            if verified and len(failed) == 0:
                confidence = 0.95  # High confidence: verified success with no failures
            elif verified and len(failed) > 0:
                confidence = 0.75  # Medium confidence: verified but with some failures
            elif not verified and len(failed) > 0:
                confidence = 0.60  # Lower confidence: verification failed
            else:
                confidence = 0.50  # Lowest confidence: unknown or no verification
        elif outcome_summary is not None:
            # Legacy path: unverified string summary
            outcome_text = f"[UNVERIFIED] {outcome_summary}"
            confidence = 0.50  # Low confidence for unverified summaries
        else:
            outcome_text = "No outcome information provided"
            confidence = 0.30
        
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
{outcome_text}
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

            reflection_text = require_real_completion(llm_res)

            # Save lesson learned to SQLite permanent memory
            mem_content = f"🧠 [SELF-REFLECTION :: {task_title}]\n{reflection_text}"
            mem_id = db.create_memory({
                "content": mem_content,
                "category": "task_reflection",
                "source": "self_reflection_engine",
                "confidence": confidence
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
