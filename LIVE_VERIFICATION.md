# Live Verification Runbook

Some tools talk to the real world (public APIs, web search, messaging). The
development sandbox has **no internet and no credentials**, so those tools are
unit-tested there for **parsing, validation, and graceful degradation** — but not
for live end-to-end success. This runbook closes that gap on your machine.

## What is verified live vs. sandbox

| Tool | Sandbox status | Live check |
|---|---|---|
| `crypto_price` (CoinGecko) | parser + validation tested | ✅ `scripts/live_check.py` |
| `stock_price` (Stooq) | parser + validation tested | ✅ `scripts/live_check.py` |
| `fetch_feed` (RSS/Atom) | parser tested against fixtures | ✅ `scripts/live_check.py` |
| `resolve_dns` / `check_port` | localhost tested | ✅ `scripts/live_check.py` |
| `fact_check` / `research_digest` (web search) | mocked search + LLM tested | ✅ `scripts/live_check.py` |
| `send_telegram` (Bot API) | validation + mocked send tested | ✅ (needs token) |
| `send_whatsapp` (Twilio) | validation + mocked send tested | ✅ (needs credentials) |
| Everything else | fully tested end-to-end | n/a |

## Run it

```bash
cd /path/to/arena-agent-
. .venv/bin/activate
python scripts/live_check.py
```

Each probe prints `PASS` / `FAIL` / `SKIP`:

- **PASS** — the tool returned real data.
- **FAIL** — the tool errored; investigate.
- **SKIP** — credentials not configured (Telegram/WhatsApp); not a failure.

Exit code is `0` if nothing failed, `1` otherwise — safe to wire into a pre-commit
or manual check.

## Configure messaging (optional)

Telegram and WhatsApp report `SKIP` until you set credentials. Add to your `.env`
(or export in the shell):

```bash
# Telegram (create a bot with @BotFather → token; your chat id via @userinfobot)
ARENA_TELEGRAM_BOT_TOKEN=...
ARENA_TELEGRAM_CHAT_ID=...

# WhatsApp via Twilio (Account SID + Auth Token from console.twilio.com)
ARENA_TWILIO_ACCOUNT_SID=...
ARENA_TWILIO_AUTH_TOKEN=...
ARENA_TWILIO_FROM=whatsapp:+14155238886
```

The live check probes these with **non-intrusive** calls (`getMe` for Telegram,
account fetch for Twilio) — it will not send any real message.

## Honest expectation

A `FAIL` on the live check is a *finding*, not a code defect necessarily — e.g. a
rate-limited CoinGecko, a blocked port, or a search engine that changed its HTML.
The point is to surface which external integrations actually work on your network,
so we fix real breakages instead of assuming they work.
