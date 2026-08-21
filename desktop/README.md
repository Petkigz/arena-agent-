# Arena Native Desktop Client (browser-free)

A PySide6 (Qt) desktop window that talks to the Arena backend over localhost —
no browser, no HTML, no permission prompts. The backend (`app.server:app`) owns
all native hardware access (mic, camera, screen, location, filesystem); this
client is the window.

## Design

Matches the existing web UI's **"Beanie"** design language:

- A **floating, breathing presence orb** — color + pulse reflect the agent's
  state (idle=blue / working=amber / listening=green / speaking=purple /
  offline=gray), painted with a 3D radial gradient + soft glow.
- **"BEANIE" / "Personal AI"** branding with a status message.
- **Quick actions** ("Continue project", "What's new?", "Research", "Talk to me")
  and a **"🎙 Talk to Beanie"** button.
- **Bottom navigation** (Beanie / Chat / Tools) on the Arena dark theme
  (#0F172A background, #1E293B surface).

## Run

```bash
# 1. Install the GUI dependency (one-time)
pip install PySide6

# 2. Start the backend
PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000

# 3. Launch the desktop window
PYTHONPATH=. python -m desktop.main
```

## Phase status

- ✅ **Phase 1** — window shell, connection status, text chat.
- ✅ **Phase 2** — native hardware (Tools tab):
  - **Camera** — live webcam preview + still capture (uploads to the backend).
    Requires `pip install opencv-python`; degrades gracefully without it.
  - **Location** — resolve native location (phone GPS → IP fallback) off-thread.
  - **Files** — search the filesystem via the backend's `/filesystem/search`.
  - **Status** — live hardware telemetry (CPU/RAM/disk) + backend/LM Studio status.
- ⏳ **Phase 3** — system tray, notifications, wake word, settings persistence.

See `../DESKTOP_APP_PLAN.md` for the full plan.
