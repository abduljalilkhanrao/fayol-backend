from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict | None:
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")

    if not all([host, port, user, password]):
        return None

    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "from_addr": os.environ.get("SMTP_FROM", "noreply@fayolsolutions.com"),
    }


async def send_email(
    to: str | list[str],
    subject: str,
    html_body: str,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    config = _get_smtp_config()
    if config is None:
        logger.warning("SMTP not configured — email not sent (subject: %s, to: %s)", subject, to)
        return False

    if isinstance(to, str):
        to = [to]
    if isinstance(cc, str):
        cc = [cc]
    if isinstance(bcc, str):
        bcc = [bcc]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_addr"]
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)

    msg.attach(MIMEText(html_body, "html"))

    all_recipients = list(to)
    if cc:
        all_recipients.extend(cc)
    if bcc:
        all_recipients.extend(bcc)

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["user"], config["password"])
            server.sendmail(config["from_addr"], all_recipients, msg.as_string())
        logger.info("Email sent successfully (subject: %s, to: %s)", subject, to)
        return True
    except Exception:
        logger.exception("Failed to send email (subject: %s, to: %s)", subject, to)
        return False
