# Rules & Permission Boundaries

This file defines the authorization model for Arena's cognitive system.

## Design Philosophy

Arena is a **full-capability coworker**, not a restricted demo. All capabilities are available, but sensitive actions require explicit user approval. The system distinguishes between:

- **Can the agent do this?** (capability availability)
- **May it execute this autonomously right now?** (approval gate)

Capabilities are **approval-gated**, not permanently removed from consideration. The owner defines which actions require confirmation and may pause all execution, block exact actions, lower the autonomous safety ceiling, or require approval for every action or plan.

## Authority Levels

### Level 0: Read/Observe (Fully Autonomous)
- Read files, directories, and databases
- Search local memory and knowledge stores
- Inspect screen state and screenshots
- Conduct web searches (read-only)
- Monitor system state and hardware metrics
- Query beliefs, outcomes, and lessons learned

### Level 1: Draft (Autonomous in Workspace)
- Create or update drafts (CV, cover letters, reports, code)
- Prepare emails, forms, or social media posts in draft status
- Generate summaries and analysis documents
- Create planning artifacts and task breakdowns

### Level 2: Reversible Action (Autonomous with Active Log)
- Organize files and directories
- Open applications (allow-listed or user-approved)
- Fill out web forms (without submitting)
- Execute scripts in sandboxed environments
- Install packages in virtual environments
- Create git commits and branches

### Level 3: Sensitive/Irreversible Action (REQUIRES Explicit Approval)
- Submitting applications, forms, or registrations
- Sending emails, messages, or publishing content
- Deleting files or uninstalling packages
- Executing real financial transactions
- Running code on production systems
- Accessing external APIs with credentials
- Modifying system configurations

## Decision-stage separation

The system must not confuse analysis with permission. It may consider
uncomfortable, sensitive, or restricted alternatives and explain why they
could be useful. Those alternatives should remain visible with ranked expected
benefits, risks, uncertainty, reversibility, and likely consequences.

The stages are separate and auditable:

1. **Consideration:** side-effect-free comparison; no alternative is executed.
2. **Recommendation:** the agent explains a preferred option; no authority is granted.
3. **Authorization:** owner policy or explicit approval authorizes one exact scope.
4. **Execution:** only that authorized action and unmodified payload may run.

Policy restrictions apply to authorization and execution, not to merely
thinking about or explaining an alternative. Approval of one option never
implicitly approves another option, a changed payload, or a broader scope.

## Approval Model

### Default Approval Requirements

The following action types require explicit user approval by default:

```python
REQUIRES_APPROVAL = {
    # Level 3 actions
    "send_email", "send_message", "publish_content",
    "delete_file", "uninstall_package",
    "execute_financial_transaction",
    "run_production_code",
    "access_external_api",
    "modify_system_config",
    
    # User can add custom restrictions
    # "custom_action_type",
}
```

### Configurable Policies

The persistent Owner Control Plane (`app/cognition/owner_control.py`) supports:

1. **Control mode** — observe only, suggest only, approve every action, approve
   each plan, bounded autonomy, or custom allowlist.
2. **Autonomous ceiling** — choose the highest delegated level from 0 through 2.
3. **Per-action rules** — actions that always require approval or are absolutely blocked.
4. **Emergency pause** — stop all capability execution before prediction or resource work.
5. **Resource/domain scopes** — additional bounded-execution constraints (expanded incrementally).

The authenticated control surface is:

```text
GET    /owner-control
PUT    /owner-control
POST   /owner-control/pause
GET    /owner-control/approvals
POST   /owner-control/approvals/{action_id}/decision
GET    /owner-control/authorizations
POST   /owner-control/authorizations
DELETE /owner-control/authorizations/{authorization_id}
POST   /owner-control/execute-authorized
GET    /owner-control/plans
GET    /owner-control/plans/{plan_id}
PUT    /owner-control/plans/{plan_id}
POST   /owner-control/plans/{plan_id}/decision
POST   /owner-control/plans/{plan_id}/revoke
POST   /owner-control/plans/{plan_id}/execute
```

In approve-each-plan mode, generated `ExecutionPlan` step graphs are persisted as
revisioned review snapshots. The owner can edit step descriptions and evidence
contracts, approve or reject an exact revision, revoke it before completion, and
start execution separately. Unknown dependencies, dependency cycles, stale
revision writes, and execution of unapproved plans are rejected. Plan approval
only delegates Levels 0–2 up to the configured ceiling; Level 3 and explicit
per-action rules still require exact action authorization.

Persistent project DAG scheduling is owner opt-in (`PUT /projects/{id}/scheduler`)
and bounded per cycle. Exact action/payload steps are reviewable in
approve-each-plan mode. Unverified steps enter `waiting_evidence` and are never
blindly repeated; Level-3 steps enter `waiting_approval` and resume only with the
matching single-use authorization. `POST /projects/{id}/run-ready` runs a bounded
batch manually. Pending project/action approvals are available under
`/owner-control/approvals`.

Explicit approval creates a short-lived grant bound to the exact action type and
SHA-256 digest of the canonical payload. Grants are single-use by default,
expire within at most one hour, are lost on process restart, and are all revoked
by emergency pause. Changing any payload field invalidates the grant.

Executing that grant does not bypass cognition: the exact proposal passes through
ActionGate, capability execution, independent observation, tri-state goal
verification, prediction-error measurement, reflection, outcome/lesson storage,
and causal learning. No automatic replan is permitted under the old grant;
an alternative or retry requires a new owner authorization.

The default remains bounded autonomy through Level 2. Owner policy can tighten
that authority but cannot silently make a manifest Level-3 action autonomous.

## Continual-learning authority

Verified success may create a **pending** LoRA training candidate only. Automatic
approval, dataset inclusion, training, activation, and claims of improvement are
forbidden. Candidates are deterministically redacted and deduplicated; the owner
may edit, approve, or reject each exact pair. Export requires at least five
approved examples and creates a reproducible held-out evaluation split with a
source-candidate manifest. Selecting a PEFT adapter in Arena is metadata only
until the external inference provider actually loads/merges it and a before/after
held-out evaluation demonstrates improvement.

## Domain-Specific Policies (Optional)

Users may define additional restrictions for specific domains. These are **user-configured**, not hardcoded:

### Cybersecurity & Pentesting (User-Defined Scope)
- **Default:** All targets allowed with Level 3 approval
- **Optional restriction:** User can define authorized target scopes
  ```python
  # User can add this to their config if desired
  PENTEST_AUTHORIZED_TARGETS = ["192.168.1.0/24", "*.local.lab"]
  ```

### Financial Trading (User-Defined Mode)
- **Default:** Real transactions allowed with Level 3 approval
- **Optional restriction:** User can force simulation mode
  ```python
  # User can add this to their config if desired
  TRADING_MODE = "simulation"  # or "live"
  ```

## Audit Trail

All actions are logged with:
- Timestamp
- Action type and payload
- Approval status (autonomous vs user-approved)
- Execution result
- Verification outcome
- Lessons learned

Logs are stored in:
- `data/logs/audit.log` — Action audit trail
- `data/outcomes.db` — Strategy outcomes
- `data/lessons.db` — Extracted lessons
- `data/patterns.db` — Planning patterns

## Modifying Rules

Use the Owner Control API to change mode, approval lists, block lists, and the
autonomous ceiling. Changes are persisted atomically to
`data/owner_control.json` and apply to the next proposal without a restart.

Manifest Level-3 classifications remain a minimum safety boundary. Lowering
owner restrictions must not downgrade a tool's authoritative manifest level.

## Security Model

Arena uses a **trust-but-verify** model:

1. **Trust:** Capabilities are available by default
2. **Gate:** Sensitive actions require approval
3. **Verify:** Goal verification confirms outcomes
4. **Learn:** Lessons are extracted from failures
5. **Audit:** All actions are logged for review

This model balances autonomy with safety, allowing the system to operate efficiently while maintaining user control over critical actions.
