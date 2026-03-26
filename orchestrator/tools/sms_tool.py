"""
SMS Tool (Twilio)
-----------------
Sends SMS messages via Twilio REST API.
"""

import base64
import os
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "") or os.getenv("TWILIO_SSID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "") or os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "") or os.getenv("TWILIO_PHONE_NUMBER", "")


def _normalize_us_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if str(phone).startswith("+"):
        return str(phone)
    return f"+{digits}"


def is_configured() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)


def send_sms(to_number: str, body: str, from_number: str = "") -> dict:
    if not is_configured() and not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and (from_number or TWILIO_FROM_NUMBER)):
        return {
            "sent": False,
            "error": "Twilio not configured. Set TWILIO_ACCOUNT_SID/TWILIO_SSID, TWILIO_AUTH_TOKEN/TWILIO_TOKEN, TWILIO_FROM_NUMBER/TWILIO_PHONE_NUMBER",
        }

    sender = _normalize_us_phone(from_number or TWILIO_FROM_NUMBER)
    to_number = _normalize_us_phone(to_number)
    if not to_number:
        return {"sent": False, "error": "Missing destination phone number"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    payload = urllib.parse.urlencode({"To": to_number, "From": sender, "Body": body}).encode("utf-8")

    auth_raw = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode("utf-8")
    auth_header = base64.b64encode(auth_raw).decode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body_raw = resp.read().decode("utf-8", errors="ignore")
            return {
                "sent": resp.status in (200, 201),
                "status_code": resp.status,
                "response": body_raw,
                "to": to_number,
                "from": sender,
                "sent_at": datetime.now().isoformat(),
            }
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        return {
            "sent": False,
            "error": f"Twilio HTTP {e.code}",
            "details": detail,
            "to": to_number,
            "from": sender,
        }
    except Exception as e:
        return {"sent": False, "error": str(e), "to": to_number, "from": sender}
