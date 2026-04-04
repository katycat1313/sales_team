"""
Google Calendar Tool
--------------------
Creates callback events for Eric when Google Calendar is configured.
"""

import json
import os
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _load_service_account_info() -> dict:
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    if raw_json:
        return json.loads(raw_json)

    if file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def is_configured() -> bool:
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "").strip()
    return bool(calendar_id and _load_service_account_info())


def _client():
    info = _load_service_account_info()
    if not info:
        raise RuntimeError("Google service account credentials not configured")
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(
    summary: str,
    start_at: datetime,
    duration_minutes: int = 20,
    description: str = "",
    attendee_email: str = "",
) -> dict:
    if not is_configured():
        return {"created": False, "error": "Google Calendar not configured"}

    if not start_at.tzinfo:
        raise ValueError("start_at must include timezone")

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "").strip()
    tz_name = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Los_Angeles").strip() or "America/Los_Angeles"
    end_at = start_at + timedelta(minutes=max(5, int(duration_minutes or 20)))

    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_at.isoformat(), "timeZone": tz_name},
        "end": {"dateTime": end_at.isoformat(), "timeZone": tz_name},
    }

    email = (attendee_email or "").strip()
    if email and "@" in email:
        body["attendees"] = [{"email": email}]

    service = _client()
    event = service.events().insert(
        calendarId=calendar_id,
        body=body,
        sendUpdates="all" if email and "@" in email else "none",
        conferenceDataVersion=0,
    ).execute()

    return {
        "created": True,
        "event_id": event.get("id"),
        "html_link": event.get("htmlLink"),
        "hangout_link": event.get("hangoutLink", ""),
    }
