"""
errormon - Lightweight error monitoring client library.

Module-level API (recommended):
    import errormon
    errormon.init(config={"api_url": "http://localhost:5001", "service_name": "my-svc"})

    # Then from any file in your project:
    import errormon
    errormon.report(exception)

Direct client (if you need multiple configs):
    from errormon import ErrormonClient
    client = ErrormonClient(config={"api_url": "http://localhost:5001"})
    client.report(exception)
"""

from .client import ErrormonClient, init, report

# Backwards-compatible alias
catchError = ErrormonClient

__all__ = ["ErrormonClient", "init", "report", "catchError"]
