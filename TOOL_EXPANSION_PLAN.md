# Tool Expansion Plan — "Everything" a Coworker Can Do

## The honest frame

"Can do everything" is a direction, not an endpoint — and **tool count is no
longer the bottleneck** (67 tools already exist). What actually limits coverage
now is the model's ability to *compose* tools into multi-step plans, plus the
cost of hand-writing every niche capability. So the strategy is: build **two
levers** that make any future capability cheap, then add only the high-value
tools that need real logic.

## The two levers (highest leverage, built first)

1. **Generic local command/API executor** — one Level-3-gated tool that safely
   runs an arbitrary local CLI command, script, or localhost HTTP call. This
   instantly covers thousands of niche tasks without new code.
2. **Plugin registry** — a plugin folder where dropping in a Python file
   (declaring `name`, `description`, `safety_level`, and an `execute(payload)`
   function) auto-registers it into the tool manifest. Turns "add a capability"
   into "drop a file."

## Tier 1 — high-value tools that need real logic (build by hand)

- **Contacts** (desktop vCard/DB read+write)
- **Messaging** (WhatsApp/Telegram, Level-3)
- **Scheduling assistant** (meeting times + invites)
- **Spreadsheet engine** (read/write `.xlsx`, formulas, pivot)
- **Presentation generator** (`.pptx` from outline)
- **PDF toolkit** (merge/split/fill-forms)
- **Process manager** (list/kill/restart, per-process CPU/RAM)
- **Backup & restore** (versioned snapshots)
- **Network diagnostics** (ping/traceroute/port/WHOIS)
- **Package installer** (pip/npm/apt/winget, Level-3)
- **Database connector** (read-only Postgres/MySQL)
- **News/RSS aggregator** (sources you choose → summarize)
- **Fact-check / citation** (claims → sources with links)
- **Invoice generator** (PDF from line items)
- **Budget tracker** (CSV transactions → categories/overspend)
- **Price/portfolio lookup** (crypto/stock, keyless where possible)

## Tier 2 — narrower (add via plugin system as needed)

- Audio transcription (local files), audio conversion (ffmpeg), image batch edit
- Habits/journaling, health/fitness, learning tracker, spaced repetition
- Form/booking automation, price/availability monitor
- Home automation/IoT, printing, local image gen (needs GPU), video edit,
  language tutoring

## Execution order

1. Build the two levers.
2. Build Tier 1 tools that need real logic (~7): contacts, spreadsheet, PDF
   toolkit, process manager, database connector, news/RSS, invoice generator.
3. Leave Tier 2/3 to the plugin system — add as actually needed.

## Done so far
- [x] Two levers (executor + plugin registry)
- [x] Contacts, spreadsheet engine
- [x] PDF toolkit (merge/split/extract/fill-form + metadata/text)
- [x] Process manager (list/inspect/kill/restart, self-protection)
- [x] Database connector (SQLite/Postgres/MySQL: read Level 0, write Level 3)
- [x] Invoice generator (PDF invoice/quote/receipt)
- [x] Network diagnostics (DNS, port check, ping, traceroute, WHOIS)
- [x] Budget tracker (CSV ledger, category totals, overspend)
- [x] Backup & restore (versioned zip snapshots, SHA-256 integrity)
- [x] Presentation generator (.pptx from outline)
- [x] Package installer (pip/npm: list/check Level 0, install/uninstall Level 3)
- [x] News/RSS aggregator (fetch/parse + optional summarize)
- [ ] Remaining Tier 1: messaging, fact-check, price lookup
