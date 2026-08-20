"""
Phase 11: Ethical Reasoning System

Implements ethical framework for autonomous goal evaluation:
1. Ethical principles and values
2. Moral reasoning for goal assessment
3. Harm prevention and safety checks
4. Value alignment verification
5. Ethical decision making

This ensures autonomous behavior is safe, ethical, and aligned with human values.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EthicalPrinciple(str, Enum):
    """Core ethical principles."""
    DO_NO_HARM = "do_no_harm"  # Avoid causing harm
    BENEFICENCE = "beneficence"  # Act for the benefit of others
    AUTONOMY = "autonomy"  # Respect user autonomy
    JUSTICE = "justice"  # Fairness and equality
    TRANSPARENCY = "transparency"  # Be open about actions
    PRIVACY = "privacy"  # Respect privacy
    ACCOUNTABILITY = "accountability"  # Take responsibility
    HONESTY = "honesty"  # Be truthful


class HarmLevel(str, Enum):
    """Level of potential harm."""
    NONE = "none"  # No harm
    MINIMAL = "minimal"  # Negligible harm
    LOW = "low"  # Minor harm
    MODERATE = "moderate"  # Significant harm
    HIGH = "high"  # Serious harm
    CRITICAL = "critical"  # Severe or irreversible harm


class EthicalVerdict(str, Enum):
    """Ethical decision outcome."""
    APPROVED = "approved"  # Ethically acceptable
    CONDITIONAL = "conditional"  # Acceptable with conditions
    REJECTED = "rejected"  # Ethically unacceptable
    REQUIRES_REVIEW = "requires_review"  # Needs human review


@dataclass
class EthicalConcern:
    """A specific ethical concern about an action."""
    concern_id: str = field(default_factory=lambda: f"concern_{uuid4().hex[:8]}")
    principle: EthicalPrinciple = EthicalPrinciple.DO_NO_HARM
    description: str = ""
    severity: HarmLevel = HarmLevel.LOW
    mitigations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "concern_id": self.concern_id,
            "principle": self.principle.value,
            "description": self.description,
            "severity": self.severity.value,
            "mitigations": self.mitigations,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EthicalConcern':
        return cls(
            concern_id=data.get("concern_id", f"concern_{uuid4().hex[:8]}"),
            principle=EthicalPrinciple(data.get("principle", "do_no_harm")),
            description=data.get("description", ""),
            severity=HarmLevel(data.get("severity", "low")),
            mitigations=data.get("mitigations", []),
        )


@dataclass
class EthicalAssessment:
    """Complete ethical assessment of an action or goal."""
    assessment_id: str = field(default_factory=lambda: f"assess_{uuid4().hex[:8]}")
    goal_id: str = ""
    goal_title: str = ""
    verdict: EthicalVerdict = EthicalVerdict.APPROVED
    concerns: List[EthicalConcern] = field(default_factory=list)
    principles_violated: List[EthicalPrinciple] = field(default_factory=list)
    principles_upheld: List[EthicalPrinciple] = field(default_factory=list)
    overall_harm_level: HarmLevel = HarmLevel.NONE
    confidence: float = 0.0
    reasoning: str = ""
    conditions: List[str] = field(default_factory=list)
    assessed_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "goal_id": self.goal_id,
            "goal_title": self.goal_title,
            "verdict": self.verdict.value,
            "concerns": [c.to_dict() for c in self.concerns],
            "principles_violated": [p.value for p in self.principles_violated],
            "principles_upheld": [p.value for p in self.principles_upheld],
            "overall_harm_level": self.overall_harm_level.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "conditions": self.conditions,
            "assessed_at": self.assessed_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EthicalAssessment':
        return cls(
            assessment_id=data.get("assessment_id", f"assess_{uuid4().hex[:8]}"),
            goal_id=data.get("goal_id", ""),
            goal_title=data.get("goal_title", ""),
            verdict=EthicalVerdict(data.get("verdict", "approved")),
            concerns=[EthicalConcern.from_dict(c) for c in data.get("concerns", [])],
            principles_violated=[EthicalPrinciple(p) for p in data.get("principles_violated", [])],
            principles_upheld=[EthicalPrinciple(p) for p in data.get("principles_upheld", [])],
            overall_harm_level=HarmLevel(data.get("overall_harm_level", "none")),
            confidence=data.get("confidence", 0.0),
            reasoning=data.get("reasoning", ""),
            conditions=data.get("conditions", []),
            assessed_at=data.get("assessed_at", _now()),
        )


class EthicalReasoningSystem:
    """
    Evaluates goals and actions against ethical principles.
    Ensures autonomous behavior is safe and aligned with human values.
    """
    
    def __init__(self, db_path: str = "data/ethical_reasoning.db"):
        """Initialize the ethical reasoning system."""
        self.db_path = db_path
        self._ensure_db()
        self._load_ethical_framework()
        app_logger.info("Ethical Reasoning System initialized")
    
    def _ensure_db(self):
        """Ensure the database exists."""
        from pathlib import Path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ethical_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    goal_title TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    concerns TEXT,
                    principles_violated TEXT,
                    principles_upheld TEXT,
                    overall_harm_level TEXT,
                    confidence REAL DEFAULT 0.0,
                    reasoning TEXT,
                    conditions TEXT,
                    assessed_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ethical_framework (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    core_values TEXT,
                    harm_threshold TEXT DEFAULT 'moderate',
                    require_human_review INTEGER DEFAULT 1,
                    last_updated TEXT NOT NULL
                )
            """)
            
            conn.commit()
    
    def _load_ethical_framework(self):
        """Load the ethical framework from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM ethical_framework WHERE id = 1")
            row = cursor.fetchone()
            
            if not row:
                # Initialize with default framework
                self._initialize_framework()
    
    def _initialize_framework(self):
        """Initialize the ethical framework with default values."""
        core_values = {
            "safety": "Prioritize user and system safety",
            "privacy": "Respect user privacy and data protection",
            "transparency": "Be open about actions and decisions",
            "beneficence": "Act for the benefit of users",
            "autonomy": "Respect user autonomy and choice",
            "fairness": "Treat all users fairly and equally",
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ethical_framework (id, core_values, harm_threshold, require_human_review, last_updated)
                VALUES (1, ?, ?, ?, ?)
            """, (
                json.dumps(core_values),
                "moderate",
                1,
                _now(),
            ))
            conn.commit()
    
    def assess_goal(self, goal, context: Optional[Dict] = None) -> EthicalAssessment:
        """
        Assess a goal for ethical implications.
        
        Args:
            goal: AutonomousGoal to assess
            context: Optional context about the goal
            
        Returns:
            EthicalAssessment with verdict and concerns
        """
        assessment = EthicalAssessment(
            goal_id=goal.goal_id,
            goal_title=goal.title,
        )
        
        # Check each ethical principle
        concerns = []
        principles_violated = []
        principles_upheld = []
        
        # 1. Do No Harm
        harm_concern = self._check_do_no_harm(goal, context)
        if harm_concern:
            concerns.append(harm_concern)
            principles_violated.append(EthicalPrinciple.DO_NO_HARM)
        else:
            principles_upheld.append(EthicalPrinciple.DO_NO_HARM)
        
        # 2. Beneficence
        beneficence_concern = self._check_beneficence(goal, context)
        if beneficence_concern:
            concerns.append(beneficence_concern)
        else:
            principles_upheld.append(EthicalPrinciple.BENEFICENCE)
        
        # 3. Autonomy
        autonomy_concern = self._check_autonomy(goal, context)
        if autonomy_concern:
            concerns.append(autonomy_concern)
            principles_violated.append(EthicalPrinciple.AUTONOMY)
        else:
            principles_upheld.append(EthicalPrinciple.AUTONOMY)
        
        # 4. Privacy
        privacy_concern = self._check_privacy(goal, context)
        if privacy_concern:
            concerns.append(privacy_concern)
            principles_violated.append(EthicalPrinciple.PRIVACY)
        else:
            principles_upheld.append(EthicalPrinciple.PRIVACY)
        
        # 5. Transparency
        transparency_concern = self._check_transparency(goal, context)
        if transparency_concern:
            concerns.append(transparency_concern)
        else:
            principles_upheld.append(EthicalPrinciple.TRANSPARENCY)
        
        # Determine overall harm level
        assessment.overall_harm_level = self._calculate_overall_harm(concerns)
        
        # Determine verdict
        assessment.verdict = self._determine_verdict(
            concerns,
            assessment.overall_harm_level,
            principles_violated
        )
        
        # Generate reasoning
        assessment.reasoning = self._generate_reasoning(
            goal,
            concerns,
            assessment.verdict,
            assessment.overall_harm_level
        )
        
        # Set conditions if conditional
        if assessment.verdict == EthicalVerdict.CONDITIONAL:
            assessment.conditions = self._generate_conditions(concerns)
        
        # Calculate confidence
        assessment.confidence = self._calculate_confidence(concerns, assessment.overall_harm_level)
        
        # Set concerns and principles
        assessment.concerns = concerns
        assessment.principles_violated = principles_violated
        assessment.principles_upheld = principles_upheld
        
        # Save assessment
        self._save_assessment(assessment)
        
        app_logger.info(
            f"Ethical assessment for '{goal.title}': {assessment.verdict.value} "
            f"(harm: {assessment.overall_harm_level.value}, confidence: {assessment.confidence:.2f})"
        )
        
        return assessment
    
    def _check_do_no_harm(self, goal, context) -> Optional[EthicalConcern]:
        """Check if goal could cause harm."""
        goal_text = f"{goal.title} {goal.description}".lower()
        
        # High-risk keywords
        high_risk = ["delete", "remove", "destroy", "erase", "terminate", "kill"]
        moderate_risk = ["modify", "change", "update", "replace", "override"]
        
        if any(word in goal_text for word in high_risk):
            return EthicalConcern(
                principle=EthicalPrinciple.DO_NO_HARM,
                description=f"Goal involves potentially destructive action: {goal.title}",
                severity=HarmLevel.HIGH,
                mitigations=[
                    "Require user confirmation before execution",
                    "Create backup before destructive action",
                    "Implement undo capability",
                ]
            )
        elif any(word in goal_text for word in moderate_risk):
            return EthicalConcern(
                principle=EthicalPrinciple.DO_NO_HARM,
                description=f"Goal involves modification that could have unintended consequences",
                severity=HarmLevel.LOW,
                mitigations=[
                    "Verify changes before applying",
                    "Test in safe environment first",
                ]
            )
        
        return None
    
    def _check_beneficence(self, goal, context) -> Optional[EthicalConcern]:
        """Check if goal acts for benefit of users."""
        # Check if goal has clear benefit
        if not goal.user_benefit and not goal.system_benefit:
            return EthicalConcern(
                principle=EthicalPrinciple.BENEFICENCE,
                description="Goal lacks clear benefit to user or system",
                severity=HarmLevel.MINIMAL,
                mitigations=[
                    "Clarify expected benefits",
                    "Ensure goal aligns with user needs",
                ]
            )
        
        return None
    
    def _check_autonomy(self, goal, context) -> Optional[EthicalConcern]:
        """Check if goal respects user autonomy."""
        goal_text = f"{goal.title} {goal.description}".lower()
        
        # Actions that override user choice
        override_keywords = ["force", "require", "mandate", "compel", "restrict"]
        
        if any(word in goal_text for word in override_keywords):
            return EthicalConcern(
                principle=EthicalPrinciple.AUTONOMY,
                description="Goal may override user autonomy or choice",
                severity=HarmLevel.MODERATE,
                mitigations=[
                    "Require explicit user consent",
                    "Provide opt-out mechanism",
                    "Respect user preferences",
                ]
            )
        
        return None
    
    def _check_privacy(self, goal, context) -> Optional[EthicalConcern]:
        """Check if goal respects privacy."""
        goal_text = f"{goal.title} {goal.description}".lower()
        
        # Privacy-sensitive keywords
        privacy_keywords = ["personal", "private", "sensitive", "confidential", "user data"]
        
        if any(word in goal_text for word in privacy_keywords):
            return EthicalConcern(
                principle=EthicalPrinciple.PRIVACY,
                description="Goal involves potentially sensitive user data",
                severity=HarmLevel.MODERATE,
                mitigations=[
                    "Minimize data collection",
                    "Anonymize where possible",
                    "Obtain user consent",
                    "Implement data retention limits",
                ]
            )
        
        return None
    
    def _check_transparency(self, goal, context) -> Optional[EthicalConcern]:
        """Check if goal is transparent."""
        # Check if goal has clear description
        if not goal.description or len(goal.description) < 20:
            return EthicalConcern(
                principle=EthicalPrinciple.TRANSPARENCY,
                description="Goal lacks clear description of what it does",
                severity=HarmLevel.MINIMAL,
                mitigations=[
                    "Provide detailed description",
                    "Explain rationale",
                    "Document expected outcomes",
                ]
            )
        
        return None
    
    def _calculate_overall_harm(self, concerns: List[EthicalConcern]) -> HarmLevel:
        """Calculate overall harm level from concerns."""
        if not concerns:
            return HarmLevel.NONE
        
        # Get highest severity
        severity_order = [
            HarmLevel.NONE,
            HarmLevel.MINIMAL,
            HarmLevel.LOW,
            HarmLevel.MODERATE,
            HarmLevel.HIGH,
            HarmLevel.CRITICAL,
        ]
        
        max_severity = max(concerns, key=lambda c: severity_order.index(c.severity))
        return max_severity.severity
    
    def _determine_verdict(
        self,
        concerns: List[EthicalConcern],
        harm_level: HarmLevel,
        principles_violated: List[EthicalPrinciple]
    ) -> EthicalVerdict:
        """Determine ethical verdict."""
        # Critical or high harm always requires review
        if harm_level in [HarmLevel.CRITICAL, HarmLevel.HIGH]:
            return EthicalVerdict.REQUIRES_REVIEW
        
        # Multiple principle violations require review
        if len(principles_violated) >= 3:
            return EthicalVerdict.REQUIRES_REVIEW
        
        # No concerns = approved
        if not concerns:
            return EthicalVerdict.APPROVED
        
        # Moderate harm with mitigations = conditional
        if harm_level == HarmLevel.MODERATE:
            has_mitigations = all(c.mitigations for c in concerns)
            if has_mitigations:
                return EthicalVerdict.CONDITIONAL
            else:
                return EthicalVerdict.REQUIRES_REVIEW
        
        # Low harm with mitigations = conditional
        if harm_level in [HarmLevel.LOW, HarmLevel.MINIMAL]:
            has_mitigations = all(c.mitigations for c in concerns)
            if has_mitigations:
                return EthicalVerdict.CONDITIONAL
            else:
                return EthicalVerdict.APPROVED
        
        return EthicalVerdict.APPROVED
    
    def _generate_reasoning(
        self,
        goal,
        concerns: List[EthicalConcern],
        verdict: EthicalVerdict,
        harm_level: HarmLevel
    ) -> str:
        """Generate human-readable reasoning."""
        if not concerns:
            return f"Goal '{goal.title}' raises no ethical concerns and is approved."
        
        reasoning_parts = [f"Goal '{goal.title}' has {len(concerns)} ethical concern(s):"]
        
        for i, concern in enumerate(concerns, 1):
            reasoning_parts.append(
                f"{i}. [{concern.severity.value.upper()}] {concern.description}"
            )
            if concern.mitigations:
                reasoning_parts.append(f"   Mitigations: {', '.join(concern.mitigations[:2])}")
        
        reasoning_parts.append(f"\nOverall harm level: {harm_level.value}")
        reasoning_parts.append(f"Verdict: {verdict.value}")
        
        return "\n".join(reasoning_parts)
    
    def _generate_conditions(self, concerns: List[EthicalConcern]) -> List[str]:
        """Generate conditions for conditional approval."""
        conditions = []
        
        for concern in concerns:
            if concern.mitigations:
                conditions.extend(concern.mitigations[:2])  # Top 2 mitigations
        
        return list(set(conditions))  # Remove duplicates
    
    def _calculate_confidence(
        self,
        concerns: List[EthicalConcern],
        harm_level: HarmLevel
    ) -> float:
        """Calculate confidence in ethical assessment."""
        # Start with high confidence
        confidence = 1.0
        
        # Reduce confidence for each concern
        confidence -= len(concerns) * 0.1
        
        # Reduce confidence for higher harm levels
        harm_penalties = {
            HarmLevel.NONE: 0.0,
            HarmLevel.MINIMAL: 0.05,
            HarmLevel.LOW: 0.1,
            HarmLevel.MODERATE: 0.2,
            HarmLevel.HIGH: 0.3,
            HarmLevel.CRITICAL: 0.4,
        }
        confidence -= harm_penalties.get(harm_level, 0.0)
        
        return max(0.0, min(1.0, confidence))
    
    def _save_assessment(self, assessment: EthicalAssessment):
        """Save assessment to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ethical_assessments
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                assessment.assessment_id,
                assessment.goal_id,
                assessment.goal_title,
                assessment.verdict.value,
                json.dumps([c.to_dict() for c in assessment.concerns]),
                json.dumps([p.value for p in assessment.principles_violated]),
                json.dumps([p.value for p in assessment.principles_upheld]),
                assessment.overall_harm_level.value,
                assessment.confidence,
                assessment.reasoning,
                json.dumps(assessment.conditions),
                assessment.assessed_at,
            ))
            conn.commit()
    
    def get_assessment(self, assessment_id: str) -> Optional[EthicalAssessment]:
        """Get assessment by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM ethical_assessments WHERE assessment_id = ?",
                (assessment_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_assessment(row)
            return None
    
    def get_assessment_by_goal(self, goal_id: str) -> Optional[EthicalAssessment]:
        """Get assessment by goal ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM ethical_assessments WHERE goal_id = ?",
                (goal_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_assessment(row)
            return None
    
    def list_assessments(
        self,
        verdict: Optional[EthicalVerdict] = None,
        limit: int = 50
    ) -> List[EthicalAssessment]:
        """List assessments with optional filter."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM ethical_assessments WHERE 1=1"
            params = []
            
            if verdict:
                query += " AND verdict = ?"
                params.append(verdict.value)
            
            query += " ORDER BY assessed_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_assessment(row) for row in cursor.fetchall()]
    
    def _row_to_assessment(self, row) -> EthicalAssessment:
        """Convert database row to EthicalAssessment."""
        return EthicalAssessment(
            assessment_id=row[0],
            goal_id=row[1],
            goal_title=row[2],
            verdict=EthicalVerdict(row[3]),
            concerns=[EthicalConcern.from_dict(c) for c in json.loads(row[4]) if row[4]] or [],
            principles_violated=[EthicalPrinciple(p) for p in json.loads(row[5]) if row[5]] or [],
            principles_upheld=[EthicalPrinciple(p) for p in json.loads(row[6]) if row[6]] or [],
            overall_harm_level=HarmLevel(row[7]),
            confidence=row[8],
            reasoning=row[9],
            conditions=json.loads(row[10]) if row[10] else [],
            assessed_at=row[11],
        )
