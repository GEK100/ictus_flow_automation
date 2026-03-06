"""Resend email wrapper for Ictus Flow notifications."""

import os
import resend
from dotenv import load_dotenv

load_dotenv(r"C:\Users\gk100\Ictus Flow Automation Secrets\.env")

resend.api_key = os.getenv('RESEND_API_KEY')

FROM_ADDRESS = 'Ictus Flow <hello@ictusflow.com>'


def send_email(to, subject, html_body, attachments=None):
    """Send an email via Resend.

    Args:
        to: Recipient email or list of addresses.
        subject: Email subject.
        html_body: HTML content.
        attachments: Optional list of dicts with 'filename' and 'content' (bytes).
    """
    params = {
        'from': FROM_ADDRESS,
        'to': to if isinstance(to, list) else [to],
        'subject': subject,
        'html': html_body,
    }
    if attachments:
        params['attachments'] = attachments
    return resend.Emails.send(params)


def send_notification(client_config, subject, body_html):
    """Send a notification to a client's contact email."""
    return send_email(client_config['contact_email'], subject, body_html)


def send_admin_notification(subject, body_html):
    """Send a notification to the Ictus Flow admin."""
    admin_email = os.getenv('ADMIN_EMAIL', 'gareth@ictusflow.com')
    return send_email(admin_email, subject, body_html)
