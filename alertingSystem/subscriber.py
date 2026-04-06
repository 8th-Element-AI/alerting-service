"""
subscriber.py - Pub/Sub consumer with deduplication and alerting.

Design decisions:
- Extends BaseWorker (pub_sub/server.py) so transport details stay in one place.
- Redis handles fast distributed dedup across multiple subscriber instances.
- Postgres persists last_alerted_at so cooldown survives restarts.
- Every error is stored in Postgres regardless of whether an alert fires.
- Deduplication window prevents alert storms — same error within DEDUP_WINDOW_SECONDS
  is suppressed.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv

    _candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
    ]
    for _dotenv_path in _candidates:
        if _dotenv_path.exists():
            load_dotenv(_dotenv_path, override=True)
except ImportError:
    pass

from db import get_database_url, init_db
from processing import ErrorOccurrenceProcessor
from pub_sub.server import BaseWorker
from utils.logger import get_logger

logger = get_logger(__name__)


DEDUP_WINDOW_SECONDS = int(os.getenv("DEDUP_WINDOW_SECONDS", "360"))


class ErrorSubscriber(BaseWorker):
    """
    Subscribes to a Pub/Sub subscription and processes incoming error messages.

    Flow per message:
        1. Store error in Postgres immediately.
        2. Check Redis — if key exists, suppress (still in cooldown window).
        3. If Redis cold (restart), check last_alerted_at from Postgres.
        4. If not in cooldown → fire alert, update last_alerted_at in Postgres.
    """

    def __init__(self, subscription_name: Optional[str] = None):
        _db_url = get_database_url()
        if not _db_url:
            raise RuntimeError("DATABASE_URL is required.")
        init_db(_db_url)
        super().__init__(subscription_name)
        self._processor = ErrorOccurrenceProcessor()

   
    async def process_message(self, message_data: Dict[str, Any]) -> bool:
        """
        Process one error message from Pub/Sub.

        Returns True on success (even if the error is suppressed),
        so BaseWorker always acks the message.
        """
        return self._processor.process(message_data)


if __name__ == "__main__":
    logger.info(
        f"Starting ErrorSubscriber "
        f"(dedup_window={DEDUP_WINDOW_SECONDS}s)..."
    )
    worker = ErrorSubscriber()
    worker.start()
