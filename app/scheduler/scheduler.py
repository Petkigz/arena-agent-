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

    @classmethod
    def shutdown(cls, wait: bool = False) -> bool:
        """Stop the scheduler when the owner shuts the system down (8.9).

        Shutdown-cooperation contract: background work must not outlive the
        shutdown request — a killed process must never leave the autonomous
        cycle running or dying mid-job at interpreter exit. Only an EXISTING
        scheduler is stopped: a shutdown path that lazily CREATES a scheduler
        thread would be the opposite of cooperation. Idempotent; the instance
        reference is cleared first so a later get_scheduler() starts a fresh
        scheduler with no stale jobs.
        """
        sched = cls._scheduler
        if sched is None:
            return False
        cls._scheduler = None
        try:
            sched.shutdown(wait=wait)
            app_logger.info(
                "Proactive Background Task Scheduler stopped (shutdown cooperation).")
            return True
        except Exception as e:  # noqa: BLE001 — a broken scheduler must not block exit
            app_logger.warning(f"Scheduler shutdown encountered an error (continuing): {e}")
            return False

scheduler_engine = ProactiveScheduler.get_scheduler()
