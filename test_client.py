from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "alertingSystem"))

import errormon

errormon.init(config={
    "api_url": "http://localhost:5000",
    "api_key": "CFG0ZgXzRm28Q-6Y56ORIvvRFUWXrJa98",
    "service_name": "test_client",
    "environment": "development",
})


def run_test():
    try:
        value = 1 / 0
        return value
    except Exception as exc:
        errormon.report(exc, metadata={"module": "test_client", "user_id": "123"})


if __name__ == "__main__":
    print("Sending test exception to API...")
    run_test()
    print("Done. Check API terminal logs for /errors request.")