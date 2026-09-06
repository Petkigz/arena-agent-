# Arena UI Unification Plan

Round-21. Owner directive: the **web client is the canonical visual reference** — do not
rebuild it; bring the desktop client to the same design language; extract ONE shared design
system (tokens, UX rules, Beanie state model, API contracts) as shared *specifications*, not
shared component source (clients differ in technology). Android later, from the same spec.

## Ground truth vs. the external analysis

The external UI review (verdict ~7/10) was written from screenshots. The repo tells a more
precise — and better — story:

| Analysis assumption | Repo reality |
| --- | --- |
| Desktop is a separate visual product needing a rebuild | Desktop (PySide6) is already modularized (`theme.py`, `styles.py`, `pages/`, `widgets/`) and deliberately mirrors the web palette — the docstring says so. The disease is **token duplication**, not two independent designs. |
| Beanie state machine must be created/designed | It already exists **twice**, in near-perfect agreement: 11 states, identical colors (web `ReactiveBeanieOrb.tsx` COLORS vs desktop `theme.py` PRESENCE_COLORS). It needed *mechanical* sharing, not design. |
| Web presence palette is the model | Web tailwind config only had **4 of 11** states (`idle/working/listening/speaking`); the orb had all 11. Now all 11 flow everywhere from one file. |
| Android client planned | Confirmed: **no Android client exists in this repo.** Out of scope until the owner starts one — it will consume `design/tokens.json` + the documented API from day one. |

Confirmed drift (all now fixed or enforced):
- Desktop dark `TEXT_SECONDARY`/`TEXT_MUTED` were one shade lighter than web (`#CBD5E1/#94A3B8` vs canonical `#94A3B8/#64748B`).
- Desktop light theme carried an accent override (`#2563EB`) the web does not have.

## Phase 1 — DONE (this round): one source of truth for design tokens

Drift is now **impossible by construction**, not merely detected: both clients *import the
same file*.

- `design/tokens.json` — canonical: both themes (background/text/accent), semantic accent
  scale, the 11 Beanie presence states × {label, color, duration_ms}, typography base.
- `desktop/design_tokens.py` — pure-Python loader (no Qt): validates schema, serves
  `THEME_COLORS` / `PRESENCE_COLORS` / `PRESENCE_DURATIONS` / `PRESENCE_LABELS`.
- `desktop/theme.py` — consumes the loader; keeps an embedded fallback for packaged builds,
  **pinned to canonical by test** so even that path cannot rot. The two historical drifts are
  corrected (desktop dark text-secondary/muted now match web; light accent unified to
  `#3B82F6`).
- `frontend/src/design/tokens.ts` — typed entry point; `BeanieOrbStatus` is now *derived from
  the JSON keys*, so adding a state in one place extends the type everywhere.
- `frontend/tailwind.config.js` — presence palette (all 11 states) and accent scale derived
  from tokens; legacy `background-dark` block too. No hardcoded hexes remain.
- `frontend/src/components/presence/ReactiveBeanieOrb.tsx` — hardcoded `COLORS` map deleted;
  resolves via `BEANIE_STATES`.
- `frontend/src/index.css` — unchanged mechanism (CSS variables are the runtime theming
  switch), values already canonical; **enforced** against tokens.json by test.
- Guards: `tests/test_design_tokens.py` (11 tests — validates the JSON schema, desktop
  loader, desktop theme *headless via a QColor stub*, index.css variables, and that the web
  config/orb really import the tokens) + `frontend/src/test/design-tokens.test.ts` (5 tests).
  Web sources are parsed from Python, so the design system is guarded even without node.

## Phase 1.5 — DONE (round-21b): rendering integrity — why the screen didn't match the code

The owner reported the UI "isn't coming out like that" despite the tokens existing. Root cause
found in the desktop rendering pipeline, now fixed:

**The live-theme (and saved-light-startup) bug.** Every page binds theme constants at import
time (`from desktop.theme import BG_PRIMARY, ...` = a snapshot of the values at import, dark by
default). `apply_theme('light')` mutated only `desktop.theme`'s globals, so `refresh_theme()`
"re-applied" stylesheets rebuilt from the STALE dark copies — the switch was a silent no-op for
most of the UI, and only helpers using function-local imports (`_input_style()` etc.) picked up
fresh values. Result: a mixed dark/light UI that never matched the design. Fix (general, one
place): `desktop.theme.apply_theme` now rebinds every `desktop.*` module's copied constants
after switching, so all existing `from ... import` sites render the current palette with zero
per-page plumbing. Regression-guarded twice: a headless mechanism test
(`test_apply_theme_rebinds_importer_modules`) and a real widget test that switches to light
and asserts the repainted stylesheet carries light values
(`test_live_theme_switch_actually_repaints`, runs wherever a Qt runtime exists).

**Duplicated semantic palettes on the web.** `KnowledgeGraphView` and `NodeDetailPanel`
hand-copied the SAME node-type color dict (two copies that could drift apart);
`LearningPatterns` hand-copied memory-type colors; `ListeningIndicator` hand-copied
voice-state colors. All now come from `design/tokens.json`
(`color.knowledge_node_types`, `color.memory_types`, `beanie.states` via `beanieColor`).
The desktop chat voice banner's hand-copied presence hexes now read `PRESENCE_COLORS`.
Remaining intentional hex literals: the orb's internal white highlights, the
ScreenshotAnnotator user pen palette (data, not theming), and one graph-edge default stroke.

## Phase 1.6 — DONE (round-21c): fine-tunes & professional-grade layer

The review's fine-tune directives, implemented as canonical scales (values grounded in what the
web already compiles to — this is canonicalization, not a redesign):

- **Token scales added** to `design/tokens.json`: radius (4/6/8/12/16/full — exactly the
  Tailwind v4 defaults the web ships), spacing (4px grid + component paddings from the web's
  `py-2 px-4` buttons and `px-4 py-2.5` bubbles), typography scale (caption 12 / body 14 /
  subtitle 16 / title 18 / display 30) + weights, elevation (the web's shadow set), motion
  (150/300ms, pulse cadences, shared easing), focus ring (2px accent).
- **Desktop normalized onto the scales**: message bubbles 14px→16px radius and 10×14→10×16
  padding (web's `rounded-2xl px-4 py-2.5`); buttons 10px→8px radius, `10px 14px`→`8px 16px`
  padding (web's `py-2 px-4`); inputs `8px 10px`→`8px 12px`; voice banner now a true pill
  (9999px); odd font sizes 13/15px eliminated (scale was 12/13/14/15/16/18/30 → now exactly
  12/14/16/18/30).
- **Professional interaction states**: QSS helpers gained `:pressed` (darkened), `:focus`
  (accent ring, padding-compensated so text doesn't shift — the web's `focus:ring-2`), and
  `:disabled` styling; previously only `:hover` existed anywhere.
- **Chat composer** mirrors the web composer (`rounded-2xl`, generous padding) via a new
  `_composer_style()`.
- **Progressive context**: `ContextPanel` is now collapsible (chevron toggle → slim 36px rail;
  choice persisted in settings). Context is on demand, not a permanent third column.
- **Guards**: QSS normalization lints — every `border-radius`/`font-size` anywhere in
  `desktop/` must be a token value (fails CI on the next off-scale one-off); QSS state
  coverage test; bubble-geometry test; collapse widget tests; web shadow-scale token wiring
  test. QSS helper tests run headless (Qt stubbed), so CI without a GL runtime still guards
  them.

Remaining for the fine-tune track: web `transition-all` usages could narrow to specific
properties (repaint hygiene); sidebar collapse-to-icon-rail (needs design iteration → Phase 3).

## Phase 2 — DONE (round-21d): desktop shell hierarchy — the review's §2/§3/§5/§7

Executed against the full review text (re-read this round), following its order (their
"Phase 2 — fix desktop shell", "Phase 3 — make context progressive"):

- **§2 Restrained Beanie landing** (`desktop/pages/beanie.py`): the four 56px quick-action
  tiles and the giant "🎙 Talk to Beanie" button are gone. Landing = orb → "Beanie" →
  time-based greeting ("Good evening.") → "What are we working on today?" → a landing
  composer ("Ask Beanie anything…" + inline 🎙 + ➤, wired through `app._landing_submit` to
  hand the message to the conversation and switch to it) → the same four actions as subtle
  flat text chips. Beanie is the identity layer, not a voice-assistant landing page.
- **§3 Context progressive by default**: `context_collapsed` now defaults to True — the rail
  is hidden unless the owner expands it ("Otherwise: hide it"). Toggle + persistence
  unchanged from round-21c.
- **§5 Grouped sidebar** (`desktop/widgets/sidebar.py`): the flat 10-button dashboard stack
  is now grouped sections — **Conversations** (Chats + recent list), **Workspace** (Pansophy,
  Projects, Files), **Tools** (Images, Code), **Owner** (Owner Control, Tools, Beanie),
  **System** (Settings) — with flat transparent nav items (hover surface, like the web's
  sidebar items) instead of boxed buttons. Owner/admin surfaces live in their own area.
- **§7 De-buttoned composer** (`desktop/pages/chat.py`): "Send" → compact ➤ accent icon;
  mic fixed-size icon button. Everything else stays contextual.
- The "Talk to me" chip now actually toggles voice (it previously mapped to an empty prompt).

**Not done this round (honest scope):** the inline "Working context" card inside the
conversation (review §4's mockup) needs backend surface area the desktop chat flow doesn't
have yet (project/objective per turn) — it rides with Phase 4 (API contracts). Mobile shell
(§8) remains future work; the review itself confirmed no Android client exists in the repo.

Guards: widget tests (restrained landing, chip actions, grouped sidebar routing — run
wherever Qt exists) + headless source checks in `tests/test_design_tokens.py`.

## Phase 2b — Beanie state machine as a shared specification

Largely DONE by Phase 1's plumbing: `desktop/pages/beanie.py` already imports
`PRESENCE_COLORS`/`PRESENCE_DURATIONS` from `desktop.theme`, which now serves the canonical
tokens; the web orb reads the same file. Remaining: extend `design/tokens.json` per state with
the *character* spec (animation metaphor: breathing/pulse/sweep/ripple/disturbance) so the
per-state motion vocabulary is named in one place, and sweep `desktop/app.py`'s tray/presence
code for any remaining local literals. No behavior change — just one spec.

## Phase 3 — Desktop shell hierarchy (needs visual iteration; next rounds)

The web already implements the target hierarchy (conversation primary, progressive context).
Align the desktop shell file-by-file: chat page as the home surface, context/sidebar
(`desktop/widgets/context.py`, `sidebar.py`) progressive — collapsible, not permanent columns.
reuse `styles.py` helpers; do NOT tweak margins ad hoc — spacing/radius tokens enter
`design/tokens.json` first, then styles reference them. (The import-time theme-binding wart
that used to live here is fixed — see Phase 1.5 — but pages still rebuild stylesheets in
`refresh_theme()` one by one; folding that into a single restyle pass belongs in this phase.)

## Phase 4 — DONE (round-21e): API contracts formalized + the §4 working-context card

- `docs/UI_API_CONTRACT.md` — the UI-facing contract, grounded in the REAL route table
  (`app.server`): the `/ws` message protocol (both directions, matching what
  `desktop/chat_client.py` actually speaks), the HTTP surface (core + owner/autonomy), the
  UX compositions built on it, and the client rules (echo suppression, cross-device follow).
- `tests/test_ui_api_contract.py` pins the document against the live app: every documented
  endpoint must exist on the server, and every WS message type the desktop client
  handles/sends must be documented. (The test caught three stale paths in the doc's first
  draft — exactly the drift class it exists to prevent.) A future Android client codes
  against this document, not against the web's fetch calls.
- **The review §4 working-context card is implemented**: while a turn streams, the
  conversation itself carries a compact "Working context" card (Project / Objective /
  Memories), composed on a worker thread from the same contract endpoints the web context
  panels use (`desktop/widgets/working_context.py`, `WorkingContextWorker`, wired in
  app.py with a still-working guard so a late fetch never shows a stale card; hidden on
  completion/error; partial context renders, offline renders nothing).

## Phase 5 — STARTED (round-21f): Android revival — same Beanie, mobile body

The Android client EXISTS (`android/`, Kotlin + Jetpack Compose, ~5k LOC — missed by the
reviewer's GitHub search and by our own round-21 inventory; corrected). The review's salvage
rule applies cleanly: networking (`ApiClient`), the WebSocket conversation client, voice
services and models are sound and already speak the Phase-4 API contract — KEPT. The
presentation layer was revived:

- **One Arena theme** (`ui/Theme.kt`): Material 3 roles mapped to `design/tokens.json`
  (background/surface/surfaceVariant ← bg primary/secondary/surface; onBackground/onSurface ←
  text.primary; onSurfaceVariant ← text.secondary; outline ← text.muted; primary/secondary/
  tertiary/error ← accent scale). `dynamicColor` now defaults to **false** — Arena's palette,
  not the device wallpaper (Material You remains opt-in). Light-scheme drifts fixed
  (#FFFFFF surface → #E2E8F0; #0F172A onBackground → #1E293B). Status bar follows the canvas,
  not the accent.
- **Restrained landing** (mirrors desktop round-21d): orb → "Beanie" → time-based greeting →
  "What are we working on today?" → landing composer ("Ask Beanie anything…" + inline mic +
  send, routed to the conversation) → the four quick actions as subtle text chips. The 56dp
  tiles and the giant talk button are gone; the "Talk to me" chip now actually toggles voice
  (it mapped to an empty prompt, same bug as desktop).
- **Theme-driven screens**: every hardcoded `Color(0xFF…)` in Chat/Pansophy/Files/Vision
  screens replaced with Material roles; the voice pill reads the PresenceStatus palette
  (shared state machine); bubbles use the token radius (16dp = xxl); the composer matches the
  web/desktop composer radius.
- **Machine-guarded like the other clients** (`tests/test_android_design_tokens.py`, 7
  tests): Theme.kt schemes == canonical tokens, the Compose PresenceStatus enum == the 11
  Beanie states (color + duration), screens stay theme-driven, landing structure pinned —
  parsed from Python, so the guard runs without an Android toolchain.

Next on Android (needs a real build/device loop): the §4 working-context card in the
conversation, drawer-grouped navigation beyond the 7-tab bottom bar, and voice-flow polish.
Note: Kotlin changes are source-verified (structure + drift tests) but not compiled here —
no Android SDK in the sandbox; first Gradle build may surface routine compile fixes.

## Phase 6 — Polish last

Density/compact mode, motion timing, shadows/elevation. Only after hierarchy is unified —
per the owner's directive, no random margin fixes.

## Explicitly not done

- No WebUI rebuild or restyle (canonical + frozen; only mechanical token-plumbing).
- No desktop layout rewrite in this round (Phase 3, needs visual iteration with the owner).
- No invented tokens (radius/spacing/shadow scales wait until Phase 3 adopts them with real
  values — the token file grows by adoption, not speculation).
