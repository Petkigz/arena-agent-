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

## Phase 2 — Beanie state machine as a shared specification

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
`design/tokens.json` first, then styles reference them. Known pre-existing wart to fix here:
pages bind `TEXT_*`/`BG_*` constants at import time, so an `apply_theme` switch after import
leaves stale copies — move to reading through `desktop.theme` (function accessors) during
this pass.

## Phase 4 — API contracts formalized

Both clients already share the HTTP backend (`desktop/backend_client.py`). Formalize the
contract: document the endpoints the UI depends on (chat, presence, autonomy, files) in one
place so a future mobile client codes against the document, not against the web's fetch calls.

## Phase 5 — Mobile shell (future)

Genuinely different shell per the analysis — not a squeezed desktop. Built from
`design/tokens.json` + Phase-4 contracts. No work until the owner starts it.

## Phase 6 — Polish last

Density/compact mode, motion timing, shadows/elevation. Only after hierarchy is unified —
per the owner's directive, no random margin fixes.

## Explicitly not done

- No WebUI rebuild or restyle (canonical + frozen; only mechanical token-plumbing).
- No desktop layout rewrite in this round (Phase 3, needs visual iteration with the owner).
- No invented tokens (radius/spacing/shadow scales wait until Phase 3 adopts them with real
  values — the token file grows by adoption, not speculation).
