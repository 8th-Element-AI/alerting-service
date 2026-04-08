"""
main.py - Example usage of the errormon client library.

This file shows how any service integrates errormon.
Notice: no GCP credentials, no Pub/Sub imports — just an API URL.
"""

from errormon import catchError

# Initialize once (e.g. at app startup)
# Reads ALERTING_API_URL, ALERTING_API_KEY, SERVICE_NAME, ENVIRONMENT from env
client = catchError()


def raise_exception():
    try:
        a = 1 / 0
    except ZeroDivisionError as e:
        # Sends error to API → Pub/Sub → Subscriber → Alert
        client.catchError(e)


raise_exception()
