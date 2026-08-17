"""Unit P1-A: Canonical CognitiveRuntime Composition Root Integration."""

from __future__ import annotations
import re
import uuid
import time
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
from app.cognition.world_ingest import WorldIngestor
from app.cognition.belief_engine import BeliefEngine
from app.cognition.action_selection import ActionSelector, InvestigationExecutor
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner
from app.cognition.reflection import ReflectionEngine
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

class CognitiveRuntime:
    """
    P1-A: Authoritative Single Composition Root for Arena's Cognitive Architecture.
    Wires Perception ➔ WorldModel ➔ Blackboard ➔ Beliefs ➔ Attention ➔ CognitiveReasoningLoop ➔ DecisionRouter ➔ Prediction ➔ ActionGates ➔ Capability Execution ➔ GoalVerifier ➔ GoalReplanner ➔ Reflection ➔ MemoryLearner.
    """

    _instance: Optional[CognitiveRuntime] = None

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> CognitiveRuntime:
        if cls._instance is None:
            cls._instance = CognitiveRuntime(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: Optional[str] = None, max_steps: int = 3) -> None:
        path = db_path or str(settings.DB_PATH)
        self.state = CognitiveState()
        self.blackboard = Blackboard()
        self.events = EventBus()
        self.world = WorldModel(path)
        self.world_ingest = WorldIngestor(self.world, self.events)
        self.beliefs = BeliefEngine(db_path=path)
        self.actions = ActionSelector()
        self.executor = InvestigationExecutor()
        self.memory = MemoryStore(path)
        self.learning = MemoryLearner(self.memory)
        self.reflection = ReflectionEngine()
        self.attention = AttentionManager()
        self.prediction = PredictionEngine()
        self.counterfactual = CounterfactualSimulator()
        self.registry = ToolRegistry(event_bus=self.events)
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

    def classify_query_predicate(self, user_text: str) -> str:
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(user_text)
        return goal_rep.primary_intent_type

    def generate_candidate_action_proposal(self, user_text: str, complexity: str = "fast", goal_rep: Optional[Any] = None) -> ActionProposal:
        from app.cognition.action_planner import ActionPlanner
        res = ActionPlanner.plan_and_evaluate_action(user_text, complexity=complexity, goal_rep=goal_rep)
        if isinstance(res, ActionProposal):
            return res
        return ActionProposal(
            action_type=str(res),
            payload={"query": user_text, "complexity": complexity, "action_type": str(res)}
        )

    def classify_fine_grained_action_type(self, user_text: str) -> str:
        prop = self.generate_candidate_action_proposal(user_text)
        return prop.action_type

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
        self.blackboard.set("current_user_query", user_text, source="user_input", confidence=1.0)
        try:
            sliced_ctx = PromptSlicerEngine.slice_context_for_task(user_text)
            self.blackboard.set("sliced_context", sliced_ctx.compact_prompt_str, source="prompt_slicer")
        except Exception as e:
            app_logger.warning(f"PromptSlicer error: {e}")

        # 4. Semantic Goal Representation v2 & WorldModel / Belief Ingestion
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(user_text, complexity=complexity)
        query_pred = goal_rep.primary_intent_type
        tracker.transition(GoalLifecycleState.UNDERSTOOD, f"Parsed goal in domain '{goal_rep.target_domain}'")

        try:
            self.world_ingest.ingest(
                subject="user",
                predicate=query_pred,
                value=user_text[:200],
                source="user_input",
                task_id=session_id
            )
            belief_res = self.beliefs.ingest(
                subject="user",
                predicate=query_pred,
                value=user_text[:200],
                source="user_input",
                task_id=session_id
            )
            trace.belief_confidence = float(getattr(belief_res, "confidence", goal_rep.confidence))
        except Exception as e:
            app_logger.warning(f"WorldModel/Belief ingestion warning: {e}")

        # Run Authoritative Cognitive Reasoning Loop with semantic query_pred
        loop_trace = self.loop.run(
            subject=user_text[:30].strip() or "user_query",
            predicate=query_pred,
            value=user_text[:200],
            source="user_input",
            task_id=session_id,
            action_available=True
        )

        last_decision = loop_trace.decisions[-1] if loop_trace.decisions else None
        reasoning_action = last_decision.action if last_decision else ReasoningAction.ACT

        # 5. DECISION ROUTER:
        # Branch A: ANSWER / Direct Conversational Q&A
        if reasoning_action == ReasoningAction.ANSWER and not any(k in user_text.lower() for k in ["open", "launch", "start", "run", "search", "call", "sms", "photo", "screenshot", "briefing", "play", "find"]):
            tracker.transition(GoalLifecycleState.EXECUTING, "Formulating direct conversational answer.")
            system_instruction = CoworkerBrain.format_coworker_prompt(user_text)
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", "Done.")

            verify_res = GoalVerifier.verify_goal_achievement(goal_rep, [], assistant_reply, tracker=tracker)
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
            return {
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": assistant_reply,
                "executed_actions": [],
                "action_type": "formulate_answer",
                "reasoning_action": "answer",
                "goal_lifecycle_state": tracker.current_state.value,
                "goal_verified": verify_res.verified_success,
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
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", investigation_summary)

            verify_res = GoalVerifier.verify_goal_achievement(goal_rep, [investigation_summary], assistant_reply, tracker=tracker)
            trace.goal_verified = verify_res.verified_success

            try:
                lesson_rec = self.learning.process_outcome_reflection(
                    task_title=f"Investigation: {user_text[:30]}",
                    goal=user_text,
                    outcome_summary=investigation_summary,
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
            return {
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": assistant_reply,
                "executed_actions": [investigation_summary],
                "action_type": "investigate",
                "reasoning_action": "investigate",
                "goal_lifecycle_state": tracker.current_state.value,
                "goal_verified": verify_res.verified_success,
                "prediction_surprisal": 0.1,
                "reflection_lesson": trace.reflection_lesson,
                "latency_ms": round(latency, 2),
                "model_used": llm_res.get("model", "fast")
            }

        # Branch C: DEFER / SAFELY ASK USER
        elif reasoning_action == ReasoningAction.DEFER:
            tracker.transition(GoalLifecycleState.FAILED, "Evidence is insufficient for a safe decision.")
            defer_msg = f"Deferred task: {last_decision.reason if last_decision else 'Evidence is insufficient for a safe decision.'}"
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
            return {
                "success": True,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": defer_msg,
                "executed_actions": [],
                "action_type": "defer",
                "reasoning_action": "defer",
                "goal_lifecycle_state": tracker.current_state.value,
                "goal_verified": False,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ReasoningCycle"
            }

        # Branch D: ACT / Action Strategy Simulation ➔ ActionProposal ➔ Prediction ➔ ActionGate ➔ Capability Execution
        tracker.transition(GoalLifecycleState.PLANNED, "Simulated candidate branches with CounterfactualSimulator.")
        proposal = getattr(last_decision, "proposed_action", None) or self.generate_candidate_action_proposal(user_text, complexity=complexity, goal_rep=goal_rep)
        fine_action_type = proposal.action_type

        if not proposal.predicted_outcome:
            pred = self.prediction.predict_action(proposal.action_type, proposal.payload)
            proposal.predicted_outcome = pred.expected_changes
        else:
            from app.cognition.prediction_engine import WorldPrediction
            pred = WorldPrediction(action_type=proposal.action_type, expected_changes=proposal.predicted_outcome)
        trace.predicted_outcome = proposal.predicted_outcome

        # Multi-Gate Checks (Policy, Resource, Prediction)
        gate_res = ActionGate.evaluate_proposal(proposal)
        trace.gate_decision = gate_res.gate_name

        if not gate_res.allowed:
            tracker.transition(GoalLifecycleState.FAILED, f"Action blocked by {gate_res.gate_name}")
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
            return {
                "success": False,
                "session_id": session_id,
                "trace_id": trace.trace_id,
                "user_text": user_text,
                "assistant_reply": blocked_msg,
                "executed_actions": [],
                "requires_approval": gate_res.requires_approval,
                "gate_blocked": gate_res.gate_name,
                "goal_lifecycle_state": tracker.current_state.value,
                "goal_verified": False,
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ActionGate"
            }

        # Capability Execution Layer (Executes selected ActionProposal directly without re-routing)
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing selected action strategy via capability layer.")
        from app.agents.master_agent import MasterAgentOrchestrator
        agent_res = MasterAgentOrchestrator.execute_proposal(proposal, user_text, complexity=complexity)
        executed_actions = agent_res.get("executed_actions", [])
        assistant_reply = agent_res.get("assistant_reply", "Done.")

        # Goal Verification
        verify_res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, assistant_reply, failed_action_type=proposal.action_type, tracker=tracker)
        trace.goal_verified = verify_res.verified_success

        # Reassessment & Replanning on Goal Verification Failure
        if not verify_res.verified_success:
            replan_proposal = GoalReplanner.execute_reassessment_and_replan(user_text, goal_rep, verify_res, tracker, complexity=complexity)
            if replan_proposal:
                replan_gate_res = ActionGate.evaluate_proposal(replan_proposal)
                if replan_gate_res.allowed:
                    replan_agent_res = MasterAgentOrchestrator.execute_proposal(replan_proposal, user_text, complexity=complexity)
                    executed_actions.extend(replan_agent_res.get("executed_actions", []))
                    assistant_reply = replan_agent_res.get("assistant_reply", assistant_reply)
                    verify_res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, assistant_reply, failed_action_type=replan_proposal.action_type, tracker=tracker)
                    trace.goal_verified = verify_res.verified_success
                assistant_reply = replan_agent_res.get("assistant_reply", assistant_reply)
                verify_res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, assistant_reply, tracker=tracker)
                trace.goal_verified = verify_res.verified_success

        # Observe Reality & Calculate Prediction Error (Surprisal)
        try:
            self.world_ingest.ingest(
                subject="system",
                predicate="response",
                value=assistant_reply[:200],
                source="master_agent",
                task_id=session_id
            )
        except Exception as e:
            app_logger.warning(f"WorldIngest response warning: {e}")

        actual_state = {
            "actions": executed_actions,
            "reply": assistant_reply[:100],
            "app_state": "running",
            "success": verify_res.verified_success
        }
        surprisal = self.prediction.evaluate_surprisal(pred, actual_state)
        trace.prediction_surprisal = surprisal

        # Reflection & Memory Learning
        lesson_text = ""
        try:
            lesson_rec = self.learning.process_outcome_reflection(
                task_title=user_text[:50],
                goal=user_text,
                outcome_summary=f"Action: {fine_action_type} | Executed: {executed_actions} | Verified: {verify_res.verified_success}",
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
                source="cognitive_runtime"
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

        return {
            "success": True,
            "session_id": session_id,
            "trace_id": trace.trace_id,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "action_type": fine_action_type,
            "reasoning_action": reasoning_action.value if hasattr(reasoning_action, "value") else str(reasoning_action),
            "goal_lifecycle_state": tracker.current_state.value,
            "goal_verified": verify_res.verified_success,
            "prediction_surprisal": surprisal,
            "reflection_lesson": lesson_text,
            "latency_ms": round(latency, 2),
            "model_used": trace.model_used
        }
