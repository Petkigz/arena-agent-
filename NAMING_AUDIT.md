# Naming & Consistency Audit — Full System Scan

**Scanned:** 2026-08-21 · Scope: capability strings, action types, tool names,
safety-level sources, WebSocket message types, manifest↔method signatures.

---

## Finding 1 (CRITICAL) — Three conflicting sources of safety truth

Tool safety levels are declared in **three** places that disagree:

| Source | Count | Example |
|---|---|---|
| `app/tools/manifest.py` `safety_level` | 66 tools | `search_files`→0, `create_note`→1, `send_email`→3 |
| `app/policy.py` `PolicyEvaluator` | ~20 old names | `read_file`, `capture_screen`, `search_notes` |
| `app/cognition/action_proposal.py` `POLICY_ACTION_MAP` | 7 mappings | `search_files`→`read_file` |

**Consequence:** `ActionGate.evaluate_proposal` calls `PolicyEvaluator.evaluate_action`
for every action, but only 7 action types are mapped to a known policy name. The
other ~59 tools hit the fallback `"Unknown action → Level 3 requires approval"`.
So **harmless reads (`list_notes`, `weather`, `translate`, `read_document`,
`analyze_data`) all require approval**, contradicting their manifest safety level.

The manifest's safety level is the well-thought-out truth but is **never consulted**.

## Finding 2 (CRITICAL) — Manifest breaks zero-arg tool methods

`ToolRegistry.execute_registered_tool` always calls `handler(payload)`. But many
tools registered *directly* (not via `_wrap`) are zero-arg `@classmethod`/
`@staticmethod` methods, so they get `payload` as an unexpected argument:

```
TypeError: NotesManager.list_notes() takes 1 positional argument but 2 were given
```

Affected: `list_notes`, `list_apps`, `list_workspace`, `list_events`,
`due_reminders`, `list_windows`, `screen_capture`, `camera_photo`,
`resolve_location`, `daily_briefing`, `opsec_audit`, `read_inbox`,
`phone_screenshot`.

## Finding 3 (MEDIUM) — `action_approval` message is dead on both ends

- `frontend/src/services/websocket.ts` defines `approveAction()` → sends
  `action_approval`.
- No UI component ever calls it, and the server has **no handler** for it.
- The runtime sets `WAITING_FOR_USER` on Level-3 blocks, but there is no resume/
  approval path. → The approval flow is half-built.

## Finding 4 (RESOLVED) — Dotted vs underscore capabilities

`goal_interpreter` emits dotted `required_capabilities` (`filesystem.search`,
`vision.analyze`) while action types are underscores (`search_files`,
`vision_analyze`). Fixed in `runtime.check_capability_availability` via
dot/underscore + action-stem normalization.

## Finding 5 (RESOLVED) — `wake_word_detected` was unhandled

Fixed earlier (server now routes it to `VoiceService.notify_wake_word`).

---

## Fix plan (implemented this session)

1. **Manifest safety_level becomes authoritative** in `ActionGate`.
2. **Wrap all zero-arg tools** in the manifest (`_ignore_payload`).
3. **Add a server handler + minimal approval store for `action_approval`**.
