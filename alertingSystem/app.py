"""
app.py - Error Ingestion API

Gateway between client libraries and the alerting pipeline.

Flow:
- If GCP Pub/Sub is configured  → publish to Pub/Sub → subscriber processes → email
- If GCP Pub/Sub is not configured → process directly → email

The library only needs an API URL + optional API key. No GCP credentials leak out.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

from db import get_database_url, init_pool
from processing import ErrorOccurrenceProcessor
from pub_sub.base import GCPConfig
from pub_sub.client import PubSubClient
from utils.logger import get_logger

logger = get_logger(__name__)


_db_url = get_database_url()
if not _db_url:
    raise RuntimeError("DATABASE_URL is required.")
init_pool(_db_url)


TOPIC_ID = os.getenv("GCP_TOPIC_ID")
_pubsub: PubSubClient | None = None

_gcp_config = GCPConfig.load_from_env()
if _gcp_config.project_id and TOPIC_ID:
    try:
        _pubsub = PubSubClient(_gcp_config)
        _ = _pubsub.publisher
        logger.info("Pub/Sub configured — errors will be queued.")
    except Exception as e:
        logger.warning(f"Pub/Sub init failed, falling back to direct processing: {e}")
        _pubsub = None
else:
    logger.info("Pub/Sub not configured — running in direct processing mode.")



app = Flask(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("REDIS_URL", "redis://localhost:6379"),
    storage_options={"socket_connect_timeout": 1},
    swallow_errors=True,
    on_breach=lambda limit: logger.warning(f"Rate limit breached: {limit}"),
)


_redis_healthy = True

@limiter.request_filter
def log_redis_error():
    global _redis_healthy
    try:
        limiter.storage.check()
        if not _redis_healthy:
            logger.info("Rate limiter Redis is back online.")
            _redis_healthy = True
    except Exception as e:
        if _redis_healthy:
            logger.error(f"Rate limiter Redis unavailable — rate limiting disabled: {e}")
            _redis_healthy = False
    return False

API_KEY = os.getenv("ALERTING_API_KEY")
REQUIRED_FIELDS = {"error_type", "error_message", "stack_trace"}

_processor = ErrorOccurrenceProcessor()


def _is_authorized() -> bool:
    if not API_KEY:
        return True
    return request.headers.get("X-API-Key") == API_KEY


@app.route("/errors", methods=["POST"])
@limiter.limit("60 per minute")
def ingest_error():
    """
    POST /errors

    Accepts an error payload from client libraries, validates it,
    enriches it with server-side metadata, then either queues it to
    Pub/Sub or processes it directly.

    Expected JSON body:
        {
            "error_type":    "ZeroDivisionError",
            "error_message": "division by zero",
            "stack_trace":   "Traceback ...",
            "timestamp":     "2026-03-27T10:00:00Z",   # optional
            "service_name":  "payment-service",         # optional
            "environment":   "production",              # optional
            "metadata":      {}                         # optional
        }
    """
    if not _is_authorized():
        logger.warning(f"Unauthorized /errors request from {request.remote_addr}")
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        return jsonify({"error": f"Missing required fields: {sorted(missing)}"}), 422

    payload["received_at"] = datetime.now(timezone.utc).isoformat()
    payload["source_ip"] = request.remote_addr
    payload["request_path"] = request.path
    payload["request_method"] = request.method

    logger.info(
        f"Error received: [{payload.get('service_name', 'unknown')}] "
        f"{payload['error_type']}: {payload['error_message']}"
    )

    if _pubsub and TOPIC_ID:
        try:
            _pubsub.publish_message(TOPIC_ID, payload)
            logger.info("Error queued to Pub/Sub.")
        except Exception as e:
            logger.error(f"Pub/Sub publish failed, falling back to direct processing: {e}")
            _processor.process(payload)
    else:
        _processor.process(payload)
        logger.info("Error processed directly.")

    return jsonify({"status": "received"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.error(f"Unhandled exception in API: {e}", exc_info=True)
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting Error Ingestion API on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
