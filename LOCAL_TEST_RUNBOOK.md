# Local Machine Test Runbook

Run this on the owner machine (i9-14900K / RX 580 / 48 GB / LM Studio) to
verify fixes **#6, #7, #8, #9**, the proxy-checker fix for real, and —
since `1b99119` — the whole owner-review window (P0 #1–#6, P1 #7–#9,
P2 items 9–10, Execution Truth Layer). The sandbox proves logic; this
machine proves the parts CI (Ubuntu-only) and the sandbox cannot: real
hardware sensors, real autostart inventory, real system logs, real
package installs, and the LM Studio embedding backend.

Everything below lives on branch `arena/01a0579e-arena-agent`
(latest: `1b99119`). Merge to `main` only after this runbook passes.

**The primary gate for the owner-review window is the diagnostics pack
(step 3): it exercises the D1–D9 battery with programmatic ground truth
(arithmetic values, created rows, installed tools, found files) and the
hardware probes (screen, VLM, LoRA/GPU, ADB, audio, browser).** The unit
suite (step 2) and `verify_fixes_live.py` (step 4) cover the rest.

Order matters: the unit suite wants **LM Studio shut down** (~13 tests
assert offline behavior); the diagnostics pack wants **LM Studio
running** with your models loaded.

---

## 1. Get the code and set up the environment

```bash
git fetch origin
git checkout arena/01a0579e-arena-agent
git pull

# fresh venv (Python 3.11, same as CI)
python -m venv .venv

# Windows:
.venv\Scripts\pip install -r requirements-core.txt -r requirements-test.txt
# Linux/macOS:
.venv/bin/pip install -r requirements-core.txt -r requirements-test.txt
```

## 2. Unit suite (the regression gate)

**Before running: shut down LM Studio** (or unload its models). Roughly 13
tests assert offline behavior — "no LLM configured → success=False",
"embedding backend is 'local'", "domain is classified as X" — and a running
LM Studio with a loaded embedding model legitimately flips those outcomes.
Those are live-environment disagreements, not regressions; run them with
LM Studio closed and they go green.

Also on Windows: run commands **one per line** — PowerShell 5 does not
accept `&&`, and `install` is not a command (that's pip). And use the
**venv** interpreter (`.venv\Scripts\python`), not system Python — a bare
`python` hits PEP 668's externally-managed environment on some setups and
mixes dependency sets.

```bash
.venv\Scripts\python -m pytest tests/ -q          # Windows
.venv/bin/python -m pytest tests/ -q              # Linux/macOS
```

**Expected:** `2817 passed, 4 skipped` (± a few skips depending on your
optional dependencies — skips are honest, failures are not).

**Windows note:** a handful of pre-existing tests still fail on Windows for
platform reasons (they assume Linux: `journalctl`, process groups,
`xdg-open`, the ~15.6ms clock resolution, SQLite-handle cleanup in tests
that use `TemporaryDirectory` around other modules' connections). None are
regressions from this branch; the branch's own tests are Windows-clean.

## 3. Owner diagnostics pack — the primary gate for the review window

**Before running: start LM Studio and load your models** (MAIN_MODEL and
FAST_MODEL as configured — the pack's Environment section probes
reachability, loaded models, and latency; the chat battery needs a real
brain).

```bash
.venv\Scripts\python scripts\owner_diagnostics.py     # Windows
.venv/bin/python scripts/owner_diagnostics.py         # Linux/macOS
```

Every check is independent (one failure never stops the pack) and
verified against programmatic ground truth — never the agent's own
claim of success. It ends with a compact paste-back block (also saved
under `data/owner_diagnostics_<timestamp>.json`): **paste that block
back into the agent session** so failures map to exact fixes.

What it proves, per section:

| Section | Covers | Proves |
|---|---|---|
| 0 Environment | P1 #9 | LM Studio reachable, MAIN/FAST models actually loaded (item 1's routing ladder), latency sane |
| A Brain online (D1–D9) | items 1–8 | arithmetic/data-statistic deterministic answers, task/project creation closes goals, self-evolution installs for real, file search finds the file, code execution runs pure + gates arbitrary, compound conditions |
| B Hardware probes | items 9–10 + F4 | screen capture, VLM status (honest until installed), LoRA/GPU, ADB phone (honest until installed), audio devices, browser extraction |

Note: chat tasks create real goals/projects in `data/assistant.db`, and a
successful D6 self-evolution check installs a real `reverse_words` tool —
that is what a real session does; nothing destructive runs.

## 4. Live verification of the older fixes (no mocks)

```bash
.venv\Scripts\python scripts/verify_fixes_live.py     # Windows
.venv/bin/python scripts/verify_fixes_live.py         # Linux/macOS
```

**Expected:** `22 passed, 0 failed, 1 skipped`, exit code `0`. (On a machine
with missing optional dependencies, A6 turns its SKIP into a PASS — any
`0 failed` result is green.)

What each section proves:

| Section | Fix | Proves |
|---|---|---|
| E1–E3 REST | — | availability endpoint, owner refresh endpoint, full listing (the old 500) |
| A1–A6 cache | #6 | revision-tagged cache, invalidation on change/registration/execution-contradiction, **real pip install** notifies the registry |
| B1–B3 breadth | #7 | adaptive tiers, full-pool ranking (no 8-ceiling), rank evidence |
| C1–C8 bridge | #8 | slow-computer scenario → discover → plan → **execute on real hardware**, no pollution |
| D1–D3 authority | #9 | override raises the gate; safety/availability/execution one view |

### Platform differences you SHOULD see

| Check | Linux | Windows |
|---|---|---|
| C4 temperature | real sensor readings (throttling flag) | honest `available: false` (psutil has no Windows sensors) |
| C6 startup | systemd units + XDG autostart | **registry Run keys + Startup folders** — CI never covers this path |
| C7 logs | journalctl / syslog | **Event Log via wevtutil** — CI never covers this path |
| A6 missing dep | passes if any optional dep is absent | same |

If C6/C7 FAIL on Windows, that is a **real finding** — those code paths
have never executed anywhere. Report the detail line and it gets fixed
before anything else.

## 4. Only-your-machine checks (not possible in CI/sandbox)

### 4a. LM Studio embedding backend (the other half of fix #8)

The concept bridge works without any model; the EMBEDDING backend is the
general semantic layer. Load an embedding model in LM Studio (any
`*-embed-*` model), then:

```python
.venv\Scripts\python -c "from app.cognition.tool_matcher import rank_tools; \
hits = rank_tools('find why my computer suddenly became slow', limit=10); \
print([(h.action_type, h.semantic_backend, h.semantic_score) for h in hits])"
```

**Expected:** `semantic_backend` is `embeddings` (not `local`), and the
diagnostic tools still rank (bridge + embeddings stack, not compete).
If LM Studio is off, the log line says `no embedding model loaded ...
using local fuzzy matching` — that is honest degradation, not a failure.

### 4b. The full out-of-band invalidation flow (fix #6 end to end)

```bash
# 1. server up
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. probe a tool that needs an optional dependency you DON'T have
curl "http://127.0.0.1:8000/tools/availability?tool=ocr_read&probe=true"

# 3. install that dependency from a normal terminal (outside Arena),
#    into the SAME environment the server runs from
pip install pytesseract

# 4. declare the change (the owner declaration Arena cannot observe itself)
curl -X POST http://127.0.0.1:8000/tools/availability/refresh \
     -H "Content-Type: application/json" -d "{\"reason\": \"installed pytesseract manually\"}"

# 5. probe again — must now report available, no restart, no TTL wait
curl "http://127.0.0.1:8000/tools/availability?tool=ocr_read&probe=true"
```

**Expected:** step 2 `available: false` → step 5 `available: true`. This
is the exact scenario the finding described.

### 4c. Real hardware diagnostics (fix #8)

```bash
curl "http://127.0.0.1:8000/tools/availability?tool=system_metrics&probe=true"
```

24 logical cores, 48 GB, real per-core load, real disk IO counters — the
sandbox saw 2 cores / 4 GB. On Linux also check `temperature_status` for
real thermal readings.

## 5. If anything fails

- Note the check id (e.g. `C6`) and the detail line.
- Unit failure → full pytest output for the failing test.
- Live failure → the script's detail line plus OS + Python version.
- A FAIL is a finding, not noise — the whole point of this runbook is that
  fixes are proven on the machine that runs them.
