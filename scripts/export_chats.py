#!/usr/bin/env python
"""Export Arena chats + cognitive traces into one shareable file.

Run this on YOUR machine, then attach the output file in the Arena chat so
the agent can read exactly what was said and how each message was reasoned
about — no more copy-pasting server logs.

Usage (PowerShell, from the repo root):
    python scripts\\export_chats.py
    python scripts\\export_chats.py --messages 500 --traces 100 --full
    python scripts\\export_chats.py --no-redact

Output: data/chats_export.md (change with --out). By default the export
redacts your Windows user profile path (C:\\Users\\<you> -> ~) so paths stay
private; --no-redact turns that off.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.join("data", "assistant.db")
DEFAULT_OUT = os.path.join("data", "chats_export.md")


def _row_factory(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def _connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"error: database not found: {db_path} (run from the repo root)")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = _row_factory
    return conn


def _redact(text: str, home: str) -> str:
    if not text:
        return text
    out = text.replace(home, "~")
    # Also catch the bare username in C:/Users/<name> style paths.
    out = re.sub(r"(?i)([A-Z]:[/\\]+Users[/\\]+)[^/\\\s]+", r"\1<user>", out)
    return out


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if limit and len(text) > limit:
        return text[:limit] + f" …[+{len(text) - limit} chars]"
    return text


def export(db_path: str, out_path: str, messages: int, traces: int,
           audits: int, full: bool, redact: bool,
           home: str | None = None) -> str:
    conn = _connect(db_path)
    home = home or os.path.expanduser("~")
    msg_limit = 0 if full else 1500
    reply_limit = 0 if full else 600

    lines: list[str] = []
    lines.append(f"# Arena chat export — {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    shown_db = _redact(db_path, home) if redact else db_path
    lines.append(f"- database: `{shown_db}`")
    lines.append(f"- redacted home path: {'yes' if redact else 'NO'}")
    lines.append("")

    # ── Conversations (the chat every UI syncs from) ─────────────────────
    try:
        convs = conn.execute(
            "SELECT conversation_id, COUNT(*) AS n, MAX(created_at) AS last_at "
            "FROM conversations GROUP BY conversation_id "
            "ORDER BY MAX(id) DESC LIMIT 50"
        ).fetchall()
        lines.append(f"## Conversations ({len(convs)} most recent)\n")
        for c in convs:
            lines.append(f"### {c['conversation_id']} — {c['n']} messages (last {c['last_at']})")
            rows = conn.execute(
                "SELECT role, content, created_at FROM conversations "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (c["conversation_id"], max(4, min(messages, 60))),
            ).fetchall()
            for r in reversed(rows):
                content = _clip(r["content"], msg_limit)
                if redact:
                    content = _redact(content, home)
                lines.append(f"- **{r['role']}** ({r['created_at']}): {content}")
            lines.append("")
    except sqlite3.Error as e:
        lines.append(f"(conversations unavailable: {e})\n")

    # ── Cognitive traces (how each message was reasoned about) ───────────
    try:
        tl = conn.execute(
            "SELECT trace_id, user_input, assistant_reply, model_used, latency_ms, "
            "goal_verified, goal_lifecycle_state, gate_decision, created_at "
            "FROM cognitive_traces ORDER BY rowid DESC LIMIT ?",
            (traces,),
        ).fetchall()
        lines.append(f"## Cognitive traces ({len(tl)} most recent, newest first)\n")
        for t in tl:
            user = _clip(t["user_input"], msg_limit)
            reply = _clip(t["assistant_reply"], reply_limit)
            if redact:
                user, reply = _redact(user, home), _redact(reply, home)
            verified = "?" if t["goal_verified"] is None else ("yes" if t["goal_verified"] else "no")
            lines.append(
                f"- `{t['trace_id']}` ({t['created_at']}) model={t['model_used']} "
                f"latency={t['latency_ms']:.0f}ms goal_verified={verified} "
                f"state={t['goal_lifecycle_state'] or '-'} gate={t['gate_decision'] or '-'}"
            )
            lines.append(f"  - in: {user}")
            lines.append(f"  - out: {reply}")
        lines.append("")
    except sqlite3.Error as e:
        lines.append(f"(traces unavailable: {e})\n")

    # ── Recent audit events (tool executions, learning) ──────────────────
    try:
        audits_rows = conn.execute(
            "SELECT timestamp, action, status, details FROM audit_logs "
            "ORDER BY id DESC LIMIT ?", (audits,),
        ).fetchall()
        lines.append(f"## Recent audit events ({len(audits_rows)}, newest first)\n")
        for a in audits_rows:
            details = _clip(a["details"], 300)
            if redact:
                details = _redact(details, home)
            lines.append(f"- {a['timestamp']} {a['action']} [{a['status']}]: {details}")
        lines.append("")
    except sqlite3.Error as e:
        lines.append(f"(audit log unavailable: {e})\n")

    content = "\n".join(lines)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Arena chats for sharing")
    parser.add_argument("--db", default=DEFAULT_DB, help="path to assistant.db")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output markdown file")
    parser.add_argument("--messages", type=int, default=200,
                        help="max messages kept per conversation (capped at 60)")
    parser.add_argument("--traces", type=int, default=50, help="recent cognitive traces")
    parser.add_argument("--audits", type=int, default=60, help="recent audit events")
    parser.add_argument("--full", action="store_true", help="no truncation of long messages")
    parser.add_argument("--no-redact", action="store_true",
                        help="keep real paths (default redacts your user folder)")
    args = parser.parse_args()

    out = export(args.db, args.out, args.messages, args.traces, args.audits,
                 args.full, redact=not args.no_redact)
    size = os.path.getsize(out)
    print(f"wrote {out} ({size:,} bytes) — attach that file in the Arena chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
