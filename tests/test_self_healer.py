import pytest
import asyncio
from app.scheduler.self_healer import AutonomousSelfHealer

@pytest.mark.anyio
async def test_autonomous_self_healer():
    res = await AutonomousSelfHealer.run_maintenance_cycle()
    assert res["success"] is True
    assert "failed_tools_count" in res or "patched_tool" in res
