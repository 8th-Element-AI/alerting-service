# alerting-service

Error monitoring service. Client libraries report exceptions, the API ingests and deduplicates them, and sends email alerts.


## Architecture

Service (errormon client) sends POST /errors to the Flask API.
The API either queues to GCP Pub/Sub (processed by the Subscriber) or processes directly.
The processor stores every error in PostgreSQL, deduplicates via Redis with DB fallback, and sends an email alert via SMTP.


## Setup

1. Copy .env.example to .env and fill in your values.
2. Place your GCP service account JSON in the secrets/ folder (only if using Pub/Sub).
3. Run: docker-compose up --build -d
4. Verify: curl http://localhost:5001/health returns {"status": "ok"}


## Frontend (Browser) Usage

Copy `alertingSystem/errormon/errormon.js` into your frontend project.

Script tag:
    <script src="errormon.js"></script>
    <script>
      const monitor = new Errormon({
        apiUrl: "http://your-api:5001",
        serviceName: "my-react-app",
        environment: "production",
      });
      monitor.install(); // auto-captures window.onerror + unhandledrejection
    </script>

ES module:
    import Errormon from "./errormon.js";
    const monitor = new Errormon({ apiUrl: "...", serviceName: "my-app" });
    monitor.install();

Manual reporting inside try/catch:
    try { riskyOperation(); }
    catch (err) { monitor.catchError(err, { userId: "123" }); }

Required server-side setup:
    Set CORS_ALLOWED_ORIGINS in your .env to the origin(s) of your frontend.
    Example: CORS_ALLOWED_ORIGINS=http://localhost:3000,https://app.yourcompany.com

Security note:
    Do NOT set ALERTING_API_KEY if calling from the browser — the key would be
    visible in DevTools. Either disable API key auth or proxy requests through
    your own backend.


## Client Library

Install from the wheel file:
    pip install errormon-0.1.0-py3-none-any.whl

Sync usage:
    from errormon import catchError
    client = catchError()
    client.catchError(exception, metadata={"job_id": "123"})

Async usage:
    from errormon import AsyncCatchError
    client = AsyncCatchError()
    await client.catchError(exception, metadata={"job_id": "123"})

Config via dict (skips env vars):
    client = catchError({"api_url": "...", "api_key": "...", "service_name": "...", "environment": "..."})

Required env vars for client:
    ALERTING_API_URL    URL of the API server
    SERVICE_NAME        Your service name (shown in alerts)
    ENVIRONMENT         production / staging / development
    ALERTING_API_KEY    Optional — must match server if set


## API

POST /errors — ingest an error
    Required fields: error_type, error_message, stack_trace
    Optional fields: service_name, environment, metadata (dict)
    Headers: Content-Type: application/json, X-API-Key: <key> (if auth enabled)
    Response: 200 {"status": "received"}

GET /health
    Response: 200 {"status": "ok"}


## Environment Variables

DATABASE_URL                PostgreSQL connection string (required)
REDIS_URL                   Redis connection string (default: redis://localhost:6379)
PORT                        API server port (default: 5000)
ALERTING_API_KEY            Enables API key auth if set
DEDUP_WINDOW_SECONDS        Duplicate suppression window in seconds (default: 360)
ALERT_EMAIL_GROUP           Comma-separated recipient emails (required)
ALERT_FROM_EMAIL            Sender email address (required)
SMTP_HOST                   SMTP server host (required)
SMTP_PORT                   SMTP port (default: 587)
SMTP_USER                   SMTP username
SMTP_PASS                   SMTP password
SMTP_USE_TLS                Enable STARTTLS (default: true)
GOOGLE_CLOUD_PROJECT_ID     GCP project ID — enables Pub/Sub mode if set
GOOGLE_APPLICATION_CREDENTIALS  Path to GCP service account JSON
GCP_TOPIC_ID                Full Pub/Sub topic path
ALERTING_SUBSCRIPTION       Full Pub/Sub subscription path
LOG_LEVEL                   DEBUG / INFO / WARNING / ERROR (default: INFO)


## Project Structure

alerting-service/
    alertingSystem/
        app.py              Flask API
        processing.py       Dedup and alert logic
        alerts.py           Email dispatch
        subscriber.py       Pub/Sub consumer
        errormon/           pip-installable client library
        pub_sub/            GCP Pub/Sub wrappers
        utils/              Logger
    db.py                   Database operations
    Dockerfile
    docker-compose.yml
    pyproject.toml
    requirements.txt
