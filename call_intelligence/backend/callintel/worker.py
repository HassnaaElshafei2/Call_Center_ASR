"""Background worker: runs queued jobs (transcription, analysis, search indexing).

    python -m callintel.worker
"""
import logging
import signal
import threading
import time
import traceback

from .config import settings
from .db import engine, session_scope
from .models import Call
from .services import jobs
from .services.pipeline import HANDLERS

log = logging.getLogger("callintel.worker")
stop = threading.Event()


def run_one() -> bool:
    with session_scope() as db:
        job = jobs.claim(db)
        if not job:
            return False
        kind, payload, jid = job.kind, dict(job.payload), job.id
    log.info("job %s %s %s", jid, kind, payload)
    err = None
    try:
        with session_scope() as db:
            HANDLERS[kind](db, **payload)
    except Exception as e:                       # noqa: BLE001 - every failure is recorded on the job
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
        log.warning("job %s failed: %s", jid, e)
    with session_scope() as db:
        from .models import Job
        job = db.get(Job, jid)
        jobs.finish(db, job, err)
        if err and job.status == "failed" and payload.get("call_id"):
            call = db.get(Call, payload["call_id"])
            if call:
                call.status, call.status_detail = "failed", err.split("\n")[0][:500]
    return True


def loop():
    while not stop.is_set():
        try:
            if not run_one():
                stop.wait(settings().worker_poll_s)
        except Exception:                        # noqa: BLE001 - keep the worker alive (database restarts, ...)
            log.exception("worker loop error")
            stop.wait(5)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    threads = [threading.Thread(target=loop, daemon=True) for _ in range(settings().worker_concurrency)]
    for t in threads:
        t.start()
    log.info("worker started with %d threads", len(threads))
    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
    for t in threads:
        t.join(timeout=30)


if __name__ == "__main__":
    main()
