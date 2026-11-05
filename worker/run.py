"""Start the RQ worker for OCR jobs. A plain Worker keeps a warm OCR model between jobs."""

from redis import Redis
from rq import SimpleWorker

from app.config import get_settings
from app.jobs import QUEUE_NAME

if __name__ == "__main__":
    connection = Redis.from_url(get_settings().redis_url)
    SimpleWorker([QUEUE_NAME], connection=connection).work(with_scheduler=False)
