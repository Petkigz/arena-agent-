# Desktop Window Plan — Native (Browser-Free) Arena Client

## Goal

A native desktop window that replaces the React SPA as the primary UI, giving
**full, frictionless hardware access** (mic, camera, storage, location) with no
browser sandbox, no permission prompts, no HTML/CSS constraints.

## Architecture

Keep the existing FastAPI backend (`app.server:app`) as the **brain** — it already
owns native hardware access (mic via PyAudio, camera via OpenCV, screen via mss,
location via ADB/IP, filesystem). Build a **native client** that talks to it over
localhost HTTP + WebSocket.

```
┌───────────────────────────────┐        HTTP / WS        ┌──────────────────────────┐
│  Native desktop window        │ ──────────────────────► │  FastAPI backend (brain) │
│  (PySide6 / Qt)               │  localhost:8000         │  + 15 cognition modules  │
│  - chat (text + voice)        │                          │  + native tools          │
│  - webcam preview             │                          │  + LM Studio (Qwen)      │
│  - location / files / status  │                          └──────────────────────────┘
└───────────────────────────────┘
```

**Why PySide6 (Qt):**
- Native widgets + OS integration, LGPL license (free for commercial use).
- Can display webcam frames directly (`QImage`/`QPixmap`) — no browser.
- Native file dialogs, system tray, notifications.
- Mature, cross-platform (Windows/macOS/Linux).

## Phases

### Phase 1 — Skeleton + backend connection + chat (this turn)
- `desktop/` package: `main.py` entry, `app.py` window, `backend_client.py` (HTTP + WS).
- Window with: connection status, a **chat** tab (send text → backend → streamed reply).
- Auto-detect/launch the backend if not running.
- Graceful "backend offline" state.

### Phase 2 — Native hardware tabs
- **Voice**: mic button (PyAudio capture → stream PCM → backend STT → reply + TTS).
- **Camera**: live webcam preview + still capture (OpenCV), save/annotate.
- **Location**: current location card (ADB phone GPS → IP fallback), refresh.
- **Files**: native file browser (list/open) over the backend's filesystem tool.

### Phase 3 — System tray + notifications + polish
- Minimize to tray, native notifications, wake-word (openWakeWord) integration,
  keyboard shortcuts, settings persistence (server URL, models, wake word).

## Non-goals (kept as-is)
- The cognitive engine, tools, and API stay unchanged — only the *client* is new.
- The React SPA remains available (optional) at `http://localhost:8000/`.

## Verification
- Unit tests for `backend_client.py` (HTTP + WS parsing) — runnable in CI.
- Manual smoke on the user's machine (GUI needs a display).
- `desktop/README.md` with run instructions.
