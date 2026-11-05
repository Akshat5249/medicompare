"""Scheduled jobs: run retention at start-up, then hourly."""

import json
import time

from app.jobs import retention_job

INTERVAL_SECONDS = 3600

if __name__ == "__main__":
    while True:
        try:
            print(json.dumps({"event": "retention_run", **retention_job()}), flush=True)
        except Exception as exc:  # keep the scheduler alive; the next run retries
            print(
                json.dumps({"event": "retention_failed", "error_type": type(exc).__name__}),
                flush=True,
            )
        time.sleep(INTERVAL_SECONDS)
