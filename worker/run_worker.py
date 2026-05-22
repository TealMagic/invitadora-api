import logging
import time
import uuid

from app.core.config import get_settings
from app.core.logging import log_extra, setup_logging
from app.db.repositories import JobRepository
from app.db.session import SessionLocal
from app.services.worker_service import WorkerService

logger = logging.getLogger(__name__)


def run_once() -> bool:
    settings = get_settings()
    db = SessionLocal()
    try:
        jobs = JobRepository(db)
        lock_token = str(uuid.uuid4())
        job = jobs.claim_next(lock_token)
        if not job:
            return False
        log_extra(logger, logging.INFO, "job_claimed", job_id=str(job.id))
        worker = WorkerService(db)
        try:
            worker.process_job(job)
            log_extra(logger, logging.INFO, "job_completed", job_id=str(job.id))
        except Exception as e:
            jobs.mark_failed(job, str(e), retry=True)
            log_extra(logger, logging.ERROR, "job_failed", job_id=str(job.id), detail=str(e))
        return True
    finally:
        db.close()


def main() -> None:
    settings = get_settings()
    setup_logging(service="worker", level=settings.log_level)
    log_extra(logger, logging.INFO, "worker_started", detail=f"poll={settings.worker_poll_seconds}s")
    while True:
        processed = run_once()
        if not processed:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
