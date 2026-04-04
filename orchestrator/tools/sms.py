import os
import asyncio
from typing import Optional

try:
    from twilio.rest import Client
except Exception:
    Client = None  # requirements may not be installed in dev environment


def _get_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise RuntimeError("Twilio credentials not set in TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN")
    if Client is None:
        raise RuntimeError("Twilio library not installed. Add to requirements and install.")
    return Client(sid, token)


def _send_sms_sync(to: str, body: str, from_: Optional[str] = None):
    client = _get_client()
    from_number = from_ or os.getenv("TWILIO_PHONE_NUMBER")
    if not from_number:
        raise RuntimeError("TWILIO_PHONE_NUMBER not set")
    msg = client.messages.create(body=body, from_=from_number, to=to)
    return msg.sid


async def send_sms(to: str, body: str, from_: Optional[str] = None) -> str:
    """Send SMS asynchronously. Returns message SID."""
    return await asyncio.to_thread(_send_sms_sync, to, body, from_)
