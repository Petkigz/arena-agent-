#!/usr/bin/env python3
"""
Demo AGI capabilities — P1-1 → P3 push toward human intelligence.

This script exercises the new capabilities added in this session:
- Perception grounding (object detection + auto-grounding)
- Causal learning from execution + surprisal
- Memory association + causal consolidation
- Curiosity info-gain goals
- Resource-aware planning
- Prosody emotion from real signals
- Multimodal chat (text+image)
- Self-evolution verified
- Project management (long-horizon + multi-session)
- VLM optional (Moondream2) with fallback
- LoRA continual learning

Run (on your PC, not sandbox — some parts need models):
    PYTHONPATH=. python scripts/demo_agi.py

All probes are best-effort and degradable — if a model is missing, it logs and continues.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.cognition.runtime import CognitiveRuntime
from app.utils.logger import app_logger


def demo_scorecard():
    print("=== 1. Capability Scorecard (27 checks) ===")
    runtime = CognitiveRuntime.get_instance()
    report = runtime.measure_capabilities()
    print(f"Verified: {report['verified_count']}/{report['total_count']}")
    for cat, stats in report.get("categories", {}).items():
        print(f"  {cat}: {stats['verified']}/{stats['total']} verified")
    print()
    for check in report.get("checks", []):
        status = "✅" if check["status"] == "verified" else "❌"
        print(f"  {status} {check['capability']} [{check.get('category','')}] — {check.get('evidence','')}")
    print()


def demo_hardware():
    print("=== 2. Hardware Self-Awareness ===")
    runtime = CognitiveRuntime.get_instance()
    report = runtime.get_hardware_self_report()
    print(report.get("summary", ""))
    print(f"Full: {report.get('hardware_self_model', {})}")
    print()


def demo_perception_grounding():
    print("=== 3. Perception → Grounding Loop (P1-1) ===")
    try:
        from app.tools.object_detector import ObjectDetectorTool
        from app.tools.screen_capture import ScreenCaptureTool

        # Capture screen (or use dummy in headless)
        cap = ScreenCaptureTool.capture_screen()
        if cap.get("success"):
            img_path = cap.get("file_path")
            print(f"Captured: {img_path}")
            det_res = ObjectDetectorTool.analyze_image_grounded(img_path, auto_create_groundings=True)
            print(f"Detections: {det_res.get('count',0)} via {det_res.get('engine','')} — {det_res.get('detections',[])[:3]}")
            print(f"Groundings created: {det_res.get('groundings_count',0)} — {det_res.get('groundings_created',[])[:3]}")
        else:
            print(f"Capture failed: {cap.get('error')}")
    except Exception as e:
        print(f"Perception grounding demo failed (best-effort): {e}")
    print()


def demo_causal_learning():
    print("=== 4. Causal Learning from Execution + Surprisal (P1-2) ===")
    try:
        runtime = CognitiveRuntime.get_instance()
        ci = runtime.causal_inference

        # Add some causal edges and learn
        edge1 = ci.add_causal_relationship("search_files", "file_found", strength=0.9, confidence=0.8, evidence=["demo"])
        print(f"Added edge: {edge1}")

        # Learn from execution
        edge2 = ci.learn_from_execution("search_files", "file_found", success=True, evidence=["demo success"])
        print(f"Learned from success: {edge2}")

        edge3 = ci.learn_from_execution("search_files", "file_found", success=False, evidence=["demo failure"])
        print(f"Learned from failure: {edge3}")

        # Learn from surprisal
        edge4 = ci.learn_from_surprisal("web_search", "info_gathered", surprisal=0.2, evidence=["low surprisal"])
        print(f"Learned from low surprisal: {edge4}")

        edge5 = ci.learn_from_surprisal("web_search", "info_gathered", surprisal=0.8, evidence=["high surprisal"])
        print(f"Learned from high surprisal: {edge5}")

        summary = ci.get_causal_graph_summary()
        print(f"Graph summary: {summary}")

        # Root cause analysis
        causes = ci.root_cause_analysis("file_found", "present")
        print(f"Root causes for file_found: {causes[:2]}")

    except Exception as e:
        print(f"Causal learning demo failed: {e}")
    print()


def demo_memory_association():
    print("=== 5. Memory Consolidation + Association (P1-3) ===")
    try:
        runtime = CognitiveRuntime.get_instance()
        summary = runtime.consolidate_memory()
        print(f"Consolidation summary: {summary}")
    except Exception as e:
        print(f"Memory consolidation failed: {e}")
    print()


def demo_curiosity():
    print("=== 6. Curiosity via Information Gain (P1-4) ===")
    try:
        runtime = CognitiveRuntime.get_instance()
        # Generate curiosity goals from info-gain
        goals = runtime.goal_generator.generate_goals_from_information_gain(
            world_model=runtime.world,
            language_grounding=runtime.language_grounding,
            causal_engine=runtime.causal_inference,
        )
        print(f"Generated {len(goals)} curiosity goals (info-gain):")
        for g in goals[:3]:
            print(f"  - {g.title} (source: {g.source.value}, score: {g.overall_score:.2f})")

        # Also from structured signals
        signals = {
            "unknown_entities": ["mystery_file.txt", "unknown_process"],
            "low_confidence_groundings": ["chair"],
            "unexplored_files": ["new_dataset.csv"],
            "weak_causal_edges": ["search_files → file_found"],
        }
        signal_goals = runtime.goal_generator.generate_goals_from_signals(signals)
        print(f"Generated {len(signal_goals)} goals from signals: {[g.title for g in signal_goals[:3]]}")

    except Exception as e:
        print(f"Curiosity demo failed: {e}")
    print()


def demo_resource_aware():
    print("=== 7. Resource-Aware Planning (P2) ===")
    try:
        from app.cognition.counterfactual_simulator import CounterfactualSimulator
        runtime = CognitiveRuntime.get_instance()

        candidates = [
            {"name": "Web search", "action_type": "web_search", "payload": {"query": "test"}},
            {"name": "Vision analyze", "action_type": "vision_analyze", "payload": {"image_path": "test.png"}},
            {"name": "Coding agent", "action_type": "run_coding_agent", "payload": {"task": "fix bug"}},
        ]

        result = CounterfactualSimulator.simulate_competing_branches(
            "Analyze codebase and find bugs",
            candidates,
            goal_type="analysis",
            outcome_store=runtime.outcomes,
            lesson_store=runtime.lessons,
            hardware_self_model=runtime.hardware_self_model,
            resource_manager=getattr(runtime.advanced_cognition, "resource_manager", None),
        )

        print(f"Winning branch: {result.winning_branch.branch_name} ({result.winning_branch.hypothetical_action}) utility {result.winning_branch.utility_score:.4f}")
        for b in result.competing_branches:
            print(f"  - {b.branch_name}: utility {b.utility_score:.4f} — {b.reasoning_summary}")

    except Exception as e:
        print(f"Resource-aware planning demo failed: {e}")
    print()


def demo_prosody():
    print("=== 8. Prosody Emotion from Real Signals (P2) ===")
    try:
        from app.tools.prosody_analyzer import ProsodyAnalyzerTool
        import numpy as np

        # Create synthetic audio: high energy high pitch (joy)
        sr = 16000
        t = np.linspace(0, 1, sr)
        # 200 Hz sine with high amplitude
        audio_joy = (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)

        res_joy = ProsodyAnalyzerTool.analyze_prosody(audio_joy, sample_rate=sr)
        print(f"Joy-like audio: {res_joy.get('emotion')} intensity {res_joy.get('intensity'):.2f} — {res_joy.get('triggers')}")

        # Low energy low pitch (sadness)
        audio_sad = (0.03 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
        res_sad = ProsodyAnalyzerTool.analyze_prosody(audio_sad, sample_rate=sr)
        print(f"Sad-like audio: {res_sad.get('emotion')} intensity {res_sad.get('intensity'):.2f} — {res_sad.get('triggers')}")

        # High ZCR (fear)
        audio_fear = np.random.randn(sr).astype(np.float32) * 0.1
        res_fear = ProsodyAnalyzerTool.analyze_prosody(audio_fear, sample_rate=sr)
        print(f"Noisy audio: {res_fear.get('emotion')} intensity {res_fear.get('intensity'):.2f}")

    except Exception as e:
        print(f"Prosody demo failed: {e}")
    print()


def demo_multimodal():
    print("=== 9. Multimodal Chat (P2) ===")
    try:
        runtime = CognitiveRuntime.get_instance()
        # Try with image_path if exists
        from app.tools.screen_capture import ScreenCaptureTool
        cap = ScreenCaptureTool.capture_screen()
        if cap.get("success"):
            result = runtime.process_cognitive_cycle(
                user_text="What do you see in this image? Describe objects and what I should do next.",
                complexity="fast",
                image_path=cap.get("file_path"),
            )
            print(f"Multimodal reply: {result.get('assistant_reply','')[:300]}")
            print(f"Goal verified: {result.get('goal_verified')}, state: {result.get('goal_lifecycle_state')}")
        else:
            # Text-only fallback
            result = runtime.process_cognitive_cycle(
                user_text="Hello, what hardware are you running on?",
                complexity="fast",
            )
            print(f"Text-only reply: {result.get('assistant_reply','')[:300]}")
    except Exception as e:
        print(f"Multimodal chat demo failed: {e}")
    print()


def demo_projects():
    print("=== 10. Project Management (P2 long-horizon + multi-session) ===")
    try:
        runtime = CognitiveRuntime.get_instance()
        # Create a project
        proj = runtime.project_manager.create_project(
            name="Demo: Setup dev environment + research",
            description="Setup environment, research, and report — complex goal that should be decomposed",
            priority="high",
            milestones=["Check prerequisites", "Install packages", "Configure", "Verify"],
            tags=["setup_environment", "research"],
        )
        print(f"Created project: {proj.project_id} — {proj.name} — {proj.milestones_total} milestones")

        # Start session
        sess = runtime.project_manager.start_session(proj.project_id)
        print(f"Started session: {sess.session_id if sess else 'none'}")

        # Decompose goal
        decomp = runtime.goal_decomposer.decompose("Setup development environment and research latest AI trends and generate report", intent_type="setup_environment")
        print(f"Decomposed into {len(decomp.sub_goals)} sub-goals:")
        for sg in decomp.sub_goals[:3]:
            print(f"  - {sg.description} ({sg.action_type}) depends_on {sg.depends_on}")

        # Get resume context
        resume = runtime.project_manager.get_resume_context(proj.project_id)
        print(f"Resume context: {resume.get('progress_percent')}% — pending: {resume.get('pending_milestones',[])[:2]}")

    except Exception as e:
        print(f"Projects demo failed: {e}")
    print()


def demo_vlm():
    print("=== 11. VLM Integration (P3 optional) ===")
    try:
        from app.tools.vlm_analyzer import VlmAnalyzerTool
        status = VlmAnalyzerTool.get_status()
        print(f"VLM status: available={status.get('available')}, engine={status.get('engine')}, model_id={status.get('model_id')}")
        print(f"Note: {status.get('note','')}")

        # Try to analyze latest screenshot if VLM available or fallback
        from app.tools.screen_capture import ScreenCaptureTool
        cap = ScreenCaptureTool.capture_screen()
        if cap.get("success"):
            res = VlmAnalyzerTool.analyze_image(cap.get("file_path"), prompt="What is in this image?")
            print(f"VLM analysis success={res.get('success')} engine={res.get('engine')}")
            print(f"Analysis: {str(res.get('vlm_analysis',''))[:300]}")
    except Exception as e:
        print(f"VLM demo failed (expected in sandbox without models): {e}")
    print()


def demo_lora():
    print("=== 12. LoRA Continual Learning (P3) ===")
    try:
        from app.tools.lora_manager import LoraManagerTool

        status = LoraManagerTool.get_status()
        print(f"LoRA dir: {status.get('loras_dir')}")
        print(f"Adapters: {status.get('adapters_count')} — {status.get('adapters',[])[:2]}")
        print(f"Active: {status.get('active')}")
        print(f"Datasets: {status.get('datasets')}")

        # Prepare a tiny dataset for demo
        examples = [
            {"prompt": "What is your name?", "response": "I am Beanie, your local AI coworker."},
            {"prompt": "What hardware are you running on?", "response": "I run on i9-14900K with RX 580, Qwen 3B/9B via LM Studio."},
        ]
        ds_res = LoraManagerTool.prepare_dataset("general", examples)
        print(f"Prepared dataset: {ds_res}")

        # Create job config (won't train in sandbox without peft)
        job = LoraManagerTool.create_training_job("demo_adapter", skill_name="general")
        print(f"Training job: success={job.get('success')} — {job.get('error','')[:200]}")
        if job.get("instructions"):
            print(f"Instructions: {job.get('instructions','')[:300]}")

    except Exception as e:
        print(f"LoRA demo failed: {e}")
    print()


def main():
    print("Arena Agent — AGI Demo (P1-1 → P3)")
    print("====================================\n")

    demo_scorecard()
    demo_hardware()
    demo_perception_grounding()
    demo_causal_learning()
    demo_memory_association()
    demo_curiosity()
    demo_resource_aware()
    demo_prosody()
    demo_multimodal()
    demo_projects()
    demo_vlm()
    demo_lora()

    print("=== Demo Complete ===")
    print("All probes are best-effort and degradable. On your PC with models installed, VLM and LoRA will be fully exercised.")
    print("Run with: PYTHONPATH=. python scripts/demo_agi.py")


if __name__ == "__main__":
    main()
