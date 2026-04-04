import os
import smtplib
from email.message import EmailMessage


def send_email(to: str, subject: str, body: str, from_name: str = "Katy Team", reply_to: str = "") -> dict:
    """Send email via Gmail SMTP using app password.

    Requires env vars:
      GMAIL_ADDRESS
      GMAIL_APP_PASSWORD

    Returns:
      {"sent": bool, "error": str?}
    """
    try:
        gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
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
        msg["From"] = f"{from_name} <{gmail_address}>" if from_name else gmail_address
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_address, gmail_app_password)
            smtp.send_message(msg)

        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}
