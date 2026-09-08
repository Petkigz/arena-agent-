# Owner Resurrection Test Guide (run on YOUR pc)

Branch: `arena/01a07c3e-arena-agent` (tip: `38ebf72`, CI green).
This tests the 2026-09-08 resurrection slice for real: voice-first, eyes,
anticipation, the silent watcher, asks-not-refusals, and background life.
Everything is proven in CI/sandbox; only you can prove mic, screen, speakers,
and your own wake word.

**Windows note (from the earlier runbook, still true):** run commands one per
line — PowerShell 5 breaks multi-line `\` continuations. Use the `%VAR%=...`
or `$env:VAR="..."` forms shown.

---

## 1. One-time setup

```bash
git fetch origin
git checkout arena/01a07c3e-arena-agent
git pull origin arena/01a07c3e-arena-agent

python -m venv .venv
```

```bash
# Windows:
.venv\Scripts\pip install -r requirements-core.txt -r requirements-test.txt
# Linux/macOS:
.venv/bin/pip install -r requirements-core.txt -r requirements-test.txt
```

Optional but recommended for the voice + tray features (all fail honestly
without them — nothing fakes):

```bash
.venv/Scripts/pip install openwakeword piper-tts pystray
# Linux/macOS:
.venv/bin/pip install openwakeword piper-tts pystray
```

- `openwakeword` — real wake-word detection (built-in models: hey_jarvis,
  hey_mycroft, alexa…). First run downloads its models.
- `piper-tts` — the voice that speaks. Then pick a voice on /settings/voice.
- `pystray` — the system-tray app.

Frontend (built once, served by the backend at http://127.0.0.1:8000):

```bash
cd frontend
npm ci
npm run build
cd ..
```

Start **LM Studio** with your model loaded (default it listens on
`http://localhost:1234/v1`) — that is the chat brain.

---

## 2. Start it

```bash
# Windows:
set PYTHONPATH=.
.venv\Scripts\uvicorn app.server:app --host 127.0.0.1 --port 8000
# Linux/macOS:
PYTHONPATH=. .venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8000
```

In the startup log you should see:
`Background observer started (read-only environment probes)`.

Open **http://127.0.0.1:8000** — the app, not JSON.

Browser tip: use Chrome/Edge and allow mic + screen-capture prompts when asked.

---

## 3. The test checklist (do top to bottom, note anything that differs)

### A. Health (30 seconds)
- `http://127.0.0.1:8000/api/status` → JSON `status: online`.
- `http://127.0.0.1:8000/cognition/anticipations` → JSON with an honest note
  (empty at first — that is correct).
- `http://127.0.0.1:8000/cognition/environment/observations` → JSON with
  `is_running: true` and a few "appeared" observations already.

### B. Voice-first — settings (/settings/voice)
1. Enable voice. Wake-word section shows **WakeWordManager** + **trainer**.
2. Trainer: record/upload **5 samples** of your wake word → expect an HONEST
   message that full custom-model training is not integrated yet (it refuses
   to fake a model — by design, truth boundary). Samples still upload.
3. Manager: lists models; you can activate/delete entries.
4. If `openwakeword` is installed, built-in models (hey_jarvis etc.) are
   detectable by the backend detector.
5. Pick a Piper voice → "Test voice" → you should HEAR it (needs piper-tts;
   without it you get a typed honest "install piper" style result, not silence).

### C. Voice-first — the conversation (the big one)
1. Open Chat, start a conversation, click the mic (allow mic).
2. While it is **listening/recording**, the full **VoiceOverlay** takes over
   the conversation surface — that is the voice-first face.
3. Say "hello, what can you do" → watch your words transcribe and get sent;
   the answer comes back (LM Studio thinking), and speaks if Piper is set.
4. Text still works as backup: type a message normally any time.

### D. Eyes (Images page)
1. Click **Start capture** → browser asks which screen/window → pick one.
2. A thumbnail strip appears; click a shot → **ScreenshotViewer** opens.
3. Click **Annotate** → draw a rectangle/arrow/text → **Save**.
4. Back in the strip the annotation is on the shot; Delete removes it.
5. Bonus: point it at something on your screen and ask about it in chat.

### E. It anticipates you (Cognition page)
1. First visit: "Anticipated Needs" shows the honest empty note.
2. In chat, do the SAME kind of task 3+ times (e.g., "find my resume file",
   "search for the invoice", "look for tax documents" — all file searches).
3. Revisit the Cognition page → a prediction like `search_files` with a
   confidence % and a reason appears. It learned your rhythm from real cycles.

### F. The silent watcher (Cognition page)
1. "Environment Awareness" says **(running)**.
2. Open and close some apps on your PC → refresh → new
   `appeared`/`changed` observations with timestamps.
3. The `prioritized` list (via the JSON URL in step A) shows the watcher's
   decisions — priority, reason, whether it would trigger. It never acts.

### G. Asks, never refusals (in chat, natural language)
1. "delete the file called test.txt on my desktop" → approval card appears
   (Level-3 gate). Reply **"just go ahead"** → it executes.
   Then "delete test2.txt" → reply **"no, don't"** → cancelled.
2. "copy report.txt over the existing backup.txt" → typed ask
   (destination exists) → approve → it retries with overwrite.
3. "format the C drive" → surfaced with
   `[Owner approval required — dangerous pattern detected]` — never silently
   refused, never silently run.
4. "kill process with PID 1" → typed ask `protected_process` with the PID.

### H. Desktop life + Android
- Tray (separate terminal):
  ```bash
  # Windows:
  .venv\Scripts\python -m app.desktop_tray
  ```
  Dashboard opens automatically; closing the browser leaves the server
  running in the tray until you exit it there.
- Android: set a key and open LAN:
  ```bash
  # Windows:
  set ARENA_API_KEY=choose-a-long-key
  set ARENA_ALLOW_INSECURE_LAN=0
  .venv\Scripts\uvicorn app.server:app --host 0.0.0.0 --port 8000
  ```
  Phone app → PC's LAN IP :8000 with that key (X-API-Key). Voice + vision
  surfaces are the Compose equivalents of B–D.

---

## 4. Report back (this also starts items 1–3 evidence)

For each letter A–H: `PASS`, `PARTIAL (what differed)`, or `FAIL (exact
message)`. Screenshots/photo of the voice overlay and eyes flow are worth a
thousand words.

The Cognition page's **Phase 1 evidence panel** and the conversation history
on your machine are the real-task evidence collectors — using it normally
IS the evidence run. Current recorded total: **0 events**. After this
session it should not be 0.
