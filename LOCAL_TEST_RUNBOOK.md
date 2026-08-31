# Local Machine Test Runbook

Run this on the owner machine (i9-14900K / RX 580 / 48 GB / LM Studio) to
verify fixes **#6, #7, #8, #9** and the proxy-checker fix for real. The
sandbox proves logic; this machine proves the parts CI (Ubuntu-only) and
the sandbox cannot: real hardware sensors, real autostart inventory, real
system logs, real package installs, and the LM Studio embedding backend.

Everything below lives on branch `arena/01a0579e-arena-agent`
(latest: `6f79ccf`). Merge to `main` only after this runbook passes.

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

```bash
.venv\Scripts\python -m pytest tests/ -q          # Windows
.venv/bin/python -m pytest tests/ -q              # Linux/macOS
```

**Expected:** `2478 passed, 4 skipped` (± a few skips depending on your
optional dependencies — skips are honest, failures are not).

## 3. Live verification of the fixes (no mocks)

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
