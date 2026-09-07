# Repository-wide dead-code and repetition audit

**Date:** 2026-09-07
**Baseline:** `9e73816` on `arena/01a07ad8-arena-agent`
**Scope:** all 1,121 files tracked at the start; 257,181 text lines, including tests, documentation and lockfiles.

## Verdict and limits

**This is not a “100% clean” certification.** The repository-wide structural and
reference sweep is complete, and confirmed defects were repaired. Unique
unconnected work has deliberately been retained, following the owner's choice
**“Preserve unique features; flag gaps.”** Those gaps must not be called working
features or silently replaced with another implementation.

Every tracked file was inventoried and fingerprinted. Applicable parsers,
compiler checks, reference analysis and clone detection covered the code.
Findings and safety-sensitive call sites received targeted manual review.
**This is not a claim that a human manually verified the semantics of every one
of the 257,181 lines, or exercised every runtime branch.** Dynamic registrations,
external plugins, third-party binaries, real inference and native devices limit
what a static scan and a sandbox test suite can establish.

The [file-by-file ledger](REPOSITORY_AUDIT_FILES.csv) records baseline/current
hashes, line counts, syntax checks, reference evidence, review scope, removals
and retained gaps. It includes removed baseline files and newly added source/test
files. This report and the ledger are excluded from recursive self-fingerprinting.

## How the scan was performed

| Surface | Checks actually performed |
|---|---|
| Python | Every tracked `.py` parsed with Python AST; Ruff name/import/local/redefinition checks; Vulture advisory scan; existing unreachable-statement auditor; module/import/literal dynamic-import graph; exact function-body comparison |
| Web | TypeScript compiler for app/config projects; symbol/reference graph rooted at `src/main.tsx`, with barrel/type-only references distinguished; route/back-link review; Vitest; production build; browser/server tests |
| Android | All 36 Kotlin and 3 Kotlin build-script files parsed with the Kotlin Tree-sitter grammar; manifest/resources reviewed as XML; Compose/Hilt/manifest entry points identified. **No Android compilation/device execution** |
| Config and assets | Strict JSON, TypeScript JSONC, YAML, XML/SVG and JavaScript syntax checks as applicable; shell syntax checks; all files fingerprinted. Gradle wrapper JAR and image binary internals were **not** decompiled/audited |
| Repetition | jscpd over production Python, TypeScript/TSX, JavaScript and Kotlin, threshold 10 lines / 90 tokens; exact file hashes and Python function-body comparisons; manual classification of matches |
| Runtime registration | Inspected the assembled FastAPI route table in isolated storage; checked duplicate method/URL matchers and static routes hidden behind earlier parameter routes |

Tool versions used: Python 3.11, Ruff 0.16.6, Vulture 2.16, the repository's
TypeScript/Vitest toolchain, and Tree-sitter Kotlin 1.1.0. Raw diagnostic reports
and the read-only analysis scripts are retained under `logs/repository-audit/`
(ignored generated artifacts, not application code).

A detector warning was **not** treated as a deletion instruction. For example,
registered API handlers look unused to Vulture, Qt callback parameters are
required by their ABI, package exports are consumed by other modules, and a
property getter/setter legitimately has the same Python name twice.

## Confirmed findings repaired

### 1. Fake-success and generated leftovers

Removed these exact tracked artifacts; history retains them:

- `app/tools/dynamic_fibonacci_calc.py`: returned a success sentence without
  calculating Fibonacci numbers.
- `app/tools/dynamic_systemloganalyzer.py`: returned a success sentence without
  analyzing logs.
- `drafts/test_suite_python.py`: an offline-model response stored as Python;
  it did not parse.
- `drafts/script_youtube_local_ai_assistant_d.md`: generated offline-model output,
  not implementation or owner configuration.
- `replace_console.sh`: obsolete one-off migration with a sandbox-specific
  absolute path and incorrect generic import paths for nested components.
  Existing logging remains intact.

**No registered static tool was removed.** The placeholder files were not
entries in the live tool manifest.

### 2. Copied imports and dead locals

Removed roughly 800 unused import bindings, including the large monolithic
import lists copied into desktop pages/widgets during extraction. Preserved
public compatibility exports explicitly instead of deleting them to satisfy a
linter. This includes the scheduler exports, `app.main` request/endpoint exports,
desktop compatibility names, and `world_model.ObservationType`.

Removed unused manifest proxy objects that registered no action, obsolete local
calculations, discarded execution-success variables in observation collection,
and an unused `adb get-state` probe whose result could not verify an SMS/tap
postcondition. The latter still returns UNKNOWN; connection state was **not**
misused as evidence that the requested action happened. Cancellation cleanup
calls remain; only unused cleanup bookkeeping was removed.

The missing `Tuple` import used by model-router type annotations was repaired.
Production Ruff `F` checks now cover these cases as a regression gate.

### 3. Duplicate or misleading execution surfaces

- Removed private, uncalled `_parse_and_execute_intent` and
  `_enrich_messages_with_local_tools_and_rag` wrappers from `app/main.py`.
  Both ran a complete cognitive request behind helper names; neither had a caller.
- Removed the unused transport-level `SYSTEM_PROMPT`. The real prompt path
  remains in the cognitive runtime/CoworkerBrain.
- Kept `app.cognition.pipeline` as a compatibility import surface, but made
  `PipelineBridge` an alias of the same `CognitivePipeline`, not another wrapper
  implementation.

**Important correction to earlier overview wording:** `backend.main:app` is an
alias of the unified server. **`app.main:app` is a separate, core-only compatibility
ASGI application, not the identical app object.** Both use the shared cognitive
runtime. Its supported legacy HTTP/auth behavior is retained rather than silently
removed or conflated with the unified WebSocket/voice server.

### 4. Shadowed and dropped route registrations

The unified app had two registrations each for `GET /` and `GET /conversations`.
Only the first registration could serve a request.

- The legacy root is now registered only on the core-only compatibility app.
- The unified conversation listing uses the existing owner-control router; the
  unreachable fallback handler was removed.
- Removed `APIRouter.mount()` declarations that FastAPI drops during inclusion.
  Actual `/static` and `/audio` mounts remain on the ASGI applications.

New tests check duplicate URL matchers, static-path shadowing, and dropped mounts.
Legacy authentication and unified endpoints remain covered.

### 5. Web duplication and an incorrectly disconnected page

- Mobile and desktop had copied route lists. They now use **one destination list**
  with a layout choice.
- `ProjectDetailPage` already navigated back to `/projects`, but the existing
  `ProjectsPage` was not registered. The existing destination is now reachable
  on both layouts. It was **not** deleted merely because a graph called it orphaned.
- Removed the unused page-wide focus-trap implementation from `useAccessibility`;
  modals retain the existing container-scoped `useFocusTrap`.
- File/attachment icon and size rules now have one shared implementation,
  `utils/filePresentation.ts`, consumed by four existing views.
- Conversation-store Markdown export delegates to the existing graph-export
  formatter. The conversation export service re-exports the existing download
  helper rather than copying its implementation.

No unique screenshot, wake-word, animation or other unmounted feature was deleted.

### 6. Ignored results were safety bugs, not harmless unused variables

- `ConnectorsTool.prepare_email_draft()` ignored `DocumentManager` failure and
  returned success anyway. It now propagates failure and carries the real
  writer's artifact path when one exists.
- The owner ADB diagnostic could label a failed device-listing response “pass.”
  It now reports failure instead.

These values were **used correctly**, not simply deleted to make warnings vanish.

### 7. Misleading/repetitive validation

`validate.py` advertised `--quick`/`--full` without parsing them, ran the full suite
and then an already-included integration suite again, and called a handful of
attribute checks “all components wired.” Its fixed five-minute timeout was also
shorter than the current full suite.

It now parses its flags, runs the selected existing pytest suite once, uses the
real exit code/JUnit results, isolates configured validation data, and labels the
result as software regression validation—not live capability certification.
The CI installer prints the current branch instead of an obsolete hard-coded one;
the installer itself was not executed.

## Unique work intentionally retained: not live-feature evidence

### Backend: no production caller found

| File | What it is / distinction from the live path |
|---|---|
| `app/cognition/autonomous_operator.py` | Separate prototype task/approval/escalation queue. The live path uses owner control, goal generation/execution and scheduling. Do not introduce it as a second authorization authority. |
| `app/cognition/cognitive_router.py` | Prototype deterministic/fast/cognitive router, not the live reasoning/manifest route. |
| `app/cognition/confidence.py` | Source-reliability prototype; not the same responsibility as outcome confidence calibration. Do not merge merely because class names resemble each other. |
| `app/perception/anticipation_engine.py` | Anticipation implementation exercised by isolated tests, not connected to the server/runtime. |
| `app/perception/background_observer.py` | Probe/background-observer framework; not started by the live server. Its abstract probe method is intentional. |
| `app/perception/event_prioritizer.py` | Event-priority prototype; no live subscription found. |
| `app/runtime/resource_manager.py` | Separate resource-policy prototype; the actual runtime uses other hardware/resource managers. |

`app/cognition/cross_domain_transfer.py` is imported, but its `_generate_embedding`
extension still returns an empty list. Discarded text preparation was removed and
the comment corrected. This remains an explicit partial feature, not a claim
that domain embeddings are being computed.

### Web: no main-entry value consumer found

Preserved 20 files as unique unmounted features or library utilities:

- UI: `Spinner`, `Skeleton`, `SkeletonCard`, `Banner`, `VoiceOverlay`,
  `ScreenCapture`, `ScreenshotViewer`, `ScreenshotAnnotator`, `WakeWordTrainer`,
  `WakeWordManager`.
- `stores/wakeWordStore.ts`.
- Animation helpers/demo: `AnimatedWrapper`, `PageTransition`, `StaggerList`,
  `InteractiveElements`, `AnimationDemo`, plus `hooks/useReducedMotion.ts`.
- `components/presence/PresenceOrb.tsx`.
- `utils/accessibility.ts`, `utils/themeUtils.ts`.

These are not all equivalent to broken features: some are reusable utilities.
But an export from a barrel, or a standalone test, does not prove an app feature
is mounted. The ledger marks these separately from actual value-reference paths.
Package initializers, barrels, type contracts and framework callbacks are not
classified as dead solely because they lack an ordinary direct caller.

## Repetition that remains and why

At the stated jscpd threshold, production matches fell from **22 blocks / 538
matched lines** to **8 blocks / 109 matched lines**. Remaining matches are:

- common Android import declarations in separate compilation units;
- required missing-payload checks at initial execution and retry boundaries;
- ordinary connection/lock/schema setup in different persistent stores;
- explicit response-envelope fields on different runtime exit paths;
- small per-resource HTTP wrapper patterns in the API service.

These are not eight separate brains or eight unused features. Collapsing distinct
schemas or safety boundaries purely to force a zero clone count would add risk.
The exact AST scan also found three test-only matches: two scoped fixture pairs
and a repeated positive verifier case. They are recorded, not advertised as
independent evidence of additional product functionality. Threshold-based clone
detection does not prove there is no smaller or semantic repetition elsewhere.

## Validation

Final full-suite results are below. Focused checks also passed for legacy/unified
routes, model imports, observation compatibility, file search, draft failure
handling, the structural gates, and the corrected `validate.py --quick` runner
(46 checks). The static tool names, categories and safety levels are unchanged
across all 184 manifest entries.

- Backend: **3,165 tests passed**, 14 skipped, 7 e2e deselected, 3 environment/dependency warnings. Browser checks were run separately below.

- Frontend: **252 tests passed**, production build passed, lint **0 errors / 18
  existing warnings**.
- Browser/server: **7 e2e checks passed**, including the existing review/restart/
  correction workflow and project back-links on desktop/mobile widths.
- Python production `F` checks: **passed**.
- Python syntax/unreachable-statement and effective-route checks: **passed**.
- Kotlin/KTS grammar: **39 files parsed**, no grammar errors; **not compiled**.
- Native Qt validation: attempted a PySide6 installation, but this sandbox lacks
  required graphics/system libraries and the package mirrors were unavailable.
  The temporary Qt installation was removed to restore the test environment.
  **Native GUI execution is not certified.**

The new tests in `tests/test_repository_structure.py` guard names/imports/locals,
syntax, unreachable statements, route shadowing, compatibility aliases and type
annotation resolution. Ruff 0.16.6 was added to **test dependencies**, not core
runtime dependencies. Vulture, clone and native grammar tools were audit tooling
only; no model/audio/GPU stack was added to production requirements.

## Reproduce the bounded checks

Using the repository's test environment:

```text
python -m ruff check app backend desktop scripts validate.py --select F
python -m pytest tests/test_repository_structure.py tests/test_audit_cleanup_regressions.py -q
python validate.py --quick
python -m pytest tests/ -q
```

For the existing unreachable-statement tool, pass the tracked Python file list
rather than only its default test discovery. Frontend checks are `npm test`,
`npm run build` and `npm run lint` from `frontend/`. Browser tests require a built
SPA and Playwright Chromium: `python -m pytest tests/e2e -m e2e -q`.

## Before feature development resumes

1. Use this ledger and actual callers/registrations before adding another module.
2. Treat retained unconnected features as integration/deprecation decisions,
   not completed capabilities and not a reason to build parallel replacements.
3. Keep running structural, behavioral and browser checks after changes.
4. Validate Android, real Qt, inference, audio, OS and device paths on supported
   environments before claiming them verified.

Passing this audit's bounded checks is evidence of the repairs above. It is not
proof that every dependency, external plugin, hardware path or future state is
bug-free, and it is not permission to report “100% clean.”

---

## Incremental audit — 2026-09-07 (post-session tree, head `546f5f2`)

**Trigger:** owner directive to re-scan the whole project for dead code and
repetition before any further feature work, with specific suspicion on the
session's own additions (evidence panel, in-chat corrections, benchmark checks,
desktop/Android review slices, shutdown tests, maturity docs).

**Method (five independent passes, all reproducible):**

1. **Vulture 2.16** at 90% confidence over `app/ backend/ desktop/ scripts/`
   → 5 candidates; manual review identified every one as an
   **interface-mandated callback parameter** (pystray menu handler
   `(icon, item_obj)`, Win32 `EnumWindowsProc(hwnd, lparam)`, PyAudio
   `time_info`, balance-score pair) — none dead. At 60% confidence:
   **0 unused imports**.
2. **Zero-reference symbol sweep** — every function/class/method in production
   Python cross-referenced by name against ALL repository text (code, strings,
   tests, docs, CI): **0 symbols with zero references**.
3. **Stricter code-only sweep** — same sweep counting references only in
   executable code (py/ts/tsx/kt), so prose mentions no longer count as life:
   **0 symbols with zero code references**.
4. **Unreachable-statement scan** (AST: statements following `return`/`raise`
   within a function): **0 findings**.
5. **Repetition fingerprinting** — normalized 8-line sliding windows over
   production Python, frontend TS/TSX (src, non-test), and Kotlin:
   **38 cross-file pairs** share ≥1 window. Dispositions below.

**Fixes applied this pass:**

- `frontend/src/services/http.ts` (NEW): the byte-identical private fetch
  helper (`cognitionRequest` / `evidenceRequest`) — the repetition this
  session's item-2 slice introduced — is consolidated into one
  `requestJson<T>` helper; both service modules now import it under their
  previous local names (zero call-site churn, zero behavior change).
  Frontend: 257 tests passed, build OK, lint 18 warnings / 0 errors (baseline).

**Reviewed and accepted (documented rationale, not silent retention):**

- `Phase0Run` (phase0_evaluation.py) ↔ `BenchmarkRun` (intelligence_benchmark.py):
  same run-container shape and `to_dict` (9 shared windows), but different
  check dataclasses, separate persistence schemas, and deliberate evaluator
  isolation. Unifying would couple two independent evaluators for ~12 lines —
  rejected as worse than the duplication.
- Benchmark held-out causal checks construct their own small `SceneObject`
  fixtures inline (same-file near-repetition): deliberate scenario isolation —
  each held-out scenario must remain independently readable and tamper-proof
  against shared-fixture drift.
- Desktop (`desktop/pages/response_review.py`) vs web (`ResponseReviewBar`
  components) vs Android (`ResponseReviewBar.kt`): three platform
  implementations of one review flow over the SAME endpoints/stores —
  cross-language platform clients, not consolidation candidates.

**Reported for owner decision (real repetition, real refactor cost):**

- `components/knowledge/NodeEditorModal.tsx` ↔ `components/memory/MemoryEditorModal.tsx`
  (28 shared windows, ~200-line components) and
  `components/knowledge/KnowledgeGraphView.tsx` ↔ `components/memory/MemoryBrowser.tsx`
  (18 shared windows): the knowledge and memory editors/graphs are scaffold-level
  copies. Consolidation means extracting shared editor/graph scaffolding — a
  visual-regression-risky UI refactor on two owner-facing surfaces with no
  component-test coverage. Per the standing rule (unique-feature refactors are
  owner decisions), this is queued as a proposal, not silently executed.
- Remaining ≤6-window pairs are conventional boilerplate (modal shells, settings
  pages, agent scaffolds) and are individually below action threshold.

**This pass's limits (unchanged from the audit's framing):** dynamic dispatch,
string-keyed registrations, `getattr` wiring, third-party plugins, real
inference, and native/device paths bound what static analysis plus the sandbox
suite can prove. Android and browser e2e remain unexecutable in this sandbox.
