import email
import imaplib
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.header import decode_header


def send_email(to: str, subject: str, body: str, from_name: str = "Katy", reply_to: str = "") -> dict:
    """Send email via Gmail SMTP using app password.

    Requires env vars: GMAIL_ADDRESS, GMAIL_APP_PASSWORD
    Returns: {"sent": bool, "error": str?}
    """
    try:
        gmail_address     = os.getenv("GMAIL_ADDRESS", "").strip()
        gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        if not gmail_address or not gmail_app_password:
            return {"sent": False, "error": "Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD"}
        if not to:
            return {"sent": False, "error": "Missing recipient email"}
        if not subject:
            return {"sent": False, "error": "Missing email subject"}
        if not body:
            return {"sent": False, "error": "Missing email body"}

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{gmail_address}>" if from_name else gmail_address
        msg["To"]      = to
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_address, gmail_app_password)
            smtp.send_message(msg)

        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}


def check_replies(since_hours: int = 48) -> list[dict]:
    """
    Poll Gmail inbox for unread emails that look like prospect replies.
    Returns a list of reply dicts: {from_email, from_name, subject, body, received_at}

    Requires env vars: GMAIL_ADDRESS, GMAIL_APP_PASSWORD
    """
    gmail_address      = os.getenv("GMAIL_ADDRESS", "").strip()
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_address or not gmail_app_password:
        return [{"error": "Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD"}]

    replies = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail_address, gmail_app_password)
        mail.select("INBOX")

        # Search for unread messages in the last N hours
        since_date = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(UNSEEN SINCE "{since_date}")')

        if status != "OK" or not data[0]:
            mail.logout()
            return []

        message_ids = data[0].split()
        for msg_id in message_ids[-20:]:  # Process at most 20 newest
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # Decode sender
                from_raw  = msg.get("From", "")
                from_name, from_email = _parse_from(from_raw)

                # Skip emails from ourselves or obvious automated senders
                if from_email.lower() == gmail_address.lower():
                    continue
                if any(x in from_email.lower() for x in ["noreply", "no-reply", "donotreply", "mailer-daemon"]):
                    continue

                # Decode subject
                subject_raw = msg.get("Subject", "")
                subject     = _decode_header_value(subject_raw)

                # Extract plain text body
                body = _extract_body(msg)
                if not body.strip():
                    continue

                # Date
                date_str = msg.get("Date", "")

                replies.append({
                    "from_email":  from_email,
                    "from_name":   from_name,
                    "subject":     subject,
                    "body":        body[:2000],
                    "received_at": date_str,
                    "msg_id":      msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                })

                # Mark as read so we don't process it again
                mail.store(msg_id, "+FLAGS", "\\Seen")

            except Exception:
                continue

        mail.logout()
    except Exception as e:
        return [{"error": f"IMAP error: {e}"}]

    return replies


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _parse_from(from_header: str) -> tuple[str, str]:
    """Return (name, email) from a From: header."""
    try:
        name_parts, addr = email.utils.parseaddr(from_header)
        name = _decode_header_value(name_parts) if name_parts else ""
        return name, addr
    except Exception:
        return "", from_header


def _extract_body(msg) -> str:
    """Extract plain text from a possibly multipart email."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or "utf-8"
                try:
                    return part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            return ""
    return ""
