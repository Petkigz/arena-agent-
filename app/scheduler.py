from typing import List, Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from app.utils.logger import app_logger, audit_logger

class ProactiveScheduler:
    _scheduler: Optional[BackgroundScheduler] = None

    @classmethod
    def get_scheduler(cls) -> BackgroundScheduler:
        if cls._scheduler is None:
            cls._scheduler = BackgroundScheduler(daemon=True)
            cls._scheduler.start()
            app_logger.info("Proactive Background Task Scheduler started.")
        return cls._scheduler

    @classmethod
    def list_jobs(cls) -> List[Dict[str, Any]]:
        sched = cls.get_scheduler()
        jobs = []
        for j in sched.get_jobs():
            jobs.append({
                "id": j.id,
                "name": j.name,
                "next_run": str(j.next_run_time) if j.next_run_time else "Paused"
            })
        return jobs

    @classmethod
    def remove_job(cls, job_id: str) -> bool:
        sched = cls.get_scheduler()
        try:
            sched.remove_job(job_id)
            audit_logger.info(f"Removed background job '{job_id}'")
            return True
        except Exception:
            return False

scheduler_engine = ProactiveScheduler.get_scheduler()
