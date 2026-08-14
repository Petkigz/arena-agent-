"""Phase D: Executive Attention & Priority Allocation Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class FocusTarget:
    target_name: str
    priority_score: float
    urgency: str = "normal"  # 'low', 'normal', 'urgent'
    updated_at: str = field(default_factory=_now)

class AttentionManager:
    """Manages cognitive focus and prioritizes active goals/threats on the i9-14900K."""

    def __init__(self) -> None:
        self.active_focus: Optional[FocusTarget] = None
        self.focus_queue: List[FocusTarget] = []

    def allocate_attention(self, target_name: str, priority_score: float, urgency: str = "normal") -> FocusTarget:
        target = FocusTarget(target_name=target_name, priority_score=priority_score, urgency=urgency)
        if not self.active_focus or priority_score > self.active_focus.priority_score or urgency == "urgent":
            if self.active_focus:
                self.focus_queue.append(self.active_focus)
            self.active_focus = target
        else:
            self.focus_queue.append(target)

        # Sort queue by priority score
        self.focus_queue.sort(key=lambda x: x.priority_score, reverse=True)
        return self.active_focus

    def release_focus(self) -> Optional[FocusTarget]:
        if self.focus_queue:
            self.active_focus = self.focus_queue.pop(0)
        else:
            self.active_focus = None
        return self.active_focus
