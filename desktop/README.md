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
- ✅ **Phase 2** — native hardware (Tools tab): camera preview/capture, location,
  filesystem search, hardware + backend status.
- ✅ **Phase 3** — polish layer:
  - **System tray** — minimize-to-tray, tray menu (Show/Hide, Talk to Beanie, Quit),
    and the orb as the tray icon.
  - **Native notifications** — desktop toasts when the agent replies while hidden.
  - **Wake-word voice** — "🎙 Talk to Beanie" captures the mic (PyAudio) and
    streams PCM to the backend (utterance detection → STT → cognitive runtime);
    replies are spoken locally (pyttsx3, optional).
  - **Settings persistence** — server URL, wake word, voice speed, minimize-to-tray,
    and notifications, stored via QSettings (`desktop/settings.py`).

## Optional dependencies

- `PySide6` — required (the window itself).
- `opencv-python` — camera tab.
- `pyaudio` — voice ("Talk to Beanie").
- `pyttsx3` — spoken replies.
- `faster-whisper` (backend) — speech-to-text for voice input.

All are optional and degrade gracefully when absent.

See `../DESKTOP_APP_PLAN.md` for the full plan.
