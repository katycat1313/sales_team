import os
from typing import Optional

from twilio.rest import Client


def send_sms(to_number: str, body: str, from_number: Optional[str] = None) -> dict:
    """Synchronous SMS sender used by VAPI function endpoints.

    Returns:
      {"sent": bool, "sid": str?, "error": str?}
    """
    try:
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_TOKEN") or os.getenv("TWILIO_AUTH_TOKEN")
        sender = from_number or os.getenv("TWILIO_PHONE_NUMBER")

        if not sid or not token:
            return {"sent": False, "error": "Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN"}
        if not sender:
            return {"sent": False, "error": "Missing TWILIO_PHONE_NUMBER"}
        if not to_number:
            return {"sent": False, "error": "Missing destination number"}
        if not body:
            return {"sent": False, "error": "Missing message body"}

        client = Client(sid, token)
        msg = client.messages.create(
            body=body,
            from_=sender,
            to=to_number,
        )
        return {"sent": True, "sid": msg.sid}
    except Exception as e:
        return {"sent": False, "error": str(e)}
