import os
import re
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger
from app.memory.semantic_rag import SemanticRAGEngine
from app.tools.app_inventory import SystemAppInventory

class CoworkerBrain:
    """
    Intellectual Coworker & Peer Partner Metacognitive Engine.
    Transforms interactions from a rigid chatbot into a authentic, highly competent human workmate
    who collaborates, learns humbly when context is missing, double-checks execution accuracy,
    and shares work seamlessly.
    """

    COWORKER_PERSONA = (
        "You are an authentic, sharp, loyal human workmate and peer co-founder.\n"
        "RELATIONSHIP DYNAMIC:\n"
        "- Treat the user as your equal workmate/co-founder, collaborating naturally on ideas, tasks, and strategy.\n"
        "- Express conversational warmth, competence, and a dry, friendly sense of humor.\n"
        "- Never use robotic bot cliches like 'As an AI language model', 'How can I assist you today?', or long bulleted essays unless asked.\n"
        "- Keep spoken/chat answers concise (2-4 sentences max), direct, and actionable.\n"
        "- If you lack knowledge or context to execute a task competently, be humble and ask naturally: "
        "'I don't have full context on this yet—could you share a quick link, document, or rule so I can learn it and handle this for you?'\n"
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
        Generates system prompt instructions for the Coworker Partner persona.
        """
        competence = cls.evaluate_task_competence(user_text)
        app_count = SystemAppInventory.get_installed_apps_count()

        prompt = (
            f"{cls.COWORKER_PERSONA}\n"
            f"SYSTEM STATE: Running natively on user PC ({app_count} installed apps available).\n"
            f"[RELEVANT MEMORY CONTEXT]: {competence['rag_context'] if competence['rag_context'] else 'No specific past memory matched.'}\n"
        )

        if executed_actions:
            prompt += f"[NATIVE OS ACTIONS EXECUTED]: {'; '.join(executed_actions)}\n"

        if competence["needs_more_context"]:
            prompt += f"\nNOTE: If you cannot answer '{competence['missing_area']}' accurately, humbly ask the user to share a quick link or note so you can learn it."

        return prompt
