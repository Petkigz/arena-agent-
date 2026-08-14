"""Resource-aware request routing primitives.

Phase 1 deliberately uses deterministic heuristics. A model-backed classifier
can be added later without changing the router's public result contract.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import re


@dataclass(frozen=True)
class RouteDecision:
    route: str
    complexity: float
    ambiguity: float
    risk: float
    reversible: bool
    reasoning_required: bool
    model_tier: Optional[str]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CognitiveRouter:
    """Choose the cheapest adequate execution path."""

    _direct_patterns = (
        r"^\s*(open|launch|start)\s+[^?!.]+[.!]?\s*$",
        r"^\s*(close|stop|quit)\s+[^?!.]+[.!]?\s*$",
    )

    _complex_markers = (
        "why", "debug", "diagnose", "investigate", "compare", "design",
        "analyze", "analyse", "research", "fix", "build", "develop",
        "plan", "figure out", "find out", "optimize", "optimise",
    )

    _high_risk_markers = (
        "delete", "remove", "format", "wipe", "send", "publish", "deploy",
        "install", "execute", "password", "credential", "financial",
    )

    def route(self, text: str, *, risk_hint: Optional[float] = None) -> RouteDecision:
        text = (text or "").strip()
        lowered = text.lower()

        if any(re.match(pattern, text, re.IGNORECASE) for pattern in self._direct_patterns):
            return RouteDecision("deterministic", 0.05, 0.02, risk_hint or 0.05,
                                 True, False, None, "matched simple deterministic action")

        complexity = min(1.0, 0.15 + 0.12 * sum(marker in lowered for marker in self._complex_markers))
        ambiguity = 0.25 if not text else min(1.0, 0.1 + 0.08 * text.count("?"))
        risk = risk_hint if risk_hint is not None else min(
            0.9, 0.05 + 0.18 * sum(marker in lowered for marker in self._high_risk_markers)
        )

        if complexity >= 0.4 or len(text.split()) > 25:
            return RouteDecision("cognitive", complexity, ambiguity, risk, risk < 0.4,
                                 True, "main", "complex or multi-step request")

        return RouteDecision("fast", complexity, ambiguity, risk, risk < 0.4,
                             False, "fast", "simple request without a deterministic shortcut")
