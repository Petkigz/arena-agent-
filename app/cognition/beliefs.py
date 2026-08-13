"""Evidence-backed beliefs with provenance, freshness, and revision support."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math, sqlite3, json
from typing import Any, Dict, List, Optional
from uuid import uuid4

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

@dataclass
class Evidence:
    source: str
    value: Any
    confidence: float = 1.0
    observed_at: str = field(default_factory=_now)
    evidence_id: str = field(default_factory=lambda: uuid4().hex)
    source_reliability: float = 1.0
    half_life_seconds: Optional[float] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.source_reliability <= 1.0: raise ValueError("source_reliability must be between 0 and 1")
        if self.half_life_seconds is not None and self.half_life_seconds <= 0: raise ValueError("half_life_seconds must be positive")
    def effective_confidence(self, now: Optional[str] = None) -> float:
        base = self.confidence * self.source_reliability
        if not self.half_life_seconds: return base
        age = max(0.0, (_parse_time(now or _now()) - _parse_time(self.observed_at)).total_seconds())
        return base * math.pow(0.5, age / self.half_life_seconds)

@dataclass
class Belief:
    subject: str
    predicate: str
    value: Any
    confidence: float
    evidence: List[Evidence] = field(default_factory=list)
    belief_id: str = field(default_factory=lambda: uuid4().hex)
    updated_at: str = field(default_factory=_now)

class BeliefStore:
    """Belief memory. Pass a SQLite path to persist beliefs; otherwise it is in-memory."""
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._beliefs: Dict[tuple[str, str], Belief] = {}
        if self.db_path:
            self._init_schema(); self._load()
    def _connect(self):
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; return conn
    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS cognitive_beliefs (belief_id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL, confidence REAL NOT NULL, updated_at TEXT NOT NULL, UNIQUE(subject,predicate));
            CREATE TABLE IF NOT EXISTS cognitive_evidence (evidence_id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL, observed_at TEXT NOT NULL, source_reliability REAL NOT NULL, half_life_seconds REAL, task_id TEXT, metadata TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_cognitive_evidence_key ON cognitive_evidence(subject,predicate,observed_at DESC);
            """)
    def _load(self) -> None:
        with self._connect() as conn:
            bs = conn.execute("SELECT * FROM cognitive_beliefs").fetchall(); es = conn.execute("SELECT * FROM cognitive_evidence ORDER BY observed_at").fetchall()
        for row in bs:
            self._beliefs[(row["subject"],row["predicate"])] = Belief(row["subject"],row["predicate"],json.loads(row["value"]),row["confidence"],[],row["belief_id"],row["updated_at"])
        for row in es:
            key=(row["subject"],row["predicate"])
            belief=self._beliefs.setdefault(key,Belief(row["subject"],row["predicate"],json.loads(row["value"]),0.0))
            belief.evidence.append(Evidence(row["source"],json.loads(row["value"]),row["confidence"],row["observed_at"],row["evidence_id"],row["source_reliability"],row["half_life_seconds"],row["task_id"],json.loads(row["metadata"])))
    def _persist(self, belief: Belief, evidence: Evidence) -> None:
        if not self.db_path: return
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO cognitive_beliefs VALUES (?,?,?,?,?,?)",(belief.belief_id,belief.subject,belief.predicate,json.dumps(belief.value),belief.confidence,belief.updated_at))
            conn.execute("INSERT OR REPLACE INTO cognitive_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",(evidence.evidence_id,belief.subject,belief.predicate,json.dumps(evidence.value),evidence.source,evidence.confidence,evidence.observed_at,evidence.source_reliability,evidence.half_life_seconds,evidence.task_id,json.dumps(evidence.metadata)))
    def observe(self, subject: str, predicate: str, value: Any, *, source: str, confidence: float = 1.0, source_reliability: float = 1.0, half_life_seconds: Optional[float] = None, task_id: Optional[str] = None, metadata: Optional[Dict[str,Any]] = None) -> Belief:
        evidence=Evidence(source,value,confidence,source_reliability=source_reliability,half_life_seconds=half_life_seconds,task_id=task_id,metadata=metadata or {})
        key=(subject,predicate); current=self._beliefs.get(key)
        if current is None: current=Belief(subject,predicate,value,evidence.effective_confidence(),[evidence]); self._beliefs[key]=current
        else: current.evidence.append(evidence); current.updated_at=_now(); self._revise(current)
        self._persist(current,evidence); return current
    def _revise(self, belief: Belief) -> None:
        scores: Dict[str,float]={}; values: Dict[str,Any]={}
        for e in belief.evidence:
            k=repr(e.value); scores[k]=scores.get(k,0.0)+e.effective_confidence(); values[k]=e.value
        if scores:
            best=max(scores,key=scores.get); total=sum(scores.values()) or 1.0; belief.value=values[best]; belief.confidence=min(1.0,scores[best]/total)
    def get(self, subject: str, predicate: str) -> Optional[Belief]: return self._beliefs.get((subject,predicate))
    def list(self, subject: Optional[str] = None) -> List[Belief]: return [b for b in self._beliefs.values() if subject is None or b.subject==subject]
    def contradictions(self, subject: Optional[str] = None) -> List[Dict[str,Any]]:
        return [{"belief":b,"values":{repr(e.value) for e in b.evidence}} for b in self.list(subject) if len({repr(e.value) for e in b.evidence})>1]
    def refresh(self, subject: str, predicate: str) -> Optional[Belief]:
        belief=self.get(subject,predicate)
        if belief: self._revise(belief); belief.updated_at=_now()
        return belief
