"""Lightweight information-seeking primitives for uncertain beliefs."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class InformationNeed:
    question: str
    target: str
    reason: str
    priority: float = 0.5


def choose_information_need(unknowns: list[InformationNeed]) -> InformationNeed | None:
    if not unknowns:
        return None
    return max(unknowns, key=lambda item: item.priority)
