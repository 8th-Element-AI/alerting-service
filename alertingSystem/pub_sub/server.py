import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.subscriber.message import Message

from .base import GCPConfig
from .client import PubSubClient
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseWorker(ABC):

    def __init__(self, subscription_name: Optional[str] = None):
        if not subscription_name:
            subscription_name = os.getenv("ALERTING_SUBSCRIPTION")

        if not subscription_name:
            raise ValueError(
                "subscription_name is required. Set ALERTING_SUBSCRIPTION env var."
            )

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        if subscription_name.startswith("projects/"):
            self.subscription_path = subscription_name
        else:
            self.subscription_path = f"projects/{project_id}/subscriptions/{subscription_name}"

        flow_max = int(os.getenv("FLOW_CONTROL_MAX_MESSAGES", "5"))
        self.flow_control = pubsub_v1.types.FlowControl(max_messages=flow_max)

        gcp_config = GCPConfig.load_from_env()
        pubsub = PubSubClient(gcp_config)
        self.subscriber = pubsub.subscriber
        self._project_id = gcp_config.project_id
        self._running = False

    @abstractmethod
    async def process_message(self, message_data: Dict[str, Any]) -> bool:
        raise NotImplementedError()

    def _callback(self, message: Message) -> None:
        """Orchestrates: parse → process → ack/nack."""
        message_data = self._parse(message)
        if message_data is None:
            message.ack()  # discard malformed messages
            return

        success = self._run(message_data)
        if success:
            message.ack()
        else:
            message.nack()

    def _parse(self, message: Message) -> Optional[Dict[str, Any]]:
        """Decode and parse the raw Pub/Sub message into a dict."""
        try:
            return json.loads(message.data.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message JSON, discarding: {e}")
            return None

    def _run(self, message_data: Dict[str, Any]) -> bool:
        """Run process_message in a fresh event loop. Returns True on success."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.process_message(message_data))
            return bool(result)
        except Exception as e:
            logger.error(f"Unexpected error processing message, nacking: {e}")
            return False
        finally:
            loop.close()

    def start(self) -> None:
        self._running = True
        try:
            self.subscriber.get_subscription(request={"subscription": self.subscription_path})
            streaming_pull_future = self.subscriber.subscribe(
                self.subscription_path,
                callback=self._callback,
                flow_control=self.flow_control,
            )
            try:
                streaming_pull_future.result()
            except KeyboardInterrupt:
                streaming_pull_future.cancel()
                try:
                    streaming_pull_future.result()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error starting worker: {e}")
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
