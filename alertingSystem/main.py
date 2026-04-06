"""
main.py - Example usage of the errormon client library.

This file shows how any service integrates errormon.
Notice: no GCP credentials, no Pub/Sub imports — just an API URL.
"""

from errormon import catchError

# Initialize once (e.g. at app startup)
client = catchError(
    config={
        "api_url": "http://localhost:5000",   # your API server
        "api_key": "your-api-key",            # optional, remove if auth disabled
        "service_name": "payment-service",
        "environment": "production",
    }
)


def raise_exception():
    try:
        a = 1 / 0
    except ZeroDivisionError as e:
        # Sends error to API → Pub/Sub → Subscriber → Alert
        client.catchError(e)


raise_exception()
