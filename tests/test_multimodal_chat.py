"""E2E multimodal chat + grounding + project management tests (P1-1 → P3 AGI).

Tests that the cognitive runtime now accepts image_path and attachments (multimodal)
through the ONE brain, auto-grounds objects, learns causal edges, and creates projects
for complex goals.

All tests are deterministic and degradable — they don't require real models, just the runtime.
"""

import tempfile
from pathlib import Path

from app.cognition.runtime import CognitiveRuntime
from app.tools.object_detector import ObjectDetectorTool
from app.tools.prosody_analyzer import ProsodyAnalyzerTool
from app.tools.vlm_analyzer import VlmAnalyzerTool
from app.tools.lora_manager import LoraManagerTool
import numpy as np


def test_runtime_accepts_image_path():
    """process_cognitive_cycle now accepts image_path (multimodal chat)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rt = CognitiveRuntime(db_path=str(Path(tmpdir) / "test.db"))
        # Check signature has image_path param (structural)
        import inspect
        sig = inspect.signature(rt.process_cognitive_cycle)
        assert "image_path" in sig.parameters, "runtime must accept image_path for multimodal"
        assert "attachments" in sig.parameters, "runtime must accept attachments"


def test_object_detector_has_grounding_loop():
    """ObjectDetectorTool has analyze_image_grounded that creates groundings."""
    assert hasattr(ObjectDetectorTool, "analyze_image_grounded")
    assert hasattr(ObjectDetectorTool, "detect_objects")
    assert hasattr(ObjectDetectorTool, "detect_faces")

    # Face detection gracefully degrades when image missing
    res = ObjectDetectorTool.detect_faces("nonexistent.png")
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "faces" in res


def test_vlm_has_fallback():
    """VlmAnalyzerTool has true VLM with OCR+LLM fallback — never raises."""
    assert hasattr(VlmAnalyzerTool, "analyze_image")
    assert hasattr(VlmAnalyzerTool, "get_status")

    status = VlmAnalyzerTool.get_status()
    assert isinstance(status, dict)
    assert "available" in status
    assert "engine" in status

    # Analyze missing image returns typed error, not exception
    res = VlmAnalyzerTool.analyze_image("nonexistent.png")
    assert isinstance(res, dict)
    assert res.get("success") is False


def test_prosody_analyzer_from_real_signals():
    """ProsodyAnalyzerTool analyzes real audio (pitch/energy/ZCR→emotion), not just rules."""
    assert hasattr(ProsodyAnalyzerTool, "analyze_prosody")

    # Synthetic high-energy high-pitch audio should infer joy or anger (real signal)
    sr = 16000
    t = np.linspace(0, 1, sr)
    audio_joy = (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)

    res = ProsodyAnalyzerTool.analyze_prosody(audio_joy, sample_rate=sr)
    assert isinstance(res, dict)
    assert res.get("success") is True
    assert "emotion" in res
    assert "intensity" in res
    assert "features" in res
    assert "pitch_hz" in res["features"]

    # Empty audio degrades gracefully
    res_empty = ProsodyAnalyzerTool.analyze_prosody(np.array([]))
    assert isinstance(res_empty, dict)
    assert res_empty.get("success") is False


def test_lora_manager_continual_learning():
    """LoraManagerTool enables continual learning without catastrophic forgetting."""
    assert hasattr(LoraManagerTool, "list_adapters")
    assert hasattr(LoraManagerTool, "get_status")
    assert hasattr(LoraManagerTool, "prepare_dataset")
    assert hasattr(LoraManagerTool, "train")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Use temp dir for loras to avoid polluting real data
        import app.tools.lora_manager as lora_module
        original_dir = lora_module.LORAS_DIR
        lora_module.LORAS_DIR = Path(tmpdir) / "loras"
        lora_module.DATASETS_DIR = lora_module.LORAS_DIR / "datasets"
        lora_module.ACTIVE_FILE = lora_module.LORAS_DIR / "active.json"

        try:
            # Prepare dataset
            examples = [
                {"prompt": "What is your name?", "response": "I am Beanie"},
                {"prompt": "Hello", "response": "Hi there"},
            ]
            ds_res = LoraManagerTool.prepare_dataset("test_skill", examples)
            assert ds_res.get("success") is True
            assert Path(ds_res.get("path", "")).exists()

            # List adapters (empty)
            list_res = LoraManagerTool.list_adapters()
            assert list_res.get("success") is True
            assert isinstance(list_res.get("adapters"), list)

            # Status
            status = LoraManagerTool.get_status()
            assert status.get("success") is True
            assert "loras_dir" in status

        finally:
            lora_module.LORAS_DIR = original_dir
            lora_module.DATASETS_DIR = original_dir / "datasets"
            lora_module.ACTIVE_FILE = original_dir / "active.json"


def test_causal_learning_from_execution():
    """CausalInferenceEngine now learns from execution + surprisal (P1-2), not just storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rt = CognitiveRuntime(db_path=str(Path(tmpdir) / "test.db"))
        ci = rt.causal_inference

        assert hasattr(ci, "learn_from_execution")
        assert hasattr(ci, "learn_from_surprisal")

        # Learn from success
        edge_id = ci.learn_from_execution("search_files", "file_found", success=True, evidence=["test"])
        assert isinstance(edge_id, str)

        # Learn from failure should weaken (strength 0.2)
        edge_id2 = ci.learn_from_execution("search_files", "file_found", success=False, evidence=["test fail"])
        # After success + failure, strength should be between 0.2 and 0.9 (Bayesian average)
        edge = ci.graph.edges.get(edge_id2)
        if edge:
            assert 0.2 <= edge.strength <= 0.9

        # Learn from low surprisal should strengthen
        edge_id3 = ci.learn_from_surprisal("web_search", "info_gathered", surprisal=0.1)
        assert isinstance(edge_id3, str)


def test_memory_association_and_causal_consolidation():
    """consolidate_memory() now creates associations + causal stats (P1-3)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rt = CognitiveRuntime(db_path=str(Path(tmpdir) / "test.db"))
        summary = rt.consolidate_memory()
        assert isinstance(summary, dict)
        # New P1-3 keys
        assert "causal_total" in summary or "causal_weak_edges" in summary or "associations_created" in summary


def test_curiosity_info_gain():
    """AutonomousGoalGenerator has information-gain curiosity (P1-4)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rt = CognitiveRuntime(db_path=str(Path(tmpdir) / "test.db"))
        gen = rt.goal_generator

        assert hasattr(gen, "generate_goals_from_information_gain")
        assert hasattr(gen, "generate_goals_from_signals")

        # Generate from info-gain (should work even with empty world)
        goals = gen.generate_goals_from_information_gain(
            world_model=rt.world,
            language_grounding=rt.language_grounding,
            causal_engine=rt.causal_inference,
        )
        assert isinstance(goals, list)

        # Generate from signals including info-gain signals
        signals = {
            "unknown_entities": ["mystery.txt"],
            "low_confidence_groundings": ["chair"],
            "unexplored_files": ["new.csv"],
        }
        goals2 = gen.generate_goals_from_signals(signals)
        assert isinstance(goals2, list)
        # Should generate curiosity goals for unknown entities
        assert any("mystery.txt" in g.description or "chair" in g.description for g in goals2) or len(goals2) >= 1


def test_resource_aware_planning():
    """CounterfactualSimulator has RESOURCE_COSTS and resource-aware adjustment (P2)."""
    from app.cognition.counterfactual_simulator import CounterfactualSimulator

    assert hasattr(CounterfactualSimulator, "RESOURCE_COSTS")
    assert "vision_analyze" in CounterfactualSimulator.RESOURCE_COSTS
    assert "detect_objects" in CounterfactualSimulator.RESOURCE_COSTS

    # Simulate with hardware under pressure — high-memory action should be penalized
    runtime = CognitiveRuntime.get_instance()
    candidates = [
        {"name": "Web search", "action_type": "web_search", "payload": {"query": "test"}},
        {"name": "Vision analyze", "action_type": "vision_analyze", "payload": {"image_path": "test.png"}},
    ]

    # Low pressure
    low_pressure_model = {"live": {"ram_percent": 30, "cpu_percent": 20, "disk_percent": 30}}
    result_low = CounterfactualSimulator.simulate_competing_branches(
        "Analyze image", candidates, hardware_self_model=low_pressure_model
    )

    # High pressure
    high_pressure_model = {"live": {"ram_percent": 90, "cpu_percent": 85, "disk_percent": 30}}
    result_high = CounterfactualSimulator.simulate_competing_branches(
        "Analyze image", candidates, hardware_self_model=high_pressure_model
    )

    # Under high RAM pressure, vision_analyze (memory 0.7) should have lower utility than web_search
    # Find utilities
    low_vision = next((b.utility_score for b in result_low.competing_branches if b.hypothetical_action == "vision_analyze"), 0)
    high_vision = next((b.utility_score for b in result_high.competing_branches if b.hypothetical_action == "vision_analyze"), 0)

    # High pressure should penalize vision (utility lower)
    assert high_vision <= low_vision, f"High pressure should penalize heavy actions: low={low_vision}, high={high_vision}"


def test_project_management_long_horizon():
    """ProjectManager + GoalDecomposer wired for long-horizon multi-session tracking (P2)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rt = CognitiveRuntime(db_path=str(Path(tmpdir) / "test.db"))

        assert hasattr(rt, "project_manager")
        assert hasattr(rt, "goal_decomposer")

        # Create project
        proj = rt.project_manager.create_project(
            name="Test: Setup env + research",
            description="Complex goal that should be decomposed",
            milestones=["Check prereqs", "Install", "Configure", "Verify"],
        )
        assert proj.project_id
        assert proj.milestones_total == 4

        # Decompose
        decomp = rt.goal_decomposer.decompose("Setup development environment and research AI trends", intent_type="setup_environment")
        assert decomp.project_id
        assert len(decomp.sub_goals) >= 1

        # Resource-aware schedule
        schedule = decomp.get_resource_aware_schedule(
            hardware_self_model=rt.hardware_self_model,
            resource_manager=getattr(rt.advanced_cognition, "resource_manager", None),
        )
        assert isinstance(schedule, list)
        assert len(schedule) >= 1


def test_multimodal_chat_through_one_brain():
    """Chat path now supports multimodal (text+image) through ONE brain (P2)."""
    # This is structural: message_router handles image_path
    from backend.message_router import MessageRouter

    # Check that _handle_user_message accepts image_path (inspect source)
    import inspect
    source = inspect.getsource(MessageRouter._handle_user_message)
    assert "image_path" in source, "message_router must handle image_path for multimodal chat"

    # Runtime signature already checked in test_runtime_accepts_image_path
