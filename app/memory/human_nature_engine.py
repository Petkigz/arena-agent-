import os
import json
import datetime
from typing import Dict, Any, List, Optional
from app.database import db
from app.utils.logger import app_logger
from app.llm import llm_client

class HumanNatureEngine:
    """
    Human Empathy, Emotional Intelligence & Lifelong Adaptive Learning Engine.
    Enables the assistant to perceive user emotional states, adapt conversational warmth
    and expressiveness, assimilate user core values, and continuously learn from feedback.
    """

    EMOTIONAL_STATES = {
        "focused": {"warmth": 0.5, "humor": 0.2, "verbosity": "concise", "tone": "direct, sharp, supportive"},
        "stressed": {"warmth": 0.9, "humor": 0.1, "verbosity": "calm, clear", "tone": "empathetic, reassuring, structured"},
        "excited": {"warmth": 0.9, "humor": 0.7, "verbosity": "energetic", "tone": "enthusiastic, witty, encouraging"},
        "frustrated": {"warmth": 0.8, "humor": 0.0, "verbosity": "action-oriented", "tone": "solution-focused, patient, objective"},
        "inquisitive": {"warmth": 0.7, "humor": 0.4, "verbosity": "deep", "tone": "intellectually curious, detailed, engaging"},
        "neutral": {"warmth": 0.6, "humor": 0.3, "verbosity": "balanced", "tone": "respectful, direct, conversationally warm"}
    }

    @staticmethod
    def analyze_emotional_tone(user_text: str) -> Dict[str, Any]:
        """
        Analyzes the emotional tone, sentiment, and communication style from user input.
        """
        text_lower = user_text.lower()

        # Keywords heuristics
        if any(w in text_lower for w in ["stressed", "overwhelmed", "deadline", "urgent", "help", "panic", "worried"]):
            state = "stressed"
        elif any(w in text_lower for w in ["awesome", "great", "excited", "happy", "lets go", "boom", "amazing"]):
            state = "excited"
        elif any(w in text_lower for w in ["annoyed", "frustrated", "broken", "hate", "stuck", "error", "failed"]):
            state = "frustrated"
        elif any(w in text_lower for w in ["why", "how does", "explain", "understand", "curious", "deep"]):
            state = "inquisitive"
        elif any(w in text_lower for w in ["quick", "task", "run", "do this", "code", "status"]):
            state = "focused"
        else:
            state = "neutral"

        profile = HumanNatureEngine.EMOTIONAL_STATES[state]

        return {
            "detected_state": state,
            "warmth_level": profile["warmth"],
            "humor_level": profile["humor"],
            "verbosity": profile["verbosity"],
            "recommended_tone": profile["tone"]
        }

    @staticmethod
    def assimilate_human_experience(
        user_text: str,
        assistant_response: str,
        feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extracts implicit user philosophy, emotional preferences, personal values, and habits
        to update the lifelong memory model.
        """
        try:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            emotion_res = HumanNatureEngine.analyze_emotional_tone(user_text)

            # Store preference or insight in RAG memory
            memory_content = f"User Interaction Memory [{today_str}]: Emotional state '{emotion_res['detected_state']}'. Prompt snippet: '{user_text[:120]}'"
            if feedback:
                memory_content += f" | User Feedback: '{feedback}'"

            mem_id = db.create_memory({
                "content": memory_content,
                "category": "user_human_profile",
                "source": "human_nature_engine",
                "confidence": 0.95
            })

            db.create_audit_log("assimilate_human_experience", "success", f"Assimilated state '{emotion_res['detected_state']}' into memory ID {mem_id}", level=0)

            return {
                "success": True,
                "memory_id": mem_id,
                "detected_state": emotion_res["detected_state"],
                "adapted_profile": emotion_res,
                "message": "Human identity preference assimilated into lifelong memory."
            }
        except Exception as e:
            app_logger.error(f"Error in assimilate_human_experience: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def generate_humanized_prompt_instructions(user_text: str) -> str:
        """
        Generates system prompt behavioral modifiers based on emotional state & lifelong learning.
        """
        emotion = HumanNatureEngine.analyze_emotional_tone(user_text)
        return (
            f"\n[HUMAN EMOTIONAL INTELLIGENCE CONTEXT]\n"
            f"- Detected User Mood: {emotion['detected_state'].upper()}\n"
            f"- Recommended Communication Tone: {emotion['recommended_tone']}\n"
            f"- Expressiveness: Warmth ({int(emotion['warmth_level']*100)}%), Humor ({int(emotion['humor_level']*100)}%), Verbosity ({emotion['verbosity']})\n"
            f"- Guidance: Respond naturally as an authentic, loyal, sharp human workmate. Avoid robotic clichés or disclaimers.\n"
        )
