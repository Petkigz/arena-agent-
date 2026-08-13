import time
from typing import Optional
from app.cognition.trace import CognitiveTrace
from app.agents.master_agent import MasterAgentOrchestrator
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.logger import app_logger

class CognitivePipeline:
    """
    The unified entrypoint for all user requests.
    Currently wraps the MasterAgentOrchestrator to enforce tracing and resource awareness.
    """
    
    @staticmethod
    def process_chat(user_text: str, complexity: str = "fast", session_id: Optional[str] = None) -> dict:
        start_time = time.time()
        
        # 1. Initialize Trace
        trace = CognitiveTrace(
            user_input=user_text,
            complexity_requested=complexity,
            session_id=session_id
        )
        
        # 2. Snapshot Resources (Hardware Awareness)
        try:
            hw_stats = HardwareMonitor.get_hardware_stats()
            trace.vram_pressure_at_start = hw_stats.get("vram_used_percent", 0.0)
            trace.ram_pressure_at_start = hw_stats.get("ram_used_percent", 0.0)
        except Exception as e:
            app_logger.warning(f"Pipeline: Could not snapshot hardware stats: {e}")

        # 3. Execute via existing Orchestrator (The "Body")
        try:
            agent_res = MasterAgentOrchestrator.process_user_task(user_text, complexity=complexity)
        except Exception as e:
            app_logger.error(f"Pipeline: MasterAgentOrchestrator failed: {e}")
            agent_res = {
                "assistant_reply": "I encountered an internal error processing that request.",
                "model_used": "error",
                "executed_actions": []
            }

        # 4. Finalize Trace
        latency = (time.time() - start_time) * 1000
        trace.finalize(
            reply=agent_res.get("assistant_reply", ""),
            actions=agent_res.get("executed_actions", []),
            latency=latency
        )
        trace.model_used = agent_res.get("model_used", "unknown")
        
        # 5. Log/Persist Trace
        app_logger.info(f"TRACE [{trace.trace_id[:8]}] | Route: {trace.route_chosen} | "
                        f"Model: {trace.model_used} | Latency: {trace.latency_ms:.0f}ms | "
                        f"VRAM: {trace.vram_pressure_at_start}%")

        # 6. Return standard format expected by main.py
        return {
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "assistant_reply": trace.assistant_reply,
            "model_used": trace.model_used,
            "executed_actions": trace.actions_executed
        }
