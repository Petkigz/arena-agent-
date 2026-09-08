"""Mind API — owner-visible window onto BeanieMind (AGI roadmap Phase 1).

The dashboard/clients can read WHO is answering (identity), WHAT the mind's
internal state looks like right now (BeanieState skeleton), and WHICH doors
input is arriving through (entry ledger). Read-only in Phase 1 — the owner
sees the mind; nobody silently edits it (identity edits, when they come,
are explicit owner actions).
"""

from fastapi import APIRouter, Query

from app.mind import BeanieMind

router = APIRouter()


@router.get("/mind/identity")
def mind_identity() -> dict:
    """The persisted 'I am Beanie' record plus development milestones."""
    return BeanieMind.get_instance().describe()


@router.get("/mind/state")
def mind_state() -> dict:
    """The BeanieState skeleton (M2): every room, honestly marked
    ok / wired / unavailable."""
    return {
        "success": True,
        "identity": BeanieMind.get_instance().identity.get("name", "Beanie"),
        "state": BeanieMind.get_instance().state(),
    }


@router.get("/mind/entries")
def mind_entries(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    """Recent inputs through the one door, newest first."""
    mind = BeanieMind.get_instance()
    return {
        "success": True,
        "entries": mind.entries(limit=limit),
        "stats": mind.entry_stats(),
    }
