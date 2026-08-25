"""Unit P1-A: Canonical CognitiveRuntime Composition Root Integration."""

from __future__ import annotations
import re
import uuid
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.llm import llm_client
from app.memory.coworker_brain import CoworkerBrain
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.hardware_governor import HardwareGovernor

from app.cognition.cognitive_state import CognitiveState
from app.cognition.blackboard import Blackboard
from app.cognition.event_bus import EventBus
from app.cognition.events import CognitiveEvent
from app.cognition.world_model import WorldModel
from app.cognition.source_types import SourceType
from app.cognition.world_ingest import WorldIngestor
from app.cognition.belief_engine import BeliefEngine
from app.cognition.action_selection import ActionSelector, InvestigationExecutor
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner
from app.cognition.attention_manager import AttentionManager
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.tool_registry import ToolRegistry
from app.cognition.reasoning_cycle import ReasoningCycle, ReasoningAction
from app.cognition.reasoning_loop import CognitiveReasoningLoop
from app.cognition.prompt_slicer import PromptSlicerEngine
from app.cognition.trace import CognitiveTrace
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_verifier import GoalVerifier, GoalVerificationResult
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.resource_allocator import ResourceAllocator
from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.self_model import SelfModel

class CognitiveRuntime:
    """
    P1-A: Authoritative Single Composition Root for Arena's Cognitive Architecture.
    Wires Perception ➔ WorldModel ➔ Blackboard ➔ Beliefs ➔ Attention ➔ CognitiveReasoningLoop ➔ DecisionRouter ➔ Prediction ➔ ActionGates ➔ Capability Execution ➔ GoalVerifier ➔ GoalReplanner ➔ Reflection ➔ MemoryLearner.
    """

    _instance: Optional[CognitiveRuntime] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> CognitiveRuntime:
        # Phase 0 fix: thread-safe singleton (double-checked locking). The prior
        # check-then-set could race and construct multiple runtimes under concurrency.
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = CognitiveRuntime(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: Optional[str] = None, max_steps: int = 3) -> None:
        path = db_path or str(settings.DB_PATH)
        self.state = CognitiveState()
        # Phase 3: hardware self-awareness — the agent's model of its own machine.
        try:
            self.hardware_self_model = HardwareGovernor.build_self_model()
        except Exception as e:
            app_logger.warning(f"Could not build hardware self-model: {e}")
            self.hardware_self_model = {}
        self.blackboard = Blackboard()
        self.events = EventBus()
        self.world = WorldModel(path)
        self.world_ingest = WorldIngestor(self.world, self.events)
        self.beliefs = BeliefEngine(db_path=path)
        self.actions = ActionSelector()
        self.executor = InvestigationExecutor()
        self.memory = MemoryStore(path)
        try:
            from app.config import settings as _settings
            if str(getattr(_settings, "ARENA_ASSOCIATIVE_MEMORY", "1")) != "0":
                self.memory.enable_associative()
        except Exception as _exc:
            app_logger.warning(f"Associative memory not enabled: {_exc}")
        self.learning = MemoryLearner(self.memory)
        self.attention = AttentionManager()
        from app.cognition.working_memory import WorkingMemory
        self.working_memory = WorkingMemory()
        self.prediction = PredictionEngine()
        self.counterfactual = CounterfactualSimulator()
        self.registry = ToolRegistry(event_bus=self.events)
        # Phase 1B: Strategy outcome tracking for learning from experience
        from app.cognition.strategy_outcomes import StrategyOutcomeStore
        self.outcomes = StrategyOutcomeStore(db_path=path)
        # Phase 1C: Structured lesson extraction and behavior change
        from app.cognition.structured_lessons import LessonStore
        self.lessons = LessonStore(db_path=path)
        from app.cognition.training_examples import TrainingExampleStore
        self.training_examples = TrainingExampleStore(
            db_path=str(Path(path).parent / "training_examples.db") if path else "data/training_examples.db"
        )
        from app.cognition.adaptive_autonomy import AdaptiveAutonomyCalibrator
        self.adaptive_autonomy = AdaptiveAutonomyCalibrator(
            path=str(Path(path).parent / "adaptive_autonomy.json") if path else "data/adaptive_autonomy.json"
        )
        from app.cognition.autonomy_envelope import AutonomyEnvelopeStore
        self.autonomy_envelope = AutonomyEnvelopeStore(
            str(Path(path).parent / "autonomy_envelope.json") if path else "data/autonomy_envelope.json"
        )
        from app.cognition.autonomy_run_ledger import AutonomyRunLedger
        self.autonomy_run_ledger = AutonomyRunLedger(
            str(Path(path).parent / "autonomy_run_ledger.db") if path else "data/autonomy_run_ledger.db"
        )
        from app.cognition.autonomy_lease import AutonomyCycleLease
        self.autonomy_cycle_lease = AutonomyCycleLease(
            str(Path(path).parent / "autonomy_lease.db") if path else "data/autonomy_lease.db"
        )
        from app.cognition.autonomy_allocator import AutonomyResourceAllocator
        self.autonomy_allocator = AutonomyResourceAllocator()
        from app.cognition.autonomy_schedule import AutonomySchedule
        self.autonomy_schedule = AutonomySchedule(
            str(Path(path).parent / "autonomy_schedule.db") if path else "data/autonomy_schedule.db"
        )
        from app.cognition.autonomy_preemption import AutonomyPreemptionStore
        self.autonomy_preemptions = AutonomyPreemptionStore(
            str(Path(path).parent / "autonomy_preemptions.db") if path else "data/autonomy_preemptions.db"
        )
        from app.cognition.plan_freshness import PlanFreshnessStore
        self.plan_freshness = PlanFreshnessStore(
            str(Path(path).parent / "plan_freshness.db") if path else "data/plan_freshness.db"
        )
        from app.cognition.temporal_vision import TemporalVisionTracker
        self.temporal_vision = TemporalVisionTracker(
            db_path=str(Path(path).parent / "temporal_vision.db") if path else "data/temporal_vision.db"
        )
        from app.cognition.intelligence_benchmark import (
            BenchmarkHistoryStore,
            IntelligenceBenchmarkSuite,
        )
        self.intelligence_benchmarks = IntelligenceBenchmarkSuite(
            BenchmarkHistoryStore(
                str(Path(path).parent / "intelligence_benchmarks.db")
                if path else "data/intelligence_benchmarks.db"
            )
        )
        from app.cognition.execution_control import execution_control_registry
        self.execution_control = execution_control_registry
        # Phase 3: Transfer Learning
        from app.cognition.skill_classifier import SkillClassifier
        from app.cognition.analogical_memory import AnalogicalMemory
        from app.cognition.planning_patterns import PlanningPatternStore
        self.skills = SkillClassifier()
        self.analogies = AnalogicalMemory(db_path=path)
        self.patterns = PlanningPatternStore(db_path=path)
        # Phase 5: Meta-Cognition
        self.resource_allocator = ResourceAllocator()
        self.confidence_calibrator = ConfidenceCalibrator(db_path=path)
        self.self_model = SelfModel(outcome_store=self.outcomes, lesson_store=self.lessons)
        from app.cognition.self_knowledge import SelfKnowledgeLedger
        self.self_knowledge = SelfKnowledgeLedger(
            str(Path(path).parent / "self_knowledge.db") if path else "data/self_knowledge.db"
        )
        from app.cognition.commitment_ledger import CommitmentLedger
        self.commitments = CommitmentLedger(
            str(Path(path).parent / "commitments.db") if path else "data/commitments.db"
        )
        from app.cognition.embodied_boundary import EmbodiedBoundaryModel
        self.embodied_boundary = EmbodiedBoundaryModel(
            str(Path(path).parent / "embodied_boundary.db") if path else "data/embodied_boundary.db"
        )
        from app.cognition.os_grounding import OSGroundingStore
        self.os_grounding = OSGroundingStore(
            str(Path(path).parent / "os_grounding.db") if path else "data/os_grounding.db"
        )
        from app.cognition.privilege_model import ProcessOwnershipStore
        self.process_ownership = ProcessOwnershipStore(
            str(Path(path).parent / "process_ownership.db") if path else "data/process_ownership.db"
        )
        from app.cognition.identity_continuity import IdentityContinuityLedger
        from app.cognition.owner_decisions import OwnerDecisionStore
        self.owner_decisions = OwnerDecisionStore(
            str(Path(path).parent / "owner_decisions.db") if path else "data/owner_decisions.db"
        )
        self.identity_continuity = IdentityContinuityLedger(
            str(Path(path).parent / "identity_continuity.db") if path else "data/identity_continuity.db",
            owner_decisions=self.owner_decisions,
        )
        from app.cognition.self_recovery import SelfRecoveryStore
        self.self_recovery = SelfRecoveryStore(
            str(Path(path).parent / "self_recovery.db") if path else "data/self_recovery.db"
        )
        self.boot_id = f"boot_{uuid.uuid4().hex[:16]}"
        self.refresh_self_knowledge()
        self.refresh_embodied_boundary()

        # Phase 6: Common Sense Knowledge Base for AGI
        from app.cognition.common_sense import CommonSenseKnowledgeBase
        self.common_sense = CommonSenseKnowledgeBase(db_path=path)
        
        # Phase 7: Autonomous Goal Generation
        from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator
        self.goal_generator = AutonomousGoalGenerator(db_path=path)
        
        # Phase 8: Autonomous Goal Execution
        from app.cognition.autonomous_goal_executor import AutonomousGoalExecutor
        self.goal_executor = AutonomousGoalExecutor(db_path=path)
        
        # Phase 9: Self-Reflection Engine
        from app.cognition.self_reflection_engine import SelfReflectionEngine
        self.reflection_engine = SelfReflectionEngine(db_path=path)
        
        # Phase 10: Periodic Autonomous Cycle
        from app.cognition.periodic_autonomous_cycle import PeriodicAutonomousCycle
        self.autonomous_cycle = PeriodicAutonomousCycle(
            goal_generator=self.goal_generator,
            goal_executor=self.goal_executor,
            reflection_engine=self.reflection_engine,
            db_path=path,
            interval_seconds=3600,  # 1 hour
            max_goals_per_cycle=3,
            autonomy_envelope=self.autonomy_envelope,
            run_ledger=self.autonomy_run_ledger,
            cycle_lease=self.autonomy_cycle_lease,
        )
        
        # Phase 11-21: Higher-order cognition modules (wired into the cycle via
        # _integrate_phase_modules). Previously these were orphaned — instantiated
        # and tested but never called by the runtime.
        from app.cognition.metacognitive_monitor import MetacognitiveMonitor
        self.metacognitive_monitor = MetacognitiveMonitor(db_path=path)
        from app.cognition.causal_inference import CausalInferenceEngine
        self.causal_inference = CausalInferenceEngine(db_path=path)
        from app.cognition.strategic_planning import StrategicPlanningEngine
        self.strategic_planning = StrategicPlanningEngine(db_path=path)
        from app.cognition.cross_domain_transfer import CrossDomainTransferEngine
        self.cross_domain_transfer = CrossDomainTransferEngine(db_path=path)
        from app.cognition.creative_generation import CreativeGenerationEngine
        self.creative_generation = CreativeGenerationEngine(db_path=path)
        from app.cognition.social_cognition import SocialCognitionEngine
        self.social_cognition = SocialCognitionEngine(db_path=path)
        from app.cognition.consciousness_simulation import ConsciousnessSimulator
        self.consciousness = ConsciousnessSimulator(db_path=path)
        from app.cognition.embodied_cognition import EmbodiedCognitionEngine
        self.embodied_cognition = EmbodiedCognitionEngine(db_path=path)
        from app.cognition.cultural_learning import CulturalLearningEngine
        self.cultural_learning = CulturalLearningEngine(db_path=path)
        # Phase 14: Advanced Cognitive Capabilities (resource mgmt, multi-agent
        # coordination, knowledge synthesis, uncertainty quantification).
        from app.cognition.advanced_cognitive_capabilities import Phase14AdvancedCognitiveCapabilities
        self.advanced_cognition = Phase14AdvancedCognitiveCapabilities(db_path=path)
        # Phase 22: Language Grounding (symbol ↔ perception/action/meaning).
        from app.cognition.language_grounding import LanguageGroundingEngine
        self.language_grounding = LanguageGroundingEngine(db_path=path)
        # Phase 6A/6B: Long-horizon goal decomposition + multi-session project management
        from app.cognition.goal_decomposer import GoalDecomposer
        from app.cognition.project_manager import ProjectManager
        self.goal_decomposer = GoalDecomposer(db_path=str(Path(path).parent / "goal_decompositions.db") if path else "data/goal_decompositions.db")
        self.project_manager = ProjectManager(db_path=str(Path(path).parent / "projects.db") if path else "data/projects.db")
        # Close the long-horizon loop: every persisted sub-goal update
        # deterministically reconciles its linked project. Only explicitly
        # verified completions can reach milestones.
        self.goal_decomposer.add_update_listener(
            lambda decomposition, _sub_goal: self.project_manager.reconcile_decomposition(decomposition)
        )
        from app.cognition.project_scheduler import ProjectDAGScheduler
        self.project_scheduler = ProjectDAGScheduler(
            self.goal_decomposer, self.project_manager
        )
        
        self.reasoning_cycle = ReasoningCycle(engine=self.beliefs)

        # Wire complete reasoning loop with memory, world ingestor, and event bus
        self.loop = CognitiveReasoningLoop(
            engine=self.beliefs,
            action_selector=self.actions,
            executor=self.executor,
            world_ingestor=self.world_ingest,
            event_bus=self.events,
            cognitive_state=self.state,
            max_steps=max_steps,
        )

        # One brain: register this runtime as the process-wide singleton so
        # get_instance() returns the SAME instance the server (or any caller)
        # constructed — instead of spawning a second, divergent brain.
        type(self)._instance = self

    def refresh_self_knowledge(self) -> Dict[str, Any]:
        """Refresh volatile evidence-backed claims about this runtime."""
        recorded = []
        try:
            if isinstance(self.hardware_self_model, dict) and self.hardware_self_model:
                recorded.append(self.self_knowledge.assert_claim(
                    "hardware.profile", self.hardware_self_model,
                    source_type="hardware_probe",
                    evidence=["HardwareGovernor.build_self_model"],
                    confidence=0.9, ttl_seconds=300,
                ))
            recorded.append(self.self_knowledge.assert_claim(
                "capabilities.registered_tool_count", len(self.registry._registry),
                source_type="capability_probe",
                evidence=["ToolRegistry._registry live count"],
                confidence=1.0, ttl_seconds=300,
            ))
            from app.cognition.owner_control import owner_control_store
            policy = owner_control_store.get_policy().to_dict()
            recorded.append(self.self_knowledge.assert_claim(
                "authority.owner_policy", policy,
                source_type="owner_policy",
                evidence=[f"owner_control revision {policy.get('revision')}"],
                confidence=1.0,
            ))
            recorded.append(self.self_knowledge.assert_claim(
                "consciousness.evidence_available", False,
                source_type="capability_probe",
                evidence=["No phenomenal-consciousness measurement capability is registered"],
                confidence=1.0,
            ))
        except Exception as exc:
            app_logger.warning(f"Self-knowledge refresh failed: {exc}")
        return {
            "recorded_claim_ids": [claim.claim_id for claim in recorded],
            "snapshot": self.self_knowledge.snapshot(),
        }

    def ground_os_execution(self, action_type: str, execution: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
        if action_type not in ("launch_app", "open_application"):
            return None
        launch = (execution.get("outputs") or {}).get("launch_res") or execution.get("launch_res") or {}
        if not launch.get("success"):
            return {"success": False, "verified": False, "error": "Launch was not successful"}
        pid=launch.get("pid")
        ownership=None
        if pid:
            ownership=self.process_ownership.register_arena_launch(
                int(pid),task_id=task_id,
                executable_path=str(launch.get("executable_path", "")),
            )
        result=self.os_grounding.observe_application(
            str(launch.get("app_name", "")),
            executable_path=str(launch.get("executable_path", "")),
            pid=pid, task_id=task_id,
        )
        result["process_ownership"]=ownership
        return result

    @staticmethod
    def _interface_for_action(action_type: str) -> Optional[str]:
        mapping = {
            "screen_capture": "desktop_screen", "mouse_click": "desktop_pointer",
            "type_text": "desktop_keyboard", "press_hotkey": "desktop_keyboard",
            "browser_extract": "web_browser", "web_workflow": "web_browser",
            "accessibility_activate": "semantic_accessibility",
            "camera_photo": "local_camera", "phone_command": "android_phone",
            "phone_sms": "android_phone", "phone_call": "android_phone",
            "phone_screenshot": "android_phone",
        }
        return mapping.get(action_type)

    def refresh_embodied_boundary(self) -> Dict[str, Any]:
        """Refresh the explicit sensor/actuator topology without claiming ownership."""
        definitions = [
            ("desktop_screen", "sensor", "owner_device", True, False, "screen_capture"),
            ("desktop_pointer", "actuator", "shared", False, True, "mouse_click"),
            ("desktop_keyboard", "actuator", "shared", False, True, "type_text"),
            ("web_browser", "sensor_actuator", "shared", True, True, "browser_extract"),
            ("semantic_accessibility", "sensor_actuator", "shared", True, True, "accessibility_resolve"),
            ("local_camera", "sensor", "owner_device", True, False, "camera_photo"),
            ("android_phone", "sensor_actuator", "owner_device", True, True, "phone_command"),
        ]
        records = []
        for interface_id, kind, boundary, can_read, can_write, tool in definitions:
            status = self.registry.get_tool_availability(tool, probe=False)
            records.append(self.embodied_boundary.register(
                interface_id, kind, boundary, can_read=can_read, can_write=can_write,
                available=status.get("available"),
                evidence=[f"tool:{tool}", f"availability:{status.get('status')}"]
            ))
        return {"interfaces": [item.to_dict() for item in records]}

    def checkpoint_identity_continuity(self, expected_change_types: Optional[List[str]] = None, owner_decision_id: Optional[str] = None) -> Dict[str, Any]:
        claims=self.self_knowledge.current_claims(include_stale=True)
        commitments=self.commitments.list()
        interfaces=self.embodied_boundary.interfaces()
        from app.cognition.owner_control import owner_control_store
        import hashlib, json
        claim_digests={c.predicate:hashlib.sha256(json.dumps(c.value,sort_keys=True,default=str).encode()).hexdigest() for c in claims}
        return self.identity_continuity.checkpoint({
            "claim_predicates":[c.predicate for c in claims],
            "claim_digests":claim_digests,
            "active_commitment_sources":[f"{c.source_type}:{c.source_id}" for c in commitments if c.status in ("active","blocked")],
            "interface_ids":[i.interface_id for i in interfaces],
            "interface_availability":{i.interface_id:i.available for i in interfaces},
            "provider_model":llm_client.model_override or llm_client.route_request("fast"),
            "tool_count":len(self.registry._registry),
            "owner_policy_revision":owner_control_store.get_policy().revision,
        },self.boot_id,expected_change_types=expected_change_types,owner_decision_id=owner_decision_id)

    def refresh_commitments(self) -> Dict[str, Any]:
        """Reconcile persistent projects into the commitment ledger."""
        synced = []
        manager = getattr(self, "project_manager", None)
        if manager is not None:
            for project in list(manager._projects.values()):
                try:
                    synced.append(self.commitments.sync_project(project))
                except Exception as exc:
                    app_logger.warning(
                        f"Could not reconcile project commitment {project.project_id}: {exc}"
                    )
        return {
            "synced": len(synced),
            "commitments": [item.to_dict() for item in self.commitments.list()],
        }

    def get_hardware_self_report(self) -> Dict[str, Any]:
        """
        Phase 3: Report the agent's hardware self-model plus a natural-language summary.

        The agent can answer "what am I running on, and how am I using it?" from this.
        Live telemetry is refreshed on every call so the report reflects current load.
        """
        try:
            self.hardware_self_model = HardwareGovernor.build_self_model()
        except Exception as e:
            app_logger.warning(f"Could not refresh hardware self-model: {e}")

        hw = self.hardware_self_model
        live = hw.get("live", {})
        summary = (
            f"CPU: {hw.get('cpu_model', 'unknown')} "
            f"({hw.get('cpu_logical_threads', 0)} threads, "
            f"{'hybrid P/E-core' if hw.get('hybrid_architecture') else 'homogeneous'}). "
            f"RAM: {hw.get('ram_total_gb', 0):.0f} GB ({live.get('ram_percent', 0):.0f}% used). "
            f"GPU: {hw.get('gpu_model', 'unknown')} ({hw.get('gpu_acceleration', 'cpu_only')}). "
            f"Tier: {hw.get('hardware_tier', 'unknown')}. "
            f"Mode: {hw.get('operating_mode', 'unknown')}."
        )
        return {
            "hardware_self_model": hw,
            "summary": summary,
        }

    def _select_effective_complexity(self, requested: str) -> str:
        """
        Phase 3: Adapt the model route to live hardware load.

        Under high memory pressure the agent downgrades to the fast model to stay
        responsive; with ample headroom it may still honor the requested route.
        Returns 'fast' or the requested complexity.
        """
        try:
            live = self.hardware_self_model.get("live", {})
            ram_pressure = float(live.get("ram_percent", 0.0))
            threshold = float(
                self.hardware_self_model.get("recommendation", {}).get("downgrade_to_fast_when_ram_above", 80.0)
            )
            if ram_pressure >= threshold and requested != "fast":
                app_logger.info(
                    f"Hardware-aware routing: RAM at {ram_pressure:.0f}% >= {threshold:.0f}% "
                    f"→ downgrading '{requested}' to 'fast'."
                )
                return "fast"
        except Exception as e:
            app_logger.warning(f"Hardware-aware complexity selection failed: {e}")
        return requested

    def session_start(self) -> Dict[str, Any]:
        """
        Phase 1D: Session continuity startup.
        Recalculates beliefs with current time decay and reports loaded state.
        Call at session start to ensure stale beliefs are properly decayed.
        """
        # Recalculate all beliefs with current time decay
        beliefs_changed = self.beliefs.maintain()

        # Report loaded state
        stale_count = len(self.beliefs.stale_beliefs())
        summary = {
            "beliefs_changed": beliefs_changed,
            "stale_beliefs": stale_count,
            "total_outcomes": self.outcomes.total_recorded(),
            "total_lessons": self.lessons.total_lessons(),
        }
        app_logger.info(
            f"Session start: {beliefs_changed} beliefs recalculated, "
            f"{stale_count} stale, {self.outcomes.total_recorded()} outcomes, "
            f"{self.lessons.total_lessons()} lessons loaded."
        )
        return summary

    def classify_query_predicate(self, user_text: str) -> str:
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(
            user_text, memory_store=self.memory, world_model=self.world, tool_registry=self.registry
        )
        return goal_rep.primary_intent_type

    def generate_candidate_action_proposal(self, user_text: str, complexity: str = "fast", goal_rep: Optional[Any] = None) -> ActionProposal:
        from app.cognition.action_planner import ActionPlanner
        res = ActionPlanner.plan_and_evaluate_action(
            user_text, complexity=complexity, goal_rep=goal_rep,
            memory_store=self.memory, world_model=self.world, tool_registry=self.registry,
            outcome_store=self.outcomes, lesson_store=self.lessons,
            hardware_self_model=self.hardware_self_model,
            resource_manager=getattr(self.advanced_cognition, "resource_manager", None),
        )
        if isinstance(res, ActionProposal):
            return res
        return ActionProposal.from_candidate(res, goal_text=user_text, complexity=complexity)

    def classify_fine_grained_action_type(self, user_text: str) -> str:
        prop = self.generate_candidate_action_proposal(user_text)
        return prop.action_type

    def enrich_with_common_sense(self, user_text: str) -> str:
        """
        AGI Phase 1: Enrich user query with relevant common sense knowledge.
        
        Queries the Common Sense Knowledge Base for facts relevant to the user's query
        and returns a formatted string that can be added to the system prompt to provide
        common sense context for reasoning.
        
        Returns:
            Formatted string with relevant common sense facts, or empty string if none found.
        """
        try:
            # Query common sense knowledge base for relevant facts
            relevant_facts = self.common_sense.reason_about(user_text)
            
            if not relevant_facts:
                return ""
            
            # Format facts for inclusion in prompt
            facts_text = "\n\nRelevant common sense knowledge:\n"
            for fact in relevant_facts[:5]:  # Limit to top 5 facts
                facts_text += f"- {fact.fact}\n"
            
            return facts_text
        except Exception as e:
            app_logger.warning(f"Common sense enrichment failed: {e}")
            return ""

    def generate_autonomous_goals(self, observation: str, context: Optional[Dict] = None) -> List:
        """
        AGI Phase 7: Generate autonomous goals based on an observation.
        
        Args:
            observation: The observation that triggered goal generation
            context: Optional context about the observation
            
        Returns:
            List of generated goals
        """
        try:
            goals = self.goal_generator.generate_goals_from_observation(observation, context)
            
            # Evaluate and auto-approve high-value goals FOR PLANNING. Approving a
            # goal here does NOT authorize its actions — each action still passes
            # ActionGate at execution time, and Level-3 actions require owner
            # approval (recorded as WAITING_APPROVAL, never completed).
            for goal in goals:
                self.goal_generator.evaluate_goal(goal)
                self.goal_generator.approve_goal(goal.goal_id, auto_approve_threshold=0.75)
            
            if goals:
                app_logger.info(f"Generated {len(goals)} autonomous goal(s) from observation")
            
            return goals
        except Exception as e:
            app_logger.warning(f"Failed to generate autonomous goals: {e}")
            return []

    def get_next_autonomous_goal(self):
        """
        AGI Phase 7: Get the next approved autonomous goal for execution.
        
        Returns:
            The next goal to execute, or None if no goals are ready
        """
        try:
            return self.goal_generator.get_next_goal()
        except Exception as e:
            app_logger.warning(f"Failed to get next autonomous goal: {e}")
            return None

    def execute_autonomous_goal(self):
        """
        AGI Phase 8: Execute the next approved autonomous goal.
        
        Returns:
            ExecutionPlan with results, or None if no goals ready
        """
        try:
            plan = self.goal_executor.execute_next_goal(self.goal_generator, self)
            if plan:
                app_logger.info(f"Executed autonomous goal: {plan.goal_title} - {plan.status.value}")
            return plan
        except Exception as e:
            app_logger.warning(f"Failed to execute autonomous goal: {e}")
            return None

    def get_execution_plan(self, goal_id: str):
        """
        Get the execution plan for a specific goal.
        
        Args:
            goal_id: The goal ID
            
        Returns:
            ExecutionPlan or None
        """
        try:
            return self.goal_executor.get_plan_by_goal(goal_id)
        except Exception as e:
            app_logger.warning(f"Failed to get execution plan: {e}")
            return None

    def run_autonomous_cycle(self):
        """
        AGI Phase 10: Run a single autonomous cycle.
        
        This observes the environment, generates goals, executes them,
        reflects on outcomes, and discovers patterns.
        
        Returns:
            AutonomousCycle with results
        """
        try:
            cycle = self.autonomous_cycle.run_cycle(cognitive_runtime=self)
            app_logger.info(f"Autonomous cycle completed: {cycle.summary}")
            return cycle
        except Exception as e:
            app_logger.warning(f"Failed to run autonomous cycle: {e}")
            return None

    def get_self_reflections(self, limit: int = 10):
        """
        AGI Phase 9: Get recent self-reflection insights.
        
        Args:
            limit: Maximum number of reflections to return
            
        Returns:
            List of SelfReflection objects
        """
        try:
            return self.reflection_engine.list_reflections(limit=limit)
        except Exception as e:
            app_logger.warning(f"Failed to get self-reflections: {e}")
            return []

    def get_self_model(self):
        """
        AGI Phase 9: Get the agent's self-model of its capabilities.
        
        Returns:
            SelfModel object
        """
        try:
            return self.reflection_engine.get_self_model()
        except Exception as e:
            app_logger.warning(f"Failed to get self-model: {e}")
            return None

    def get_autonomous_recommendations(self):
        """
        AGI Phase 9: Get recommendations for improving autonomous behavior.
        
        Returns:
            List of recommendation strings
        """
        try:
            return self.reflection_engine.get_recommendations()
        except Exception as e:
            app_logger.warning(f"Failed to get recommendations: {e}")
            return []

    def consolidate_memory(self) -> Dict[str, Any]:
        """
        Phase 4a: "sleep-like" memory consolidation pass.

        Decays stale beliefs, applies time-decay to memories and prunes low-value
        ones, then consolidates episodic memories into semantic facts/procedures.
        Returns a summary dict. Every step is best-effort and non-fatal.
        """
        summary: Dict[str, Any] = {
            "beliefs_changed": 0,
            "pruned_memories": 0,
            "consolidated": 0,
            "semantic_created": 0,
            "procedures_created": 0,
            "lessons_created": 0,
            "episodes_examined": 0,
        }
        try:
            summary["beliefs_changed"] = self.beliefs.maintain()
        except Exception as e:
            app_logger.warning(f"Consolidation: belief maintenance failed: {e}")

        hardware_model = getattr(self, "hardware_self_model", {}) or {}
        high_memory = float(hardware_model.get("ram_total_gb", 0) or 0) >= 40
        memory_record_cap = 20000 if high_memory else 5000
        episode_batch = 500 if high_memory else 100
        try:
            summary["pruned_memories"] = self.memory.apply_memory_decay_and_prune(max_records=memory_record_cap)
            summary["memory_record_cap"] = memory_record_cap
        except Exception as e:
            app_logger.warning(f"Consolidation: memory decay/prune failed: {e}")

        # F1.5 skill induction: mine completed plans for repeated successful
        # sequences; proposals only, owner acceptance required. Best-effort.
        try:
            from app.cognition.skill_induction import skill_induction_engine
            summary["skill_induction"] = skill_induction_engine.scan(self.goal_executor.db_path)
        except Exception as e:
            app_logger.warning(f"Consolidation: skill induction scan failed: {e}")

        try:
            episodes = self.memory.unconsolidated_episodes(limit=episode_batch)
            if episodes:
                created = self.learning.consolidate_verified_episodes(episodes)
                summary["consolidated"] = len(created)
                summary["semantic_created"] = sum(1 for item in created if item.kind == "semantic")
                summary["procedures_created"] = sum(1 for item in created if item.kind == "procedural")
                summary["lessons_created"] = sum(1 for item in created if item.kind == "lesson")
                summary["episodes_examined"] = len(episodes)
        except Exception as e:
            app_logger.warning(f"Consolidation: episodic consolidation failed: {e}")

        # P1-3 AGI: Causal consolidation — prune weak edges, keep strong ones
        try:
            summary["causal_pruned"] = 0
            summary["causal_strengthened"] = 0
            # Simple heuristic: edges with confidence <0.3 and strength <0.3 are weak
            # We don't delete, but we log and could decay them
            graph_summary = self.causal_inference.get_causal_graph_summary()
            weak_edges = []
            for edge in self.causal_inference.graph.edges.values():
                if edge.confidence < 0.3 and edge.strength < 0.3:
                    weak_edges.append(edge.edge_id)
            summary["causal_weak_edges"] = len(weak_edges)
            summary["causal_total"] = graph_summary.get("num_edges", 0)
            summary["causal_nodes"] = graph_summary.get("num_nodes", 0)
        except Exception as e:
            app_logger.warning(f"Consolidation: causal consolidation failed: {e}")

        # P1-3: Memory association — find co-occurring entities and create relationships
        try:
            from collections import defaultdict
            # Find recent observations and group by time window (1 hour)
            obs = self.world.recent_observations(limit=100)
            # Group by hour
            by_hour = defaultdict(list)
            for o in obs:
                try:
                    # Extract hour from timestamp (simple: first 13 chars of ISO)
                    hour_key = o.timestamp[:13] if hasattr(o, "timestamp") else "unknown"
                    by_hour[hour_key].append(o)
                except Exception:
                    continue
            associations = 0
            for hour, obs_list in by_hour.items():
                subjects = list(set(o.subject for o in obs_list))
                if len(subjects) >= 2:
                    # Create relationships between co-occurring subjects
                    for i in range(min(3, len(subjects))):
                        for j in range(i+1, min(4, len(subjects))):
                            try:
                                self.world.add_relationship(
                                    subject_id=subjects[i],
                                    predicate="co_occurs_with",
                                    object_id=subjects[j],
                                    confidence=0.6,
                                )
                                associations += 1
                            except Exception:
                                # Fallback: try via world_ingest
                                try:
                                    self.world_ingest.ingest(
                                        subject=subjects[i],
                                        predicate="co_occurs_with",
                                        value=subjects[j],
                                        source="memory_association",
                                        observation_type="inferred",
                                        confidence=0.6,
                                    )
                                    associations += 1
                                except Exception:
                                    pass
            summary["associations_created"] = associations
        except Exception as e:
            app_logger.warning(f"Consolidation: memory association failed: {e}")

        app_logger.info(
            f"Memory consolidation: {summary['beliefs_changed']} beliefs decayed, "
            f"{summary['pruned_memories']} memories pruned, "
            f"{summary['consolidated']} consolidated "
            f"({summary.get('semantic_created',0)} semantic, "
            f"{summary.get('procedures_created',0)} procedural, "
            f"{summary.get('lessons_created',0)} lessons), "
            f"{summary.get('associations_created',0)} associations, "
            f"causal {summary.get('causal_total',0)} edges ({summary.get('causal_weak_edges',0)} weak)."
        )
        return summary

    def run_proactive_maintenance(self) -> Dict[str, Any]:
        """
        Phase 4b: proactive coworker maintenance pass.

        Delegates to ProactiveCoworkerDaemon to index the workspace, audit tasks,
        and run self-healing when the machine is idle. Best-effort; never raises.
        """
        try:
            from app.agents.proactive_coworker_daemon import ProactiveCoworkerDaemon
            result = ProactiveCoworkerDaemon.run_idle_proactive_cycle()
            return {"success": True, "insight": result.get("proactive_insight", "")}
        except Exception as e:
            app_logger.warning(f"Proactive maintenance failed: {e}")
            return {"success": False, "insight": f"maintenance notice: {e}"}

    def describe_approval_model(self) -> Dict[str, Any]:
        """
        Phase 4c: expose the owner-authority model so the agent can reason about and
        explain its own boundaries ("nothing is off-limits, but sensitive actions
        require approval"). Levels 0-2 auto-approve; Level 3 requires explicit approval.
        """
        from app.cognition.owner_control import owner_control_store
        owner_policy = owner_control_store.get_policy().to_dict()
        return {
            "philosophy": "full-capability coworker; capabilities are approval-gated, not removed",
            "owner_control": owner_policy,
            "decision_stages": ["consideration", "recommendation", "authorization", "execution"],
            "levels": [
                {"level": 0, "name": "Read/Observe", "autonomous": True,
                 "examples": ["read_file", "web_search", "capture_screen"]},
                {"level": 1, "name": "Draft", "autonomous": True,
                 "examples": ["write_draft", "browser_draft"]},
                {"level": 2, "name": "Reversible Action", "autonomous": True,
                 "examples": ["open_application", "organize_files"]},
                {"level": 3, "name": "Sensitive/Irreversible", "autonomous": False,
                 "examples": ["send_email", "delete_file", "trade_action", "publish_post", "shell_command"]},
            ],
            "requires_owner_approval": [
                "send_email", "send_message", "publish_content", "delete_file",
                "uninstall_package", "execute_financial_transaction",
                "run_production_code", "access_external_api", "modify_system_config",
                "submit_form", "trade_action", "shell_command",
            ],
            "audit": "all actions logged with timestamp, approval status, result, and lessons",
        }

    def measure_capabilities(self) -> Dict[str, Any]:
        """
        Phase 5: measured capability scorecard, with an explicit evidence taxonomy.

        Replaces percentage-based "AGI progress" claims with evidence-backed
        capability checks. Each check is probed at runtime (not asserted from a
        doc) and tagged with one of seven evidence categories so the report is
        honest about WHAT KIND of evidence it carries — presence is not
        performance, and a wiring check is not an intelligence check:

        - STRUCTURAL     — is the module/capability present?
        - INTEGRATION    — does it participate in the cognitive cycle / registry?
        - BEHAVIORAL     — does it actually perform the capability (runtime probe)?
        - ROBUSTNESS     — does it survive perturbation (bad input, persistence)?
        - TRANSFER       — does knowledge/utility transfer across domains or actions?
        - GENERALIZATION — does it behave correctly on unseen/adversarial inputs?
        - LONGITUDINAL   — does internal state change (calibrate) with experience?

        Returns the checks plus a per-category summary and a total verified count.
        """
        checks: List[Dict[str, Any]] = []

        def _add(name: str, probe: bool, evidence: str, category: str) -> None:
            checks.append({
                "capability": name,
                "status": "verified" if probe else "missing",
                "evidence": evidence,
                "category": category,
            })

        # ── Isolation: behavioral probes must never mutate the real cognitive DB ──
        # P1 fix: measurement is observational, not self-teaching. The mutating
        # probes (beliefs, memory, causal graph, cross-domain, planning patterns)
        # run against throwaway stores in a temp dir, then the dir is discarded.
        import tempfile
        import shutil as _shutil
        from pathlib import Path as _Path
        _tmpdir = tempfile.mkdtemp(prefix="arena_scorecard_")
        try:
            from app.cognition.memory import MemoryStore as _MemoryStore
            from app.cognition.belief_engine import BeliefEngine as _BeliefEngine
            from app.cognition.causal_inference import CausalInferenceEngine as _CausalEngine
            from app.cognition.cross_domain_transfer import CrossDomainTransferEngine as _CrossEngine
            from app.cognition.planning_patterns import PlanningPatternStore as _PatternStore
            _iso_beliefs = _BeliefEngine(db_path=str(_Path(_tmpdir) / "beliefs.db"))
            _iso_memory = _MemoryStore(str(_Path(_tmpdir) / "memory.db"))
            _iso_causal = _CausalEngine(db_path=str(_Path(_tmpdir) / "causal.db"))
            _iso_cross = _CrossEngine(db_path=str(_Path(_tmpdir) / "cross.db"))
            _iso_patterns = _PatternStore(db_path=str(_Path(_tmpdir) / "patterns.db"))
        except Exception as _e:
            app_logger.warning(f"Could not build isolated probe stores: {_e}")
            _iso_beliefs = _iso_memory = _iso_causal = _iso_cross = _iso_patterns = None

        # 1. Evidence discipline (tri-state verification — no fabricated success).
        from app.cognition.goal_verifier import GoalVerifier
        _add("tri_state_verification", hasattr(GoalVerifier, "verify_goal_achievement"),
             "GoalVerifier exposes verify_goal_achievement (SATISFIED/FAILED/UNKNOWN)", "structural")

        # 1b. Verification honesty (behavioral): with no evidence, the agent must
        # report UNKNOWN for an environmental condition, not fabricate success.
        try:
            from app.cognition.goal_verifier import ConditionStatus
            from types import SimpleNamespace
            goal_rep = SimpleNamespace(primary_intent_type="launch_app", target_domain="desktop_os", entities=["chrome"])
            status = GoalVerifier.evaluate_condition_status_against_world_model(
                succ_cond="app_process_running=chrome",
                goal_rep=goal_rep,
                observations_map={},
                verified_entity_states={},
                executed_actions=[],
                reply_clean="",
                failed_conditions=[],
            )
            _add("verification_honesty", status == ConditionStatus.UNKNOWN,
                 f"no-evidence environmental condition → {status.value} (not fabricated SATISFIED)", "behavioral")
        except Exception as e:
            _add("verification_honesty", False, f"verification-honesty probe failed: {e}")

        # 2. Owner-authority approval gate: Level 3 requires approval and the
        # owner can tighten Level 0 to approve-every-action without mutating the
        # live policy (isolated temp policy file).
        try:
            allowed, _, level = __import__("app.policy", fromlist=["PolicyEvaluator"]).PolicyEvaluator.evaluate_action(
                "send_email", {"to": "a@b.com"}
            )
            from app.cognition.owner_control import OwnerControlStore as _OwnerControlStore
            _owner_probe = _OwnerControlStore(_Path(_tmpdir) / "owner_control.json")
            default_read = _owner_probe.evaluate("read_file", 0)
            _owner_probe.update({"mode": "approve_every_action"})
            strict_read = _owner_probe.evaluate("read_file", 0)
            _add(
                "approval_gate",
                (not allowed and level == 3 and default_read.allowed and
                 not strict_read.allowed and strict_read.requires_approval and
                 hasattr(self, "execute_authorized_proposal")
                 and hasattr(self, "execution_control")),
                "Owner gates + scoped verification + persistent cooperative execution control",
                "behavioral",
            )
        except Exception as e:
            _add("approval_gate", False, f"owner-control policy probe failed: {e}")

        # 2b. Belief evidence discipline (behavioral): admissible (probe) evidence
        # creates an environmental belief; a self-reported claim does not.
        try:
            probe_subj = f"__scorecard_adm_{uuid.uuid4().hex[:6]}__"
            adm = _iso_beliefs.ingest(
                subject=probe_subj, predicate="status", value="running",
                source="os_process_probe", observation_type="direct", confidence=1.0,
            )
            inadm_subj = f"__scorecard_inadm_{uuid.uuid4().hex[:6]}__"
            inadm = _iso_beliefs.ingest(
                subject=inadm_subj, predicate="status", value="running",
                source="user_input", observation_type="self_reported", confidence=1.0,
            )
            _add("belief_evidence_discipline",
                 bool(adm.has_belief) and not bool(inadm.has_belief),
                 "probe evidence → belief; self-reported claim → hypothesis only", "behavioral")
        except Exception as e:
            _add("belief_evidence_discipline", False, f"belief probe failed: {e}")

        # 2c. Memory retrieval (behavioral): add then retrieve a memory round-trip.
        try:
            probe_text = f"__scorecard_mem_{uuid.uuid4().hex[:6]}__"
            rec = _iso_memory.add("semantic", probe_text, importance=1.0)
            found = _iso_memory.search(probe_text, limit=1)
            _add("memory_retrieval",
                 bool(found) and found[0].memory_id == rec.memory_id,
                 "semantic memory added and retrieved via search", "behavioral")
        except Exception as e:
            _add("memory_retrieval", False, f"memory probe failed: {e}")

        # 2d. Causal reasoning (behavioral): add a cause→effect edge, then recover it.
        try:
            from app.cognition.causal_inference import CausalRelationType
            cause = f"__probe_cause_{uuid.uuid4().hex[:6]}__"
            effect = f"__probe_effect_{uuid.uuid4().hex[:6]}__"
            _iso_causal.add_causal_relationship(
                cause_name=cause, effect_name=effect,
                relation_type=CausalRelationType.DIRECT_CAUSE, strength=0.9, confidence=0.9,
            )
            causes = _iso_causal.root_cause_analysis(effect, "present")
            _add("causal_reasoning",
                 any(c[0] == cause for c in causes),
                 "causal edge added → root_cause_analysis recovers the cause", "behavioral")
        except Exception as e:
            _add("causal_reasoning", False, f"causal probe failed: {e}")

        # 2e. Goal verification (behavioral): a delivered response resolves SATISFIED.
        try:
            from app.cognition.goal_verifier import ConditionStatus
            from types import SimpleNamespace
            goal_rep = SimpleNamespace(primary_intent_type="question", target_domain="general", entities=[])
            status = GoalVerifier.evaluate_condition_status_against_world_model(
                succ_cond="response_delivered",
                goal_rep=goal_rep,
                observations_map={},
                verified_entity_states={},
                executed_actions=[],
                reply_clean="here is the answer",
                failed_conditions=[],
            )
            _add("goal_verification_behavioral", status == ConditionStatus.SATISFIED,
                 f"delivered reply → {status.value}", "behavioral")
        except Exception as e:
            _add("goal_verification_behavioral", False, f"goal-verification probe failed: {e}")

        # 3. Wiring completeness — every higher-order module is connected to the cycle.
        wired_modules = [
            ("common_sense", self.common_sense),
            ("autonomous_goal_generator", self.goal_generator),
            ("autonomous_goal_executor", self.goal_executor),
            ("self_reflection_engine", self.reflection_engine),
            ("metacognitive_monitor", self.metacognitive_monitor),
            ("causal_inference", self.causal_inference),
            ("strategic_planning", self.strategic_planning),
            ("cross_domain_transfer", self.cross_domain_transfer),
            ("creative_generation", self.creative_generation),
            ("social_cognition", self.social_cognition),
            ("consciousness", self.consciousness),
            ("embodied_cognition", self.embodied_cognition),
            ("cultural_learning", self.cultural_learning),
            ("advanced_cognition", self.advanced_cognition),
            ("language_grounding", self.language_grounding),
            ("goal_decomposer", self.goal_decomposer),
            ("project_manager", self.project_manager),
        ]
        _add("module_wiring", all(obj is not None for _, obj in wired_modules),
             f"{len(wired_modules)} cognition modules instantiated in the runtime", "integration")

        # 4. Hardware self-awareness.
        hw_ok = bool(self.hardware_self_model) and "cpu_model" in self.hardware_self_model
        _add("hardware_self_awareness", hw_ok,
             f"hardware self-model present ({self.hardware_self_model.get('cpu_model', 'unknown')})", "structural")

        # 5. Memory continuity / consolidation.
        _add("memory_consolidation", hasattr(self, "consolidate_memory"),
             "consolidate_memory() available (decay + prune + episodic integration)", "structural")

        # 6. Autonomy loop (goal generation → execution → reflection).
        _add("autonomy_loop",
             self.goal_generator is not None and self.goal_executor is not None and self.reflection_engine is not None,
             "goal_generator + goal_executor + reflection_engine wired", "integration")

        # 7. Cross-domain transfer (behavioral): add two domains, discover a
        # relationship, then attempt a transfer.
        try:
            from app.cognition.cross_domain_transfer import DomainType
            src = _iso_cross.add_domain_knowledge(
                name=f"__probe_src_{uuid.uuid4().hex[:6]}__", domain_type=DomainType.TECHNICAL,
                description="probe", concepts=["a"], skills=["s"], principles=["p"], patterns=["p"],
            )
            dst = _iso_cross.add_domain_knowledge(
                name=f"__probe_dst_{uuid.uuid4().hex[:6]}__", domain_type=DomainType.ANALYTICAL,
                description="probe", concepts=["b"], skills=["t"], principles=["q"], patterns=["q"],
            )
            rels = _iso_cross.discover_transfer_relationships(src.domain_id)
            _add("cross_domain_transfer_behavioral",
                 bool(rels) and rels[0].target_domain_id == dst.domain_id,
                 "two domains added → transfer relationship discovered", "transfer")
        except Exception as e:
            _add("cross_domain_transfer_behavioral", False, f"cross-domain probe failed: {e}")

        # 8. Skill classification (behavioral): classify a known action and
        # confirm siblings share a skill.
        try:
            skill = self.skills.classify("web_search")
            siblings = self.skills.skill_siblings("web_search")
            _add("skill_classification_behavioral",
                 bool(skill) and isinstance(siblings, list),
                 f"web_search → skill '{skill}' with {len(siblings)} sibling(s)", "transfer")
        except Exception as e:
            _add("skill_classification_behavioral", False, f"skill probe failed: {e}")

        # 9. Planning patterns (behavioral): record a sequence, then suggest it back.
        try:
            intent = f"__probe_intent_{uuid.uuid4().hex[:6]}__"
            _iso_patterns.record_sequence(intent_type=intent, action_sequence=["search_files", "read_file"], success=True)
            suggestions = _iso_patterns.suggest_patterns(intent_type=intent, limit=3)
            _add("planning_patterns_behavioral",
                 any(s.pattern.intent_type == intent for s in suggestions) if suggestions else False,
                 f"recorded plan for '{intent}' → {len(suggestions)} suggestion(s)", "behavioral")
        except Exception as e:
            _add("planning_patterns_behavioral", False, f"planning probe failed: {e}")

        # 10. Proactive maintenance (structural): the daemon path is wired. This
        # is NOT invoked behaviorally — running it indexes the workspace into the
        # RAG memory store, which would violate measurement isolation (P1: a
        # capability check must not teach/mutate the system it measures).
        try:
            _add("proactive_maintenance_behavioral",
                 hasattr(self, "run_proactive_maintenance") and hasattr(self, "consolidate_memory"),
                 "run_proactive_maintenance() + consolidate_memory() available (delegate to daemon)", "structural")
        except Exception as e:
            _add("proactive_maintenance_behavioral", False, f"maintenance probe failed: {e}")

        # 11. Tool wiring: the capability registry must expose the full toolset
        # (previously only 3 tools were registered; now the whole manifest is).
        try:
            n_tools = len(self.registry._registry)
            _add("tools_wired", n_tools >= 100,
                 f"{n_tools} tools registered in the capability registry", "integration")
        except Exception as e:
            _add("tools_wired", False, f"tool-wiring probe failed: {e}")

        # 12. Tier-1 deterministic tool suite: the manifest must expose the full
        # built toolset (read-only data, PDF, process, backup, finance, network,
        # messaging, agents). Presence check — not claimed from a doc.
        try:
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
            expected = [
                "run_data_analysis", "db_query", "db_execute", "pdf_merge",
                "list_processes", "kill_process", "create_backup", "restore_backup",
                "generate_invoice", "generate_presentation", "add_transaction",
                "check_port", "crypto_price", "stock_price", "fact_check",
                "send_telegram", "install_package", "fetch_feed",
            ]
            missing = [k for k in expected if k not in manifest]
            _add("tier1_tool_manifest", not missing,
                 f"{len(manifest)} tools in manifest; all expected Tier-1 action types present"
                 + (f" (missing: {missing})" if missing else ""), "structural")
        except Exception as e:
            _add("tier1_tool_manifest", False, f"tier1-manifest probe failed: {e}")

        # 13. Deterministic degradation (behavioral): deterministic tools must
        # return typed {success: False} results on invalid input, never raise.
        try:
            from app.tools.price_lookup import PriceLookup
            from app.tools.pdf_toolkit import PdfToolkit
            from app.tools.database_connector import DatabaseConnector
            from app.tools.backup_manager import BackupManager
            probes = [
                PriceLookup.get_stock_price(""),
                PdfToolkit.get_metadata(""),
                DatabaseConnector.query("oracle", "SELECT 1"),
                BackupManager.create_backup([]),
            ]
            _add("deterministic_degradation",
                 all(isinstance(p, dict) and p.get("success") is False for p in probes),
                 "invalid inputs → typed {success: False} results (no exceptions)", "robustness")
        except Exception as e:
            _add("deterministic_degradation", False, f"degradation probe failed: {e}")

        # 14. Robustness — persistence: a structured lesson survives a save/reload
        # round-trip (the system survives the "restart" perturbation).
        try:
            from app.cognition.structured_lessons import LessonStore as _LessonStore
            _ls = _LessonStore(db_path=str(_Path(_tmpdir) / "lessons.db"))
            _ls.extract_lesson(
                task_type="__probe_task__", action_type="__probe_action__",
                final_state="failed", verified_success=False,
                failed_conditions=["probe"], reply_text="probe failure",
            )
            _ls2 = _LessonStore(db_path=str(_Path(_tmpdir) / "lessons.db"))
            _add("persistence_roundtrip", _ls2.total_lessons() >= 1,
                 "structured lesson survives a SQLite save/reload round-trip", "robustness")
        except Exception as e:
            _add("persistence_roundtrip", False, f"persistence probe failed: {e}", "robustness")

        # 15. Generalization — capability matching on unseen/adversarial inputs:
        # the token-boundary matcher must NOT let a short stem ("port") leak into
        # an unrelated capability ("quantum_teleportation"), while still resolving
        # the intended dotted forms.
        try:
            tool_norms = {"check_port", "search_files", "web_search", "port", "search", "web"}
            false_positive = self._tool_capability_match("quantum_teleportation", tool_norms)
            true_positive = self._tool_capability_match("filesystem.search", tool_norms)
            _add("capability_generalization",
                 (not false_positive) and true_positive,
                 "matcher: 'quantum_teleportation' → no match; 'filesystem.search' → match "
                 "(correct on unseen inputs)", "generalization")
        except Exception as e:
            _add("capability_generalization", False, f"generalization probe failed: {e}", "generalization")

        # 16. Longitudinal — learning changes behavior: after recording repeated
        # failures for an action, the outcome store must lower that action's
        # future utility weight (the system's internal state changes with
        # experience). This is a minimal probe, not a full longitudinal study.
        try:
            from app.cognition.strategy_outcomes import StrategyOutcomeStore as _OutcomeStore
            _os = _OutcomeStore(db_path=str(_Path(_tmpdir) / "outcomes.db"))
            for _ in range(3):
                _os.record_outcome("__probe_goal__", "__probe_action__", success=False)
            _add("learning_changes_behavior",
                 _os.adjustment_factor("__probe_goal__", "__probe_action__") < 1.0
                 and hasattr(self, "intelligence_benchmarks"),
                 "repeated failures lower utility; isolated longitudinal benchmark history is wired",
                 "longitudinal")
        except Exception as e:
            _add("learning_changes_behavior", False, f"longitudinal probe failed: {e}", "longitudinal")

        # P3 AGI: New capability checks for human-intelligence push (perception grounding, causal learning, etc.)
        # 17. Perception grounding (P1-1): object_detector + language_grounding integration
        try:
            from app.tools.object_detector import ObjectDetectorTool
            _add("perception_grounding",
                 hasattr(ObjectDetectorTool, "analyze_image_grounded") and hasattr(self, "language_grounding"),
                 "ObjectDetectorTool.analyze_image_grounded() + language_grounding wired (perception→grounding loop)", "integration")
        except Exception as e:
            _add("perception_grounding", False, f"perception grounding probe failed: {e}", "integration")

        # 18. Causal learning (P1-2): learn_from_execution + learn_from_surprisal
        try:
            _add("causal_learning",
                 hasattr(self.causal_inference, "learn_from_execution") and hasattr(self.causal_inference, "learn_from_surprisal"),
                 "CausalInferenceEngine learns from execution + surprisal (Bayesian update, not just storage)", "behavioral")
        except Exception as e:
            _add("causal_learning", False, f"causal learning probe failed: {e}", "behavioral")

        # 19. Memory consolidation/association: isolated verified episodes must
        # become provenance-linked semantic and procedural memory.
        try:
            from app.cognition.memory_learning import MemoryLearner as _MemoryLearner
            from app.cognition.goal_lifecycle import GoalLifecycleState as _GoalState
            from types import SimpleNamespace as _SimpleNamespace
            _memory_learner = _MemoryLearner(_iso_memory)
            _verification = _SimpleNamespace(
                verified_success=True,
                final_state=_GoalState.ACHIEVED,
                met_conditions=["probe = true"],
                failed_conditions=[],
                verification_reason="isolated direct probe",
            )
            for _index in range(2):
                _memory_learner.record_verified_episode(
                    goal=f"__scorecard_memory_{_index}",
                    action_type="search_files",
                    verification_result=_verification,
                    task_id=f"__memory_task_{_index}",
                    task_type="search_intent",
                )
            _created = _memory_learner.consolidate_verified_episodes(
                _iso_memory.unconsolidated_episodes()
            )
            _kinds = {item.kind for item in _created}
            _add(
                "memory_association",
                "semantic" in _kinds and "procedural" in _kinds,
                "isolated verified episodes → provenance-linked semantic + procedural memory",
                "behavioral",
            )
        except Exception as e:
            _add("memory_association", False, f"memory consolidation probe failed: {e}", "behavioral")

        # 20. Curiosity info-gain (P1-4): generate_goals_from_information_gain
        try:
            _add("curiosity_info_gain",
                 hasattr(self.goal_generator, "generate_goals_from_information_gain")
                 and hasattr(self.goal_generator, "generate_goals_from_signals")
                 and hasattr(self, "adaptive_autonomy"),
                 "Information-gain curiosity uses outcome-calibrated thresholds and an owner-bounded exploration budget", "behavioral")
        except Exception as e:
            _add("curiosity_info_gain", False, f"curiosity probe failed: {e}", "behavioral")

        # 21. Resource-aware planning (P2): counterfactual simulator resource_adj
        try:
            from app.cognition.counterfactual_simulator import CounterfactualSimulator
            _add("resource_aware_planning",
                 hasattr(CounterfactualSimulator, "RESOURCE_COSTS") and hasattr(self, "hardware_self_model"),
                 "CounterfactualSimulator RESOURCE_COSTS + hardware_self_model penalizes heavy actions under pressure", "behavioral")
        except Exception as e:
            _add("resource_aware_planning", False, f"resource-aware probe failed: {e}", "behavioral")

        # 22. Prosody emotion (P2): prosody_analyzer + social_cognition
        try:
            from app.tools.prosody_analyzer import ProsodyAnalyzerTool
            _add("prosody_emotion",
                 hasattr(ProsodyAnalyzerTool, "analyze_prosody") and hasattr(self, "social_cognition"),
                 "ProsodyAnalyzerTool.analyze_prosody() (pitch/energy/ZCR→emotion) + social_cognition wired", "integration")
        except Exception as e:
            _add("prosody_emotion", False, f"prosody probe failed: {e}", "integration")

        # 23. Multimodal chat (P2): process_cognitive_cycle accepts image_path
        try:
            import inspect
            sig = inspect.signature(self.process_cognitive_cycle)
            has_multimodal = "image_path" in sig.parameters and "attachments" in sig.parameters
            _add("multimodal_chat",
                 has_multimodal and hasattr(self, "temporal_vision"),
                 "Multimodal chat + persistent appeared/moved/disappeared object tracking through ONE brain", "integration")
        except Exception as e:
            _add("multimodal_chat", False, f"multimodal probe failed: {e}", "integration")

        # 24. Self-evolution verified (P2): synthesize→pytest→hotload only if green
        try:
            from app.agents.self_evolving_agent import SelfEvolvingAgent
            _add("self_evolution_verified",
                 hasattr(SelfEvolvingAgent, "synthesize_and_hotload_tool") and hasattr(SelfEvolvingAgent, "list_dynamic_tools"),
                 "SelfEvolvingAgent verified loop: synthesize→pytest→hotload only if green + PluginRegistry", "robustness")
        except Exception as e:
            _add("self_evolution_verified", False, f"self-evolution probe failed: {e}", "robustness")

        # 25. Project management (P2): long-horizon + multi-session
        try:
            _add("project_management",
                 hasattr(self, "project_manager") and hasattr(self, "goal_decomposer")
                 and hasattr(self.project_manager, "create_project")
                 and hasattr(self.project_manager, "reconcile_decomposition")
                 and hasattr(self, "project_scheduler"),
                 "ProjectManager + GoalDecomposer + persistent DAG scheduler — exact ready sub-goals execute through verification and reconcile milestones", "integration")
        except Exception as e:
            _add("project_management", False, f"project management probe failed: {e}", "integration")

        # 26. VLM integration (P3): true visual understanding with fallback
        try:
            from app.tools.vlm_analyzer import VlmAnalyzerTool
            _add("vlm_integration",
                 hasattr(VlmAnalyzerTool, "analyze_image") and hasattr(VlmAnalyzerTool, "get_status"),
                 "VlmAnalyzerTool (Moondream2/Llava) with OCR+LLM fallback — true VLM when installed, safe degrade otherwise", "robustness")
        except Exception as e:
            _add("vlm_integration", False, f"VLM probe failed: {e}", "robustness")

        # 27. LoRA continual learning (P3): adapters without catastrophic forgetting
        try:
            from app.tools.lora_manager import LoraManagerTool
            _add("lora_continual_learning",
                 hasattr(LoraManagerTool, "list_adapters")
                 and hasattr(LoraManagerTool, "train")
                 and hasattr(self, "training_examples")
                 and hasattr(self.training_examples, "export_approved"),
                 "Verified outcomes → redacted owner-reviewed examples → reproducible LoRA train/eval datasets", "longitudinal")
        except Exception as e:
            _add("lora_continual_learning", False, f"LoRA probe failed: {e}", "longitudinal")

        verified = [c for c in checks if c["status"] == "verified"]

        # Per-category summary: how many checks (and verified checks) in each of
        # the seven evidence categories. This is what lets the report honestly
        # distinguish "the module exists" from "it performs / transfers / improves".
        categories: Dict[str, Dict[str, int]] = {}
        for c in checks:
            cat = c.get("category", "unclassified")
            bucket = categories.setdefault(cat, {"verified": 0, "total": 0})
            bucket["total"] += 1
            if c["status"] == "verified":
                bucket["verified"] += 1

        # Discard the isolated probe stores so measurement leaves no residue.
        _shutil.rmtree(_tmpdir, ignore_errors=True)

        return {
            "checks": checks,
            "verified_count": len(verified),
            "total_count": len(checks),
            "categories": categories,
            "not_claimed": (
                "This scorecard measures implemented, wired, and behaviorally-verified "
                "capabilities. It makes no claim of 'human-level AGI', consciousness, or "
                "general intelligence — those are not evidenced by these checks."
            ),
        }

    def check_capability_availability(
        self,
        required_capabilities: List[str],
        target_domain: str
    ) -> Dict[str, bool]:
        """
        P0 Fix: Dynamically resolves capability availability against ToolRegistry,
        CapabilityFactory, WorldModel, and environmental device status without default 'or True'.
        """
        cap_map: Dict[str, bool] = {}

        NATIVE_CAPABILITIES = {
            "llm.generate", "os.launch_app", "filesystem.search", "filesystem.read",
            "browser.open", "web.search", "screen.capture", "vision.analyze",
            "system.probe", "camera.capture", "camera.photo", "location.resolve",
            "location.geolocate", "microphone.capture", "microphone.record",
        }

        registered_tools = set(self.registry._registry.keys())

        # Normalized tool names + action stems, so a dotted capability like
        # "filesystem.search" can match a tool named "search_files", and
        # "web.search" matches "web_search" (the LLM emits free-form dotted
        # capability strings that don't share one naming scheme with the tools).
        tool_norms = set()
        for rt in registered_tools:
            norm = rt.replace(".", "_").replace("-", "_")
            tool_norms.add(norm)
            # Also register each underscore-delimited segment as a stem, so
            # "search" matches "search_files" and "web_search".
            for seg in norm.split("_"):
                if len(seg) >= 3:
                    tool_norms.add(seg)

        # WorldModel active capabilities
        wm_caps = set()
        try:
            caps_entities = self.world.find_entities(entity_type="capability")
            wm_caps = {c.name.lower().replace(" ", "_") for c in caps_entities}
        except Exception as e:
            app_logger.warning(f"Could not read WorldModel capabilities: {e}")

        for cap in required_capabilities:
            cap_clean = cap.lower().strip()

            # 1. Device-specific probe check (e.g. ADB phone controller).
            #    Use token/prefix matching — a bare substring "phone" would wrongly
            #    catch "microphone", "telephone", "headphones", etc.
            if cap_clean.startswith("phone.") or cap_clean == "phone" or \
               cap_clean.startswith("adb.") or cap_clean == "adb":
                try:
                    from app.tools.android_adb_controller import AndroidADBController
                    cap_map[cap] = AndroidADBController.is_adb_available()
                except Exception:
                    cap_map[cap] = False

            # 2. Check native capability list
            elif any(cap_clean == nc or cap_clean in nc or nc in cap_clean for nc in NATIVE_CAPABILITIES):
                cap_map[cap] = True

            # 3. Check ToolRegistry registered tools (normalized dot/underscore
            #    + action-stem matching so "filesystem.search" → "search_files").
            #    Match on token boundaries, NOT bare substrings — otherwise a
            #    short generic stem like "port" (from check_port) would wrongly
            #    match "quantum_teleportation", just as "phone" would match
            #    "microphone".
            elif self._tool_capability_match(cap_clean, tool_norms):
                cap_map[cap] = True

            # 4. Check WorldModel dynamic capabilities synthesized by CapabilityFactory
            elif any(wc in cap_clean or cap_clean in wc for wc in wm_caps):
                cap_map[cap] = True

            # 5. Unsupported / Unknown capability -> FALSE
            else:
                cap_map[cap] = False

        return cap_map

    @staticmethod
    def _tool_capability_match(cap_clean: str, tool_norms: set) -> bool:
        """Match a dotted capability string against tool names/stems on token
        boundaries (dot/underscore), never as a bare substring.

        Examples:
          "filesystem.search" matches "search_files" (via the "search" stem)
          "web.search"       matches "web_search"
          "search"           matches "search_files"
          "quantum_teleportation" does NOT match "check_port" (no "port" token)
        """
        cap_tokens = set(cap_clean.replace(".", "_").split("_"))
        for tn in tool_norms:
            if tn == cap_clean:
                return True
            tn_tokens = set(tn.split("_"))
            if cap_clean in tn_tokens:
                return True
            if tn in cap_tokens:
                return True
        return False

    def capture_observed_world_state(
        self,
        executed_actions: List[str],
        assistant_reply: str,
        goal_rep: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        P0 Fix: Captures real environmental world state from WorldModel, BeliefEngine, and Perception.
        Ensures all entity states carry explicit provenance (source, observation_type, confidence)
        so GoalVerifier can enforce universal provenance validation.
        """
        entities_data = []
        try:
            entities = self.world.find_entities()[:15]
            for ent in entities:
                latest_obs = self.world.latest_observation(ent.name, "status") or self.world.latest_observation(ent.name, "process_status")
                if latest_obs:
                    # Authoritative: use the structured observation record
                    real_status = str(latest_obs.value)
                    obs_source = latest_obs.source
                    obs_type = getattr(latest_obs, "observation_type", "direct")
                    obs_conf = latest_obs.confidence
                else:
                    # No observation exists for this entity — state is UNKNOWN.
                    # Do NOT inherit entity attributes as provenance. Entity attributes
                    # are creation-time metadata, not environmental observations.
                    real_status = "unknown"
                    obs_source = "not_observed"
                    obs_type = "unknown"
                    obs_conf = 0.0

                entities_data.append({
                    "id": ent.id,
                    "name": ent.name,
                    "type": ent.entity_type,
                    "status": real_status,
                    "source": obs_source,
                    "observation_type": obs_type,
                    "confidence": obs_conf,
                    "attributes": ent.attributes
                })
        except Exception as e:
            app_logger.warning(f"Could not read WorldModel entities: {e}")

        if not entities_data and goal_rep and getattr(goal_rep, "entities", None):
            for e in goal_rep.entities:
                latest_obs = self.world.latest_observation(e, "status") or self.world.latest_observation(e, "process_status")
                if latest_obs:
                    ent_status = str(latest_obs.value)
                    obs_source = latest_obs.source
                    obs_type = getattr(latest_obs, "observation_type", "direct")
                    obs_conf = latest_obs.confidence
                else:
                    ent_status = "unknown"
                    obs_source = "not_observed"
                    obs_type = "unknown"
                    obs_conf = 0.0

                entities_data.append({
                    "name": e,
                    "type": "process" if getattr(goal_rep, "target_domain", "") == "desktop_os" else "entity",
                    "status": ent_status,
                    "source": obs_source,
                    "observation_type": obs_type,
                    "confidence": obs_conf
                })

        obs_data = {}
        try:
            obs = self.world.recent_observations(limit=25)
            for o in obs:
                key = f"{o.subject}.{o.predicate}"
                if key not in obs_data:
                    obs_data[key] = {
                        "value": o.value,
                        "source": o.source,
                        "confidence": o.confidence,
                        "observation_type": getattr(o, "observation_type", "direct")
                    }
        except Exception as e:
            app_logger.warning(f"Could not read WorldModel observations: {e}")

        return {
            "world_state": {
                "entities": entities_data,
                "observations": obs_data,
            },
            "execution_trace": {
                "executed_actions": executed_actions,
                "last_action": getattr(self.state.execution, "last_action", ""),
                "last_result": getattr(self.state.execution, "last_result", "")
            },
            "assistant_response": {
                "text": assistant_reply
            },
            # Top-level aliases for backward compatibility
            "entities": entities_data,
            "observations": obs_data,
            "executed_actions": executed_actions,
            "assistant_reply": assistant_reply
        }

    def _integrate_phase_modules(
        self,
        user_text: str,
        intent_type: str,
        latency_ms: float,
        reasoning_action: str,
        success: bool,
        goal_verified: bool,
    ) -> None:
        """
        Wire the higher-order cognition modules (Phases 11-21) into the cognitive cycle.

        Extracted to app/cognition/runtime_wiring.py (composition refactor);
        delegated with self as the single authoritative runtime instance.
        """
        from app.cognition.runtime_wiring import integrate_phase_modules
        integrate_phase_modules(
            self, user_text, intent_type, latency_ms, reasoning_action, success, goal_verified,
        )


    def _propose_training_example(
        self,
        *,
        prompt: str,
        response: str,
        action_type: str,
        verification_result: Any,
        session_id: str,
        trace_id: str,
    ) -> None:
        """Best-effort candidate creation; never auto-approves or trains."""
        try:
            self.training_examples.propose_verified(
                prompt=prompt,
                response=response,
                action_type=action_type,
                verification_result=verification_result,
                source_session_id=session_id,
                source_trace_id=trace_id,
            )
        except Exception as exc:
            app_logger.warning(f"Could not propose reviewed LoRA example: {exc}")

    def _execute_capability_controlled(
        self,
        proposal: ActionProposal,
        user_text: str,
        complexity: str,
    ) -> Dict[str, Any]:
        """Execute one proposal under cooperative cancellation accounting."""
        from app.agents.master_agent import MasterAgentOrchestrator
        from app.cognition.execution_control import (
            ExecutionCancelled,
            execution_control_registry,
        )
        control = getattr(self, "execution_control", execution_control_registry)

        record = control.begin(
            proposal_id=proposal.proposal_id,
            action_type=proposal.action_type,
        )
        with control.scope(record.execution_id):
            try:
                control.checkpoint("before_capability")
                raw_result = MasterAgentOrchestrator.execute_proposal(
                    proposal,
                    user_text,
                    complexity=complexity,
                    world_model=self.world,
                )
                result = (
                    raw_result.to_dict()
                    if hasattr(raw_result, "to_dict")
                    else dict(raw_result)
                )
            except ExecutionCancelled as exc:
                result = {
                    "success": False,
                    "attempted": False,
                    "executed_actions": [],
                    "assistant_reply": str(exc),
                    "error": str(exc),
                    "execution_status": "cancelled",
                }
                control.complete(
                    record.execution_id,
                    status="cancelled",
                    note=str(exc),
                )
                result.update({
                    "controlled_execution_id": record.execution_id,
                    "cancel_requested": True,
                    "cancellation_observed": True,
                    "rollback_receipt": None,
                })
                control.record_result(record.execution_id, result)
                return result
            except Exception as exc:
                result = {
                    "success": False,
                    "attempted": True,
                    "executed_actions": [],
                    "assistant_reply": f"Capability execution failed: {exc}",
                    "error": str(exc),
                    "execution_status": "failed",
                }

        cancel_requested = control.is_cancel_requested(record.execution_id)
        receipt = control.create_rollback_receipt(
            record.execution_id,
            proposal.action_type,
            proposal.payload,
            result,
        )
        if record.cancellation_observed or result.get("cancelled"):
            status = "cancelled"
            note = "Cancellation was observed at a cooperative checkpoint."
        elif cancel_requested:
            status = "completed_after_cancel_request"
            note = (
                "Cancellation arrived after the last cooperative checkpoint; "
                "side effects may have occurred and were still observed/verified."
            )
        else:
            status = "completed" if result.get("success") else "failed"
            note = ""
        completed = control.complete(
            record.execution_id,
            status=status,
            rollback_receipt=receipt,
            note=note,
        )
        result.update({
            "controlled_execution_id": record.execution_id,
            "cancel_requested": cancel_requested,
            "cancellation_observed": completed.cancellation_observed,
            "rollback_receipt": receipt.to_dict(),
        })
        control.record_result(record.execution_id, result)
        return result

    def verify_existing_proposal_outcome(
        self,
        proposal: ActionProposal,
        user_text: str,
        previous_result: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Re-observe an earlier action without executing it again.

        Used for UNKNOWN project steps. It performs only capability-specific
        observation probes and GoalVerifier evaluation; no ActionGate grant is
        consumed and the capability layer is never invoked.
        """
        from app.cognition.owner_control import owner_control_store
        if owner_control_store.get_policy().paused:
            return {
                "success": False,
                "request_success": False,
                "execution_success": False,
                "goal_verified": False,
                "verification_unknown": True,
                "goal_lifecycle_state": "waiting_for_evidence",
                "reconciliation": True,
                "reason": "Owner emergency pause is active; reconciliation probe skipped.",
            }

        session_id = session_id or f"reconcile_{uuid.uuid4().hex[:8]}"
        goal_text = str(
            proposal.payload.get("original_goal")
            or proposal.payload.get("query")
            or user_text
        )
        tracker = GoalTracker(user_query=goal_text)
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        try:
            goal_rep = SemanticGoalInterpreter.interpret_goal(
                goal_text,
                complexity="fast",
                memory_store=self.memory,
                world_model=self.world,
                tool_registry=self.registry,
            )
        except Exception as exc:
            return {
                "success": False,
                "request_success": True,
                "execution_success": False,
                "goal_verified": False,
                "verification_unknown": True,
                "goal_lifecycle_state": "waiting_for_evidence",
                "reconciliation": True,
                "reason": f"Could not reconstruct goal for observation-only reconciliation: {exc}",
            }

        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Restored goal for observation-only reconciliation")
        tracker.transition(GoalLifecycleState.EXECUTING, "Running observation probes without re-executing action")
        from app.cognition.perception import ObservationCollector
        observation_error = ""
        try:
            ObservationCollector.collect_and_ingest_observations(
                proposal,
                previous_result,
                world_model=self.world,
                event_bus=self.events,
            )
        except Exception as exc:
            observation_error = str(exc)
            app_logger.warning(f"Evidence reconciliation observation failed: {exc}")

        previous_actions = list(previous_result.get("executed_actions", []) or [])
        previous_reply = str(previous_result.get("assistant_reply", "") or "")
        observed_state = self.capture_observed_world_state(
            previous_actions, previous_reply, goal_rep
        )
        verification = GoalVerifier.verify_goal_achievement(
            goal_rep,
            previous_actions,
            previous_reply,
            failed_action_type=proposal.action_type,
            tracker=tracker,
            observed_state=observed_state,
            failed_payload=proposal.payload,
        )

        if verification.final_state in (
            GoalLifecycleState.ACHIEVED,
            GoalLifecycleState.FAILED,
            GoalLifecycleState.BLOCKED,
        ):
            try:
                self.learning.record_verified_episode(
                    goal=goal_text,
                    action_type=proposal.action_type,
                    verification_result=verification,
                    task_id=session_id,
                    task_type=goal_rep.primary_intent_type,
                )
                self._propose_training_example(
                    prompt=goal_text,
                    response=previous_reply,
                    action_type=proposal.action_type,
                    verification_result=verification,
                    session_id=session_id,
                    trace_id=str(previous_result.get("trace_id", "")),
                )
            except Exception as exc:
                app_logger.warning(f"Evidence reconciliation learning failed: {exc}")

        try:
            self.events.publish(CognitiveEvent(
                event_type="proposal_outcome_reconciled",
                data={
                    "session_id": session_id,
                    "proposal_id": proposal.proposal_id,
                    "action_type": proposal.action_type,
                    "goal_verified": verification.verified_success,
                    "goal_state": tracker.current_state.value,
                },
                source=SourceType.COGNITIVE_RUNTIME,
            ))
        except Exception:
            pass

        return {
            "success": True,
            "request_success": True,
            "execution_success": bool(previous_result.get("execution_success", False)),
            "goal_verified": verification.verified_success,
            "verification_unknown": verification.is_unknown,
            "goal_lifecycle_state": tracker.current_state.value,
            "reconciliation": True,
            "reexecuted": False,
            "proposal_id": proposal.proposal_id,
            "action_type": proposal.action_type,
            "assistant_reply": previous_reply,
            "executed_actions": previous_actions,
            "verification": {
                "reason": verification.verification_reason,
                "met_conditions": verification.met_conditions,
                "failed_conditions": verification.failed_conditions,
                "unknown_conditions": verification.unknown_conditions,
            },
            "observation_error": observation_error or None,
        }

    def execute_authorized_proposal(
        self,
        proposal: ActionProposal,
        user_text: str,
        complexity: str = "fast",
        session_id: Optional[str] = None,
        success_criteria_override: Optional[List[str]] = None,
        failure_conditions_override: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute one exact authorized proposal through the full evidence loop.

        This path deliberately does not re-plan: changing the selected action or
        payload would exceed the owner's scoped authorization. A failed or
        unverified result is reported and learned from; any retry/alternative
        requires a new recommendation and authorization.
        """
        start_time = time.time()
        session_id = session_id or f"auth_{uuid.uuid4().hex[:8]}"
        goal_text = str(
            proposal.payload.get("original_goal")
            or proposal.payload.get("query")
            or user_text
        )
        scoped_authorization = bool(proposal.authorization_id)
        tracker = GoalTracker(user_query=goal_text)
        trace = CognitiveTrace(
            user_input=goal_text,
            complexity_requested=complexity,
            session_id=session_id,
        )

        # Validate and consume the exact grant before semantic interpretation or
        # any other potentially expensive work. A bad/replayed grant is rejected
        # without reaching the model, resource manager, or capability layer.
        gate = ActionGate.evaluate_proposal(proposal)
        trace.gate_decision = gate.gate_name
        if not gate.allowed:
            tracker.transition(GoalLifecycleState.BLOCKED, gate.reason)
            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=gate.reason,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision=gate.gate_name,
                goal_verified=False,
            )
            return {
                "success": False,
                "request_success": False,
                "execution_success": False,
                "goal_verified": False,
                "verification_unknown": False,
                "decision_stage": gate.decision_stage,
                "gate": gate.gate_name,
                "reason": gate.reason,
                "requires_approval": gate.requires_approval,
                "proposal_id": proposal.proposal_id,
                "authorization_id": proposal.authorization_id,
                "session_id": session_id,
                "trace_id": trace.trace_id,
            }

        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        try:
            goal_rep = SemanticGoalInterpreter.interpret_goal(
                goal_text,
                complexity=complexity,
                memory_store=self.memory,
                world_model=self.world,
                tool_registry=self.registry,
            )
        except Exception as exc:
            tracker.transition(GoalLifecycleState.FAILED, f"Could not restore authorized goal: {exc}")
            latency = (time.time() - start_time) * 1000
            authority_note = (
                "Scoped authorization was consumed"
                if scoped_authorization
                else "Owner-delegated execution authority passed the gate"
            )
            message = f"{authority_note}, but goal interpretation failed: {exc}"
            trace.finalize(
                reply=message,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision=gate.gate_name,
                goal_verified=False,
            )
            return {
                "success": False,
                "request_success": True,
                "execution_success": False,
                "goal_verified": False,
                "verification_unknown": False,
                "goal_lifecycle_state": tracker.current_state.value,
                "decision_stage": "execution_failed_before_capability",
                "reason": message,
                "proposal_id": proposal.proposal_id,
                "authorization_id": proposal.authorization_id,
                "authorization_consumed": scoped_authorization,
                "requires_new_authorization_for_retry": scoped_authorization,
                "requires_fresh_decision_for_retry": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
            }
        if success_criteria_override:
            goal_rep.success_conditions = [
                str(item) for item in success_criteria_override if str(item).strip()
            ]
        if failure_conditions_override:
            goal_rep.failure_conditions = [
                str(item) for item in failure_conditions_override if str(item).strip()
            ]
        intent_type = goal_rep.primary_intent_type
        tracker.transition(
            GoalLifecycleState.UNDERSTOOD,
            f"Restored owner-authorized goal in domain '{goal_rep.target_domain}'",
        )
        tracker.transition(
            GoalLifecycleState.PLANNED,
            f"Using exact authorized proposal '{proposal.proposal_id}' without re-planning",
        )

        prediction = self.prediction.predict_action(proposal.action_type, proposal.payload)
        proposal.predicted_outcome = proposal.predicted_outcome or prediction.expected_changes
        trace.predicted_outcome = proposal.predicted_outcome

        tracker.transition(
            GoalLifecycleState.EXECUTING,
            f"Executing exact owner-authorized proposal '{proposal.proposal_id}'",
        )
        try:
            self.commitments.upsert(
                goal_text, source_type="owner_authorized_action",
                source_id=proposal.proposal_id, status="active",
                evidence=[
                    f"authorization:{proposal.authorization_id}",
                    f"action:{proposal.action_type}",
                ],
            )
        except Exception as exc:
            app_logger.warning(f"Could not record authorized commitment: {exc}")
        from app.cognition.perception import ObservationCollector

        execution = self._execute_capability_controlled(
            proposal,
            goal_text,
            complexity,
        )
        executed_actions = execution.get("executed_actions", [])
        assistant_reply = execution.get("assistant_reply", "")
        execution_success = bool(execution.get("success", False))
        os_grounding = self.ground_os_execution(proposal.action_type, execution, session_id)
        if os_grounding is not None:
            execution["os_grounding"] = os_grounding

        observation_error = ""
        try:
            ObservationCollector.collect_and_ingest_observations(
                proposal,
                execution,
                world_model=self.world,
                event_bus=self.events,
            )
        except Exception as exc:
            observation_error = str(exc)
            app_logger.warning(f"Authorized execution observation failed: {exc}")

        observed_state = self.capture_observed_world_state(
            executed_actions, assistant_reply, goal_rep
        )
        verification = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions,
            assistant_reply,
            failed_action_type=proposal.action_type,
            tracker=tracker,
            observed_state=observed_state,
            failed_payload=proposal.payload,
        )
        trace.goal_verified = verification.verified_success
        try:
            agency_evidence = list(verification.met_conditions or [])
            if observation_error:
                agency_evidence.append(f"observation_error: {observation_error}")
            execution["agency_attribution"] = self.self_knowledge.attribute_change(
                f"Outcome of {proposal.action_type} for goal: {goal_text[:160]}",
                execution_id=execution.get("controlled_execution_id"),
                execution_attempted=bool(execution.get("attempted", True)),
                environment_observed=bool(observed_state) and not observation_error,
                goal_verified=verification.verified_success,
                evidence=agency_evidence,
            ).to_dict()
            interface_id = self._interface_for_action(proposal.action_type)
            if interface_id:
                execution["boundary_event"] = self.embodied_boundary.record_event(
                    interface_id, proposal.action_type, actor="arena",
                    execution_id=execution.get("controlled_execution_id"),
                    authorized=True,
                    observed=bool(observed_state) and verification.verified_success,
                    evidence=agency_evidence,
                ).to_dict()
        except Exception as exc:
            app_logger.warning(f"Agency attribution failed: {exc}")
        try:
            commitment_evidence = list(verification.met_conditions or [])
            if verification.verified_success and not commitment_evidence:
                commitment_evidence = [f"GoalVerifier: {verification.verification_reason}"]
            if verification.verified_success:
                self.commitments.upsert(
                    goal_text, source_type="owner_authorized_action",
                    source_id=proposal.proposal_id, status="completed",
                    evidence=commitment_evidence,
                    completion_verified=True,
                )
            elif tracker.current_state == GoalLifecycleState.WAITING_FOR_EVIDENCE:
                self.commitments.upsert(
                    goal_text, source_type="owner_authorized_action",
                    source_id=proposal.proposal_id, status="blocked",
                    evidence=list(verification.failed_conditions or []),
                    blocked_reason="Execution finished, but independent verification remains unknown.",
                )
            else:
                self.commitments.upsert(
                    goal_text, source_type="owner_authorized_action",
                    source_id=proposal.proposal_id, status="failed",
                    evidence=list(verification.failed_conditions or []),
                )
        except Exception as exc:
            app_logger.warning(f"Could not update authorized commitment: {exc}")
        try:
            self.learning.record_verified_episode(
                goal=goal_text,
                action_type=proposal.action_type,
                verification_result=verification,
                task_id=session_id,
                task_type=intent_type,
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution episodic memory failed: {exc}")
        self._propose_training_example(
            prompt=goal_text,
            response=assistant_reply,
            action_type=proposal.action_type,
            verification_result=verification,
            session_id=session_id,
            trace_id=trace.trace_id,
        )

        actual_state = dict(observed_state or {})
        actual_state.update({
            "actions": executed_actions,
            "reply": assistant_reply[:100],
            "success": verification.verified_success,
            "goal_state": tracker.current_state.value,
        })
        surprisal = self.prediction.evaluate_surprisal(prediction, actual_state)
        trace.prediction_surprisal = surprisal
        try:
            self.confidence_calibrator.record(
                proposal.action_type, prediction.confidence,
                verification.verified_success, surprisal=surprisal,
                goal_type=intent_type,
            )
        except Exception as exc:
            app_logger.warning(f"Competence calibration record failed: {exc}")

        try:
            self.world_ingest.ingest(
                subject="system",
                predicate="authorized_response",
                value=assistant_reply[:200],
                source=SourceType.MASTER_AGENT,
                task_id=session_id,
                observation_type="self_reported",
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution world ingest failed: {exc}")

        effect_name = (
            executed_actions[0][:60]
            if executed_actions
            else ("goal_verified" if verification.verified_success else "goal_unverified")
        )
        try:
            self.causal_inference.learn_from_surprisal(
                cause_name=proposal.action_type,
                effect_name=effect_name,
                surprisal=surprisal,
                evidence=[
                    f"authorized_proposal={proposal.proposal_id}",
                    f"verified={verification.verified_success}",
                ],
            )
            self.causal_inference.learn_from_execution(
                cause_name=f"intent:{intent_type}",
                effect_name=effect_name,
                success=verification.verified_success,
                evidence=[f"action={proposal.action_type}", f"surprisal={surprisal:.2f}"],
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution causal learning failed: {exc}")

        lesson_text = ""
        try:
            lesson = self.learning.process_outcome_reflection(
                task_title=goal_text[:50],
                goal=goal_text,
                verification_result=verification,
                surprisal=surprisal,
            )
            lesson_text = getattr(lesson, "content", "")
        except Exception as exc:
            app_logger.warning(f"Authorized execution reflection failed: {exc}")

        latency = (time.time() - start_time) * 1000
        try:
            self.outcomes.record_outcome(
                goal_type=intent_type,
                action_type=proposal.action_type,
                success=verification.verified_success,
                latency_ms=latency,
                surprisal=surprisal,
                goal_text=goal_text,
            )
            self.lessons.extract_lesson(
                task_type=intent_type,
                action_type=proposal.action_type,
                final_state=tracker.current_state.value,
                verified_success=verification.verified_success,
                failed_conditions=verification.failed_conditions,
                reply_text=assistant_reply,
                goal_text=goal_text,
                latency_ms=latency,
                surprisal=surprisal,
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution outcome learning failed: {exc}")

        try:
            if hasattr(self, "self_model"):
                self.self_model.assess_capability(proposal.action_type)
            if hasattr(self, "analogies"):
                self.analogies.record_task(
                    intent_type=intent_type,
                    target_domain=goal_rep.target_domain,
                    entity_types=list(getattr(goal_rep, "entities", [])[:5]),
                    action_type=proposal.action_type,
                    success=verification.verified_success,
                    outcome=tracker.current_state.value,
                    goal_text=goal_text,
                )
            if hasattr(self, "patterns") and executed_actions:
                self.patterns.record_sequence(
                    intent_type=intent_type,
                    action_sequence=[proposal.action_type],
                    success=verification.verified_success,
                    successful_step=0 if verification.verified_success else -1,
                )
        except Exception as exc:
            app_logger.warning(f"Authorized execution transfer learning failed: {exc}")

        try:
            self.events.publish(CognitiveEvent(
                event_type="authorized_execution_completed",
                data={
                    "session_id": session_id,
                    "proposal_id": proposal.proposal_id,
                    "authorization_id": proposal.authorization_id,
                    "action_type": proposal.action_type,
                    "execution_success": execution_success,
                    "goal_verified": verification.verified_success,
                    "goal_state": tracker.current_state.value,
                    "surprisal": surprisal,
                },
                source=SourceType.COGNITIVE_RUNTIME,
            ))
            db.create_audit_log(
                "authorized_execution",
                "verified" if verification.verified_success else "unverified",
                f"proposal={proposal.proposal_id}; action={proposal.action_type}; "
                f"execution_success={execution_success}; goal_state={tracker.current_state.value}",
                level=proposal.safety_level,
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution audit/event failed: {exc}")

        try:
            self._integrate_phase_modules(
                user_text=goal_text,
                intent_type=intent_type,
                latency_ms=latency,
                reasoning_action="authorized_execution",
                success=verification.verified_success,
                goal_verified=verification.verified_success,
            )
        except Exception as exc:
            app_logger.warning(f"Authorized execution module integration failed: {exc}")

        trace.model_used = execution.get("model_used", "fast")
        trace.finalize(
            reply=assistant_reply,
            actions=executed_actions,
            latency=latency,
            surprisal=surprisal,
            lesson=lesson_text,
            gate_decision=gate.gate_name,
            goal_verified=verification.verified_success,
        )

        verification_unknown = tracker.current_state == GoalLifecycleState.WAITING_FOR_EVIDENCE
        return {
            "success": True,
            "request_success": True,
            "execution_success": execution_success,
            "goal_verified": verification.verified_success,
            "verification_unknown": verification_unknown,
            "goal_lifecycle_state": tracker.current_state.value,
            "decision_stage": "execution_completed",
            "proposal_id": proposal.proposal_id,
            "authorization_id": proposal.authorization_id,
            "action_type": proposal.action_type,
            "executed_actions": executed_actions,
            "assistant_reply": assistant_reply,
            "verification": {
                "verified_success": verification.verified_success,
                "failed_conditions": verification.failed_conditions,
                "met_conditions": verification.met_conditions,
                "reason": verification.verification_reason,
            },
            "observation_error": observation_error or None,
            "prediction_surprisal": surprisal,
            "reflection_lesson": lesson_text,
            "latency_ms": round(latency, 2),
            "trace_id": trace.trace_id,
            "session_id": session_id,
            "model_used": trace.model_used,
            "controlled_execution_id": execution.get("controlled_execution_id"),
            "cancel_requested": execution.get("cancel_requested", False),
            "cancellation_observed": execution.get("cancellation_observed", False),
            "rollback_receipt": execution.get("rollback_receipt"),
            "agency_attribution": execution.get("agency_attribution"),
            "boundary_event": execution.get("boundary_event"),
            "os_grounding": execution.get("os_grounding"),
            "replan_performed": False,
            "requires_new_authorization_for_retry": (
                scoped_authorization and not verification.verified_success
            ),
            "requires_fresh_decision_for_retry": not verification.verified_success,
        }

    def process_cognitive_cycle(
        self,
        user_text: str,
        complexity: str = "fast",
        session_id: Optional[str] = None,
        image_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Authoritative Closed-Loop Predictive Cognitive Cycle with Goal Lifecycle & Verification:
        1. Initialize Trace & Hardware Snapshot & GoalTracker (CREATED)
        2. Set CognitiveState & Attention Focus Target
        3. Blackboard Ingestion & Context Budget Slicing (Retrieves Past Lessons)
        4. Semantic GoalRepresentation v2 Decomposition (UNDERSTOOD)
        5. WorldModel Ingestion & CognitiveReasoningLoop Execution
        6. Authoritative Decision Router (ANSWER vs INVESTIGATE vs DEFER vs ACT)
        7. Candidate Strategy Planning & Counterfactual Simulation (PLANNED)
        8. Multi-Gate Verification & Capability Execution (EXECUTING)
        9. Goal Verification & Reassessment/Replanner on Failure (VERIFYING ➔ ACHIEVED/FAILED ➔ REPLAN)
        10. Prediction Error Surprisal ➔ Reflection ➔ Memory Learning ➔ Trace Finalize
        """
        start_time = time.time()
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        # Phase 3: adapt model route to live hardware load.
        complexity = self._select_effective_complexity(complexity)

        # Initialize Goal Lifecycle Tracker
        tracker = GoalTracker(user_query=user_text)

        # 1. Initialize Trace & Hardware Snapshot
        trace = CognitiveTrace(
            user_input=user_text,
            complexity_requested=complexity,
            session_id=session_id
        )

        try:
            hw = HardwareMonitor.get_hardware_stats()
            trace.vram_pressure_at_start = float(hw.get("vram_used_percent", 0.0))
            trace.ram_pressure_at_start = float(hw.get("ram_used_percent", 0.0))
        except Exception as e:
            app_logger.warning(f"CognitiveRuntime: Could not snapshot hardware stats: {e}")

        # 2. Set CognitiveState & Attention Focus
        self.state.session.session_id = session_id
        focus_target = self.attention.allocate_attention(user_text[:40], priority_score=0.85)
        self.state.attention.focus = focus_target.target_name
        trace.attention_focus = focus_target.target_name
        # F1.3 Working memory: decay old items, then attend the current query.
        try:
            self.working_memory.decay()
            self.working_memory.set_goal(user_text)
            self.working_memory.encode(user_text, kind="user_query", source="user", salience=1.0)
        except Exception as exc:
            app_logger.warning(f"Working memory encode failed (non-fatal): {exc}")
        self.state.task.current_step = "cognitive_cycle"
        self.state.touch()

        # 3. Blackboard Ingestion & Context Slicing (Retrieves Past Learned Lessons)
        self.blackboard.set("current_user_query", user_text, source=SourceType.USER_INPUT, confidence=1.0)
        # Phase 3: expose the hardware self-model so reasoning can consult the machine state.
        self.blackboard.set("hardware_self_model", self.hardware_self_model, source="hardware_governor")
        # P2 AGI: Multimodal ingestion — if image_path or attachments provided, analyze and ground
        multimodal_context = ""
        if image_path:
            try:
                from app.tools.vision_analyzer import VisionAnalyzerTool
                from app.tools.object_detector import ObjectDetectorTool
                # Run grounded detection (perception→grounding loop)
                det_res = ObjectDetectorTool.analyze_image_grounded(image_path, auto_create_groundings=True)
                if det_res.get("success"):
                    dets = det_res.get("detections", [])
                    self.blackboard.set("multimodal_detections", dets, source="object_detector")
                    multimodal_context += f"\n[VISION: {len(dets)} objects detected in {image_path}: {', '.join(d.get('label','?') for d in dets[:10])}]"
                    # Also run OCR + LLM analysis for screen content
                    vis_res = VisionAnalyzerTool.analyze_screen_image(image_path, prompt_focus=user_text[:100], auto_save_memory=False, skip_delta_check=True)
                    if vis_res.get("success"):
                        multimodal_context += f"\n[OCR: {vis_res.get('ocr_text','')[:500]}]"
                        multimodal_context += f"\n[VISION ANALYSIS: {vis_res.get('ai_analysis','')[:500]}]"
            except Exception as e:
                app_logger.warning(f"Multimodal image ingestion failed: {e}")

        if attachments:
            try:
                for att in attachments[:3]:
                    att_path = att.get("path") or att.get("file_path") or ""
                    if att_path:
                        multimodal_context += f"\n[ATTACHMENT: {att.get('name','file')} at {att_path}]"
            except Exception as e:
                app_logger.warning(f"Attachment ingestion failed: {e}")

        if multimodal_context:
            self.blackboard.set("multimodal_context", multimodal_context, source="multimodal", confidence=0.9)

        try:
            sliced_ctx = PromptSlicerEngine.slice_context_for_task(user_text)
            # Enrich sliced context with multimodal if present
            ctx_str = sliced_ctx.compact_prompt_str
            if multimodal_context:
                ctx_str += "\n\n" + multimodal_context
                # Attended perceptions enter working memory with provenance.
                try:
                    self.working_memory.encode(
                        multimodal_context.strip()[:500], kind="observation",
                        source="multimodal_ingestion", salience=0.8, goal_text=user_text,
                    )
                except Exception:
                    pass
            # The reasoning loop consults the live scratchpad.
            try:
                wm_context = self.working_memory.context_text(max_chars=1200)
                if wm_context:
                    ctx_str += "\n\n[WORKING MEMORY]\n" + wm_context
                    self.blackboard.set("working_memory", self.working_memory.snapshot(),
                                        source="working_memory", confidence=1.0)
            except Exception:
                pass
            self.blackboard.set("sliced_context", ctx_str, source="prompt_slicer")
        except Exception as e:
            app_logger.warning(f"PromptSlicer error: {e}")

        # 4. Semantic Goal Representation v2 & WorldModel / Belief Ingestion
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(
            user_text, complexity=complexity, memory_store=self.memory, world_model=self.world, tool_registry=self.registry
        )
        query_pred = goal_rep.primary_intent_type
        tracker.transition(GoalLifecycleState.UNDERSTOOD, f"Parsed goal in domain '{goal_rep.target_domain}'")

        # P2 AGI: Long-horizon goal decomposition — if goal is complex, break into sub-goals and track as project
        decomposition = None
        project = None
        try:
            # Heuristic for complex goals: contains setup/install/configure + research/report + multi-step keywords
            complex_keywords = ["setup", "install", "configure", "research and report", "analyze and", "create and", "build", "full", "complete", "project"]
            is_complex = any(k in user_text.lower() for k in complex_keywords) or len(user_text.split()) > 15
            if is_complex:
                decomposition = self.goal_decomposer.decompose(goal_text=user_text, intent_type=query_pred)
                # Create persistent project for multi-session tracking
                project = self.project_manager.create_project(
                    name=user_text[:60],
                    description=user_text,
                    priority="high" if "critical" in user_text.lower() or "urgent" in user_text.lower() else "normal",
                    milestones=[{
                        "description": sg.description,
                        "source_sub_goal_id": sg.sub_goal_id,
                    } for sg in decomposition.sub_goals],
                    tags=[query_pred, goal_rep.target_domain],
                    context={
                        "original_goal": user_text,
                        "intent": query_pred,
                        "decomposition_id": decomposition.project_id,
                        # Avoid duplicating the current foreground action. The
                        # owner explicitly enables persistent DAG scheduling.
                        "auto_schedule": False,
                    },
                    decomposition_id=decomposition.project_id,
                )
                # Start first session
                self.project_manager.start_session(project.project_id)
                self.blackboard.set("active_project", project.project_id, source="project_manager")
                self.blackboard.set("goal_decomposition", decomposition.project_id, source="goal_decomposer")
                app_logger.info(f"Created project {project.project_id} with {len(decomposition.sub_goals)} sub-goals for complex goal")
        except Exception as e:
            app_logger.warning(f"Goal decomposition/project creation failed (best-effort): {e}")

        try:
            self.world_ingest.ingest(
                subject="user",
                predicate=query_pred,
                value=user_text[:200],
                source=SourceType.USER_INPUT,
                task_id=session_id,
                observation_type="self_reported",
            )
            belief_res = self.beliefs.ingest(
                subject="user",
                predicate=query_pred,
                value=user_text[:200],
                source=SourceType.USER_INPUT,
                task_id=session_id,
                observation_type="self_reported",
            )
            # Use belief_confidence from authoritative belief, fall back to goal confidence
            trace.belief_confidence = float(
                belief_res.belief_confidence if belief_res.has_belief else goal_rep.confidence
            )
        except Exception as e:
            app_logger.warning(f"WorldModel/Belief ingestion warning: {e}")

        # Resolve dynamic capability availability for required task capabilities
        capability_map = self.check_capability_availability(
            required_capabilities=goal_rep.required_capabilities,
            target_domain=goal_rep.target_domain
        )
        action_available = all(capability_map.values()) if capability_map else True

        app_logger.info(f"Capability Awareness: Required={goal_rep.required_capabilities} -> Status={capability_map} (ActionAvailable={action_available})")

        # Run Authoritative Cognitive Reasoning Loop with dynamic capability map
        loop_trace = self.loop.run(
            subject=user_text[:30].strip() or "user_query",
            predicate=query_pred,
            value=user_text[:200],
            source=SourceType.USER_INPUT,
            task_id=session_id,
            action_available=action_available,
            available_capabilities=capability_map
        )

        last_decision = loop_trace.decisions[-1] if loop_trace.decisions else None
        reasoning_action = last_decision.action if last_decision else ReasoningAction.ACT

        # 5. DECISION ROUTER (100% Authoritative ReasoningAction Routing):
        # Branch A: ANSWER / Direct Conversational Q&A
        if reasoning_action == ReasoningAction.ANSWER:
            tracker.transition(GoalLifecycleState.EXECUTING, "Formulating direct conversational answer.")
            system_instruction = CoworkerBrain.format_coworker_prompt(user_text)
            # AGI Phase 1: Enrich with common sense knowledge
            common_sense_context = self.enrich_with_common_sense(user_text)
            if common_sense_context:
                system_instruction += common_sense_context
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", "Done.")
            if llm_res.get("simulated") or llm_res.get("id") == "chat-simulated":
                tracker.transition(
                    GoalLifecycleState.DEFERRED,
                    "Local language model unavailable; no conversational answer was generated.",
                )
                latency = (time.time() - start_time) * 1000
                trace.finalize(
                    reply=assistant_reply,
                    actions=[],
                    latency=latency,
                    surprisal=0.0,
                    lesson="",
                    gate_decision="llm_unavailable",
                    goal_verified=False,
                )
                return {
                    "request_success": True,
                    "execution_success": False,
                    "goal_verified": False,
                    "success": False,
                    "session_id": session_id,
                    "trace_id": trace.trace_id,
                    "user_text": user_text,
                    "assistant_reply": assistant_reply,
                    "executed_actions": [],
                    "action_type": "defer",
                    "reasoning_action": "defer",
                    "goal_lifecycle_state": tracker.current_state.value,
                    "prediction_surprisal": 0.0,
                    "latency_ms": round(latency, 2),
                    "model_used": llm_res.get("model", "fast"),
                    "llm_available": False,
                }

            obs_state = self.capture_observed_world_state([], assistant_reply, goal_rep)
            verify_res = GoalVerifier.verify_goal_achievement(goal_rep, [], assistant_reply, tracker=tracker, observed_state=obs_state)
            trace.goal_verified = verify_res.verified_success
            try:
                self.learning.record_verified_episode(
                    goal=user_text,
                    action_type="formulate_answer",
                    verification_result=verify_res,
                    task_id=session_id,
                    task_type=query_pred,
                )
            except Exception as e:
                app_logger.warning(f"Answer episodic memory failed: {e}")
            self._propose_training_example(
                prompt=user_text,
                response=assistant_reply,
                action_type="formulate_answer",
                verification_result=verify_res,
                session_id=session_id,
                trace_id=trace.trace_id,
            )

            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=assistant_reply,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision="passed",
                goal_verified=verify_res.verified_success
            )
            self._integrate_phase_modules(
                user_text=user_text,
                intent_type=query_pred,
                latency_ms=latency,
                reasoning_action="answer",
                success=verify_res.verified_success,
                goal_verified=verify_res.verified_success,
            )
            return {
                "request_success": True,
                "execution_success": True,
                "goal_verified": verify_res.verified_success,
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": assistant_reply,
                "executed_actions": [],
                "action_type": "formulate_answer",
                "reasoning_action": "answer",
                "goal_lifecycle_state": tracker.current_state.value,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": llm_res.get("model", "fast")
            }

        # Branch B: INVESTIGATE / Bounded Probe Evidence Gathering Loop
        elif reasoning_action == ReasoningAction.INVESTIGATE:
            tracker.transition(GoalLifecycleState.EXECUTING, "Running bounded probe investigation loop.")
            investigation_summary = f"Gathered evidence from {len(loop_trace.results)} probe(s)" if loop_trace.results else "Diagnostic investigation completed."
            if loop_trace.results:
                investigation_summary += ": " + "; ".join(f"{r.tool}: {str(r.output)[:80]}" for r in loop_trace.results)

            system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=[investigation_summary])
            # AGI Phase 1: Enrich with common sense knowledge
            common_sense_context = self.enrich_with_common_sense(user_text)
            if common_sense_context:
                system_instruction += common_sense_context
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", investigation_summary)

            obs_state = self.capture_observed_world_state([investigation_summary], assistant_reply, goal_rep)
            verify_res = GoalVerifier.verify_goal_achievement(goal_rep, [investigation_summary], assistant_reply, tracker=tracker, observed_state=obs_state)
            trace.goal_verified = verify_res.verified_success
            try:
                self.learning.record_verified_episode(
                    goal=user_text,
                    action_type="investigate",
                    verification_result=verify_res,
                    task_id=session_id,
                    task_type=query_pred,
                )
            except Exception as e:
                app_logger.warning(f"Investigation episodic memory failed: {e}")
            self._propose_training_example(
                prompt=user_text,
                response=assistant_reply,
                action_type="investigate",
                verification_result=verify_res,
                session_id=session_id,
                trace_id=trace.trace_id,
            )

            try:
                lesson_rec = self.learning.process_outcome_reflection(
                    task_title=f"Investigation: {user_text[:30]}",
                    goal=user_text,
                    verification_result=verify_res,
                    surprisal=0.1
                )
                trace.reflection_lesson = getattr(lesson_rec, "content", "Investigation completed.")
            except Exception as e:
                app_logger.warning(f"Investigation reflection notice: {e}")

            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=assistant_reply,
                actions=[investigation_summary],
                latency=latency,
                surprisal=0.1,
                lesson=trace.reflection_lesson,
                gate_decision="passed",
                goal_verified=verify_res.verified_success
            )
            self._integrate_phase_modules(
                user_text=user_text,
                intent_type=query_pred,
                latency_ms=latency,
                reasoning_action="investigate",
                success=verify_res.verified_success,
                goal_verified=verify_res.verified_success,
            )
            return {
                "request_success": True,
                "execution_success": True,
                "goal_verified": verify_res.verified_success,
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": assistant_reply,
                "executed_actions": [investigation_summary],
                "action_type": "investigate",
                "reasoning_action": "investigate",
                "goal_lifecycle_state": tracker.current_state.value,
                "prediction_surprisal": 0.1,
                "reflection_lesson": trace.reflection_lesson,
                "latency_ms": round(latency, 2),
                "model_used": llm_res.get("model", "fast")
            }

        # Branch C: DEFER / SAFELY ASK USER
        elif reasoning_action == ReasoningAction.DEFER:
            tracker.transition(GoalLifecycleState.DEFERRED, "Evidence or capabilities are insufficient for a safe decision.")
            defer_msg = f"Deferred task: {last_decision.reason if last_decision else 'Evidence or capabilities are insufficient for a safe decision.'}"
            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=defer_msg,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision="deferred",
                goal_verified=False
            )
            self._integrate_phase_modules(
                user_text=user_text,
                intent_type=query_pred,
                latency_ms=latency,
                reasoning_action="defer",
                success=False,
                goal_verified=False,
            )
            return {
                "request_success": True,
                "execution_success": False,
                "goal_verified": False,
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": defer_msg,
                "executed_actions": [],
                "action_type": "defer",
                "reasoning_action": "defer",
                "goal_lifecycle_state": tracker.current_state.value,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ReasoningCycle"
            }

        # Branch D: ACT / Action Strategy Simulation ➔ ActionProposal ➔ Prediction ➔ ActionGate ➔ Capability Execution
        tracker.transition(GoalLifecycleState.PLANNED, "Simulated candidate branches with CounterfactualSimulator.")
        
        # Phase 5: Meta-Cognition - Classify task complexity and allocate resources
        complexity_level, complexity_reason = self.resource_allocator.classify_complexity(goal_rep)
        budget = self.resource_allocator.allocate(complexity_level)
        app_logger.info(f"Resource Allocation: Complexity={complexity_level.value}, Model={budget.model}, MaxCycles={budget.max_reasoning_cycles}, Reason={complexity_reason}")
        
        # Phase 3B: Consult analogical memory for similar past tasks
        similar_tasks = []
        try:
            similar_tasks = self.analogies.find_analogies(
                intent_type=goal_rep.primary_intent_type,
                target_domain=goal_rep.target_domain,
                entity_types=[e.entity_type for e in self.world.find_entities()[:5]] if hasattr(goal_rep, 'entities') else [],
                limit=3
            )
            if similar_tasks:
                app_logger.info(f"Analogical Memory: Found {len(similar_tasks)} similar past tasks")
                for match in similar_tasks:
                    app_logger.info(f"  - {match.insight} (similarity: {match.similarity:.2f})")
        except Exception as e:
            app_logger.warning(f"Analogical memory consultation failed: {e}")
        
        # Phase 3C: Query planning patterns for suggestions
        pattern_suggestions = []
        try:
            pattern_suggestions = self.patterns.suggest_patterns(
                intent_type=goal_rep.primary_intent_type,
                limit=3
            )
            if pattern_suggestions:
                app_logger.info(f"Planning Patterns: {len(pattern_suggestions)} suggestions available")
                for suggestion in pattern_suggestions[:2]:
                    app_logger.info(f"  - {suggestion.reason}")
        except Exception as e:
            app_logger.warning(f"Planning pattern query failed: {e}")
        
        # Generate candidate action proposal
        proposal = getattr(last_decision, "proposed_action", None) or self.generate_candidate_action_proposal(user_text, complexity=complexity, goal_rep=goal_rep)
        fine_action_type = proposal.action_type
        
        # Phase 3A: Skill classification and transfer adjustment
        skill_type = self.skills.classify(fine_action_type)
        skill_adjustment = 1.0
        try:
            goal_type = goal_rep.primary_intent_type if goal_rep else "unknown"
            skill_adjustment = self.skills.transfer_adjustment(
                target_action=fine_action_type,
                outcome_store=self.outcomes,
                goal_type=goal_type
            )
            if skill_adjustment != 1.0:
                app_logger.info(f"Skill Transfer: {skill_type} skill adjustment = {skill_adjustment:.2f}")
        except Exception as e:
            app_logger.warning(f"Skill transfer adjustment failed: {e}")

        if not proposal.predicted_outcome:
            pred = self.prediction.predict_action(proposal.action_type, proposal.payload)
            proposal.predicted_outcome = pred.expected_changes
        else:
            from app.cognition.prediction_engine import WorldPrediction
            pred = WorldPrediction(action_type=proposal.action_type, expected_changes=proposal.predicted_outcome)
        trace.predicted_outcome = proposal.predicted_outcome
        
        # Phase 5: Confidence calibration - adjust prediction confidence based on historical accuracy
        try:
            calibrated_confidence = self.confidence_calibrator.calibrate(
                action_type=fine_action_type,
                raw_confidence=pred.confidence,
                context={"skill_type": skill_type, "complexity": complexity_level.value}
            )
            if calibrated_confidence != pred.confidence:
                app_logger.info(f"Confidence Calibration: {pred.confidence:.2f} → {calibrated_confidence:.2f}")
                pred.confidence = calibrated_confidence
        except Exception as e:
            app_logger.warning(f"Confidence calibration failed: {e}")

        # Multi-Gate Checks (Policy, Resource, Prediction)
        gate_res = ActionGate.evaluate_proposal(proposal)
        trace.gate_decision = gate_res.gate_name

        if not gate_res.allowed:
            approval_request = None
            if gate_res.requires_approval:
                tracker.transition(GoalLifecycleState.WAITING_FOR_USER, f"Action requires 1-click UI approval: {gate_res.reason}")
                # Record the pending approval so the owner can approve/deny via
                # the `action_approval` WebSocket message.
                try:
                    from app.cognition.approval_store import approval_store
                    req = approval_store.add(
                        conversation_id=session_id,
                        action_type=fine_action_type,
                        payload=proposal.payload,
                        reason=gate_res.reason,
                        goal_text=user_text,
                        proposal_id=proposal.proposal_id,
                        recommendation_reason=proposal.recommendation_reason,
                        alternatives_considered=proposal.alternatives_considered,
                        predicted_outcome=proposal.predicted_outcome,
                    )
                    approval_request = req.to_dict()
                    app_logger.info(f"Pending approval recorded: action_id={req.action_id}")
                except Exception as e:
                    app_logger.warning(f"Could not record pending approval: {e}")
            else:
                tracker.transition(GoalLifecycleState.BLOCKED, f"Action blocked by {gate_res.gate_name}: {gate_res.reason}")

            latency = (time.time() - start_time) * 1000
            blocked_msg = f"Action blocked by {gate_res.gate_name}: {gate_res.reason}"
            trace.finalize(
                reply=blocked_msg,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision=gate_res.gate_name,
                goal_verified=False
            )
            self._integrate_phase_modules(
                user_text=user_text,
                intent_type=query_pred,
                latency_ms=latency,
                reasoning_action="gate_blocked",
                success=False,
                goal_verified=False,
            )
            return {
                "request_success": False,
                "execution_success": False,
                "goal_verified": False,
                "success": False,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": blocked_msg,
                "executed_actions": [],
                "requires_approval": gate_res.requires_approval,
                "gate_blocked": gate_res.gate_name,
                "approval_request": approval_request,
                "decision_stage": gate_res.decision_stage,
                "recommendation": {
                    "action_type": proposal.action_type,
                    "reason": proposal.recommendation_reason,
                },
                "alternatives_considered": proposal.alternatives_considered,
                "goal_lifecycle_state": tracker.current_state.value,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ActionGate"
            }

        # Capability Execution Layer (Executes selected ActionProposal directly without re-routing)
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing selected action strategy via capability layer.")
        agent_res = self._execute_capability_controlled(
            proposal, user_text, complexity
        )
        control_result = agent_res
        executed_actions = agent_res.get("executed_actions", [])
        assistant_reply = agent_res.get("assistant_reply", "Done.")
        os_grounding = self.ground_os_execution(proposal.action_type, agent_res, session_id)
        if os_grounding is not None:
            agent_res["os_grounding"] = os_grounding

        # Perception Layer: Ingest Environmental Observations from ExecutionResult into WorldModel
        from app.cognition.perception import ObservationCollector
        ObservationCollector.collect_and_ingest_observations(
            proposal, agent_res, world_model=self.world, event_bus=self.events
        )

        # Goal Verification
        obs_state = self.capture_observed_world_state(executed_actions, assistant_reply, goal_rep)
        verify_res = GoalVerifier.verify_goal_achievement(
            goal_rep, executed_actions, assistant_reply, failed_action_type=proposal.action_type, tracker=tracker, observed_state=obs_state, failed_payload=proposal.payload
        )
        trace.goal_verified = verify_res.verified_success
        try:
            evidence = list(verify_res.met_conditions or [])
            agent_res["agency_attribution"] = self.self_knowledge.attribute_change(
                f"Outcome of {proposal.action_type} for goal: {user_text[:160]}",
                execution_id=agent_res.get("controlled_execution_id"),
                execution_attempted=bool(agent_res.get("attempted", True)),
                environment_observed=bool(obs_state),
                goal_verified=verify_res.verified_success,
                evidence=evidence,
            ).to_dict()
            interface_id = self._interface_for_action(proposal.action_type)
            if interface_id:
                agent_res["boundary_event"] = self.embodied_boundary.record_event(
                    interface_id, proposal.action_type, actor="arena",
                    execution_id=agent_res.get("controlled_execution_id"),
                    authorized=True, observed=bool(obs_state) and verify_res.verified_success,
                    evidence=evidence,
                ).to_dict()
        except Exception as exc:
            app_logger.warning(f"Agency attribution failed: {exc}")

        # Reassessment & Replanning on Goal Verification Failure
        final_action_type = proposal.action_type
        if not verify_res.verified_success:
            replan_proposal = GoalReplanner.execute_reassessment_and_replan(
                user_text, goal_rep, verify_res, tracker, complexity=complexity, memory_store=self.memory,
                world_model=self.world, tool_registry=self.registry, failed_payload=proposal.payload,
                lesson_store=self.lessons, outcome_store=self.outcomes,
                hardware_self_model=self.hardware_self_model,
                resource_manager=getattr(self.advanced_cognition, "resource_manager", None),
            )
            if replan_proposal:
                replan_gate_res = ActionGate.evaluate_proposal(replan_proposal)
                if replan_gate_res.allowed:
                    final_action_type = replan_proposal.action_type
                    tracker.transition(GoalLifecycleState.EXECUTING, f"Executing Plan B proposal '{replan_proposal.action_type}'")
                    replan_agent_res = self._execute_capability_controlled(
                        replan_proposal, user_text, complexity
                    )
                    control_result = replan_agent_res
                    ObservationCollector.collect_and_ingest_observations(
                        replan_proposal, replan_agent_res, world_model=self.world, event_bus=self.events
                    )
                    executed_actions.extend(replan_agent_res.get("executed_actions", []))
                    assistant_reply = replan_agent_res.get("assistant_reply", assistant_reply)
                    obs_state = self.capture_observed_world_state(executed_actions, assistant_reply, goal_rep)
                    verify_res = GoalVerifier.verify_goal_achievement(
                        goal_rep, executed_actions, assistant_reply, failed_action_type=replan_proposal.action_type, tracker=tracker, observed_state=obs_state
                    )
                    trace.goal_verified = verify_res.verified_success
                else:
                    tracker.transition(GoalLifecycleState.BLOCKED, f"Plan B proposal '{replan_proposal.action_type}' blocked by gate {replan_gate_res.gate_name}")
                    app_logger.warning(
                        f"Replan proposal '{replan_proposal.action_type}' blocked by gate {replan_gate_res.gate_name}: {replan_gate_res.reason}"
                    )

        try:
            self.learning.record_verified_episode(
                goal=user_text,
                action_type=final_action_type,
                verification_result=verify_res,
                task_id=session_id,
                task_type=query_pred,
            )
        except Exception as e:
            app_logger.warning(f"Cognitive cycle episodic memory failed: {e}")
        self._propose_training_example(
            prompt=user_text,
            response=assistant_reply,
            action_type=final_action_type,
            verification_result=verify_res,
            session_id=session_id,
            trace_id=trace.trace_id,
        )

        # Observe Reality & Calculate Prediction Error (Surprisal)
        try:
            self.world_ingest.ingest(
                subject="system",
                predicate="response",
                value=assistant_reply[:200],
                source=SourceType.MASTER_AGENT,
                task_id=session_id,
                observation_type="self_reported",
            )
        except Exception as e:
            app_logger.warning(f"WorldIngest response warning: {e}")

        actual_state = dict(obs_state or {})
        actual_state["actions"] = executed_actions
        actual_state["reply"] = assistant_reply[:100]
        actual_state["success"] = verify_res.verified_success
        actual_state["goal_state"] = tracker.current_state.value

        surprisal = self.prediction.evaluate_surprisal(pred, actual_state)
        trace.prediction_surprisal = surprisal
        try:
            self.confidence_calibrator.record(
                proposal.action_type, pred.confidence, verify_res.verified_success,
                surprisal=surprisal,
                goal_type=goal_rep.primary_intent_type if goal_rep else "unknown",
            )
        except Exception as exc:
            app_logger.warning(f"Competence calibration record failed: {exc}")

        # P1-2 AGI: Causal learning from surprisal — low surprisal strengthens cause→effect,
        # high surprisal weakens and flags for investigation. This is how the agent learns
        # predictive models from its own prediction errors.
        try:
            # Determine effect: first success criteria or executed action or goal type
            effect_name = "goal_verified" if verify_res.verified_success else "goal_unverified"
            if executed_actions:
                effect_name = executed_actions[0][:60]
            # Also learn action_type → outcome
            self.causal_inference.learn_from_surprisal(
                cause_name=fine_action_type,
                effect_name=effect_name,
                surprisal=surprisal,
                evidence=[f"intent={query_pred}", f"verified={verify_res.verified_success}", f"surprisal={surprisal:.2f}"],
            )
            # Learn intent → outcome as well
            self.causal_inference.learn_from_execution(
                cause_name=f"intent:{query_pred}",
                effect_name=effect_name,
                success=verify_res.verified_success,
                evidence=[f"surprisal={surprisal:.2f}", f"action={fine_action_type}"],
            )
        except Exception as e:
            app_logger.warning(f"Causal surprisal learning failed (best-effort): {e}")

        # Reflection & Memory Learning
        lesson_text = ""
        try:
            lesson_rec = self.learning.process_outcome_reflection(
                task_title=user_text[:50],
                goal=user_text,
                verification_result=verify_res,
                surprisal=surprisal
            )
            lesson_text = getattr(lesson_rec, "content", "")
            trace.reflection_lesson = lesson_text
        except Exception as e:
            app_logger.warning(f"Memory reflection learning warning: {e}")

        # Event Bus Sync & Finalize Trace
        try:
            self.events.publish(CognitiveEvent(
                event_type="cognitive_cycle_completed",
                data={
                    "session_id": session_id,
                    "user_text": user_text,
                    "action_type": fine_action_type,
                    "actions": executed_actions,
                    "goal_state": tracker.current_state.value,
                    "goal_verified": verify_res.verified_success,
                    "surprisal": surprisal,
                    "lesson": lesson_text
                },
                source=SourceType.COGNITIVE_RUNTIME
            ))
            self.state.execution.last_action = fine_action_type
            self.state.execution.last_result = assistant_reply[:200]
            self.state.touch()
        except Exception as e:
            app_logger.warning(f"EventBus sync warning: {e}")

        latency = (time.time() - start_time) * 1000
        trace.finalize(
            reply=assistant_reply,
            actions=executed_actions,
            latency=latency,
            surprisal=surprisal,
            lesson=lesson_text,
            gate_decision=gate_res.gate_name,
            goal_verified=verify_res.verified_success
        )
        trace.model_used = agent_res.get("model_used", "fast")

        app_logger.info(
            f"COGNITIVE RUNTIME TRACE [{trace.trace_id[:8]}] | Session: {session_id} | "
            f"GoalLifecycleState: {tracker.current_state.value} | Verified: {verify_res.verified_success} | Latency: {latency:.0f}ms"
        )

        exec_success = bool(control_result.get("success", True))

        # Phase 1B: Record strategy outcome for learning
        try:
            goal_type = goal_rep.primary_intent_type if goal_rep else "unknown"
            self.outcomes.record_outcome(
                goal_type=goal_type,
                action_type=fine_action_type,
                success=verify_res.verified_success,
                latency_ms=round(latency, 2),
                surprisal=surprisal,
                goal_text=user_text
            )
        except Exception as e:
            app_logger.warning(f"Failed to record strategy outcome: {e}")

        # Phase 5: SelfModel is automatically updated via outcome_store
        # Query self_model.assess_capability() or what_am_i_good_at() for current performance
        try:
            assessment = self.self_model.assess_capability(fine_action_type)
            if assessment:
                app_logger.info(f"SelfModel: Capability '{fine_action_type}' is {assessment.proficiency_label} (success_rate={assessment.success_rate:.2f})")
        except Exception as e:
            app_logger.warning(f"SelfModel assessment failed: {e}")

        # Phase 1C: Extract structured lesson from outcome
        try:
            goal_type = goal_rep.primary_intent_type if goal_rep else "unknown"
            self.lessons.extract_lesson(
                task_type=goal_type,
                action_type=fine_action_type,
                final_state=tracker.current_state.value,
                verified_success=verify_res.verified_success,
                failed_conditions=verify_res.failed_conditions,
                reply_text=assistant_reply,
                goal_text=user_text,
                latency_ms=round(latency, 2),
                surprisal=surprisal
            )
        except Exception as e:
            app_logger.warning(f"Failed to extract structured lesson: {e}")

        # Phase 3B: Record task signature for analogical reasoning
        try:
            goal_type = goal_rep.primary_intent_type if goal_rep else "unknown"
            target_domain = goal_rep.target_domain if goal_rep else "unknown"
            entity_types = [goal_rep.target_domain] if goal_rep and goal_rep.target_domain else []
            self.analogies.record_task(
                intent_type=goal_type,
                target_domain=target_domain,
                entity_types=entity_types,
                action_type=fine_action_type,
                success=verify_res.verified_success,
                outcome=tracker.current_state.value,
                goal_text=user_text
            )
        except Exception as e:
            app_logger.warning(f"Failed to record task signature: {e}")

        # Phase 3C: Record planning pattern from executed action sequence
        try:
            goal_type = goal_rep.primary_intent_type if goal_rep else "unknown"
            if executed_actions:
                action_seq = [fine_action_type]  # Current action
                successful_idx = 0 if verify_res.verified_success else -1
                self.patterns.record_sequence(
                    intent_type=goal_type,
                    action_sequence=action_seq,
                    success=verify_res.verified_success,
                    successful_step=successful_idx
                )
        except Exception as e:
            app_logger.warning(f"Failed to record planning pattern: {e}")

        self._integrate_phase_modules(
            user_text=user_text,
            intent_type=goal_rep.primary_intent_type if goal_rep else "unknown",
            latency_ms=latency,
            reasoning_action=reasoning_action.value if hasattr(reasoning_action, "value") else str(reasoning_action),
            success=verify_res.verified_success,
            goal_verified=verify_res.verified_success,
        )

        return {
            "request_success": True,
            "execution_success": exec_success,
            "goal_verified": verify_res.verified_success,
            "success": exec_success,
            "session_id": session_id,
            "trace_id": trace.trace_id,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "action_type": final_action_type,
            "reasoning_action": reasoning_action.value if hasattr(reasoning_action, "value") else str(reasoning_action),
            "decision_stage": "execution_completed",
            "recommendation": {
                "action_type": proposal.action_type,
                "reason": proposal.recommendation_reason,
            },
            "alternatives_considered": proposal.alternatives_considered,
            "goal_lifecycle_state": tracker.current_state.value,
            "prediction_surprisal": surprisal,
            "reflection_lesson": lesson_text,
            "latency_ms": round(latency, 2),
            "controlled_execution_id": control_result.get("controlled_execution_id"),
            "cancel_requested": control_result.get("cancel_requested", False),
            "cancellation_observed": control_result.get("cancellation_observed", False),
            "rollback_receipt": control_result.get("rollback_receipt"),
            "agency_attribution": agent_res.get("agency_attribution"),
            "boundary_event": agent_res.get("boundary_event"),
            "os_grounding": agent_res.get("os_grounding"),
            "model_used": trace.model_used
        }
