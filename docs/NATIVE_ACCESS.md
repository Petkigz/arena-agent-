# Native (Browser-Free) Hardware Access

The cognitive engine and every capability run as a **native Python process** with
full OS permissions — no browser sandbox, no HTML/CSS constraints, no permission
prompts. The React SPA is *only* a remote-control UI; the system works fully
without it (voice, tray icon, native tools).

## What is already native

| Capability | Module | Notes |
|---|---|---|
| Storage / filesystem | `app/tools/universal_filesystem.py`, `deep_os_controller.py`, `doc_manager.py` | Full read/write, no browser FS restrictions |
| Microphone | `backend/voice/audio_capture.py` (PyAudio) | Records directly from the OS — no `getUserMedia`, no HTTPS, no prompt |
| Screen capture | `app/tools/screen_capture.py` (mss) | Full desktop grab |
| Webcam (phone) | `app/tools/android_adb_controller.py` | ADB camera shutter |
| Notifications | `plyer`, `pystray` (system tray) | Native OS notifications |
| Desktop webcam | `app/tools/camera_capture.py` (OpenCV) | Direct webcam frame capture — no browser |
| Location | `app/tools/location_service.py` | Phone GPS via ADB, or IP geolocation — no browser geolocation prompt |

## The two newly-added native capabilities

1. **Desktop webcam** (`camera_capture.py`) — captures a still frame from device 0
   via OpenCV. Enables with `pip install opencv-python`. Gracefully reports
   "no webcam" when absent.
2. **Location** (`location_service.py`) — resolves coordinates from the phone's GPS
   (ADB `dumpsys location`) or, failing that, IP geolocation (free, keyless).
   Returns "unknown" when offline.

Both follow the project's graceful-degradation pattern: if the hardware or the
optional dependency is missing, they return a clear failure result instead of
crashing the pipeline.

## Why this matters (vs. a browser app)

A browser can never do these things without friction:

- **Microphone/camera** require HTTPS + a user-gesture + a permission prompt, and
  the browser decides the format/limits.
- **Filesystem** is sandboxed (no arbitrary read/write of the whole disk).
- **Location** requires a permission prompt and the browser's own (often blocked)
  geolocation path.

The native backend bypasses all of that — it *is* the machine.

## Running browser-free

```bash
# Start the native server + system-tray icon (no browser required):
PYTHONPATH=. python -m app.desktop_tray

# Or headless (voice-driven, no UI at all):
PYTHONPATH=. uvicorn app.server:app --host 0.0.0.0 --port 8000
```

The web UI at `http://localhost:8000/` remains available as a convenience, but it
is optional.
