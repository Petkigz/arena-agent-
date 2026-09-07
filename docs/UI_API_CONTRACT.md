# Arena UI API Contract

Round-21e. The shared specification every client (web, desktop, future Android) codes
against — per the design review: *"share design tokens, UX rules, component
specifications, state models, API contracts — not component source."* The HTTP/WS backend
is the single source of truth; this document freezes the UI-facing subset. All three
clients must consume these endpoints as specified, so a future mobile client is coded
against the document, not against the web's fetch calls.

Design tokens and the Beanie state model live in `design/tokens.json` (see
`docs/UI_UNIFICATION_PLAN.md`). This document covers transport + payloads.

## 1. WebSocket — `/ws` (conversation transport)

Client → server messages:

| type | payload | purpose |
| --- | --- | --- |
| `join_conversation` | `conversation_id` | join a conversation room |
| `user_message` | `conversation_id`, `content` | send a message (streams the reply) |
| `create_conversation` | `title` | create + join a conversation |
| `list_conversations` | — | request the conversation list |
| `get_history` | `conversation_id` | request the message history |

Server → client messages:

| type | payload | purpose |
| --- | --- | --- |
| `conversation_list` | `conversations: [{id\|conversation_id, title}]` | sidebar list |
| `conversation_history` | `conversation_id`, `messages: [{message_id, role, content, created_at, trace_id?}]` | durable history on join; legacy rows may lack trace links |
| `conversation_created` | `conversation_id`, `title` | after create |
| `message_token` | `conversation_id`, `message_id`, `token`, `done` | streaming reply (token-by-token; `done: true` ends the turn) |
| `cognitive_metadata` | `conversation_id`, `message_id`, `trace_id`, `epistemic_presentation`, `grounding` | evidence metadata for one exact assistant reply, never the latest message by position |
| `correction_recorded` | `conversation_id`, `correction_type`, `signal`, `target_trace_id`, `candidate_id`, `generalized`, `duplicate` | an explicit in-chat owner correction was understood and recorded through the existing owner-correction path; the candidate stays pending owner review. `duplicate=true` retries stay silent. Clients may ignore it; web shows a transient notice, desktop shows a note above the composer |
| `room_message` | `message_id`, `content` | message from another client in the shared room (echo suppression is client-side) |
| `action_step` | `label`, `status` | streamed tool activity attached to the assistant reply; `status` streams `in_progress` → `complete` (web: ActionSteps, Android: ToolActivity, desktop: Live Context rail) |
| `conversation_activity` | `conversation_id` | owner-wide signal: another device moved the active conversation (cross-device follow) |
| `error` | `message` | transport/processing error |

Client rule (UX): locally sent messages render immediately; `room_message` echoes of our
own sends are suppressed client-side (`_sent_echoes` pattern).

## 2. HTTP — UI-facing endpoints

Auth: optional API key header on every call (shared setting `api_key`).

### Core
| endpoint | shape (UI-relevant) |
| --- | --- |
| `GET /health` | `{status}` — connection indicator |
| `GET /api/status` | presence/agent status — drives the Beanie orb |
| `GET /api/hardware-stats` | hardware stats for the context rail |
| `POST /chat` | one-shot chat `{reply}` (non-streaming fallback) |
| `GET /conversations` | conversation list |
| `GET /projects`, `GET /projects/{project_id}` | `{projects: [{name, status, progress_percent, …}]}` — workspace |
| `POST /projects` | create project |
| `GET /memories` | list of memory dicts |
| `GET /memories/page` | bounded page `{items, …}` |
| `GET /knowledge/graph` | `{nodes, edges}` — knowledge graph view |
| `GET /settings` / `POST /settings` | shared settings (theme, voice, models, api key) |
| `GET /models` / `POST /models/config` | model selection |
| `GET /voice/piper-voices` / `POST /voice/piper/select` | voice list + selection |

### Response review (Phase 1.4 — web controls)

| endpoint | shape (UI-relevant) |
| --- | --- |
| `GET /cognition/traces/{trace_id}/usefulness` | `{success, trace_id, feedback: [...]}` — existing explicit owner ratings |
| `POST /cognition/traces/{trace_id}/usefulness` | `{usefulness, note?, submission_id?}` → `{success, feedback}`; does not change verification |
| `GET /benchmarks/phase1/tasks/evaluations` | optional `trace_id`, `split=held_out\|contract`, `limit`; `{success, report, evaluations}` |
| `POST /benchmarks/phase1/tasks/evaluations` | `{trace_id, task_key, observed_outcome, usefulness?, split?, condition?, correction_received?, evidence_ids?, note?, submission_id?}` → `{success, evaluation}`; measurement only |
| `GET /self-awareness/introspection/{trace_id}` | existing `{success, facts, explanation, epistemic_presentation, grounding}` used by **Why this response?** and the correction editor |
| `POST /loras/training-candidates/owner-correction` | existing correction route; `trace_id` binds source/strategy, candidate stays pending training review |

Usefulness feedback and task-evaluation usefulness are separate signals. A task
assessment must not silently create a strategy-learning rating. `submission_id`
is optional for compatibility; when provided, exact retries return the original
receipt and changed-payload reuse is rejected. See
[`PHASE1_EVIDENCE_COLLECTION.md`](PHASE1_EVIDENCE_COLLECTION.md) for the owner
workflow, valid values, pairing rules, and limits of the evidence.

Production HTTP/WS use the serving origin, preserving HTTPS and non-default ports.
Vite proxies `/backend` to the configured local backend; explicit `VITE_API_URL`
and `VITE_WS_URL` overrides remain supported. Health and manual reconnect use the
same origin contract. `correctionTrace` on the Model Settings URL selects a trace,
not a new correction workflow or an authorization grant.

The server persists new streamed message IDs and optional trace links in the
existing conversation table. Old rows keep numeric IDs without guessed traces.
Clients must bind metadata by both conversation and message IDs, preserve it
through history hydration, and never attach a preceding trace to a failed reply.
The web exposes review only for completed, trace-linked assistant responses;
native clients can ignore these additive fields until their review surfaces are
implemented. Existing action approval and model-training review remain separate.

### Owner / autonomy (owner area — desktop `Owner Control`, web owner pages)
| endpoint | shape (UI-relevant) |
| --- | --- |
| `GET /owner-control` | owner-control state |
| `PUT /owner-control` | patch state |
| `POST /owner-control/pause` | pause/resume autonomy |
| `GET /owner-control/autonomous-goals` | `{goals: [{goal_id, title, status, priority}]}` |
| `POST /owner-control/autonomous-goals` | create goal (`approve_for_planning`) |
| `POST /owner-control/autonomous-goals/{id}/decision` | approve/deny |
| `PUT /owner-control/autonomous-goals/{id}/priority` · `POST …/defer` | triage |
| `POST /owner-control/autonomous-goals/execute-next` | run next approved goal |
| `GET /owner-control/autonomy-schedule` | scheduled directives |
| `GET /owner-control/autonomy-runs` | `{events: [{cycle_id, stage, created_at}]}` |
| `GET /owner-control/autonomy-runs/{cycle_id}/timeline` | per-cycle detail |
| `GET /owner-control/approvals` · `POST …/decide` | pending approval queue |
| `GET /owner-control/plans`, `PUT /owner-control/plans/{plan_id}`, `POST /owner-control/plans/{plan_id}/decision`, `POST /owner-control/plans/{plan_id}/execute` | controlled execution |
| `GET /owner-control/autonomy-envelope` · `PUT` | budget/authority envelope |

(The authoritative list is the FastAPI app's route table; this document pins the subset
the UI depends on. Endpoint drift = test failure, see §4.)

## 3. Compositions (UX rules built on the contract)

- **Working-context card** (review §4): while a turn streams, compose
  `{project: GET /projects[0].name, objective: GET /owner-control/autonomous-goals[0].title,
  memories: len(GET /memories)}` and render inline in the conversation. Every source is
  optional; partial context still renders; offline renders nothing. Desktop implementation:
  `desktop/widgets/working_context.py` + `WorkingContextWorker`.
- **Beanie presence**: `GET /api/status` + stream events → `design/tokens.json`
  `beanie.states` → orb render. One state machine, per-platform rendering.
- **Cross-device follow**: `conversation_activity` + `list_conversations` newest-first →
  follow the owner's active conversation unless the user picked one manually or is typing.

## 4. Keeping the contract honest

- `tests/test_desktop_backend_client.py` pins the client methods' HTTP calls.
- `tests/test_response_trace_binding.py` and `tests/test_response_feedback_api.py` pin durable response identity, filtered measurements, truth boundaries, and retry receipts.
- Frontend trace/store/transport and response-review tests cover exact-message binding, metadata/token/history races, UNKNOWN defaults, explicit submissions, and failure states. Backend GitHub CI is active; frontend test/build/lint pass locally. The updated `scripts/ci/frontend.yml` template cannot be activated until the GitHub connection has workflow-edit permission.
- The Android client (`android/`) consumes the same contract: `VoiceWebSocketClient` speaks
  the `/ws` protocol above and `ApiClient` hits the documented HTTP endpoints — one contract,
  three clients.
- `tests/test_ui_api_contract.py` pins this document against the backend route table and
  the desktop client surface, so an endpoint rename fails CI instead of silently breaking
  a client.

The browser acceptance path in `tests/e2e/test_phase1_feedback_e2e.py` exercises
these surfaces against the real server/runtime and temporary stores, including
restart and the existing correction editor. It must be run explicitly with
`-m e2e`; unit pass counts are not a substitute for that path.
