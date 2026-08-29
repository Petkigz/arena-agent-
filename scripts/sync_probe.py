"""Two-client live sync probe against the running server.

Simulates: client A = web browser, client B = a second device (desktop).
Verifies the full sync chain end-to-end:
  1. A sends a message; reply streams back; room_message echo for the room.
  2. The streamed reply carries a DIFFERENT message_id than the user message
     (so second clients don't glue the reply onto the user's bubble).
  3. B lists conversations -> sees A's conversation with lastMessage.
  4. B fetches history IMMEDIATELY (no settle delay) -> user message AND the
     assistant reply (regression: reply must be persisted before the done
     token, so syncing devices never see a stale history).
  5. B joins the room; A sends again -> B receives it LIVE (room_message)
     and sees the reply stream (message_token).
  6. Everything is persisted in SQLite (survives restarts).
"""
import asyncio
import json
import sys

import websockets

URL = "ws://127.0.0.1:8000/ws"
CONV = "conv-sync-probe-001"


async def recv_until(ws, want_type, timeout=60):
    """Collect events until one of `want_type` arrives; return (all, match)."""
    events = []
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            ev = json.loads(raw)
            events.append(ev)
            if ev.get("type") in want_type:
                return events, ev
    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        return events, None


async def collect_reply(ws):
    """Accumulate every event until the done token; return (events, reply, ids)."""
    all_events = []
    reply = ""
    token_ids = set()
    while True:
        events, done = await recv_until(ws, {"message_token"}, timeout=60)
        all_events.extend(events)
        if done is None:
            return all_events, reply, token_ids, False
        reply += done.get("token", "")
        token_ids.add(done.get("message_id"))
        if done.get("done"):
            return all_events, reply, token_ids, True


async def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))

    async with websockets.connect(URL) as a:
        # ── 1. Client A (web) sends a message ─────────────────────────────
        await a.send(json.dumps({
            "type": "user_message", "conversation_id": CONV,
            "content": "hello from client A",
        }))
        events, reply, token_ids, complete = await collect_reply(a)
        check("A receives streamed reply", len(reply) > 0, f"reply={reply[:80]!r}")
        room_msgs = [e for e in events if e.get("type") == "room_message"]
        check("A gets room_message echo (cross-client broadcast)", bool(room_msgs),
              f"types={[e.get('type') for e in events][:10]}")

        # ── 2. Reply ids must differ from the user message id ─────────────
        user_ids = {e.get("message_id") for e in room_msgs}
        check("assistant reply has its own message_id (no bubble collision)",
              bool(token_ids) and not (token_ids & user_ids),
              f"user={user_ids} reply={token_ids}")

        # ── 3/4. B lists + fetches history IMMEDIATELY (race regression) ──
        async with websockets.connect(URL) as b:
            await b.send(json.dumps({"type": "list_conversations"}))
            _, listing = await recv_until(b, {"conversation_list"}, timeout=15)
            convs = (listing or {}).get("conversations", [])
            found = [c for c in convs if c.get("id") == CONV]
            check("B sees A's conversation in the list", bool(found),
                  f"conversations={[c.get('id') for c in convs]}")
            if found:
                check("preview carries lastMessage", bool(found[0].get("lastMessage")),
                      f"lastMessage={found[0].get('lastMessage')!r}")

            await b.send(json.dumps({"type": "get_history", "conversation_id": CONV}))
            _, hist = await recv_until(b, {"conversation_history"}, timeout=15)
            msgs = (hist or {}).get("messages", [])
            roles = [m.get("role") for m in msgs]
            check("B's history has user message", "user" in roles, f"roles={roles}")
            check("B's history has assistant reply (no done-token race)",
                  "assistant" in roles, f"roles={roles}")
            check("history entries carry message_id (dedupe key)",
                  all("message_id" in m for m in msgs) and len(msgs) > 0,
                  f"msgs={msgs}")

            # ── 5. Live sync: B joins the room, A talks again ─────────────
            await b.send(json.dumps({"type": "join_conversation", "conversation_id": CONV}))
            await asyncio.sleep(0.3)
            await a.send(json.dumps({
                "type": "user_message", "conversation_id": CONV,
                "content": "second message from A — B should see this live",
            }))
            b_events, b_reply, _, b_complete = await collect_reply(b)
            check("B receives A's message LIVE (room_message)",
                  any(e.get("type") == "room_message" for e in b_events),
                  f"types={[e.get('type') for e in b_events][:10]}")
            check("B sees full reply stream LIVE (message_token + done)",
                  b_complete and len(b_reply) > 0)

    # ── 6. Persistence ────────────────────────────────────────────────────
    import sqlite3
    conn = sqlite3.connect("data/assistant.db")
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE conversation_id=? ORDER BY id",
        (CONV,),
    ).fetchall()
    conn.close()
    check("persisted to SQLite", len(rows) >= 4, f"rows={len(rows)}")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
