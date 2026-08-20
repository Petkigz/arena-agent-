"""Unit P1-A: Canonical CognitiveRuntime Composition Root Integration."""

from __future__ import annotations
import re
import uuid
import time
import threading
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
        self.learning = MemoryLearner(self.memory)
        self.attention = AttentionManager()
        self.prediction = PredictionEngine()
        self.counterfactual = CounterfactualSimulator()
        self.registry = ToolRegistry(event_bus=self.events)
        # Phase 1B: Strategy outcome tracking for learning from experience
        from app.cognition.strategy_outcomes import StrategyOutcomeStore
        self.outcomes = StrategyOutcomeStore(db_path=path)
        # Phase 1C: Structured lesson extraction and behavior change
        from app.cognition.structured_lessons import LessonStore
        self.lessons = LessonStore(db_path=path)
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
            user_text, complexity=complexity, goal_rep=goal_rep, memory_store=self.memory, world_model=self.world, tool_registry=self.registry
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
            
            # Evaluate and auto-approve high-value goals
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
            "system.probe"
        }

        registered_tools = set(self.registry._registry.keys())

        # WorldModel active capabilities
        wm_caps = set()
        try:
            caps_entities = self.world.find_entities(entity_type="capability")
            wm_caps = {c.name.lower().replace(" ", "_") for c in caps_entities}
        except Exception as e:
            app_logger.warning(f"Could not read WorldModel capabilities: {e}")

        for cap in required_capabilities:
            cap_clean = cap.lower().strip()

            # 1. Device-specific probe check (e.g. ADB phone controller)
            if any(k in cap_clean for k in ["phone", "adb"]):
                try:
                    from app.tools.android_adb_controller import AndroidADBController
                    cap_map[cap] = AndroidADBController.is_adb_available()
                except Exception:
                    cap_map[cap] = False

            # 2. Check native capability list
            elif any(cap_clean == nc or cap_clean in nc or nc in cap_clean for nc in NATIVE_CAPABILITIES):
                cap_map[cap] = True

            # 3. Check ToolRegistry registered tools
            elif any(rt in cap_clean or cap_clean in rt for rt in registered_tools):
                cap_map[cap] = True

            # 4. Check WorldModel dynamic capabilities synthesized by CapabilityFactory
            elif any(wc in cap_clean or cap_clean in wc for wc in wm_caps):
                cap_map[cap] = True

            # 5. Unsupported / Unknown capability -> FALSE
            else:
                cap_map[cap] = False

        return cap_map

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

        Each module contributes a non-fatal, best-effort observation: failures are logged
        but never interrupt the cycle. This is what turns the previously-orphaned modules
        (causal inference, strategic planning, social/cultural cognition, metacognition,
        consciousness, embodied cognition, cross-domain transfer, creative generation)
        into live parts of the closed loop.

        Write-path modules *learn* from this cycle; read-path modules expose self-knowledge
        onto the blackboard so subsequent reasoning can consult the agent's own state.
        """
        try:
            from app.cognition.metacognitive_monitor import CognitiveProcess, ReasoningStrategy
            self.metacognitive_monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.ABDUCTIVE,
                input_data={"user_text": user_text[:200], "intent": intent_type},
                output_data={"reasoning_action": reasoning_action, "success": success},
                execution_time_ms=round(latency_ms, 2),
                confidence=0.7,
                success=success,
                errors=[] if success else [f"Cycle ended in state '{reasoning_action}' without success"],
            )
        except Exception as e:
            app_logger.warning(f"Metacognitive integration failed: {e}")

        try:
            from app.cognition.causal_inference import CausalRelationType
            self.causal_inference.add_causal_relationship(
                cause_name=f"intent:{intent_type}",
                effect_name="goal_verified" if goal_verified else "goal_unverified",
                relation_type=CausalRelationType.DIRECT_CAUSE,
                strength=0.8 if goal_verified else 0.2,
                confidence=0.6,
                evidence=[user_text[:80]],
                mechanism=f"Observed outcome of '{reasoning_action}' reasoning on '{intent_type}' tasks.",
            )
        except Exception as e:
            app_logger.warning(f"Causal inference integration failed: {e}")

        try:
            self.blackboard.set(
                "strategic_overview",
                self.strategic_planning.get_strategic_overview(),
                source="strategic_planning",
            )
        except Exception as e:
            app_logger.warning(f"Strategic planning integration failed: {e}")

        try:
            self.blackboard.set(
                "transfer_summary",
                self.cross_domain_transfer.get_transfer_summary(),
                source="cross_domain_transfer",
            )
        except Exception as e:
            app_logger.warning(f"Cross-domain transfer integration failed: {e}")

        try:
            if goal_verified:
                self.blackboard.set(
                    "creativity_summary",
                    self.creative_generation.get_creativity_summary(),
                    source="creative_generation",
                )
            else:
                # On failure, generate creative alternatives for subsequent replanning.
                ideas = self.creative_generation.generate_ideas(
                    problem=user_text,
                    context={"intent": intent_type},
                    num_ideas=3,
                )
                self.blackboard.set(
                    "creative_alternatives",
                    [i.description for i in ideas],
                    source="creative_generation",
                )
        except Exception as e:
            app_logger.warning(f"Creative generation integration failed: {e}")

        try:
            from app.cognition.social_cognition import MentalState, SocialNorm
            self.social_cognition.infer_mental_state(
                agent_id="owner",
                state_type=MentalState.INTENTION,
                content=user_text[:100],
                evidence=[f"user message: {user_text[:80]}"],
                confidence=0.6,
            )
            self.social_cognition.record_interaction(
                participants=["owner", "arena"],
                interaction_type="task",
                context=user_text[:100],
                norms_followed=[SocialNorm.COOPERATION],
                norms_violated=[],
                emotional_outcomes={},
                outcome="positive" if goal_verified else "neutral",
            )
        except Exception as e:
            app_logger.warning(f"Social cognition integration failed: {e}")

        try:
            from app.cognition.consciousness_simulation import QualiaType
            self.consciousness.create_experience(
                qualia_type=QualiaType.COGNITIVE,
                content=f"Processed '{intent_type}' task ({reasoning_action})",
                intensity=0.6,
                valence=0.3 if goal_verified else -0.2,
                arousal=0.5,
                clarity=0.7,
                duration_ms=latency_ms,
                associated_thoughts=[f"intent={intent_type}", f"verified={goal_verified}"],
            )
        except Exception as e:
            app_logger.warning(f"Consciousness integration failed: {e}")

        try:
            self.blackboard.set(
                "embodied_summary",
                self.embodied_cognition.get_embodied_summary(),
                source="embodied_cognition",
            )
        except Exception as e:
            app_logger.warning(f"Embodied cognition integration failed: {e}")

        try:
            self.cultural_learning.record_observed_behavior(
                agent_id="owner",
                behavior_type=intent_type,
                description=user_text[:100],
                context="cognitive_cycle",
                outcome="success" if goal_verified else "failure",
            )
        except Exception as e:
            app_logger.warning(f"Cultural learning integration failed: {e}")

        try:
            # Phase 14: resource/multi-agent/knowledge/uncertainty self-report.
            self.blackboard.set(
                "phase14_report",
                self.advanced_cognition.get_phase14_report(),
                source="advanced_cognition",
            )
            # Phase 14: calibrate confidence against the actual outcome (learning).
            self.advanced_cognition.uncertainty_quantifier.calibrate_confidence(
                predictions=[0.7],
                actual=[1.0 if goal_verified else 0.0],
            )
        except Exception as e:
            app_logger.warning(f"Advanced cognition integration failed: {e}")

        try:
            # Phase 22: ground the utterance to perception/action/meaning.
            grounding = self.language_grounding.ground_utterance(user_text)
            self.blackboard.set("utterance_grounding", grounding, source="language_grounding")
        except Exception as e:
            app_logger.warning(f"Language grounding integration failed: {e}")

    def process_cognitive_cycle(
        self,
        user_text: str,
        complexity: str = "fast",
        session_id: Optional[str] = None
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
        self.state.task.current_step = "cognitive_cycle"
        self.state.touch()

        # 3. Blackboard Ingestion & Context Slicing (Retrieves Past Learned Lessons)
        self.blackboard.set("current_user_query", user_text, source=SourceType.USER_INPUT, confidence=1.0)
        # Phase 3: expose the hardware self-model so reasoning can consult the machine state.
        self.blackboard.set("hardware_self_model", self.hardware_self_model, source="hardware_governor")
        try:
            sliced_ctx = PromptSlicerEngine.slice_context_for_task(user_text)
            self.blackboard.set("sliced_context", sliced_ctx.compact_prompt_str, source="prompt_slicer")
        except Exception as e:
            app_logger.warning(f"PromptSlicer error: {e}")

        # 4. Semantic Goal Representation v2 & WorldModel / Belief Ingestion
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(
            user_text, complexity=complexity, memory_store=self.memory, world_model=self.world, tool_registry=self.registry
        )
        query_pred = goal_rep.primary_intent_type
        tracker.transition(GoalLifecycleState.UNDERSTOOD, f"Parsed goal in domain '{goal_rep.target_domain}'")

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
                task_id=session_id
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

            obs_state = self.capture_observed_world_state([], assistant_reply, goal_rep)
            verify_res = GoalVerifier.verify_goal_achievement(goal_rep, [], assistant_reply, tracker=tracker, observed_state=obs_state)
            trace.goal_verified = verify_res.verified_success

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
            if gate_res.requires_approval:
                tracker.transition(GoalLifecycleState.WAITING_FOR_USER, f"Action requires 1-click UI approval: {gate_res.reason}")
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
                "goal_lifecycle_state": tracker.current_state.value,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ActionGate"
            }

        # Capability Execution Layer (Executes selected ActionProposal directly without re-routing)
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing selected action strategy via capability layer.")
        from app.agents.master_agent import MasterAgentOrchestrator
        agent_res = MasterAgentOrchestrator.execute_proposal(
            proposal, user_text, complexity=complexity, world_model=self.world
        )
        executed_actions = agent_res.get("executed_actions", [])
        assistant_reply = agent_res.get("assistant_reply", "Done.")

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

        # Reassessment & Replanning on Goal Verification Failure
        if not verify_res.verified_success:
            replan_proposal = GoalReplanner.execute_reassessment_and_replan(
                user_text, goal_rep, verify_res, tracker, complexity=complexity, memory_store=self.memory, world_model=self.world, tool_registry=self.registry, failed_payload=proposal.payload
            )
            if replan_proposal:
                replan_gate_res = ActionGate.evaluate_proposal(replan_proposal)
                if replan_gate_res.allowed:
                    tracker.transition(GoalLifecycleState.EXECUTING, f"Executing Plan B proposal '{replan_proposal.action_type}'")
                    replan_agent_res = MasterAgentOrchestrator.execute_proposal(
                        replan_proposal, user_text, complexity=complexity, world_model=self.world
                    )
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

        exec_success = bool(agent_res.get("success", True)) if isinstance(agent_res, dict) else True

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
            "action_type": fine_action_type,
            "reasoning_action": reasoning_action.value if hasattr(reasoning_action, "value") else str(reasoning_action),
            "goal_lifecycle_state": tracker.current_state.value,
            "prediction_surprisal": surprisal,
            "reflection_lesson": lesson_text,
            "latency_ms": round(latency, 2),
            "model_used": trace.model_used
        }
