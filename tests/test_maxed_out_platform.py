import pytest
import os
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.prompt_slicer import PromptSlicerEngine
from app.tools.win32_ghost_operator import Win32GhostOperator
from app.tools.app_inventory import SystemAppInventory
from app.utils.hardware_governor import HardwareGovernor
from app.scheduler.self_healer import AutonomousSelfHealer
from app.perception.speech_to_text import LocalSpeechToText

def test_maxed_out_hardware_and_cognition():
    # 1. Hardware Governor P-Core Thread Shunting
    gov = HardwareGovernor.set_thread_affinity(p_cores_only=True)
    assert gov["success"] is True

    # 2. VRAM Cache Purge
    mem = HardwareGovernor.purge_vram_and_system_memory()
    assert mem["success"] is True

    # 3. Environment App Discovery
    apps = SystemAppInventory.scan_installed_applications()
    assert apps["success"] is True

    # 4. Win32 Ghost Background Operator
    wins = Win32GhostOperator.list_open_windows()
    assert isinstance(wins, list)  # Empty is correct off Windows; no fake HWNDs.

    # 5. Counterfactual Mental Simulation
    sim = CounterfactualSimulator.simulate_competing_branches(
        target_goal="Maxed Out Task Execution",
        candidate_actions=[
            {"name": "Safe Local Execution", "action_type": "read_file", "payload": {"file_path": "README.md"}},
            {"name": "Destructive Action", "action_type": "delete_file", "payload": {"file_path": "system.dll"}}
        ]
    )
    assert sim.winning_branch.branch_name == "Safe Local Execution"

    # 6. Master Agent Unified Processing
    task_res = MasterAgentOrchestrator.process_user_task("Check my system apps and status")
    assert task_res["success"] is True
    assert len(task_res["assistant_reply"]) > 0
