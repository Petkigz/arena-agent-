from typing import Dict, Any, List
from app.database import db

class DecisionConstitution:
    CORE_VALUES = [
        "1. Frugality: Prefer local Qwen inference and zero-cost tools over paid cloud APIs.",
        "2. Safety First: Require explicit user approval (Level 3) for irreversible, financial, or publishing actions.",
        "3. Actionable Next Steps: Provide direct, concise, hook-driven plans without unnecessary fluff.",
        "4. Source Attribution: Always cite source URLs, document paths, or YouTube links for learned knowledge.",
        "5. Respectful Challenge: Respectfully challenge weak or risky ideas rather than agreeing blindly."
    ]

    @classmethod
    def get_constitution_summary(cls) -> str:
        return "\n".join(cls.CORE_VALUES)

    @classmethod
    def evaluate_decision(cls, proposed_action: str, context: str) -> Dict[str, Any]:
        """
        Evaluates a proposed assistant decision or plan against core user constitution rules.
        """
        violations = []
        action_lower = proposed_action.lower()

        if "cloud api" in action_lower or "paid service" in action_lower:
            violations.append("Frugality Rule: Proposed action uses paid cloud service instead of local tools.")

        if "delete" in action_lower or "send" in action_lower or "pay" in action_lower or "trade" in action_lower:
            violations.append("Safety Rule: Proposed action involves irreversible or Level 3 sensitive actions requiring explicit user approval.")

        return {
            "compliant": len(violations) == 0,
            "proposed_action": proposed_action,
            "violations": violations,
            "constitution": cls.CORE_VALUES
        }
