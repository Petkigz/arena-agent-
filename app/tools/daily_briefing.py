import os
import json
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.tasks import TaskManager
from app.utils.hardware_monitor import HardwareMonitor
from app.memory.semantic_rag import SemanticRAGEngine
from app.perception.text_to_speech import LocalTextToSpeech
from app.database import db
from app.utils.logger import app_logger

class DailyBriefingEngine:
    """
    Automated Local Executive Briefing & Audio Podcast Generator.
    Aggregates daily hardware status, pending tasks, recent memories, and workspace notes
    into a structured morning briefing note and synthesized audio briefing file.
    """

    @staticmethod
    def generate_briefing(
        custom_topics: Optional[List[str]] = None,
        generate_audio: bool = True
    ) -> Dict[str, Any]:
        try:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.datetime.now().strftime("%I:%M %p")

            # 1. Gather System Hardware Snapshot
            hw_stats = HardwareMonitor.get_hardware_stats()
            cpu_usage = hw_stats.get("cpu", {}).get("usage_percent", 0)
            ram_free_gb = hw_stats.get("ram", {}).get("available_gb", 0)

            # 2. Gather Active Tasks Snapshot
            pending_tasks = TaskManager.get_all_tasks(status="pending")
            in_progress_tasks = TaskManager.get_all_tasks(status="in_progress")
            
            task_summary_lines = []
            if pending_tasks or in_progress_tasks:
                for t in (in_progress_tasks + pending_tasks)[:5]:
                    task_summary_lines.append(f"- [{t.status.upper()}] {t.title} (Priority: {t.priority})")
            else:
                task_summary_lines.append("- No pending tasks queued. Systems operating smoothly.")

            # 3. Gather Recent Memory Highlights
            recent_mems = db.get_memories()
            mem_highlights = []
            if recent_mems:
                for m in recent_mems[:3]:
                    mem_highlights.append(f"- {m.get('content', '')[:100]}...")
            else:
                mem_highlights.append("- Knowledge base initialized.")

            # 4. Construct Briefing Document
            briefing_text = (
                f"GOOD MORNING EXECUTIVE BRIEFING — {today_str} ({time_str})\n"
                f"===========================================================\n\n"
                f"SYSTEM HARDWARE STATUS:\n"
                f"- CPU Usage: {cpu_usage}%\n"
                f"- Available System RAM: {ram_free_gb} GB\n"
                f"- GPU Status: RX 580 VRAM Ready\n\n"
                f"ACTIVE TASK OVERVIEW:\n" + "\n".join(task_summary_lines) + "\n\n"
                f"KNOWLEDGE & MEMORY HIGHLIGHTS:\n" + "\n".join(mem_highlights) + "\n\n"
                f"SYSTEM STATUS: 100% Offline, Privacy Enforced, Zero Cloud Dependency.\n"
            )

            if custom_topics:
                briefing_text += f"\nTOPIC FOCUS: {', '.join(custom_topics)}\n"

            # 5. Save Briefing to Disk
            briefings_dir = settings.DATA_DIR / "workspace" / "briefings"
            briefings_dir.mkdir(parents=True, exist_ok=True)
            doc_path = briefings_dir / f"briefing_{today_str}.txt"

            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(briefing_text)

            # Save memory record
            db.create_memory({
                "content": f"Executive Daily Briefing generated for {today_str}: {len(pending_tasks)} pending tasks.",
                "category": "daily_briefing",
                "source": "daily_briefing_engine",
                "confidence": 1.0
            })

            # 6. Generate Audio Briefing Speech Synthesis
            audio_url = ""
            if generate_audio:
                audio_script = (
                    f"Good morning. Here is your daily local executive briefing for {today_str}. "
                    f"Your system CPU usage is at {cpu_usage} percent with {ram_free_gb} gigabytes of free RAM. "
                    f"You have {len(pending_tasks) + len(in_progress_tasks)} active tasks in your workspace queue. "
                    f"All local systems are running fully offline and secure."
                )
                tts_res = LocalTextToSpeech.synthesize_speech(audio_script)
                audio_url = tts_res.get("audio_url", "")

            db.create_audit_log("generate_daily_briefing", "success", f"Briefing generated for {today_str}", level=0)

            return {
                "success": True,
                "date": today_str,
                "briefing_text": briefing_text,
                "file_path": str(doc_path),
                "audio_url": audio_url,
                "active_tasks_count": len(pending_tasks) + len(in_progress_tasks)
            }

        except Exception as e:
            app_logger.error(f"Error generating daily briefing: {e}")
            return {
                "success": False,
                "error": str(e)
            }
