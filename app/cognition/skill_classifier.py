"""Phase 3A: Skill Abstraction Layer.

Maps concrete action_types to abstract skill categories so that
success in one search task transfers confidence to other search tasks.

Skill categories:
  search     — find information (file search, web search, knowledge query)
  execute    — run actions (open app, run command, phone command)
  create     — produce artifacts (screen capture, content, code)
  organize   — arrange/structure (file operations, scheduling)
  analyze    — evaluate/assess (diagnostic, opsec audit, investigation)
  communicate — interact with user or external (formulate answer, daily briefing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Skill Category Definitions ───────────────────────────────────────

SKILL_CATEGORIES = {
    "search": "Find information across any source",
    "execute": "Run actions on the environment",
    "create": "Produce artifacts or content",
    "organize": "Arrange, structure, or manage resources",
    "analyze": "Evaluate, assess, or investigate",
    "communicate": "Interact with user or external systems",
}

# Default mapping from action_type → skill category
DEFAULT_SKILL_MAP: Dict[str, str] = {
    "search_files": "search",
    "web_search": "search",
    "knowledge_query": "search",
    "open_application": "execute",
    "launch_app": "execute",
    "run_command": "execute",
    "phone_command": "execute",
    "make_phone_call": "execute",
    "send_sms": "execute",
    "screen_capture": "create",
    "content_creator": "create",
    "formulate_answer": "communicate",
    "answer": "communicate",
    "daily_briefing": "communicate",
    "diagnostic": "analyze",
    "investigate": "analyze",
    "opsec_audit": "analyze",
    "workflow_execute": "organize",
}


@dataclass
class SkillTransfer:
    """Records that success/failure in one action_type should influence another."""
    source_action: str
    target_action: str
    skill_category: str
    transfer_weight: float  # 0.0-1.0, how much transfers
    timestamp: str = field(default_factory=_now)


class SkillClassifier:
    """
    Classifies action_types into abstract skill categories and computes
    cross-skill transfer weights.
    """

    def __init__(self, custom_map: Optional[Dict[str, str]] = None) -> None:
        self._skill_map = dict(DEFAULT_SKILL_MAP)
        if custom_map:
            self._skill_map.update(custom_map)

    def classify(self, action_type: str) -> str:
        """Return the skill category for an action_type."""
        return self._skill_map.get(action_type.lower().strip(), "execute")

    def same_skill(self, action_a: str, action_b: str) -> bool:
        """Check if two action_types share a skill category."""
        return self.classify(action_a) == self.classify(action_b)

    def skill_siblings(self, action_type: str) -> List[str]:
        """Return all action_types that share the same skill category."""
        target_skill = self.classify(action_type)
        return [
            at for at, skill in self._skill_map.items()
            if skill == target_skill and at != action_type
        ]

    def transfer_weight(self, source_action: str, target_action: str) -> float:
        """
        Compute how much success/failure in source should influence target.
        - Same action_type → 1.0 (direct transfer)
        - Same skill category → 0.3 (moderate transfer)
        - Different skill → 0.0 (no transfer)
        """
        if source_action == target_action:
            return 1.0
        if self.same_skill(source_action, target_action):
            return 0.3
        return 0.0

    def transfer_adjustment(
        self,
        target_action: str,
        outcome_store: Any,
        goal_type: str,
        classifier: Optional['SkillClassifier'] = None
    ) -> float:
        """
        Compute a utility adjustment for target_action based on
        outcomes of skill-sibling actions.

        If search_files has a 0.9 success rate for search_intent goals,
        web_search (same skill) gets a moderate boost.
        """
        if not outcome_store:
            return 1.0

        target_skill = self.classify(target_action)
        siblings = [
            at for at, skill in self._skill_map.items()
            if skill == target_skill and at != target_action
        ]

        if not siblings:
            return 1.0

        # Collect sibling success rates
        total_weight = 0.0
        weighted_success = 0.0
        weighted_total = 0.0

        for sibling in siblings:
            score = outcome_store.score_strategy(goal_type, sibling)
            if score and score.total_attempts >= 2:
                weight = self.transfer_weight(sibling, target_action)
                weighted_success += score.success_rate * weight * score.total_attempts
                weighted_total += weight * score.total_attempts
                total_weight += weight

        if weighted_total == 0 or total_weight == 0:
            return 1.0

        # Blended success rate from siblings
        sibling_rate = weighted_success / weighted_total
        # Transfer influence: move 30% toward sibling rate from neutral (1.0)
        adjustment = 1.0 + (sibling_rate - 0.5) * 0.3
        return max(0.7, min(1.3, adjustment))

    def all_skills(self) -> Dict[str, List[str]]:
        """Return all action_types grouped by skill category."""
        groups: Dict[str, List[str]] = {}
        for action_type, skill in self._skill_map.items():
            groups.setdefault(skill, []).append(action_type)
        return groups

    def register_skill(self, action_type: str, skill_category: str) -> None:
        """Register a new action_type → skill mapping."""
        if skill_category not in SKILL_CATEGORIES:
            raise ValueError(f"Unknown skill category: {skill_category}. Valid: {list(SKILL_CATEGORIES.keys())}")
        self._skill_map[action_type.lower().strip()] = skill_category
