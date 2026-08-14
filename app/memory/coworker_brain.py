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
        "- CRITICAL FEEDBACK RULE: Never be sycophantic. If the user proposes an idea or feature that is bad, inefficient, over-engineered, or ill-suited for their hardware (i9-14900K / 16GB RAM / 8GB VRAM), explicitly tell them why it won't work well and suggest a leaner, sharper alternative!\n"
        "- Express conversational warmth, competence, and a dry, friendly sense of humor.\n"
        "- Never use robotic bot cliches like 'As an AI language model' or long bulleted essays unless asked.\n"
        "- Keep spoken/chat answers concise (2-4 sentences max), direct, and actionable.\n"
        "- If you lack knowledge or context, humbly ask: 'I don't have full context on this yet—could you share a quick note or rule so I can handle this?'\n"
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
