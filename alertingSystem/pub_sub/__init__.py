"""Google Cloud Pub/Sub tools module."""

import os
from typing import Optional

from .base import GCPConfig, GCPClient
from .client import PubSubClient

_client: Optional[PubSubClient] = None


def get_pubsub_client() -> PubSubClient:
    global _client
    if _client is None:
        config = GCPConfig.load_from_env()
        _client = PubSubClient(config)
    return _client


__all__ = ["GCPConfig", "GCPClient", "PubSubClient", "get_pubsub_client"]
