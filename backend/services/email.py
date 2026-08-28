"""
Email formatting and sending service.

Sends lead notifications and escalation alerts to the ID TECH sales team.
Configuration is driven by environment variables.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EmailService:
    """
    Simple SMTP-based email sender for lead notifications.

    Environment variables:
        SMTP_HOST     — SMTP server hostname (default: smtp.gmail.com)
        SMTP_PORT     — SMTP server port (default: 587)
        SMTP_USER     — SMTP username / from address
        SMTP_PASS     — SMTP password or app password
        IDTECH_SALES_EMAIL — where lead notifications go
    """

    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.sales_email = os.getenv("IDTECH_SALES_EMAIL", "sales@idtechproducts.com")
        self._configured = bool(self.smtp_user and self.smtp_pass)

    @property
    def configured(self) -> bool:
        """Whether SMTP credentials are available."""
        return self._configured

    def send_lead_notification(
        self,
        lead_name: str,
        lead_email: str,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        qualification: Optional[Dict[str, Any]] = None,
        products_shown: Optional[Dict[str, Any]] = None,
        is_escalation: bool = False,
    ) -> bool:
        """
        Send a lead notification email to the sales team.

        Returns True if the email was sent (or skipped intentionally),
        False on failure.
        """
        if not self._configured:
            logger.info(
                "SMTP not configured — skipping lead notification for %s",
                lead_email,
            )
            return True  # Not a failure — just not configured

        subject_prefix = "[ESCALATION] " if is_escalation else "[New Lead] "
        subject = f"{subject_prefix}{lead_name} — {company or 'No Company'}"

        # Build plain-text body
        lines = [
            f"Name: {lead_name}",
            f"Email: {lead_email}",
        ]
        if company:
            lines.append(f"Company: {company}")
        if phone:
            lines.append(f"Phone: {phone}")

        if qualification:
            lines.append("")
            lines.append("Qualification Summary:")
            for key, value in qualification.items():
                if isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        if sub_val is not None:
                            lines.append(f"  {key}.{sub_key}: {sub_val}")
                elif value is not None:
                    lines.append(f"  {key}: {value}")

        if products_shown:
            lines.append("")
            lines.append("Products Shown:")
            lines.append(f"  {products_shown}")

        body = "\n".join(lines)

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = self.sales_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

            logger.info(
                "Lead notification sent to %s for %s",
                self.sales_email,
                lead_email,
            )
            return True
        except Exception:
            logger.exception("Failed to send lead notification for %s", lead_email)
            return False


# Singleton
_email_service = EmailService()


def get_email_service() -> EmailService:
    return _email_service
