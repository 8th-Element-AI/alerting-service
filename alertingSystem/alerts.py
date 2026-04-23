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
from email.mime.multipart import MIMEMultipart
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
    subject = _format_subject(details)
    html_body = _format_html_body(details, count)

    logger.warning(
        f"\n{'=' * 60}\n{subject}\n{'-' * 60}\n"
        f"{_format_text_body(details, count)}\n{'=' * 60}"
    )

    return _send_email(
        subject=subject,
        html_body=html_body,
        text_body=_format_text_body(details, count),
    )


def _send_email(subject: str, *, html_body: str, text_body: str) -> bool:
    """Returns True if email was sent successfully, False otherwise."""
    recipients = [
        e.strip()
        for e in os.getenv("ALERT_EMAIL_GROUP", "").split(",")
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
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
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


def _format_text_body(details: Dict[str, Any], count: int) -> str:
    last_seen = details.get("received_at") or details.get("timestamp") or "N/A"
    stack_trace = details.get("stack_trace") or "N/A"
    max_chars = int(os.getenv("ALERT_STACKTRACE_MAX_CHARS", "8000"))
    if len(stack_trace) > max_chars:
        stack_trace = f"{stack_trace[:max_chars]}\n... (truncated)"
    return (
        f"Error Type   : {details.get('error_type', 'N/A')}\n"
        f"Error Message: {details.get('error_message', 'N/A')}\n"
        f"Service      : {details.get('service_name', 'N/A')}\n"
        f"Environment  : {details.get('environment', 'N/A')}\n"
        f"Last seen    : {last_seen}\n"
        f"\nStack Trace:\n{stack_trace}"
    )


def _format_html_body(details: Dict[str, Any], count: int) -> str:
    last_seen = details.get("received_at") or details.get("timestamp") or "N/A"
    stack_trace = details.get("stack_trace") or "N/A"
    max_chars = int(os.getenv("ALERT_STACKTRACE_MAX_CHARS", "8000"))
    truncated = len(stack_trace) > max_chars
    stack_trace = stack_trace[:max_chars]
    items = [
        ("Error type", details.get("error_type", "N/A")),
        ("Message", details.get("error_message", "N/A")),
        ("Service", details.get("service_name", "N/A")),
        ("Environment", details.get("environment", "N/A")),
        ("Last seen", last_seen),
    ]

    rows = "\n".join(
        f"<tr><th style=\"text-align:left;padding:8px;border:1px solid #e5e7eb;background:#f9fafb\">"
        f"{escape(label)}</th>"
        f"<td style=\"padding:8px;border:1px solid #e5e7eb\">{escape(str(value))}</td></tr>"
        for label, value in items
    )

    return (
        "<!doctype html>"
        "<html><body style=\"font-family:Arial,Helvetica,sans-serif;color:#111827\">"
        "<div style=\"max-width:720px;margin:0 auto\">"
        "<h2 style=\"margin:0 0 12px\">Error Alert</h2>"
        "<table cellpadding=\"0\" cellspacing=\"0\" style=\"border-collapse:collapse;width:100%\">"
        f"{rows}"
        "</table>"
        "<h3 style=\"margin:18px 0 8px\">Stack trace</h3>"
        "<pre style=\"white-space:pre-wrap;background:#0b1020;color:#e5e7eb;"
        "padding:12px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.35\">"
        f"{escape(stack_trace)}"
        f"{escape('\\n... (truncated)') if truncated else ''}"
        "</pre>"
        "</div>"
        "</body></html>"
    )


def _format_subject(details: Dict[str, Any]) -> str:
    service = details.get("service_name") or "unknown-service"
    error_type = details.get("error_type") or "Error"
    return f"[ALERT] {service} — {error_type}"
