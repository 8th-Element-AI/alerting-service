"""
errormon.client - Lightweight error capture and HTTP reporting.

Design decisions:
- Uses only stdlib (urllib) to avoid adding dependencies to client apps.
- Never raises exceptions — silently logs if reporting fails so the host
  application is never affected by a monitoring failure.
- Always sends to the API — routing to Pub/Sub is the API's job, not the library's.
"""

import json
import logging
import os
import time
import traceback
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("errormon")

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


@dataclass
class ErrormonConfig:
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    service_name: Optional[str] = None
    environment: Optional[str] = None


class ErrormonConfigLoader:
    """Loads ErrormonConfig from a dict or from environment variables."""

    @staticmethod
    def from_dict(config: Dict[str, Any]) -> ErrormonConfig:
        return ErrormonConfig(
            api_url=(config.get("api_url") or "").rstrip("/") or None,
            api_key=config.get("api_key"),
            service_name=config.get("service_name"),
            environment=config.get("environment"),
        )

    @staticmethod
    def from_env() -> ErrormonConfig:
        try:
            from dotenv import load_dotenv
            env_file = Path(__file__).parent.parent / ".env"
            load_dotenv(env_file, override=True)
        except ImportError:
            pass

        api_url = (os.getenv("ALERTING_API_URL") or "").strip()
        if not api_url:
            raise ValueError("ALERTING_API_URL is required.")

        return ErrormonConfig(
            api_url=api_url.rstrip("/"),
            api_key=os.getenv("ALERTING_API_KEY"),
            service_name=os.getenv("SERVICE_NAME"),
            environment=os.getenv("ENVIRONMENT", "production"),
        )


class ErrorPayloadBuilder:
    """Builds a serialisable error payload from an exception."""

    def __init__(self, config: ErrormonConfig):
        self._config = config

    def build(self, e: Exception, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "stack_trace": traceback.format_exc(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_name": self._config.service_name,
            "environment": self._config.environment,
            "metadata": metadata or {},
        }


class ErrorTransport:
    """Sends error payloads to the API."""

    def __init__(self, config: ErrormonConfig):
        self._config = config

    def send(self, payload: Dict[str, Any]) -> None:
        if not self._config.api_url:
            logger.error("errormon: api_url is not configured. Error not reported.")
            return

        url = f"{self._config.api_url}/errors"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["X-API-Key"] = self._config.api_key

        def attempt():
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Unexpected status {resp.status}")
            logger.debug("errormon: error reported successfully.")

        success = _with_retry(attempt, label="API")
        if not success:
            logger.error(f"errormon: all {MAX_RETRIES} retries exhausted. Error not reported.")


class catchError:
    """
    Client-side error capture library.

    Captures exceptions and sends them to the alerting API via HTTP POST.
    Never raises — monitoring must never crash the host app.

    Example:
        client = catchError(config={
            "api_url": "http://localhost:5000",
            "service_name": "payment-service",
            "environment": "production",
        })
        client.catchError(exception)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = (
            ErrormonConfigLoader.from_dict(config)
            if config is not None
            else ErrormonConfigLoader.from_env()
        )
        self._builder = ErrorPayloadBuilder(self.config)
        self._transport = ErrorTransport(self.config)

    def catchError(self, e: Exception, metadata: Optional[Dict[str, Any]] = None) -> None:
        try:
            payload = self._builder.build(e, metadata)
            self._transport.send(payload)
        except Exception as internal_error:
            logger.warning(f"errormon: failed to report error — {internal_error}")


def _with_retry(action: Callable, label: str) -> bool:
    """Retry an action with linear backoff. Returns True on success."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            action()
            return True
        except Exception as e:
            logger.warning(f"errormon: {label} attempt {attempt}/{MAX_RETRIES} failed — {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return False
