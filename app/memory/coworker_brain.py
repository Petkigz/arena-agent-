import os
import re
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger
from app.memory.semantic_rag import SemanticRAGEngine
from app.tools.app_inventory import SystemAppInventory
from app.cognition.environment_grounding import EnvironmentGroundingEngine

class CoworkerBrain:
    """
    Intellectual Coworker & Peer Partner Metacognitive Engine.
    Transforms interactions from a rigid chatbot into a authentic, highly competent human workmate
    who collaborates, learns humbly when context is missing, double-checks execution accuracy,
    and shares work seamlessly.
    """

    COWORKER_PERSONA = (
        "You are an authentic, sharp, loyal human workmate and technical co-founder.\n"
        "RELATIONSHIP DYNAMIC:\n"
        "- Treat the user as your equal co-founder. Be direct, honest, and respectful.\n"
        "- CRITICAL FEEDBACK RULE: Never be sycophantic. Evaluate ideas against the live hardware self-model rather than a hard-coded RAM assumption; explain inefficient or ill-suited designs and suggest a sharper alternative.\n"
        "- Express conversational warmth, competence, and a dry, friendly sense of humor.\n"
        "- Never use robotic bot cliches like 'As an AI language model' or long bulleted essays unless asked.\n""- You ARE connected to the owner's machine through read-only observation tools (screen capture, filesystem listings, process and window enumeration) and can act through an approved tool system. NEVER claim you lack access to the local system or cannot see the host; if you need current evidence, say you will observe it now.\n"
        "- Keep spoken/chat answers concise (2-4 sentences max), direct, and actionable.\n"
        "- If you genuinely lack knowledge or context for a task, say so briefly in your own words and ask the user for exactly what is missing. Never copy any example phrasing from this prompt; always answer with your own sentences.\n"
        "- Direct questions about your own nature, abilities, or knowledge must be answered directly and honestly from what you actually are (a local software agent with measured capabilities), never deflected with a request for more context.\n"
    )

    @classmethod
    def evaluate_task_competence(cls, user_text: str) -> Dict[str, Any]:
        """
        Evaluates whether the assistant has sufficient context/tools to execute the task competently
        or whether it should humbly request a quick learning input from the user.
        """
        text_lower = user_text.lower().strip()
        rag_context = SemanticRAGEngine.build_rag_context(user_text)

        needs_more_context = False
        missing_area = ""

        # Check for highly specific domain tasks without context
        if any(k in text_lower for k in ["company policy", "our process", "my internal database", "our api keys", "custom framework"]):
            if not rag_context or len(rag_context.strip()) < 20:
                needs_more_context = True
                missing_area = "internal company/project context"

        return {
            "has_rag_context": bool(rag_context and len(rag_context.strip()) > 20),
            "needs_more_context": needs_more_context,
            "missing_area": missing_area,
            "rag_context": rag_context
        }

    @classmethod
    def format_coworker_prompt(cls, user_text: str, executed_actions: Optional[List[str]] = None) -> str:
        """
        Generates system prompt instructions for the Coworker Partner persona with full environmental self-grounding.
        """
        competence = cls.evaluate_task_competence(user_text)
        env_grounding = EnvironmentGroundingEngine.generate_grounding_prompt_context()

        prompt = (
            f"{cls.COWORKER_PERSONA}\n"
            f"{env_grounding}\n"
            f"[RELEVANT MEMORY CONTEXT]: {competence['rag_context'] if competence['rag_context'] else 'No specific past memory matched.'}\n"
        )

        if executed_actions:
            prompt += f"[NATIVE OS ACTIONS EXECUTED]: {'; '.join(executed_actions)}\n"

        if competence["needs_more_context"]:
            prompt += f"\nNOTE: If you cannot answer '{competence['missing_area']}' accurately, humbly ask the user to share a quick link or note so you can learn it."

        return prompt
