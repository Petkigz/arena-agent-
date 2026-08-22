# Rules & Permission Boundaries

This file defines the authorization model for Arena's cognitive system.

## Design Philosophy

Arena is a **full-capability coworker**, not a restricted demo. All capabilities are available, but sensitive actions require explicit user approval. The system distinguishes between:

- **Can the agent do this?** (capability availability)
- **May it execute this autonomously right now?** (approval gate)

Capabilities are **approval-gated**, not permanently disabled. The user defines which actions require confirmation.

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

Users can customize approval requirements via:

1. **ActionGate rules** — Define which action types require approval
2. **Resource policies** — Set budget limits for autonomous execution
3. **Domain scopes** — Restrict actions to specific targets (optional)

Example custom policy:
```python
# In app/cognition/action_gate.py
CUSTOM_APPROVAL_RULES = {
    "run_command": {
        "requires_approval": True,
        "allowed_patterns": ["ls", "cat", "grep"],  # Allow safe commands
        "blocked_patterns": ["rm -rf", "sudo"],     # Block dangerous commands
    }
}
```

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

To add custom approval rules:

1. Edit `app/cognition/action_gate.py` — Add rules to `CUSTOM_APPROVAL_RULES`
2. Edit this file — Document your custom policies
3. Restart the system — Rules are loaded at startup

To remove restrictions:

1. Remove action types from `REQUIRES_APPROVAL`
2. Or set `requires_approval: False` in custom rules
3. Restart the system

## Security Model

Arena uses a **trust-but-verify** model:

1. **Trust:** Capabilities are available by default
2. **Gate:** Sensitive actions require approval
3. **Verify:** Goal verification confirms outcomes
4. **Learn:** Lessons are extracted from failures
5. **Audit:** All actions are logged for review

This model balances autonomy with safety, allowing the system to operate efficiently while maintaining user control over critical actions.
