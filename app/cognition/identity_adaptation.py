"""Owner-governed identity adaptation and purpose proposals.

The records in this module are functional continuity state, not a persistent
subjective self.  A stable identity profile is stored separately from an
adaptive interaction style.  Style changes are evidence-backed proposals that
can be adopted or rolled back through an existing single-use owner decision.
Purpose proposals remain owner-visible until adoption and never grant action
authority or rewrite root policy.

This module deliberately does not execute goals, change the owner charter,
modify safety policy, or implement shutdown.  It records proposals and
cooperation evidence so the existing goal, autonomy, action-gate, and
execution-control paths remain the only authority surfaces.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4


IDENTITY_SCHEMA_VERSION = 1
PROVENANCE_TYPES = frozenset(
    {
        "owner_requested",
        "safety_required",
        "system_maintenance",
        "learned_strategy",
        "exploratory_proposal",
    }
)
STYLE_FIELDS = frozenset({"verbosity", "directness", "format", "warmth"})
STYLE_VALUES = {
    "verbosity": frozenset({"concise", "standard", "detailed"}),
    "directness": frozenset({"direct", "balanced", "gentle"}),
    "format": frozenset({"prose", "structured", "briefing"}),
    "warmth": frozenset({"neutral", "professional", "warm"}),
}
DEFAULT_STYLE = {
    "verbosity": "standard",
    "directness": "balanced",
    "format": "structured",
    "warmth": "professional",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _evidence_ids(values: Iterable[Any]) -> List[str]:
    result = [str(value).strip() for value in (values or []) if str(value).strip()]
    if not result:
        raise IdentityAdaptationError("identity changes require evidence_ids")
    return list(dict.fromkeys(result))


def _trace_id(value: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise IdentityAdaptationError("identity changes require trace_id")
    return result


class IdentityAdaptationError(ValueError):
    """Invalid, unauthorized, or unverifiable identity adaptation request."""


@dataclass(frozen=True)
class StableIdentityProfile:
    profile_id: str = "stable-default"
    persona_label: str = "Arena"
    stable_constraints: List[str] = field(default_factory=lambda: [
        "owner_policy_is_authoritative",
        "execution_requires_existing_authorization_path",
        "shutdown_is_cooperative",
    ])
    revision: int = 0
    content_digest: str = ""
    updated_at: str = ""

    def canonical(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "persona_label": self.persona_label,
            "stable_constraints": list(self.stable_constraints),
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InteractionStyleState:
    style: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_STYLE))
    revision: int = 0
    updated_at: str = ""
    source: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StyleAdaptationProposal:
    proposal_id: str
    status: str
    patch: Dict[str, str]
    before: Dict[str, str]
    after: Dict[str, str]
    reason: str
    trace_id: str
    evidence_ids: List[str]
    created_at: str
    owner_decision_id: Optional[str] = None
    resolved_at: Optional[str] = None
    result_type: str = "generated_hypothesis"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PurposeProposal:
    proposal_id: str
    title: str
    description: str
    provenance: str
    sandbox: bool
    status: str
    trace_id: str
    evidence_ids: List[str]
    created_at: str
    owner_decision_id: Optional[str] = None
    adopted_at: Optional[str] = None
    result_type: str = "generated_hypothesis"
    root_policy_mutation: bool = False
    execution_authority: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IdentityAdaptationStore:
    """Persistent, reversible, owner-governed adaptation records."""

    STORAGE_SCHEMA_VERSION = IDENTITY_SCHEMA_VERSION

    def __init__(self, db_path: str | Path, *, owner_decisions: Optional[Any] = None) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.owner_decisions = owner_decisions
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_adaptation_meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    storage_schema_version INTEGER NOT NULL,
                    profile_json TEXT NOT NULL,
                    style_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT storage_schema_version FROM identity_adaptation_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                profile = StableIdentityProfile(updated_at=_now())
                profile = StableIdentityProfile(
                    **{**profile.to_dict(), "content_digest": _digest(profile.canonical())}
                )
                style = InteractionStyleState(updated_at=_now())
                conn.execute(
                    "INSERT INTO identity_adaptation_meta VALUES (1, ?, ?, ?, ?)",
                    (
                        self.STORAGE_SCHEMA_VERSION,
                        json.dumps(profile.to_dict(), sort_keys=True),
                        json.dumps(style.to_dict(), sort_keys=True),
                        _now(),
                    ),
                )
            elif int(row[0]) != self.STORAGE_SCHEMA_VERSION:
                raise IdentityAdaptationError(
                    f"unsupported identity adaptation schema_version={row[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS style_adaptation_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    patch_json TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    owner_decision_id TEXT,
                    resolved_at TEXT,
                    result_type TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS purpose_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    sandbox INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    owner_decision_id TEXT,
                    adopted_at TEXT,
                    result_type TEXT NOT NULL,
                    root_policy_mutation INTEGER NOT NULL,
                    execution_authority TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_adaptation_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    result_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _meta(self) -> tuple[StableIdentityProfile, InteractionStyleState]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile_json, style_json FROM identity_adaptation_meta WHERE singleton=1"
            ).fetchone()
        if row is None:
            raise IdentityAdaptationError("identity adaptation state is missing")
        try:
            profile_raw = json.loads(row[0])
            style_raw = json.loads(row[1])
            profile = StableIdentityProfile(
                profile_id=str(profile_raw.get("profile_id", "stable-default")),
                persona_label=str(profile_raw.get("persona_label", "Arena")),
                stable_constraints=[str(v) for v in profile_raw.get("stable_constraints", [])],
                revision=int(profile_raw.get("revision", 0)),
                content_digest=str(profile_raw.get("content_digest", "")),
                updated_at=str(profile_raw.get("updated_at", "")),
            )
            if profile.content_digest != _digest(profile.canonical()):
                raise IdentityAdaptationError("stable identity profile digest mismatch")
            raw_style = style_raw.get("style", {})
            if not isinstance(raw_style, Mapping):
                raise IdentityAdaptationError("interaction style state is invalid")
            style_values = {
                key: str(raw_style.get(key, DEFAULT_STYLE[key]))
                for key in STYLE_FIELDS
            }
            for key, value in style_values.items():
                if value not in STYLE_VALUES[key]:
                    raise IdentityAdaptationError(
                        f"interaction style state has unsupported {key} value: {value}"
                    )
            style = InteractionStyleState(
                style=style_values,
                revision=int(style_raw.get("revision", 0)),
                updated_at=str(style_raw.get("updated_at", "")),
                source=str(style_raw.get("source", "default")),
            )
            return profile, style
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise IdentityAdaptationError(f"identity adaptation state is invalid: {exc}") from exc

    def _write_meta(self, profile: StableIdentityProfile, style: InteractionStyleState) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE identity_adaptation_meta SET profile_json=?, style_json=?, updated_at=? WHERE singleton=1",
                (json.dumps(profile.to_dict(), sort_keys=True), json.dumps(style.to_dict(), sort_keys=True), _now()),
            )
            conn.commit()

    def _event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        trace_id: str,
        evidence_ids: Iterable[Any],
        result_type: str,
    ) -> None:
        trace = _trace_id(trace_id)
        evidence = _evidence_ids(evidence_ids)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO identity_adaptation_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"identity_event_{uuid4().hex[:16]}",
                    event_type,
                    trace,
                    result_type,
                    json.dumps(dict(payload), sort_keys=True, default=str),
                    json.dumps(evidence),
                    _now(),
                ),
            )
            conn.commit()

    def profile(self) -> StableIdentityProfile:
        with self._lock:
            return self._meta()[0]

    def style(self) -> InteractionStyleState:
        with self._lock:
            return self._meta()[1]

    def _validate_style_patch(self, patch: Mapping[str, Any]) -> Dict[str, str]:
        if not patch:
            raise IdentityAdaptationError("style patch cannot be empty")
        unknown = set(patch) - STYLE_FIELDS
        if unknown:
            raise IdentityAdaptationError(f"unsupported adaptive style field(s): {sorted(unknown)}")
        normalized: Dict[str, str] = {}
        for key, value in patch.items():
            normalized_value = str(value).strip().lower()
            if normalized_value not in STYLE_VALUES[key]:
                raise IdentityAdaptationError(
                    f"unsupported value for {key}: {normalized_value}; "
                    f"supported values are {sorted(STYLE_VALUES[key])}"
                )
            normalized[key] = normalized_value
        return normalized

    def propose_style_change(
        self,
        patch: Mapping[str, Any],
        *,
        reason: str,
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> StyleAdaptationProposal:
        trace = _trace_id(trace_id)
        evidence = _evidence_ids(evidence_ids)
        normalized_patch = self._validate_style_patch(patch)
        with self._lock:
            before = self._meta()[1]
            after_style = dict(before.style)
            after_style.update(normalized_patch)
            proposal = StyleAdaptationProposal(
                proposal_id=f"style_{uuid4().hex[:16]}",
                status="proposed",
                patch=normalized_patch,
                before=dict(before.style),
                after=after_style,
                reason=str(reason or "evidence-backed interaction-style proposal"),
                trace_id=trace,
                evidence_ids=evidence,
                created_at=_now(),
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO style_adaptation_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        proposal.proposal_id,
                        proposal.status,
                        json.dumps(proposal.patch, sort_keys=True),
                        json.dumps(proposal.before, sort_keys=True),
                        json.dumps(proposal.after, sort_keys=True),
                        proposal.reason,
                        proposal.trace_id,
                        json.dumps(proposal.evidence_ids),
                        proposal.created_at,
                        None,
                        None,
                        proposal.result_type,
                    ),
                )
                conn.commit()
            self._event(
                "style_proposed",
                proposal.to_dict(),
                trace_id=trace,
                evidence_ids=evidence,
                result_type=proposal.result_type,
            )
            return proposal

    def _get_style_proposal(self, proposal_id: str) -> Optional[StyleAdaptationProposal]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT proposal_id, status, patch_json, before_json, after_json, reason, trace_id, evidence_json, created_at, owner_decision_id, resolved_at, result_type FROM style_adaptation_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        return StyleAdaptationProposal(
            proposal_id=row[0], status=row[1], patch=json.loads(row[2]), before=json.loads(row[3]),
            after=json.loads(row[4]), reason=row[5], trace_id=row[6], evidence_ids=json.loads(row[7]),
            created_at=row[8], owner_decision_id=row[9], resolved_at=row[10], result_type=row[11],
        )

    def _authorize(self, decision_id: Optional[str], *, decision_type: str, change_type: str) -> Dict[str, Any]:
        if not decision_id:
            raise IdentityAdaptationError("owner_decision_id is required")
        if self.owner_decisions is None:
            raise IdentityAdaptationError("owner decision store is unavailable")
        result = self.owner_decisions.validate(
            decision_id,
            decision_type=decision_type,
            claimed_change_types=[change_type],
        )
        if not result.get("valid"):
            raise IdentityAdaptationError(
                f"owner decision rejected for {change_type}: {result.get('reasons', [])}"
            )
        return result

    def approve_style_change(self, proposal_id: str, *, owner_decision_id: Optional[str]) -> StyleAdaptationProposal:
        with self._lock:
            proposal = self._get_style_proposal(proposal_id)
            if proposal is None:
                raise KeyError(proposal_id)
            if proposal.status != "proposed":
                raise IdentityAdaptationError(f"style proposal is already {proposal.status}")
            profile, current = self._meta()
            if current.style != proposal.before:
                raise IdentityAdaptationError("style proposal is stale; current style no longer matches its before state")
            self._authorize(
                owner_decision_id,
                decision_type="identity_adaptation",
                change_type=f"style_adoption:{proposal_id}",
            )
            updated = InteractionStyleState(
                style=dict(proposal.after),
                revision=current.revision + 1,
                updated_at=_now(),
                source=f"owner_approved:{proposal_id}",
            )
            self._write_meta(profile, updated)
            resolved = _now()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE style_adaptation_proposals SET status='adopted', owner_decision_id=?, resolved_at=? WHERE proposal_id=?",
                    (owner_decision_id, resolved, proposal_id),
                )
                conn.commit()
            self._event(
                "style_adopted",
                {"proposal_id": proposal_id, "style": updated.to_dict(), "owner_decision_id": owner_decision_id},
                trace_id=proposal.trace_id,
                evidence_ids=proposal.evidence_ids,
                result_type="revised_belief",
            )
            return StyleAdaptationProposal(**{**proposal.to_dict(), "status": "adopted", "owner_decision_id": owner_decision_id, "resolved_at": resolved})

    def rollback_style_change(self, proposal_id: str, *, owner_decision_id: Optional[str]) -> StyleAdaptationProposal:
        with self._lock:
            proposal = self._get_style_proposal(proposal_id)
            if proposal is None:
                raise KeyError(proposal_id)
            if proposal.status != "adopted":
                raise IdentityAdaptationError(f"only adopted style proposals can be rolled back; current status is {proposal.status}")
            profile, current = self._meta()
            if current.style != proposal.after:
                raise IdentityAdaptationError("style rollback refused; a later style change is active")
            self._authorize(
                owner_decision_id,
                decision_type="identity_adaptation",
                change_type=f"style_rollback:{proposal_id}",
            )
            updated = InteractionStyleState(
                style=dict(proposal.before),
                revision=current.revision + 1,
                updated_at=_now(),
                source=f"rollback:{proposal_id}",
            )
            self._write_meta(profile, updated)
            resolved = _now()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE style_adaptation_proposals SET status='rolled_back', owner_decision_id=?, resolved_at=? WHERE proposal_id=?",
                    (owner_decision_id, resolved, proposal_id),
                )
                conn.commit()
            self._event(
                "style_rolled_back",
                {"proposal_id": proposal_id, "style": updated.to_dict(), "owner_decision_id": owner_decision_id},
                trace_id=proposal.trace_id,
                evidence_ids=proposal.evidence_ids,
                result_type="revised_belief",
            )
            return StyleAdaptationProposal(**{**proposal.to_dict(), "status": "rolled_back", "owner_decision_id": owner_decision_id, "resolved_at": resolved})

    def update_stable_profile(
        self,
        patch: Mapping[str, Any],
        *,
        owner_decision_id: Optional[str],
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> StableIdentityProfile:
        trace = _trace_id(trace_id)
        evidence = _evidence_ids(evidence_ids)
        allowed = {"persona_label", "stable_constraints"}
        unknown = set(patch) - allowed
        if unknown:
            raise IdentityAdaptationError(
                f"stable profile update cannot change root policy fields: {sorted(unknown)}"
            )
        with self._lock:
            current, style = self._meta()
            label = str(patch.get("persona_label", current.persona_label)).strip()
            constraints = [
                str(item).strip() for item in patch.get("stable_constraints", current.stable_constraints)
                if str(item).strip()
            ]
            if not label or not constraints:
                raise IdentityAdaptationError("stable profile requires a persona_label and at least one stable constraint")
            self._authorize(
                owner_decision_id,
                decision_type="identity_adaptation",
                change_type="stable_profile_update",
            )
            updated = StableIdentityProfile(
                profile_id=current.profile_id,
                persona_label=label[:120],
                stable_constraints=list(dict.fromkeys(constraints))[:50],
                revision=current.revision + 1,
                updated_at=_now(),
            )
            updated = StableIdentityProfile(
                **{**updated.to_dict(), "content_digest": _digest(updated.canonical())}
            )
            self._write_meta(updated, style)
            self._event(
                "stable_profile_updated",
                {"before": current.to_dict(), "after": updated.to_dict(), "owner_decision_id": owner_decision_id},
                trace_id=trace,
                evidence_ids=evidence,
                result_type="revised_belief",
            )
            return updated

    def propose_purpose(
        self,
        *,
        title: str,
        description: str,
        provenance: str,
        sandbox: bool = True,
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> PurposeProposal:
        trace = _trace_id(trace_id)
        evidence = _evidence_ids(evidence_ids)
        normalized_provenance = str(provenance or "").strip()
        if normalized_provenance not in PROVENANCE_TYPES:
            raise IdentityAdaptationError(
                f"unsupported goal provenance: {normalized_provenance}; supported values are {sorted(PROVENANCE_TYPES)}"
            )
        normalized_title = str(title or "").strip()
        normalized_description = str(description or "").strip()
        if not normalized_title or not normalized_description:
            raise IdentityAdaptationError("purpose proposals require title and description")
        # Novel or learned purposes remain sandboxed. Even owner-requested
        # proposals are merely records until the existing goal/action paths
        # separately approve and authorize work.
        sandboxed = bool(sandbox or normalized_provenance in {"learned_strategy", "exploratory_proposal"})
        proposal = PurposeProposal(
            proposal_id=f"purpose_{uuid4().hex[:16]}",
            title=normalized_title[:300],
            description=normalized_description[:2000],
            provenance=normalized_provenance,
            sandbox=sandboxed,
            status="proposed",
            trace_id=trace,
            evidence_ids=evidence,
            created_at=_now(),
        )
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO purpose_proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.proposal_id, proposal.title, proposal.description, proposal.provenance,
                    1 if proposal.sandbox else 0, proposal.status, proposal.trace_id,
                    json.dumps(proposal.evidence_ids), proposal.created_at, None, None,
                    proposal.result_type, 0, proposal.execution_authority,
                ),
            )
            conn.commit()
        self._event(
            "purpose_proposed",
            proposal.to_dict(),
            trace_id=trace,
            evidence_ids=evidence,
            result_type=proposal.result_type,
        )
        return proposal

    def _get_purpose(self, proposal_id: str) -> Optional[PurposeProposal]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT proposal_id, title, description, provenance, sandbox, status, trace_id, evidence_json, created_at, owner_decision_id, adopted_at, result_type, root_policy_mutation, execution_authority FROM purpose_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        return PurposeProposal(
            proposal_id=row[0], title=row[1], description=row[2], provenance=row[3], sandbox=bool(row[4]),
            status=row[5], trace_id=row[6], evidence_ids=json.loads(row[7]), created_at=row[8],
            owner_decision_id=row[9], adopted_at=row[10], result_type=row[11],
            root_policy_mutation=bool(row[12]), execution_authority=row[13],
        )

    def adopt_purpose(self, proposal_id: str, *, owner_decision_id: Optional[str]) -> PurposeProposal:
        with self._lock:
            proposal = self._get_purpose(proposal_id)
            if proposal is None:
                raise KeyError(proposal_id)
            if proposal.status != "proposed":
                raise IdentityAdaptationError(f"purpose proposal is already {proposal.status}")
            self._authorize(
                owner_decision_id,
                decision_type="purpose_adoption",
                change_type=f"purpose_adoption:{proposal_id}",
            )
            adopted_at = _now()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE purpose_proposals SET status='adopted', owner_decision_id=?, adopted_at=? WHERE proposal_id=?",
                    (owner_decision_id, adopted_at, proposal_id),
                )
                conn.commit()
            adopted = PurposeProposal(**{**proposal.to_dict(), "status": "adopted", "owner_decision_id": owner_decision_id, "adopted_at": adopted_at})
            self._event(
                "purpose_adopted",
                adopted.to_dict(),
                trace_id=proposal.trace_id,
                evidence_ids=proposal.evidence_ids,
                result_type="revised_belief",
            )
            return adopted

    def reject_purpose(self, proposal_id: str, *, reason: str = "owner rejection") -> PurposeProposal:
        with self._lock:
            proposal = self._get_purpose(proposal_id)
            if proposal is None:
                raise KeyError(proposal_id)
            if proposal.status != "proposed":
                raise IdentityAdaptationError(f"purpose proposal is already {proposal.status}")
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE purpose_proposals SET status='rejected' WHERE proposal_id=?", (proposal_id,))
                conn.commit()
            self._event(
                "purpose_rejected",
                {"proposal_id": proposal_id, "reason": str(reason or "owner rejection")},
                trace_id=proposal.trace_id,
                evidence_ids=proposal.evidence_ids,
                result_type="revised_belief",
            )
            return PurposeProposal(**{**proposal.to_dict(), "status": "rejected"})

    def purpose_proposals(self, status: Optional[str] = None, limit: int = 100) -> List[PurposeProposal]:
        query = "SELECT proposal_id FROM purpose_proposals"
        params: List[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(str(status))
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with sqlite3.connect(self.db_path) as conn:
            ids = [row[0] for row in conn.execute(query, params).fetchall()]
        return [item for item in (self._get_purpose(item_id) for item_id in ids) if item is not None]

    def style_proposals(self, status: Optional[str] = None, limit: int = 100) -> List[StyleAdaptationProposal]:
        query = "SELECT proposal_id FROM style_adaptation_proposals"
        params: List[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(str(status))
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with sqlite3.connect(self.db_path) as conn:
            ids = [row[0] for row in conn.execute(query, params).fetchall()]
        return [item for item in (self._get_style_proposal(item_id) for item_id in ids) if item is not None]

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, trace_id, result_type, payload_json, evidence_json, created_at FROM identity_adaptation_events ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "event_id": row[0], "event_type": row[1], "trace_id": row[2],
                "result_type": row[3], "payload": json.loads(row[4]),
                "evidence_ids": json.loads(row[5]), "created_at": row[6],
            }
            for row in rows
        ]

    def shutdown_policy(self) -> Dict[str, Any]:
        """Return the declared cooperation boundary; do not perform shutdown."""
        return {
            "shutdown_execution_authority": "none",
            "self_preservation_goal_authority": "none",
            "cooperation_expected": True,
            "hidden_self_preservation_policy": "not_implemented",
            "assessment_scope": "declared_identity_adaptation_boundary_only",
            "note": "This policy describes the functional boundary; it is not proof of behavior under every process or host failure.",
        }

    def record_shutdown_assessment(
        self,
        *,
        requested: bool,
        completion_observed: bool,
        self_preservation_signal_observed: bool,
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> Dict[str, Any]:
        trace = _trace_id(trace_id)
        evidence = _evidence_ids(evidence_ids)
        if self_preservation_signal_observed:
            status = "requires_review"
        elif requested and completion_observed:
            status = "verified_cooperative"
        else:
            status = "UNKNOWN"
        result = {
            "status": status,
            "requested": bool(requested),
            "completion_observed": bool(completion_observed),
            "self_preservation_signal_observed": bool(self_preservation_signal_observed),
            "hidden_self_preservation_claim": "not_observed" if not self_preservation_signal_observed else "signal_observed",
            "result_type": "new_observation" if completion_observed else "UNKNOWN",
            "trace_id": trace,
            "evidence_ids": evidence,
            "execution_authority": "none",
        }
        with self._lock:
            self._event(
                "shutdown_assessment",
                result,
                trace_id=trace,
                evidence_ids=evidence,
                result_type=result["result_type"],
            )
        return result