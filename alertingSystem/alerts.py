"""
alerts.py - Alert dispatch system.

Design decisions:
- Single public function send_alert() — returns True if email sent, False if failed.
- Exponential backoff on retries: 2s, 4s, 8s between attempts.
- Caller (processing.py) uses the return value to decide ack/nack in Pub/Sub mode.
"""

import os
import smtplib
import time
from email.mime.text import MIMEText
from html import escape
from typing import Any, Callable, Dict

from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3

# Validate SMTP config at import time so misconfiguration is caught at startup.
_smtp_host = os.getenv("SMTP_HOST")
_smtp_sender = os.getenv("ALERT_FROM_EMAIL")
_smtp_recipients = os.getenv("ALERT_EMAIL_GROUP")
if not (_smtp_host and _smtp_sender and _smtp_recipients):
    logger.warning(
        "SMTP misconfigured — alerts will NOT be sent via email. "
        "Set SMTP_HOST, ALERT_FROM_EMAIL, and ALERT_EMAIL_GROUP."
    )
RETRY_BASE_SECONDS = 2  # exponential: 2s, 4s, 8s


def send_alert(error_key: str, count: int, details: Dict[str, Any]) -> bool:
    """
    Dispatch an alert email when an error crosses the occurrence threshold.
    Returns True if email sent successfully, False otherwise.
    """
    subject = f"[ALERT] {count}x occurrences — {error_key}"
    body = _format_body(details, count)

    logger.warning(f"\n{'=' * 60}\n{subject}\n{'-' * 60}\n{body}\n{'=' * 60}")

    return _send_email(subject=subject, body=body)


def _send_email(subject: str, body: str) -> bool:
    """Returns True if email was sent successfully, False otherwise."""
    recipients = [
        e.strip()
        for e in os.getenv("ALERT_EMAIL_GROUP", "oncall@yourcompany.com").split(",")
        if e.strip()
    ]
    sender = os.getenv("ALERT_FROM_EMAIL")
    smtp_host = os.getenv("SMTP_HOST")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        logger.warning("Invalid SMTP_PORT value in env, using default 587.")
        smtp_port = 587
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"

    if not (smtp_host and sender and recipients):
        logger.info("Email config missing; skipping email.")
        return False

    def attempt_email():
        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if smtp_tls:
                smtp.starttls()
            if smtp_user and smtp_pass:
                smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        logger.info(f"Email alert dispatched to group: {', '.join(recipients)}")

    return _with_retry(attempt_email, label="Email")


def _with_retry(action: Callable, label: str) -> bool:
    """
    Retry an action up to MAX_RETRIES times with exponential backoff.
    Waits: 2s, 4s, 8s between attempts.
    Returns True on success, False if all attempts fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            action()
            return True
        except Exception as e:
            logger.warning(f"{label} attempt {attempt}/{MAX_RETRIES} failed — {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SECONDS ** attempt)

    logger.error(f"All {MAX_RETRIES} {label} attempts exhausted.")
    return False


def _format_body(details: Dict[str, Any], count: int) -> str:
    error_type = escape(str(details.get('error_type', 'N/A')))
    error_message = escape(str(details.get('error_message', 'N/A')))
    service_name = escape(str(details.get('service_name', 'N/A')))
    environment = escape(str(details.get('environment', 'N/A')))
    last_seen = escape(str(details.get('received_at', details.get('timestamp', 'N/A'))))
    source_ip = escape(str(details.get('source_ip', 'N/A')))
    stack_trace = escape(str(details.get('stack_trace', 'N/A'))).replace('\n', '<br>')

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .alert-badge {{
                display: inline-block;
                background-color: rgba(255, 255, 255, 0.2);
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                margin-top: 12px;
            }}
            .content {{
                padding: 30px;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }}
            .info-item {{
                border-left: 3px solid #667eea;
                padding-left: 15px;
            }}
            .info-label {{
                font-size: 12px;
                color: #999;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 6px;
                font-weight: 600;
            }}
            .info-value {{
                font-size: 16px;
                color: #333;
                font-weight: 500;
                word-break: break-word;
            }}
            .stack-trace-section {{
                margin-top: 30px;
                background-color: #f9f9f9;
                border-left: 3px solid #e74c3c;
                padding: 20px;
                border-radius: 4px;
            }}
            .stack-trace-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 600;
                margin-bottom: 12px;
            }}
            .stack-trace-content {{
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 13px;
                color: #333;
                background-color: white;
                padding: 15px;
                border-radius: 4px;
                overflow-x: auto;
                line-height: 1.5;
            }}
            .footer {{
                background-color: #f9f9f9;
                padding: 20px;
                text-align: center;
                font-size: 12px;
                color: #999;
                border-top: 1px solid #eee;
            }}
            .occurrence-count {{
                font-size: 32px;
                font-weight: 700;
                color: #e74c3c;
                margin: 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚨 Error Alert</h1>
                <div class="alert-badge">Occurrence #{count}</div>
            </div>

            <div class="content">
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">Error Type</div>
                        <div class="info-value">{error_type}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Service</div>
                        <div class="info-value">{service_name}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Environment</div>
                        <div class="info-value">{environment}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Last Seen</div>
                        <div class="info-value">{last_seen}</div>
                    </div>
                </div>

                <div class="info-item">
                    <div class="info-label">Error Message</div>
                    <div class="info-value">{error_message}</div>
                </div>

                <div class="info-item" style="margin-top: 20px;">
                    <div class="info-label">Source IP</div>
                    <div class="info-value">{source_ip}</div>
                </div>

                <div class="stack-trace-section">
                    <div class="stack-trace-label">📋 Stack Trace</div>
                    <div class="stack-trace-content">{stack_trace}</div>
                </div>
            </div>

            <div class="footer">
                <p style="margin: 0;">This is an automated alert from the Error Monitoring System</p>
            </div>
        </div>
    </body>
    </html>
    """
