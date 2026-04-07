"""
utils/logger.py - Shared logging factory.

Provides a consistent log format across app.py, subscriber.py, and alerts.py.
Import get_logger() instead of calling logging.getLogger() directly so all
modules share the same format and respect the LOG_LEVEL env variable.
"""

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger with a consistent format.

    Idempotent — calling this multiple times for the same name is safe.

    Args:
        name: Typically __name__ of the calling module.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    return logger
