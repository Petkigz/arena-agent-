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
    def schedule_recurring(cls, job_id: str, func, interval_seconds: int) -> bool:
        """
        Register (or replace) a recurring background job.

        Returns True if the job was scheduled successfully.
        """
        sched = cls.get_scheduler()
        try:
            sched.add_job(
                func,
                "interval",
                seconds=interval_seconds,
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            audit_logger.info(f"Scheduled recurring job '{job_id}' every {interval_seconds}s")
            return True
        except Exception as e:
            app_logger.warning(f"Failed to schedule recurring job '{job_id}': {e}")
            return False

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
