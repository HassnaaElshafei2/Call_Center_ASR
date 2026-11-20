"""A small job queue in PostgreSQL. Workers claim jobs with FOR UPDATE SKIP LOCKED, so several can run safely."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job

STALE_AFTER = timedelta(minutes=15)       # a job locked longer than this was abandoned by a crashed worker


def enqueue(db: Session, kind: str, payload: dict, delay_s: float = 0, max_attempts: int = 3) -> Job:
    job = Job(kind=kind, payload=payload, max_attempts=max_attempts,
              run_after=datetime.now(timezone.utc) + timedelta(seconds=delay_s))
    db.add(job)
    return job


def claim(db: Session, kinds: list[str] | None = None) -> Job | None:
    now = datetime.now(timezone.utc)
    # give abandoned jobs back
    for j in db.execute(select(Job).where(Job.status == "running", Job.locked_at < now - STALE_AFTER)
                        .with_for_update(skip_locked=True)).scalars():
        j.status, j.locked_at = "pending", None
    q = select(Job).where(Job.status == "pending", Job.run_after <= now)
    if kinds:
        q = q.where(Job.kind.in_(kinds))
    job = db.execute(q.order_by(Job.run_after, Job.id).limit(1).with_for_update(skip_locked=True)).scalar_one_or_none()
    if job:
        job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
    db.commit()
    return job


def finish(db: Session, job: Job, error: str | None = None, retry_in_s: float = 60):
    if error is None:
        job.status, job.error = "done", ""
    elif job.attempts < job.max_attempts:
        job.status, job.error = "pending", error[-2000:]
        job.run_after = datetime.now(timezone.utc) + timedelta(seconds=retry_in_s * job.attempts)
    else:
        job.status, job.error = "failed", error[-2000:]
    job.locked_at = None
    db.commit()
