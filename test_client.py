from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "alertingSystem"))

from errormon import catchError


client = catchError(
    config={
        "api_url": "http://localhost:5001",
        "api_key": "",  
        "service_name": "my-test-service",
        "environment": "development",
    }
)


def run_test():
    try:
        value = 1 / 0
        return value
    except Exception as exc:
        client.catchError(exc, metadata={"module": "test_client", "user_id": "123"})


if __name__ == "__main__":
    print("Sending test exception to API...")
    run_test()
    print("Done. Check API terminal logs for /errors request.")