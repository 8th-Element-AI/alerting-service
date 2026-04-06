"""Base interface for Pub/Sub (GCP credentials and client)."""

import logging
import os
from abc import ABC
from dataclasses import dataclass
from typing import Optional


@dataclass
class GCPConfig:
    """Configuration for GCP operations."""

    project_id: Optional[str] = None
    credentials_path: Optional[str] = None

    @classmethod
    def load_from_env(cls) -> "GCPConfig":
        return cls(
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
            credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        )


class GCPClient(ABC):
    """Abstract base class for GCP clients."""

    def __init__(self, config: GCPConfig):
        self.config = config
        self.project_id = config.project_id

    def _get_credentials(self):
        from google.auth import default
        from google.oauth2 import service_account

        logger = logging.getLogger(__name__)

        if self.config.credentials_path:
            try:
                return service_account.Credentials.from_service_account_file(
                    self.config.credentials_path
                )
            except FileNotFoundError:
                logger.error(f"Credentials file not found: {self.config.credentials_path}")
                raise
            except Exception as e:
                logger.error(f"Failed to load credentials from file: {e}")
                raise

        try:
            credentials, project = default()
            if self.project_id is None:
                self.project_id = project
            return credentials
        except Exception as e:
            logger.error(f"Failed to load application default credentials: {e}")
            raise
