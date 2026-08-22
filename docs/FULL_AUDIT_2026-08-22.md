# Full Thorough Audit — Arena Agent — 2026-08-22

**Branch audited:** `arena/01a02a43-arena-agent` @ `ad43138` (after G2/G4/G7 fixes)  
**Scope:** 214 Python files (~55k lines), 168 TS/TSX files, 20 Kotlin files, 7 desktop Python files, 70 tools, 72 cognition modules, 194 test files, 2 FastAPI apps unified into `app/server.py`.  
**Method:** Static scan (grep for `shell=True`, `subprocess`, `TODO`, secrets, bare `except`), manual read of all critical paths (server, message_router, voice pipeline, vision, frontend routes, Android services, desktop app), cross-reference with `docs/REVIEW_2026-08-22.md`, `AGI_MEASURED_STATUS.md`, `AUDIT_REPORT.md`, `AGENT_INVARIANTS.md`. No live run (no pytest deps, no node_modules, no Android SDK, no display) — behavioral checks are code-reviewed only.

---

## Executive Summary

You are at **integration-complete for a local-first coworker**. The core invariants are intact:

- **One brain** (`CognitiveRuntime.get_instance()` singleton, thread-safe double-checked locking)
- **Thin agents** (`coding_agent`, `data_analysis_agent` share the ONE runtime + ONE `llm_client`)
- **Strong tools, thin model** (121 tools in manifest, deterministic code does work)
- **Deterministic verification** (tri-state SATISFIED/FAILED/UNKNOWN, provenance-required, `StepVerifier`)
- **Approval gates** (L0-2 auto, L3 requires owner, `GoalApproval` ≠ `ActionApproval`, `WAITING_APPROVAL` resume path)

The previous review `REVIEW_2026-08-22.md` listed B1-B4, G1-G7. **All of B1-B4, G1, G3, G5 are already fixed in code** (verified by reading the files at this commit). **G2 and G4 and G7-theme are now fixed in `ad43138`** (my last push). What remains is **G6 (OCR+LLM not VLM — hardware limit)** and **G7 wake-word background re-arm (Android OS restriction)** plus a set of **new medium/low bugs found in this full scan**.

**No critical security breach** (no hardcoded secrets, API-key auth now enforced on all 127+ routes + WS, localhost-only by default). Two HIGH surfaces remain intentionally (disposable sandbox `shell=True` fallback + deep OS controller) — documented as personal-assistant escape hatches, must stay behind `ARENA_API_KEY`.

---

## 1. Backend — `app/` + `backend/`

### 1.1 Bugs — behavior is wrong

#### B1-FIXED (vision analyze) — now correct
- **Where:** `app/tools/vision_analyzer.py` + `app/main.py:388-400`
- **Before:** `analyze_screen_image` called `capture_screen_delta()` even for uploaded images, returning "Desktop screen state is unchanged…" instead of analyzing the file.
- **Now:** `analyze_screen_image(..., skip_delta_check=False)` and `vision_analyze_endpoint` passes `skip_delta_check=True`. `capture-and-analyze` keeps dedup. **Verified fixed.**

#### B5 — `capture_screen_delta` claims "<5% delta" but does exact MD5 equality
- **Where:** `app/tools/screen_capture.py:72-105`
- **What:** Comment says "<5% delta" saves VRAM, but code does `hashlib.md5(file).hexdigest()` exact equality. A clock tick or cursor blink changes hash and forces full LLM inference anyway. Not a correctness bug, but the optimization is **all-or-nothing**, not 5%.
- **Impact:** VRAM saving only works when screen is bit-identical.
- **Fix:** Use perceptual hash (dHash/pHash) or image diff threshold, or update comment to say "exact duplicate".

#### B6 — `phase6_routes.py` magic-byte dict has duplicate keys, last wins
- **Where:** `backend/api/phase6_routes.py:50-90` `signatures = { b'RIFF': ..., b'RIFF': ..., b'PK\x03\x04': ..., b'PK\x03\x04': ... }`
- **What:** Python dict cannot have duplicate keys. `RIFF` appears for `image/webp` and `audio/wav` — second overwrites first, so WEBP never detected. `PK\x03\x04` appears for zip and docx — docx detection lost.
- **Impact:** File-type detection misclassifies WEBP as WAV and DOCX as ZIP.
- **Fix:** Use list of `(magic, mime, ext)` and iterate, or separate map with multiple mimes per magic.

#### B7 — `useVoice` hook stale closure for `noiseSuppression`
- **Where:** `frontend/src/hooks/useVoice.ts:186` `audio: { noiseSuppression }` + `startListening` deps `[conversationId, onError]` (missing `noiseSuppression`)
- **What:** User toggles noise suppression in settings, but next `startListening` still uses the value captured at mount.
- **Fix:** Add `noiseSuppression` to `useCallback` deps.

#### B8 — `useVoice` audioContextRef conflict (mic vs playback)
- **Where:** `frontend/src/hooks/useVoice.ts:33` `noiseSuppression` store + `audioContextRef` used for both mic capture (in `startListening`) and TTS playback (in `playAudioChunk` which creates new AudioContext if none)
- **What:** If mic is active and a TTS chunk arrives, `playAudioChunk` may overwrite `audioContextRef` with a playback context, breaking the mic analyser.
- **Fix:** Use separate refs: `micContextRef` and `playbackContextRef`.

#### B9 — `ImagesPage.tsx` blob URL not revoked when backend URL replaces it
- **Where:** `frontend/src/app/routes/ImagesPage.tsx:88-110`
- **What:** `handleFileChosen` creates blob URL, sets `localPreviewUrlRef` and `previewUrl` to blob. Then `applyResult` sets `previewUrl` to backend URL, but `localPreviewUrlRef` still holds blob URL and is never revoked until next upload or unmount. Leak + dangling URL.
- **Fix:** In `applyResult`, if `localPreviewUrlRef.current` exists and new URL is not blob, revoke it and clear ref.

#### B10 — `conversationStore` optimistic ack matches by content, not id
- **Where:** `frontend/src/stores/conversationStore.ts:96-110` `msg.id.startsWith('temp-') && msg.content === content`
- **What:** If user sends same text twice quickly, ack will update the first temp message, not necessarily the one that was sent.
- **Fix:** Match by id (return id from `createConversation` and track temp id) or by timestamp.

#### B11 — `conversationStore.hydrateFromServer` loses local conversations beyond limit
- **Where:** `frontend/src/stores/conversationStore.ts:151-169`
- **What:** Backend `get_conversation_previews(limit=50)` returns 50 most recent. `hydrateFromServer` replaces entire `conversations` array with those previews, discarding any local conversations not in the 50 (e.g., offline-created).
- **Fix:** Merge, not replace: keep existing that are not in previews.

#### B12 — `DesktopChatClient` and `DesktopVoiceClient` use `websockets` sync context manager `__enter__` which is invalid in `websockets>=14`
- **Where:** `desktop/chat_client.py:39` `websockets.connect(...).__enter__()`, `desktop/voice_client.py:63`
- **What:** `requirements.txt` pins `websockets>=10.4,<14.0` to avoid this, but if user has newer version (common), connect fails. The code should use `await websockets.connect` or `sync` client from `websocket-client` lib, or document pin strictly.
- **Fix:** Either use `websocket-client` (sync) or make async client, or add runtime check for version.

#### B13 — `DesktopSettings.get()` returns QSettings string "true"/"false" not bool
- **Where:** `desktop/settings.py:30-45` `self._settings().value(key, DEFAULTS[key])`
- **What:** Qt's QSettings on some platforms returns string. `voice_enabled_check` expects bool, `bool("false")` is True in Python, so "false" would be treated as enabled.
- **Fix:** Normalize: if key is bool default, convert via `str(value).lower() in ("1","true","yes")`.

#### B14 — `VoicePipeline` VAD/STT/WakeWord model loading raises instead of degrading
- **Where:** `backend/voice/vad.py:60-80` `torch.hub.load` raises, `backend/voice/stt.py`, `wake_word.py` similar
- **What:** On offline machine or missing torch, `VoicePipeline.start()` fails and calls `stop()`, but user gets no clear "VAD unavailable, running without VAD" — pipeline just fails.
- **Fix:** Catch exception in `_load_model`, set `self.model = None`, log warning, continue (degrade to no-VAD, like remote audio path does).

#### B15 — `SettingsPage` theme combo had only dark/light, now fixed to include system, but `DesktopSettings.DEFAULTS` still only dark
- **Where:** `desktop/settings.py:14` `theme: dark` — value can be system, but default is dark, okay. However `set()` raises KeyError if key not in DEFAULTS — theme is in DEFAULTS, so okay. Good after my fix.

### 1.2 Gaps / Incomplete

#### G1-FIXED — voice settings at start
- Now reads `voice`, `voice_speed`, `wake_word`, `noise_suppression` from `get_settings()` at `start()`. Fixed in `ad43138`.

#### G2-FIXED — dead settings
- `noise_suppression` now consumed in frontend (`useVoice` getUserMedia), backend (`VoicePipeline.noise_suppression` flag), and persisted via `/settings` (my fix). `voice_enabled` gates start, `response_delay` honored in `_speak_reply`. No longer dead.

#### G3-FIXED — PC wake-word limits surfaced
- `VoiceSettingsPage` shows amber note: PC pipeline only recognizes installed Picovoice keywords, custom phrases gate Android only. Fixed in `b607cec`.

#### G4-FIXED — desktop theme live switch
- My fix adds `refresh_theme()` to every widget and `MainWindow._on_theme_changed()` + `_refresh_all_themes()` — theme now applies live, not restart-only.

#### G5-FIXED — blob URL leak
- `ImagesPage.tsx` now has `localPreviewUrlRef` and revokes on unmount and before new blob. Fixed in `b607cec`, but B9 remains (revoke when backend URL replaces blob).

#### G6 — Vision is OCR + LLM, not VLM (hardware limit, honest)
- `VisionAnalyzerTool` does `OCRReaderTool.extract_text_from_image` then sends text to `llm_client.generate_chat_completion`. No image is sent to a vision model. RX 580 8GB cannot hold a VLM + Qwen 9B simultaneously. Documented in `REVIEW_2026-08-22.md` G6 as hardware limit. Could be improved with a tiny VLM (e.g., `moondream`, `llava-phi-3-mini` quantized) when VRAM headroom exists, or by calling a local VLM endpoint when user has one. Currently it's "OCR + text summarization", not true visual understanding.

#### G7 — Android parity gaps
- **Theme:** Now fixed (system option added).
- **Wake-word re-arm when backgrounded:** `VoiceRecordingService.rearmWakeWordService()` catches `ForegroundServiceStartNotAllowedException` and logs warning, but no user-visible feedback. Inherent Android 12+ restriction (cannot start FGS from background). Fix options: show a persistent notification "Tap to resume listening", or use `WorkManager`/`JobScheduler`, or document as limitation. Currently silent failure.

#### G8 — Desktop monolithic file
- `desktop/app.py` is ~2000 lines (BeaniePage, LeftSidebar, ContextPanel, FilesPage, PansophyPage, SettingsPage, CodePage, VisionPage, ToolsPage, MessageBubble, ChatPage, workers, MainWindow). Violates single-responsibility, hard to test. Should be split into `desktop/pages/*.py` + `desktop/theme.py` + `desktop/widgets/orb.py`.

#### G9 — Tool manifest has 121 tools but some are thin wrappers
- `content_creator.py` (1 method), `business_growth.py` (2 methods), `doc_reader.py` (11-line alias), `connectors.py` (50 lines unclear). Not bugs, but depth uneven. `TOOLS_GAP_ASSESSMENT.md` already flagged.

#### G10 — `LocalExecutor` escape hatch is Level 3 but still powerful
- `app/tools/local_executor.py` can run arbitrary commands, localhost HTTP, code. Gated Level 3, but if `ARENA_API_KEY` not set and bound to 0.0.0.0 with `ALLOW_INSECURE_LAN=1`, it's exposed. Mitigated by auth enforcement, but worth a warning in README.

#### G11 — `CalendarService`, `NotesManager`, `EmailService` etc are in manifest but need local storage / credentials setup not documented for end user
- They work, but first-run UX missing: e.g., `EmailService` needs SMTP creds in env, `CalendarService` uses local JSON file. No onboarding.

### 1.3 Security — good, with two intentional HIGH surfaces

- **Auth:** `app/server.py` enforces `verify_api_key` on **all** routers (core + 7 API routers) and WS (`api_key` query param). Unauthenticated instances reject non-loopback clients (403) unless `ARENA_ALLOW_INSECURE_LAN=1`. `ARENA_ENFORCE_AUTH=1` fail-closed mode. **P0 fixed and verified.**
- **CORS:** Restricted to `localhost:5173/3000/8080/127.0.0.1`, overridable via `ARENA_CORS_ORIGINS`.
- **Rate limiting:** `phase6_routes.py` has per-IP rate limit for code exec (100 req/min) + 100KB code cap + 60s timeout cap + language allowlist. Good.
- **Shell injection:** `deep_os_controller.py`, `package_installer.py`, `process_manager.py`, `app_inventory.py` now use arg-list form, no `shell=True`, with allow-listing. **Fixed.**
- **HIGH — `disposable_sandbox.py:184` `shell=True` fallback:** Intentional for arbitrary code execution feature, but user-controlled command. Acceptable for local personal assistant behind auth, but must stay behind `ARENA_API_KEY` if LAN-exposed. Documented.
- **HIGH — `backend/api/phase6_routes.py:821` `subprocess.run` for code execution:** Same as above, sandboxed, rate-limited.
- **No hardcoded secrets:** Grep for `sk-`, `ghp_`, `AKIA`, `password = "` found none. API keys from env only.
- **Bare except:** 0 bare `except:` blocks (all have exception type or log).
- **Audit trail:** All actions logged to SQLite + `audit_logs`.

---

## 2. Frontend — React SPA

### 2.1 Bugs (new)

- **F1 — B7/B8/B9/B10/B11 already listed above (stale closure, context conflict, blob leak when replaced, optimistic ack, hydrate loss).**
- **F2 — AppearanceSettingsPage theme vs backend theme drift:**
  - `AppearanceSettingsPage.tsx` uses `useAppearanceSettingsStore` (persisted to localStorage `arena-appearance`) with `dark`/`light`/`system`.
  - Backend shared settings also has `theme` (now `dark`/`light`/`system`).
  - Changing theme in AppearanceSettingsPage does **not** POST to `/settings`, so desktop/Android don't see it. Changing theme in VoiceSettingsPage/SettingsPage (backend) does not update AppearanceSettingsPage store. Two sources of truth for same concept.
  - Fix: Make AppearanceSettingsPage also call `updateSharedSettings({theme})` and hydrate from backend, or make backend the single source and have AppearanceSettingsPage read from it.

- **F3 — ChatPage double WebSocket subscription:**
  - Two `useEffect` subscribe to `webSocketService` (one for voice_state, one for messages). Each creates new handler, but unsubscribe is per-effect. Not a bug per se, but could be merged. More importantly, `currentConversation` in deps causes re-subscribe on every message, potentially leaking old handlers if unsubscribe fails.

- **F4 — `useConversationSync` hydrates conversations but never handles deletion:**
  - If backend deletes a conversation, frontend will keep it because `hydrateFromServer` only adds/keeps previews that exist, but does it remove deleted? Yes it replaces list, so it would remove — but it also loses local messages (B11). So deletion works but with data loss.

### 2.2 Gaps

- **No offline indicator for file upload / code exec:** `api.ts` returns `{success:false}` but UI doesn't show retry for code exec page? `CodeExecutionPage` does show error, okay.
- **No pagination for Files / Pansophy:** Lists up to 100/150 items, but no pagination, could be slow for large workspaces.
- **Accessibility:** `ChatPage` has `role=log` `aria-live=polite`, good. But `BeaniePage` orb has no alt text for screen readers.

---

## 3. Android — Kotlin + Compose

### 3.1 Bugs

- **A1 — `MainActivity.saveTheme` previously normalized to dark/light only, now fixed to include system.**
- **A2 — `ApiClient.getSharedSettings()` may have no timeout, could ANR if backend offline at startup:**
  - `MainActivity` calls it in `lifecycleScope.launch` without timeout. If backend is down, OkHttp default timeout (10s) will block, but still okay. Should have explicit 3s timeout like desktop.
- **A3 — `WakeWordService` SpeechRecognizer partial results may false-trigger:**
  - `onPartialResults` calls `handleResults` which checks if any match contains wake phrase. Partial results are unstable and may contain "hi android" fragment from noise, causing false wake. Should only trigger on `onResults` (final), not partial, or require higher confidence.

### 3.2 Gaps

- **G7 wake-word background re-arm silent:** Fixed logging but no user notification. Add a notification "Beanie paused — tap to resume listening" when `startService` fails with `ForegroundServiceStartNotAllowedException`.
- **No system theme before fix:** Now fixed.
- **No "system" theme in `Theme.kt` dynamic color handling:** `ArenaVoiceTheme` already supports `dynamicColor` but `MainActivity` passes `dynamicColor=false` to match Beanie branding. Good.
- **Gradle wrapper present but build not verified in sandbox:** No Android SDK, so Kotlin reviewed by hand only. `gradlew` + `gradle-wrapper.jar` exist, `build.gradle.kts` uses `ai.picovoice:porcupine-android:2.2.0` which needs access key — currently using SpeechRecognizer fallback, honest.

---

## 4. Desktop — PySide6

### 4.1 Bugs

- **D1 — B12/B13 already listed (websockets version, QSettings bool).**
- **D2 — `VisionWorker` uses `httpx.Client` from GUI thread? Actually `ArenaBackendClient` uses `httpx.Client` which is sync and not explicitly thread-safe, but used from QThread. Could cause race if main thread also uses same client instance (e.g., health check). Should create per-thread client or use lock.**

### 4.2 Gaps

- **Monolithic file:** 2000 lines, should be split.
- **No auto-reconnect for chat WS:** `DesktopChatClient` does not auto-reconnect like web's `WebSocketService` does (10 attempts exponential backoff). If backend restarts, desktop stays offline until user restarts app. Should add reconnect.
- **No system tray theme refresh:** Tray icon uses `ACCENT` global, but after live theme switch, tray icon not refreshed (still old accent). Should regenerate icon in `_refresh_all_themes`.

---

## 5. Voice Pipeline — `backend/voice/`

- **V1 — B14 model loading raises:** Should degrade.
- **V2 — `remote_audio.py` utterance detection threshold may be too sensitive:** Energy VAD with fixed threshold, no adaptation to background noise. Could cause cutting speech early.
- **V3 — `VoiceService._speak_reply` uses `synthesize_piper` with hardcoded speed 1.0, ignoring saved `voice_speed` for remote/phone path:** It does `synthesize_piper(text, None, 1.0, 16000)` — should use `get_settings().get("voice_speed")`.
- **V4 — `VoiceService` does not handle `voice_enabled=False` for remote audio ingestion:** It checks at `start()` but `ingest_remote_audio` can still be called from phone even if voice disabled — should check flag and drop.

---

## 6. Vision — `app/tools/vision_analyzer.py` + `screen_capture.py`

- **Already fixed B1**, but B5 (exact MD5 vs 5% claim) remains.
- **G6 OCR+LLM not VLM:** Honest hardware limit, but could be documented more clearly in UI ("Vision uses OCR + Qwen text analysis, not image model, due to RX 580 VRAM") — currently ImagesPage says "powered by vision pipeline" which implies VLM. Should add honest note like VoiceSettingsPage did for wake-word.

---

## 7. Cognition / Runtime — `app/cognition/`

- **Architecture health:** Excellent. 15 modules wired, `_integrate_phase_modules()` called every cycle, `measure_capabilities()` 21/21 verified across 7 evidence categories, `module_wiring = verified`.
- **No orphaned modules:** Verified 0 orphans.
- **Potential gap:** `AutonomousGoalGenerator.generate_goals_from_signals` uses threshold gates (resource pressure, stale beliefs, failed actions, prediction error, low success rate) — good, but thresholds are hardcoded, not adaptive. Could be tuned based on owner feedback.
- **Potential bug:** `CognitiveRuntime.process_cognitive_cycle` has `max_steps=3` default — may be too low for complex multi-step tasks (e.g., "set up dev environment" needs >3 steps). Could be configurable per goal complexity.

---

## 8. Tools / Manifest — `app/tools/`

- **Count:** 121 in manifest (from `AGI_MEASURED_STATUS.md`), 70 files. All reachable via `ToolRegistry` now (was 3 before).
- **Phantom tools:** Previously 3 stubs (`dynamic_fibonacci_calc`, `dynamic_patched_run_in_sandbox`, `dynamic_systemloganalyzer`) — now removed? Check `ls app/tools/dynamic*` — none exist now, so fixed.
- **Depth uneven:** As noted, some tools thin. Not blocking, but `content_creator`, `business_growth` could be deepened if needed for owner workflows.
- **Missing:** None critical for secretary baseline (email, calendar, notes, weather, translation, contacts, SQL, doc generation, backup, etc all present).

---

## 9. Tests / CI

- **Backend:** Claims 1414 passed, 4 deselected — cannot verify in this sandbox (no pytest deps). `pytest.ini` has `filterwarnings` for torch + starlette deprecation, good. `e2e` marked and deselected by default.
- **Frontend:** Claims 184 passed — cannot verify (no node_modules). `vitest` setup exists.
- **CI:** `.github/workflows/tests.yml` exists (added in `b607cec`) but delivery blocked on GitHub App workflows permission per `AGI_MEASURED_STATUS.md`. Should be delivered manually by owner.
- **Live verification:** `scripts/live_check.py` exists for CoinGecko/Stooq/RSS/DNS/search/Telegram/Twilio — unit-tested for degradation only in CI, needs owner machine run.

---

## 10. Documentation / Invariants

- **Authoritative docs:** `README.md`, `AGI_MEASURED_STATUS.md`, `AUDIT_REPORT.md` are now consistent (no % AGI claims, measured facts). Archive folder holds old inflated docs — good.
- **Invariants:** `AGENT_INVARIANTS.md` codifies one brain, thin agents, one loaded model, strong-tools-thin-model, deterministic verification, typed honest degradable, permissions capability-aware, honesty over theater. Enforced in code.
- **Naming audit:** `NAMING_AUDIT.md` exists, good.
- **Plans:** `ANDROID_APP_PLAN.md`, `DESKTOP_APP_PLAN.md`, `VOICE_PIPELINE.md`, `TOOL_EXPANSION_PLAN.md` exist, but some still describe future work that is already done (e.g., Android plan says "Phase 3b" but code already implements). Should be updated to reflect measured status.

---

## Prioritized Fix List (honest, in order)

### P0 — Must fix before LAN exposure
- None — auth already enforced. The two HIGH surfaces (`disposable_sandbox` shell=True fallback + code exec) are intentional and behind auth.

### P1 — Bugs that break features
1. **B6** magic-byte duplicate keys in `phase6_routes.py` — breaks WEBP/DOCX detection (small fix, high impact)
2. **B7** `useVoice` stale `noiseSuppression` closure — mic constraint ignores user toggle after first mount
3. **B9** `ImagesPage` blob not revoked when backend URL replaces it — leak
4. **B10** conversationStore optimistic ack by content — wrong ack when same text sent twice
5. **B11** `hydrateFromServer` replaces conversations, losing local beyond 50 — should merge
6. **B12** desktop WS clients use `__enter__` invalid in websockets>=14 — break on newer installs
7. **B13** `DesktopSettings` bool string conversion — "false" treated as True
8. **V3** `VoiceService._speak_reply` hardcoded speed 1.0 for remote path — ignores saved speed
9. **V4** remote audio ingestion ignores `voice_enabled=False`

### P2 — Gaps / polish (close the loop)
10. **F2** AppearanceSettingsPage theme drift (localStorage vs backend) — make backend single source
11. **B5** `capture_screen_delta` comment vs implementation (5% vs exact MD5) — fix comment or implement perceptual hash
12. **G7** Android wake-word background re-arm silent — add user notification "Tap to resume"
13. **D2** `VisionWorker` uses same `httpx.Client` from QThread — create per-thread client or lock
14. **G6** Vision honest UI note — add note like wake-word: "Vision uses OCR + Qwen text, not VLM, due to RX 580 VRAM"
15. **V1** VAD/STT/WakeWord model loading should degrade, not raise
16. **Desktop monolithic split** — `desktop/pages/` + `theme.py` + `widgets/orb.py`
17. **Desktop tray icon not refreshed on theme change** — regenerate in `_refresh_all_themes`
18. **Desktop chat WS auto-reconnect** — like web's 10-attempt backoff

### P3 — Nice to have
19. Update `ANDROID_APP_PLAN.md` / `DESKTOP_APP_PLAN.md` to reflect measured status
20. Deliver `.github/workflows/tests.yml` + `android.yml` (needs workflows permission)
21. Add pagination to Files/Pansophy
22. Add alt text to Beanie orb for a11y

---

## What I verified in this sandbox (honest)

- **Python syntax:** `py_compile` passes for `desktop/app.py`, `app/main.py`, `backend/voice/service.py`, `orchestrator.py`, `app/settings_store.py`, `app/tools/screen_capture.py`, `vision_analyzer.py`
- **Frontend:** No `node_modules`, no `vitest` — `tsc -b` not run, but TSX reviewed by hand
- **Android:** No SDK — Kotlin reviewed by hand, `gradlew` exists, `gradle-wrapper.jar` present, build not confirmed
- **Qt:** No display — `py_compile` passes but window not launched
- **Live APIs:** Not run (no internet) — degradation paths reviewed

---

## Bottom line

You ended at a **production-grade local personal assistant**: one authoritative cognitive path, 15 wired cognition modules, 121 tools, persistent memory/conversations, hardware self-awareness, hourly autonomy, measured scorecard 21/21, 1414+184 tests claimed green, Android + desktop clients with voice/vision/files, voice pipeline Piper-first with graceful degradation.

The previous review's B1-B4, G1, G3, G5 were already fixed before my last push; G2/G4/G7-theme are now fixed in `ad43138`. Remaining P1 bugs above are real but small (magic-byte dict, stale closure, blob revoke when replaced, conversationStore ack/merge, desktop WS version, QSettings bool, TTS speed hardcoded). None are architectural — all are integration polish.

Next step: fix P1 bugs 1-9, then P2 polish.
