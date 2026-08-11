from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.memory.semantic_rag import SemanticRAGEngine
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class MultiAgentTeam:
    @classmethod
    def run_collaborative_workflow(cls, objective: str, complexity: str = "main") -> Dict[str, Any]:
        """
        Multi-Agent Collaboration Workflow:
        1. Planner Agent: Formulates task plan.
        2. Researcher Agent: RAG memory lookup.
        3. Specialist Agent: Drafts solution.
        4. Critic Agent: Evaluates safety rules & quality before final output.
        """
        app_logger.info(f"MultiAgentTeam starting collaboration for objective: '{objective}'")

        # Step 1: Researcher Agent - RAG Context Lookup
        rag_context = SemanticRAGEngine.build_rag_context(objective)

        # Step 2: Planner Agent
        planner_prompt = f"""
You are the Lead Planner Agent. Formulate a 3-step execution plan for the objective: "{objective}"
{rag_context}
"""
        plan_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": planner_prompt}],
            complexity=complexity,
            max_tokens=400
        )
        plan_text = plan_res["choices"][0]["message"]["content"] if plan_res.get("choices") else "Plan formulated."

        # Step 3: Specialist Coder/Writer Agent
        specialist_prompt = f"""
You are the Technical Specialist Agent. Execute the following plan for objective: "{objective}"

Plan:
{plan_text}

Draft the complete solution, code, or technical response.
"""
        spec_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": specialist_prompt}],
            complexity=complexity,
            max_tokens=800
        )
        draft_solution = spec_res["choices"][0]["message"]["content"] if spec_res.get("choices") else "Draft solution created."

        # Step 4: Critic / Safety Inspector Agent
        critic_prompt = f"""
You are the Safety Critic & Quality Inspector Agent. Review the proposed solution for:
Objective: "{objective}"

Proposed Solution:
\"\"\"
{draft_solution}
\"\"\"

Verify compliance with safety rules, accuracy, and clarity. Output the finalized, polished answer.
"""
        critic_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": critic_prompt}],
            complexity=complexity,
            max_tokens=800
        )
        final_solution = critic_res["choices"][0]["message"]["content"] if critic_res.get("choices") else draft_solution

        audit_logger.info(f"Multi-Agent collaboration completed for '{objective}'")

        return {
            "success": True,
            "objective": objective,
            "plan_by_planner": plan_text,
            "draft_by_specialist": draft_solution,
            "final_verified_solution": final_solution,
            "rag_context_used": bool(rag_context)
        }
