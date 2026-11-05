"""Queue integration. The worker process runs these jobs through RQ."""

from __future__ import annotations

import uuid

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.db import session_factory
from app.prescriptions.service import process_prescription, run_retention

QUEUE_NAME = "prescriptions"


def process_job(prescription_id: str) -> None:
    with session_factory()() as db:
        process_prescription(db, uuid.UUID(prescription_id))


def retention_job() -> dict[str, int]:
    with session_factory()() as db:
        return run_retention(db)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url))


def enqueue_processing(prescription_id: uuid.UUID) -> None:
    if get_settings().jobs_synchronous:
        process_job(str(prescription_id))
        return
    get_queue().enqueue(
        process_job, str(prescription_id), job_timeout=300, result_ttl=0, failure_ttl=3600
    )
