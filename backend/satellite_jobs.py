"""Bounded, process-local satellite jobs for a single API worker."""
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
import time
import uuid
import copy

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="satellite")
_LOCK = RLock()
_JOBS = {}
TTL_SECONDS = 3600
MAX_JOBS = 16


def _prune():
    now = time.time()
    for key, value in list(_JOBS.items()):
        if value["status"] in {"SUCCEEDED", "FAILED"} and now - value["updated_at"] > TTL_SECONDS:
            del _JOBS[key]
    while len(_JOBS) >= MAX_JOBS:
        key = next((k for k, v in _JOBS.items() if v["status"] in {"SUCCEEDED", "FAILED"}), None)
        if key is None:
            break
        del _JOBS[key]


def get(job_id):
    with _LOCK:
        _prune()
        return copy.deepcopy(_JOBS.get(job_id))


def submit(location_id, operation, work):
    with _LOCK:
        _prune()
        if any(v["status"] in {"QUEUED", "RUNNING"} for v in _JOBS.values()):
            raise RuntimeError("Satellite processing is busy. Try again after the current job completes.")
        job_id = uuid.uuid4().hex
        now = time.time()
        _JOBS[job_id] = {"job_id": job_id, "location_id": location_id, "operation": operation,
                         "status": "QUEUED", "stage": "Waiting to start", "created_at": now, "updated_at": now}

        def update(**fields):
            with _LOCK:
                _JOBS[job_id].update(fields, updated_at=time.time())

        def run():
            update(status="RUNNING")
            try:
                result = work(lambda stage: update(stage=stage))
                update(status="SUCCEEDED", stage="Complete", result=result)
            except (RuntimeError, ValueError) as exc:
                update(status="FAILED", stage="Stopped", error=str(exc))
            except Exception:
                update(status="FAILED", stage="Stopped", error="Satellite processing failed. Check server logs and retry.")
                import logging
                logging.exception("Satellite job failed")

        _POOL.submit(run)
        return copy.deepcopy(_JOBS[job_id])
