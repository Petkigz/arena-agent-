# Arena Agent — Full Architecture, Safety, Reliability, and Deployment Audit

**Audit date:** 2026-08-23  
**Audited branch:** `arena/01a02b25-arena-agent`  
**Audited commit:** `1269502` (`fix: authenticate native desktop control requests`)  
**Scope:** Python backend and cognition, tool layer, web frontend, desktop client, Android client, tests, CI, dependencies, security boundaries, evidence integrity, and deployment readiness.

## Executive verdict

Arena is now a serious local-first coworker architecture with unusually strong owner-control concepts: exact payload grants, plan revisions, emergency pause, evidence-aware projects, verification-separated execution, provenance-linked memory, and honest rollback receipts. The deterministic intelligence benchmark passed all 10 isolated checks, the web frontend passed all 184 tests, and the production frontend build succeeded.

It is **not ready for unattended or LAN deployment yet**. This audit found three release-blocking defects:

1. GitHub CI has failed before running tests on every recent push.
2. The unified server constructs a second `CognitiveRuntime`, violating the one-authoritative-brain invariant.
3. Several LLM-backed tools still convert an explicitly simulated/offline model response into `success: true`; this can create fake artifacts and contaminate learning.

Four additional high-priority problems should be resolved before deployment: the unified server cannot start from the advertised core-only dependency set, native safety-ceiling controls use the wrong API field, `/conversations` bypasses API-key authentication, and the default full test suite cannot collect with core dependencies.

**Release recommendation at audit time:** continue local development, but do not treat the audited commit as deployment-ready until all P0 and P1 findings below are fixed and CI is green from a clean checkout.

## Remediation update — later on 2026-08-23

The following findings were repaired immediately after the audit:

- **P0-1:** default CI/developer dependencies are now software-only; GPU/audio hardware packages moved behind `requirements-all.txt`.
- **P0-2:** `app.server` now uses `CognitiveRuntime.get_instance()`, with an identity regression test.
- **P0-3:** a central `require_real_completion()` contract now rejects simulated/failed model responses across every model call site; fake dynamic-capability fallbacks were removed.
- **P1-1/P1-4:** optional phase-6 tools and data analysis imports are lazy; the unified server starts core-only; broad software test dependencies are explicitly separated.
- **P1-2:** desktop and Android now use the actual `max_autonomous_level` policy field.
- **P1-3:** `/conversations` now carries API-key verification.
- **P1-6:** recommendation and decision records persist atomically, while grants remain memory-only and are never restored.
- **P2-1:** remaining ADB observation and ffprobe subprocesses use the cancellable process-group runner.

Post-remediation evidence:

- Backend: **1589 passed, 2 skipped, 4 deselected**, with two desktop-notifier environment warnings.
- Frontend: **184 passed** and production build succeeded.
- Intelligence benchmark: **10/10 passed**, no regressions.
- Focused execution/project/memory/LoRA/benchmark suites: **35 passed**.

GitHub CI confirmation remains pending until the remediation commit is pushed and its clean runner completes. Android compilation and real owner-hardware checks remain open.

---

## Evidence collected

| Check | Result |
|---|---|
| Working tree at audit start | Clean |
| Tracked files | 798 |
| Python files under app/backend/desktop/tests | 491 |
| Python source under app/backend/desktop | ~60,841 lines |
| Manifest capabilities | 133 |
| Python test definitions found statically | 1,575 across 236 files; this is not a pass count |
| Frontend tests | **184 passed** across 18 files |
| Frontend production build | **Passed** |
| Deterministic intelligence benchmark | **10/10 passed**, no regressions, isolated environment |
| Full default Python suite with `requirements-core.txt` | **Failed during collection**: `pandas` imported by `data_analysis_agent` |
| Unified server import with core dependencies | **Failed**: `backend.api.phase6_routes` imported Pillow-dependent `universal_filesystem` |
| Latest GitHub Actions runs | Latest 10 all failed in **Install dependencies**; tests never ran |
| Android build | Not runnable in this sandbox: Java/`JAVA_HOME` and Android SDK absent |
| Secret scan | No tracked production credential/key artifact found; one intentional test secret only |
| Tracked DB/model/key artifacts | None found by extension scan |

Commands used included frontend Vitest/build, the documented deterministic benchmark command, default pytest collection, manifest construction, GitHub Actions inspection, static import/unsafe-call searches, tracked-file scans, and focused source review of authority, execution, verification, memory, CI, server, native clients, and LoRA paths.

---

## What is strong and should be preserved

### A. Owner authority model

The architecture correctly distinguishes consideration, recommendation, authorization, and execution. Exact grants bind action type and canonical payload digest, default to short TTL and single use, reject replay and payload drift, and remain subordinate to emergency pause. Plan review is revision-bound, and started steps are immutable.

### B. Evidence semantics

The runtime distinguishes attempted execution, tool response, observed environment, and independently verified goal state. Unknown outcomes remain unknown. Project steps in `waiting_evidence` are re-observed rather than blindly repeated.

### C. Long-horizon projects

Persistent DAG projects, dependency readiness, verified milestone reconciliation, evidence contracts, bounded scheduling, failure blocking, and approval waiting are all substantive foundations for longer-horizon work.

### D. Memory and adaptation

Verified episodes can consolidate into provenance-linked semantic memories, lessons, and repeated-success procedures. Curiosity is calibrated from verified outcomes and remains capped by an owner-controlled hard limit.

### E. LoRA boundary

Reviewed examples, redaction, held-out skill evaluation, unrelated-domain regression checks, provider identity checks, and separate deployment are correctly designed not to claim behavioral improvement from metadata selection alone.

### F. Failure honesty in many physical capabilities

Screenshot, input control, browser automation, TTS, wake word, speaker identity, pairing, Win32 operations, and transfer predictions have been substantially hardened against fabricated success. Cancellation and rollback receipts are also materially better than typical assistant architectures.

### G. Local security posture

The server rejects unauthenticated non-loopback clients unless the owner explicitly opts into insecure LAN access. Core and API routers use API-key dependencies, WebSockets verify the configured key, CORS origins are configurable, and native desktop API credentials are local rather than synced as backend preferences.

---

# Findings

Severity definitions:

- **P0 — release blocker:** violates a foundational invariant or leaves regression control nonfunctional.
- **P1 — high:** materially breaks owner control, security claims, startup, or broad reliability.
- **P2 — medium:** important operational, test, or maintainability gap.
- **P3 — low:** cleanup, documentation, or future hardening.

## P0-1 — CI is continuously red and does not run tests

**Evidence**

- `.github/workflows/tests.yml` installs `requirements.txt`, the full core + optional hardware/model stack.
- The latest 10 GitHub Actions runs all failed at **Install dependencies** in roughly 44–95 seconds.
- The pytest step was skipped in those runs.
- The full optional set includes PyAudio and heavyweight Torch/CUDA, wake-word, browser, media, and GUI packages. A dry-run resolves multiple gigabytes of CUDA packages on an Ubuntu runner.

**Consequence**

There is currently no trustworthy branch-level regression gate. Every recent “pushed and tested” increment was only locally focused; GitHub did not validate it.

**Required fix**

1. Make the primary workflow install `requirements-core.txt`.
2. Split tests into core-safe and optional capability groups/markers.
3. Add a separate optional-tools job with explicit apt prerequisites and dependency caching.
4. Do not install GPU Torch/CUDA in normal CI; use a CPU wheel/index or a dedicated heavy-model job.
5. Add frontend `npm ci`, Vitest, and production build jobs.
6. Upgrade GitHub actions versions because the runner warns that Node 20-based actions are deprecated.

## P0-2 — Unified server violates the one-authoritative-brain invariant

**Evidence**

- `app/server.py:112` uses `runtime = CognitiveRuntime()`.
- REST routes throughout `app/main.py` use `CognitiveRuntime.get_instance()`.
- Direct construction does not populate `CognitiveRuntime._instance`; `get_instance()` can therefore create a second runtime.
- The message router is initialized with the server-global direct instance, while projects, benchmarks, adaptive autonomy, temporal vision, authorized execution, and training-example routes can use the singleton instance.

**Consequence**

WebSocket chat and REST control paths can operate on different in-memory brains, event buses, project managers, memory objects, execution state references, and module state. This directly contradicts `CognitiveRuntime remains the one authoritative brain`.

**Required fix**

Replace the server construction with `CognitiveRuntime.get_instance()` and add a regression test asserting identity among:

- `app.server.runtime`
- `CognitiveRuntime.get_instance()`
- the runtime injected into `message_router`
- runtime-dependent owner/project endpoints

## P0-3 — Simulated LLM responses still become tool success

**Confirmed reproduction**

With `llm_client.generate_chat_completion()` returning:

```json
{
  "id": "chat-simulated",
  "success": false,
  "simulated": true,
  "error": "offline",
  "choices": [{"message": {"content": "[Simulated Response - Local LLM Server Offline]"}}]
}
```

`TranslatorTool.translate()` returned:

```json
{
  "success": true,
  "translation": "[Simulated Response - Local LLM Server Offline]"
}
```

**Systemic evidence**

Multiple tools extract `choices` or call `extract_reply()` and then return `success: true` without checking `success == false` or `simulated == true`. Examples include translator, coder brain, content creation, cybersecurity planning, legal/wellness helpers, knowledge domains, music guidance, skill execution, web summaries, YouTube summaries, media analysis, and visual analysis. Several use success-sounding fallback strings such as `Code refactored.`, `Unit tests generated.`, `Security plan generated.`, or `Reflection completed.`

**Consequence**

- Fake drafts/files can be created and later observed as real artifacts.
- Goal verification may verify the artifact’s existence while its content is only an offline placeholder.
- Outcome/memory/causal stores can learn from false tool-level success.
- Reviewed LoRA candidates can potentially receive placeholder-derived content if downstream verification checks only the created artifact.
- The status document’s “simulated-success removal” claim is incomplete.

**Required fix**

Introduce one central typed completion validator, for example `require_real_completion(result)`, that rejects simulated, failed, empty, and malformed responses. All LLM-backed tools must preserve model availability separately from deterministic preprocessing success. Remove success-sounding `extract_reply` fallbacks from outcome-producing paths. Add a parameterized regression test that injects the same simulated response into every manifest tool that depends on the LLM and asserts no tool returns successful generated content or writes an artifact.

## P1-1 — Core-only installation cannot start the real unified server

**Evidence**

Importing `app.server` with `requirements-core.txt` failed because:

```text
backend.api.phase6_routes
→ app.tools.universal_filesystem
→ from PIL import Image
→ ModuleNotFoundError: PIL
```

The manifest and `app.main` are lazy, but the actual unified server still eagerly imports optional route modules and their tool dependencies.

**Consequence**

The documented claim that the core dependency set supports API/runtime startup is only true for partial construction, not for the production server entry point.

**Required fix**

Make optional API routers lazy or capability-local, and return typed 503/unavailable responses when a route’s package is absent. Add a subprocess regression test that blocks Pillow, pandas, pypdf, docx, pytesseract, mss, Playwright, YouTube transcript, and speech packages while importing `app.server` and requesting `/health` plus a core owner-control endpoint.

## P1-2 — Native autonomous safety ceiling uses the wrong field name

**Evidence**

Backend policy schema and payload use:

```text
max_autonomous_level
```

Desktop and Android read/send:

```text
max_autonomous_safety_level
```

A direct model validation of the native payload produced an empty update patch for that field.

**Consequence**

- Native clients display the ceiling as zero because the response key is absent.
- Native save operations do not update the backend safety ceiling.
- Depending on extra-field handling, the bad field is ignored rather than rejected, giving the owner false confirmation that policy was changed.

**Required fix**

Use `max_autonomous_level` consistently in desktop and Android, and add real FastAPI contract tests—not string-marker tests—that save from each native client payload and verify the persisted effective policy.

## P1-3 — `/conversations` bypasses API-key protection

**Evidence**

`app.server.create_app()` attaches auth dependencies to included routers, but defines `/conversations` directly afterward without `Depends(verify_api_key)`. `/health` is intentionally tested as public; `/conversations` has no equivalent documented exception.

**Consequence**

When authentication is enabled, an unauthenticated caller can enumerate active conversation identifiers while server logs claim all routes and WebSockets require the API key.

**Required fix**

Protect `/conversations`, or explicitly redesign it as a public minimal health metric without identifiers. Add an authentication test for every directly registered non-health route.

## P1-4 — Default Python suite cannot collect under core dependencies

**Evidence**

`python -m pytest -q` with the core environment failed during test collection:

```text
tests/test_data_analysis_agent.py
→ app.agents.data_analysis_agent
→ app.tools.data_analyzer
→ import pandas
→ ModuleNotFoundError
```

**Consequence**

Lazy tool startup does not translate into a core-safe test suite. A core CI workflow will still fail unless tests and direct module imports are separated.

**Required fix**

- Mark optional dependency tests and skip them using `pytest.importorskip` or explicit capability markers.
- Refactor agent modules to lazily import optional engines when invoked.
- Define `core`, `optional`, `hardware`, `live`, and `e2e` test groups.
- Require core collection itself to succeed in a clean core-only environment.

## P1-5 — End-to-end coverage does not exercise critical control paths

**Evidence**

The only browser E2E file checks health, SPA mount, body presence, and a WebSocket reply that merely has to be non-empty. It does not reject an offline simulated response.

Missing E2E flows include:

- consideration → recommendation → approval → exact grant → separate execution → verification
- payload drift/replay rejection through the live API
- emergency pause during a real cancellable process
- rollback request → compensation approval
- plan edit conflict and DAG completion
- multimodal upload → grounding → temporal event → response
- LoRA review → export → evaluation → separate deployment
- authenticated desktop/Android Owner Control

**Required fix**

Add local deterministic E2E fixtures and reserve live/hardware cases for opt-in jobs. Assert evidence state and verification fields, not merely non-empty text.

## P1-6 — Pending action approvals are memory-only

**Evidence**

`ApprovalStore` keeps `_requests` in memory. Exact authorizations are intentionally memory-only for safety, but pending recommendations/decisions also disappear on restart and have no persistent audit ledger in that store.

**Consequence**

A restart safely removes authority, but also removes the owner’s pending review queue and approval history. Long-running projects may reconstruct some requests, while ordinary chat recommendations are lost.

**Required fix**

Persist recommendation and decision records without persisting reusable authority. On restart, approved-but-unexecuted grants should remain revoked and require a fresh owner authorization, while the reviewed recommendation/audit record remains visible.

## P2-1 — Cancellation does not yet cover every blocking operation

**Evidence**

Direct `subprocess.run()` remains in observation probes (`app/cognition/perception.py`) and ffprobe metadata extraction (`backend/api/phase6_routes.py`). In-progress Playwright navigation and third-party model/media calls still depend on bounded timeout when no safe interrupt API exists.

**Consequence**

Emergency cancellation can be delayed, and some child processes are not managed by the shared process-group cancellation helper.

**Required fix**

Move remaining subprocesses to `run_cancellable_subprocess`; use cancellable async APIs where available; persist an “interrupt requested but underlying operation still opaque” state for non-interruptible libraries.

## P2-2 — Android code has not passed a real compile in this environment

**Evidence**

Android static contract tests pass, but Gradle could not run because Java/`JAVA_HOME` is unavailable here. The GitHub App cannot add/update an Android workflow without workflow permission.

**Consequence**

Recent Compose/API changes may contain SDK-, Kotlin-, or Material-version errors that delimiter and string-marker tests cannot detect.

**Required fix**

Run `:app:compileDebugKotlin`, unit tests, lint, and assemble on owner hardware or CI immediately after Java/SDK setup. Add API contract tests with MockWebServer rather than only Python source-marker tests.

## P2-3 — Major composition files remain oversized

Measured source sizes include:

- `app/cognition/runtime.py`: ~3,133 lines
- `app/main.py`: ~2,531 lines
- `frontend/src/app/routes/PrivacySettingsPage.tsx`: ~1,080 lines
- Android `SettingsScreen.kt`: ~718 lines
- Desktop `owner_control.py`: ~373 lines

**Consequence**

High change collision risk, hard review, broad import side effects, and weak module-level test isolation. The server/core startup defects are examples of composition complexity escaping focused tests.

**Required fix**

Split route domains, runtime integration modules, and native Owner Control sections behind typed service clients and smaller view models/components. Preserve the single runtime instance; decomposition must not create multiple brains.

## P2-4 — Hardware/model capabilities remain integration-only

Still unverified on the owner’s target machine:

- VLM quality, memory pressure, CPU fallback, and RX 580 behavior
- actual LoRA training and LM Studio base/adapter evaluation
- wake-word custom model training
- real speaker embeddings and identification thresholds
- camera, display, desktop input, Android ADB, and audio hardware paths

This is not a code-integrity defect, but no deployment claim should treat these as verified capabilities until measured.

## P2-5 — Documentation and measured counts are stale

`AGI_MEASURED_STATUS.md` still cites a previous baseline of 1,414 backend tests. The repository now contains roughly 1,575 statically detected Python test definitions, but the current suite does not collect in a core environment and CI never reaches pytest. Numerous older audit/plan documents remain present despite one document being marked canonical.

**Required fix**

Do not publish a backend pass count until a clean CI run provides it. Add generated, dated evidence metadata to the canonical status and clearly archive superseded audits.

## P3-1 — Optional modules retain broad exception swallowing and stale comments

There are many best-effort `except Exception: pass` paths. Most are defensible degradation, but some suppress diagnostics or cancellation. `app/llm.py` still describes its offline typed failure as a “mock response,” and some tool docstrings promise “always well-formed” behavior in ways that encourage callers to treat failure text as output.

**Required fix**

Audit broad catches for cancellation propagation and typed error preservation. Update comments to distinguish unavailable, simulated diagnostic text, and verified output.

---

## Architecture review by domain

| Domain | Review |
|---|---|
| Owner control model | Strong design; native safety-field bug and approval persistence gap remain |
| Exact authorization | Strong digest/replay/TTL design; native exact-scope recovery is carefully bounded |
| Goal verification | Strong separation and UNKNOWN semantics |
| Project DAGs | Strong persistence/evidence model; needs live E2E and restart tests at product level |
| Memory learning | Strong provenance design; must block placeholder-derived artifact learning systemically |
| Curiosity/adaptation | Well bounded by verified outcomes and owner cap |
| Cancellation | Broad coverage, not complete |
| Rollback | Honest compensation model; correctly never auto-executes |
| LoRA | Correct evaluation/deployment boundary; real provider unverified |
| Perception | Temporal tracking is appropriately scoped; real hardware/VLM unverified |
| API security | Good local/LAN defaults; direct conversations route exception must be fixed |
| Dependency isolation | Good manifest mechanism; incomplete at unified server/test module layers |
| Web frontend | Tests and build green; full E2E lacking |
| Desktop | Broad control parity and local auth; needs live authenticated test |
| Android | Broad control surface in source; compile/runtime unverified |
| CI/release | Not operational; primary release blocker |

---

## Recommended remediation order

### Phase 0 — Restore trustworthy engineering feedback

1. Fix CI dependency strategy and make core CI green.
2. Fix the duplicate runtime composition root and add identity tests.
3. Introduce central real-completion validation; fix every LLM tool and add a manifest-wide simulated-response regression test.
4. Make unified server startup core-safe.

### Phase 1 — Repair control/security contract gaps

5. Fix native `max_autonomous_level` payloads and add live backend contract tests.
6. Protect `/conversations` under API-key auth.
7. Persist approval/recommendation audit records without persisting authority.
8. Add frontend CI and deterministic owner-control E2E.

### Phase 2 — Complete reliability and deployment evidence

9. Extend cancellation to remaining subprocess/model/browser/media paths.
10. Compile and test Android.
11. Split composition monoliths.
12. Run owner-hardware VLM, LoRA, audio, camera, ADB, browser, and resource benchmarks.
13. Update the canonical measured status only from clean CI/hardware evidence.

---

## Deployment gate checklist

Do not move beyond localhost development until all of these are true:

- [ ] Core CI installs and runs from a clean checkout.
- [ ] Frontend CI tests and builds.
- [ ] `app.server.runtime is CognitiveRuntime.get_instance()` is regression-tested.
- [ ] Every LLM-backed tool rejects simulated/offline completions as generated success.
- [ ] Unified server starts with the documented core dependencies.
- [ ] Native safety ceiling updates the effective backend policy.
- [ ] All non-health information routes require API key when configured.
- [ ] Exact authorization, replay rejection, pause, cancellation, rollback, and plan revision conflicts pass E2E.
- [ ] Android compiles and native controls pass authenticated integration tests.
- [ ] Full optional dependency installation is documented per platform and no longer blocks core CI.
- [ ] Hardware/model capabilities are measured on the owner machine.
- [ ] Canonical status reflects current clean-run evidence rather than historical counts.

## Final assessment

The project has a credible architecture for a controlled local coworker, especially in authority separation, verification, projects, and evidence-linked learning. The current weaknesses are not primarily a lack of more “AGI modules.” They are integration integrity problems: the real server can instantiate two brains, generated-content tools can still launder offline simulation into success, and CI does not run tests. Fixing those foundations will produce more real intelligence and reliability than adding new cognitive subsystems before deployment.

This audit does **not** claim human-level AGI, consciousness, complete hardware support, or a deployment-ready state.
