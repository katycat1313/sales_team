"""
Email Tool (SendGrid)
---------------------
Sends emails via SendGrid API.
Keeps the same function interface as the original Gmail tool
so nothing else in the codebase needs to change.

Setup:
1. Sign up at sendgrid.com (free - 100 emails/day)
2. Settings → API Keys → Create API Key (Full Access)
3. Add to .env:
   SENDGRID_API_KEY=SG.xxxxxxxxxxxx
   GMAIL_ADDRESS=ifixprofiles@gmail.com   (used as the From address)
"""

import os
import urllib.request
import urllib.error
import json
from datetime import datetime

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")  # used as sender address


def is_configured() -> bool:
    return bool(SENDGRID_API_KEY and GMAIL_ADDRESS)


def send_email(
    to: str,
    subject: str,
    body: str,
    from_name: str = "Katy",
    reply_to: str = None,
) -> dict:
    """
    Send a plain text email via SendGrid.
    Returns {"sent": True, "to": to} or {"error": "..."}
    """
    if not is_configured():
        return {
            "error": "SendGrid not configured. Add SENDGRID_API_KEY and GMAIL_ADDRESS to .env",
            "sent": False,
        }

    if not to or "@" not in to:
        return {"error": f"Invalid email address: {to}", "sent": False}

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": GMAIL_ADDRESS, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=data,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            # SendGrid returns 202 Accepted on success (no body)
            if response.status in (200, 202):
                return {
                    "sent": True,
                    "to": to,
                    "subject": subject,
                    "sent_at": datetime.now().isoformat(),
                }
            else:
                return {"error": f"SendGrid returned status {response.status}", "sent": False}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        return {"error": f"SendGrid HTTP {e.code}: {error_body}", "sent": False}
    except Exception as e:
        return {"error": str(e), "sent": False}


def send_email_html(
    to: str,
    subject: str,
    plain_body: str,
    html_body: str,
    from_name: str = "Katy",
) -> dict:
    """Send email with both plain text and HTML versions via SendGrid."""
    if not is_configured():
        return {"error": "SendGrid not configured", "sent": False}

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": GMAIL_ADDRESS, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_body},
            {"type": "text/html", "value": html_body},
        ],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=data,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status in (200, 202):
                return {"sent": True, "to": to, "sent_at": datetime.now().isoformat()}
            else:
                return {"error": f"SendGrid returned status {response.status}", "sent": False}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        return {"error": f"SendGrid HTTP {e.code}: {error_body}", "sent": False}
    except Exception as e:
        return {"error": str(e), "sent": False}
