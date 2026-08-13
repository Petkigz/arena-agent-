"""Lightweight information-seeking primitives for uncertain beliefs."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class InformationNeed:
    question: str
    target: str
    reason: str
    priority: float = 0.5
    predicate: Optional[str] = None
    def __post_init__(self) -> None:
        if not 0.0 <= self.priority <= 1.0:
            raise ValueError("priority must be between 0 and 1")

def choose_information_need(unknowns: list[InformationNeed]) -> InformationNeed | None:
    if not unknowns:
        return None
    return max(unknowns, key=lambda item: item.priority)
