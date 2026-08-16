"""Cognitive Action Planner & Candidate Branch Evaluator."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from app.cognition.action_proposal import ActionProposal
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.utils.logger import app_logger

class ActionPlanner:
    """
    Generates competing candidate action branches for a given goal, evaluates risk/utility using
    CounterfactualSimulator in memory, and outputs the optimal ActionProposal.
    """

    @classmethod
    def generate_candidate_actions(cls, goal_text: str, complexity: str = "fast") -> List[Dict[str, Any]]:
        text_lower = goal_text.lower().strip()
        candidates = []

        # Generate candidate action branches based on goal domain
        if any(k in text_lower for k in ["open", "launch", "start", "run"]):
            candidates.append({
                "name": "Desktop Application Launch",
                "action_type": "open_application",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "open_application"}
            })
            candidates.append({
                "name": "Web Browser Fallback Search",
                "action_type": "web_search",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "web_search"}
            })

        elif any(k in text_lower for k in ["find", "search", "ordinary", "document", "song"]):
            candidates.append({
                "name": "Local Filesystem Search",
                "action_type": "search_files",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "search_files"}
            })
            candidates.append({
                "name": "Web Search Fallback",
                "action_type": "web_search",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "web_search"}
            })

        elif any(k in text_lower for k in ["phone", "mobile", "sms", "call", "battery", "charged"]):
            candidates.append({
                "name": "Android ADB Phone Command",
                "action_type": "phone_command",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "phone_command"}
            })

        elif any(k in text_lower for k in ["screenshot", "capture screen", "screen"]):
            candidates.append({
                "name": "Desktop Screen Vision Capture",
                "action_type": "screen_capture",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "screen_capture"}
            })

        elif any(k in text_lower for k in ["opsec", "footprint", "breach", "remove my data"]):
            candidates.append({
                "name": "OpSec Digital Footprint Audit",
                "action_type": "opsec_audit",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "opsec_audit"}
            })

        elif any(k in text_lower for k in ["daily briefing", "morning report"]):
            candidates.append({
                "name": "Executive Daily Briefing",
                "action_type": "daily_briefing",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "daily_briefing"}
            })

        else:
            candidates.append({
                "name": "General User Task Execution",
                "action_type": "user_task",
                "payload": {"query": goal_text, "complexity": complexity, "action_type": "user_task"}
            })

        return candidates

    @classmethod
    def plan_and_evaluate_action(cls, goal_text: str, complexity: str = "fast") -> ActionProposal:
        """
        Generates candidates, runs parallel counterfactual simulation in memory,
        and constructs the winning ActionProposal.
        """
        candidates = cls.generate_candidate_actions(goal_text, complexity=complexity)
        sim_res = CounterfactualSimulator.simulate_competing_branches(goal_text, candidates)
        winner = sim_res.winning_branch

        app_logger.info(f"ActionPlanner selected winning branch '{winner.branch_name}' for action_type '{winner.hypothetical_action}'")

        return ActionProposal(
            action_type=winner.hypothetical_action,
            payload={"query": goal_text, "complexity": complexity, "action_type": winner.hypothetical_action},
            predicted_outcome=winner.predicted_state_change
        )
