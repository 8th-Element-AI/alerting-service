import os
from typing import Any, Dict

import redis

from alerts import send_alert
from db import get_last_alerted_at, insert_error, mark_mail_sent, set_last_alerted_at
from utils.logger import get_logger

logger = get_logger(__name__)

ALERT_COOLDOWN_SECONDS = int(os.getenv("DEDUP_WINDOW_SECONDS", "360"))


class ErrorOccurrenceProcessor:
    def __init__(
        self,
        alert_cooldown_seconds: int = ALERT_COOLDOWN_SECONDS,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._alert_cooldown_seconds = alert_cooldown_seconds
        self._redis = redis_client or redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
            socket_connect_timeout=1,
        )
        try:
            self._redis.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable at startup — deduplication will not work until Redis recovers: {e}")

    def process(self, message_data: Dict[str, Any]) -> bool:
        error_key = self._make_error_key(message_data)

        logger.info(
            f"{message_data.get('error_type')} - "
            f"{message_data.get('error_message')} "
            f"(service={message_data.get('service_name', 'unknown')}, "
            f"env={message_data.get('environment', 'unknown')})"
        )

        # Store every error in Postgres immediately
        try:
            error_id = insert_error(message_data)
        except Exception as e:
            logger.error(f"Failed to store error in DB: {e}")
            error_id = None

        # Fast path: Redis says we've seen this recently — suppress
        is_first = self._redis.set(
            error_key,
            "1",
            nx=True,
            ex=self._alert_cooldown_seconds,
        )

        if not is_first:
            logger.info(f"Alert suppressed (Redis cooldown): {error_key}")
            return True

        # Redis didn't have it (cold start / restart) — check Postgres for last_alerted_at
        try:
            last_alerted_at = get_last_alerted_at(error_key)
        except Exception as e:
            logger.error(f"Failed to read last_alerted_at from DB: {e}")
            last_alerted_at = None

        if last_alerted_at is not None:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            elapsed = (now - last_alerted_at).total_seconds()
            if elapsed < self._alert_cooldown_seconds:
                # Still in cooldown per DB — re-seed Redis with remaining TTL
                remaining_ttl = int(self._alert_cooldown_seconds - elapsed)
                self._redis.set(error_key, "1", ex=remaining_ttl)
                logger.info(f"Alert suppressed (DB cooldown, {remaining_ttl}s remaining): {error_key}")
                return True

        # Not in cooldown — fire alert
        try:
            ok = send_alert(error_key=error_key, count=1, details=message_data)
        except Exception as e:
            logger.error(f"Failed to send alert for {error_key}: {e}")
            return False

        if ok:
            try:
                set_last_alerted_at(error_key)
            except Exception as e:
                logger.error(f"Failed to update last_alerted_at in DB: {e}")

            if isinstance(error_id, int):
                try:
                    mark_mail_sent(error_id=error_id, sent=True)
                except Exception as e:
                    logger.error(f"Failed to update mail_sent for error id={error_id}: {e}")

        return ok

    @staticmethod
    def _make_error_key(message_data: Dict[str, Any]) -> str:
        service_name = message_data.get("service_name", "unknown")
        error_type = message_data.get("error_type", "Unknown")
        error_message = message_data.get("error_message", "")
        return f"{service_name}::{error_type}::{error_message}"
