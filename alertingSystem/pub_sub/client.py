"""Google Cloud Pub/Sub client implementation."""

import json
import logging
from typing import Optional, Dict, Any

from google.cloud import pubsub_v1
from google.api_core.exceptions import AlreadyExists

from .base import GCPClient, GCPConfig

logger = logging.getLogger(__name__)


class PubSubClient(GCPClient):
    """Google Cloud Pub/Sub client for messaging operations."""

    def __init__(self, config: GCPConfig):
        super().__init__(config)
        self._publisher: Optional[pubsub_v1.PublisherClient] = None
        self._subscriber: Optional[pubsub_v1.SubscriberClient] = None

    @property
    def publisher(self) -> pubsub_v1.PublisherClient:
        if self._publisher is None:
            credentials = self._get_credentials()
            self._publisher = pubsub_v1.PublisherClient(credentials=credentials)
        return self._publisher

    @property
    def subscriber(self) -> pubsub_v1.SubscriberClient:
        if self._subscriber is None:
            credentials = self._get_credentials()
            self._subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
        return self._subscriber

    def publish_message(
        self,
        topic_name: str,
        data: Dict[str, Any],
        attributes: Optional[Dict[str, str]] = None,
    ) -> str:
        try:
            payload = json.dumps(data).encode("utf-8")
            topic_path = topic_name
            if not topic_name.startswith("projects/"):
                topic_path = self.publisher.topic_path(self.project_id, topic_name)
            message_attributes = attributes or {}
            future = self.publisher.publish(topic_path, payload, **message_attributes)
            future.add_done_callback(
                lambda f: logger.error(f"Pub/Sub publish failed: {f.exception()}")
                if f.exception()
                else logger.info(f"Published message {f.result()} to topic {topic_name}")
            )
            return ""
        except Exception as e:
            logger.error(f"Error publishing message to {topic_name}: {e}")
            raise

    def create_subscription(self, topic_name: str, subscription_name: str) -> None:
        topic_path = (
            topic_name
            if topic_name.startswith("projects/")
            else self.publisher.topic_path(self.project_id, topic_name)
        )
        subscription_path = (
            subscription_name
            if subscription_name.startswith("projects/")
            else self.subscriber.subscription_path(self.project_id, subscription_name)
        )
        try:
            self.subscriber.create_subscription(name=subscription_path, topic=topic_path)
            logger.info(f"Created subscription {subscription_name} for topic {topic_name}")
        except AlreadyExists:
            logger.info(f"Subscription {subscription_name} already exists.")

