"""Lightweight empirical calibration of evidence-source reliability."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class SourceStats:
    observations: int = 0
    correct: int = 0
    reliability: float = 0.5

class ConfidenceCalibrator:
    """Tracks outcomes without pretending calibration is a probability oracle."""
    def __init__(self, prior: float = 0.5, prior_strength: float = 2.0) -> None:
        self.prior = max(0.0, min(1.0, prior))
        self.prior_strength = max(0.0, prior_strength)
        self._stats: dict[str, SourceStats] = {}

    def reliability(self, source: str) -> float:
        stats = self._stats.get(source)
        return stats.reliability if stats else self.prior

    def record(self, source: str, correct: bool) -> float:
        stats = self._stats.setdefault(source, SourceStats())
        stats.observations += 1
        stats.correct += int(correct)
        stats.reliability = (self.prior * self.prior_strength + stats.correct) / (self.prior_strength + stats.observations)
        return stats.reliability

    def stats(self, source: str) -> SourceStats:
        return self._stats.get(source, SourceStats(reliability=self.prior))
