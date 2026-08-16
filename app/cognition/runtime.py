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

class CognitiveRuntime:
    """
    P1-A: Authoritative Single Composition Root for Arena's Cognitive Architecture.
    Wires Perception ➔ WorldModel ➔ Blackboard ➔ Beliefs ➔ Attention ➔ CognitiveReasoningLoop ➔ DecisionRouter ➔ Prediction ➔ ActionGates ➔ Capability Execution ➔ Reflection ➔ MemoryLearner.
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
        """
        Delegates semantic query predicate interpretation to SemanticGoalInterpreter.
        """
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        goal_rep = SemanticGoalInterpreter.interpret_goal(user_text)
        return goal_rep.primary_intent_type

    def generate_candidate_action_proposal(self, user_text: str, complexity: str = "fast") -> ActionProposal:
        """
        Delegates action planning and counterfactual evaluation directly to self.actions.select_action_for_query.
        """
        res = self.actions.select_action_for_query(user_text, complexity=complexity)
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
        Authoritative Closed-Loop Predictive Cognitive Cycle:
        1. Initialize Trace & Hardware Snapshot
        2. Set CognitiveState & Attention Focus Target
        3. Blackboard Ingestion & Context Budget Slicing (Retrieves Past Lessons)
        4. WorldModel Ingestion & CognitiveReasoningLoop Execution
        5. Authoritative Decision Router (ANSWER vs INVESTIGATE vs DEFER vs ACT)
        6. Fine-Grained Action Proposal & Pre-Execution Outcome Prediction
        7. Multi-Gate Verification (Policy / Resource / Prediction)
        8. Capability Execution Layer (Tool Execution or Direct Answer)
        9. Observe Reality & Calculate Prediction Error (Surprisal)
        10. Reflection & Memory Learning (ReflectionEngine ➔ MemoryLearner ➔ MemoryStore)
        """
        start_time = time.time()
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

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

        # 4. Semantic Predicate Classification & WorldModel / Belief Ingestion
        query_pred = self.classify_query_predicate(user_text)
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
            trace.belief_confidence = float(getattr(belief_res, "confidence", 1.0))
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

        # 5. DECISION ROUTER (100% Authoritative Reasoning Decision, No Keyword Overrides):
        # Branch A: ANSWER / Direct Conversational Q&A (Lazy Planning: skips action planning computation)
        if reasoning_action == ReasoningAction.ANSWER:
            system_instruction = CoworkerBrain.format_coworker_prompt(user_text)
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", "Done.")

            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=assistant_reply,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision="passed"
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
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": llm_res.get("model", "fast")
            }

        # Branch B: INVESTIGATE / Bounded Probe Evidence Gathering Loop
        elif reasoning_action == ReasoningAction.INVESTIGATE:
            investigation_summary = f"Gathered evidence from {len(loop_trace.results)} probe(s)" if loop_trace.results else "Diagnostic investigation completed."
            if loop_trace.results:
                investigation_summary += ": " + "; ".join(f"{r.tool}: {str(r.output)[:80]}" for r in loop_trace.results)

            system_instruction = CoworkerBrain.format_coworker_prompt(user_text, executed_actions=[investigation_summary])
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_text}]
            llm_res = llm_client.generate_chat_completion(messages=messages, complexity=complexity, max_tokens=150)
            assistant_reply = llm_res.get("choices", [{}])[0].get("message", {}).get("content", investigation_summary)

            # Pass investigation results through Reflection & Memory Learning Loop
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
                gate_decision="passed"
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
                "prediction_surprisal": 0.1,
                "reflection_lesson": trace.reflection_lesson,
                "latency_ms": round(latency, 2),
                "model_used": llm_res.get("model", "fast")
            }

        # Branch C: DEFER / SAFELY ASK USER
        elif reasoning_action == ReasoningAction.DEFER:
            defer_msg = f"Deferred task: {last_decision.reason if last_decision else 'Evidence is insufficient for a safe decision.'}"
            latency = (time.time() - start_time) * 1000
            trace.finalize(
                reply=defer_msg,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision="deferred"
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
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ReasoningCycle"
            }

        # Branch D: ACT / Cognitive Action Planning ➔ Counterfactual Branch Simulation ➔ ActionProposal ➔ Prediction ➔ ActionGate ➔ Capability Layer Execution
        proposal = getattr(last_decision, "proposed_action", None) or self.generate_candidate_action_proposal(user_text, complexity=complexity)
        fine_action_type = proposal.action_type
        if not proposal.predicted_outcome:
            pred = self.prediction.predict_action(proposal.action_type, proposal.payload)
            proposal.predicted_outcome = pred.expected_changes
        else:
            from app.cognition.prediction_engine import WorldPrediction
            pred = WorldPrediction(action_type=proposal.action_type, expected_changes=proposal.predicted_outcome)
        trace.predicted_outcome = proposal.predicted_outcome

        # 6. Multi-Gate Checks (Policy, Resource, Prediction) - Reuses canonical prediction
        gate_res = ActionGate.evaluate_proposal(proposal)
        trace.gate_decision = gate_res.gate_name

        if not gate_res.allowed:
            latency = (time.time() - start_time) * 1000
            blocked_msg = f"Action blocked by {gate_res.gate_name}: {gate_res.reason}"
            trace.finalize(
                reply=blocked_msg,
                actions=[],
                latency=latency,
                surprisal=0.0,
                lesson="",
                gate_decision=gate_res.gate_name
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
                "prediction_surprisal": 0.0,
                "latency_ms": round(latency, 2),
                "model_used": "ActionGate"
            }

        # 7. Capability Execution Layer (MasterAgent Capability Delegate)
        from app.agents.master_agent import MasterAgentOrchestrator
        agent_res = MasterAgentOrchestrator.process_user_task(user_text, complexity=complexity)
        executed_actions = agent_res.get("executed_actions", [])
        assistant_reply = agent_res.get("assistant_reply", "Done.")

        # 8. Observe Reality & Calculate Prediction Error (Surprisal)
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
            "success": agent_res.get("success", True)
        }
        surprisal = self.prediction.evaluate_surprisal(pred, actual_state)
        trace.prediction_surprisal = surprisal

        # 9. Reflection & Memory Learning (ReflectionEngine ➔ MemoryLearner ➔ MemoryStore)
        lesson_text = ""
        try:
            lesson_rec = self.learning.process_outcome_reflection(
                task_title=user_text[:50],
                goal=user_text,
                outcome_summary=f"Action: {fine_action_type} | Executed: {executed_actions} | Reply: {assistant_reply[:100]}",
                surprisal=surprisal
            )
            lesson_text = getattr(lesson_rec, "content", "")
            trace.reflection_lesson = lesson_text
        except Exception as e:
            app_logger.warning(f"Memory reflection learning warning: {e}")

        # 10. Event Bus Sync & Finalize Trace
        try:
            self.events.publish(CognitiveEvent(
                event_type="cognitive_cycle_completed",
                data={
                    "session_id": session_id,
                    "user_text": user_text,
                    "action_type": fine_action_type,
                    "actions": executed_actions,
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
            gate_decision=gate_res.gate_name
        )
        trace.model_used = agent_res.get("model_used", "fast")

        app_logger.info(
            f"COGNITIVE RUNTIME TRACE [{trace.trace_id[:8]}] | Session: {session_id} | "
            f"Action: {fine_action_type} | Latency: {latency:.0f}ms | Surprisal: {surprisal} | Actions: {len(executed_actions)}"
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
            "prediction_surprisal": surprisal,
            "reflection_lesson": lesson_text,
            "latency_ms": round(latency, 2),
            "model_used": trace.model_used
        }
