"""
errormon - Lightweight error monitoring client library.

Usage:
    from errormon import catchError, AsyncCatchError

    # Sync (reads config from env: ALERTING_API_URL, ALERTING_API_KEY, SERVICE_NAME, ENVIRONMENT)
    client = catchError()
    client.catchError(exception)

    # Async
    client = AsyncCatchError()
    await client.catchError(exception)
"""

from .client import AsyncCatchError, catchError

__all__ = ["catchError", "AsyncCatchError"]
