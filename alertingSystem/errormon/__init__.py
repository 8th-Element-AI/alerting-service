"""
errormon - Lightweight error monitoring client library.

Usage:
    from errormon import catchError
    client = catchError(config={"api_url": "http://localhost:5000"})
    client.catchError(exception)
"""

from .client import catchError

__all__ = ["catchError"]
