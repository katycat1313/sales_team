"""
Google Sheets Sync Tool
-----------------------
Pushes prospect data to a Google Sheet using gspread + a service account.

Setup:
1. Create a Google Service Account (see README or docs for steps).
2. Download the credentials JSON and save it as:
       orchestrator/credentials/google_service_account.json
3. Share your Google Sheet with the service account's email address
   (give it Editor access).
4. Set GOOGLE_SHEET_ID in your .env (or it defaults to the hardcoded ID below).
"""

import json
import os
import threading
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "12PoYqddT3FzQAlvL871cR4kUfk3X37M_qO10oT2V65c",
)

# Path to the service account credentials JSON file.
# Resolves relative to this file's directory: orchestrator/credentials/...
_HERE = os.path.dirname(os.path.abspath(__file__))
CREDS_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    os.path.join(_HERE, "..", "credentials", "google_service_account.json"),
)

SHEET_TAB = "Prospects"  # Name of the worksheet tab

# Columns in order — must match the header row written on first use.
COLUMNS = [
    "Business Name",
    "Phone",
    "Location",
    "Niche",
    "GBP Score",
    "Priority",
    "Issues",
    "Website",
    "Maps URL",
    "Last Call At",
    "Call Outcome",
    "Call Result",
    "Call Temperature",
    "Objections",
    "Next Action",
    "Callback Due",
    "Callback Reason",
    "Callback Status",
]

# Thread lock so concurrent saves don't race on the sheet client.
_lock = threading.Lock()
_sheet_client = None  # cached gspread worksheet


def _get_worksheet():
    """Return (and cache) the gspread Worksheet object."""
    global _sheet_client
    if _sheet_client is not None:
        return _sheet_client

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise RuntimeError(
            "gspread / google-auth not installed. "
            "Run: pip install gspread google-auth"
        ) from e

    creds_path = os.path.normpath(CREDS_PATH)
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"[Sheets] Service account credentials not found at: {creds_path}\n"
            "See the setup instructions in sheets_tool.py."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(SHEET_ID)

    # Get or create the worksheet tab.
    try:
        ws = spreadsheet.worksheet(SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_TAB, rows=1000, cols=len(COLUMNS))

    # Write header row if the sheet is empty.
    if ws.row_count == 0 or not ws.row_values(1):
        ws.append_row(COLUMNS, value_input_option="USER_ENTERED")

    _sheet_client = ws
    return ws


def push_prospect_sync(prospect: dict) -> bool:
    """
    Push a single prospect dict as a new row in the Google Sheet.
    Called from memory.py save_prospect() — runs synchronously.
    Returns True on success, False on any failure (never raises).
    """
    creds_path = os.path.normpath(CREDS_PATH)
    if not os.path.exists(creds_path):
        print(
            f"[Sheets] Skipping push — credentials not found: {creds_path}"
        )
        return False

    issues = prospect.get("gbp_issues", [])
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [issues] if issues else []
    issues_text = "; ".join(str(i) for i in issues[:3]) if issues else ""

    row = [
        prospect.get("business_name", ""),
        prospect.get("phone", ""),
        prospect.get("location", ""),
        prospect.get("niche", ""),
        prospect.get("gbp_score", ""),
        prospect.get("priority", ""),
        issues_text,
        prospect.get("website", ""),
        prospect.get("maps_url", ""),
        prospect.get("last_call_at", ""),
        prospect.get("last_call_outcome", ""),
        prospect.get("call_result_summary", ""),
        prospect.get("call_temperature", ""),
        prospect.get("objections", ""),
        prospect.get("next_action", ""),
        prospect.get("callback_due_at", ""),
        prospect.get("callback_reason", ""),
        prospect.get("callback_status", ""),
    ]

    try:
        with _lock:
            ws = _get_worksheet()
            ws.append_row(row, value_input_option="USER_ENTERED")
        print(f"[Sheets] ✓ Added: {prospect.get('business_name', '?')}")
        return True
    except Exception as e:
        print(f"[Sheets] Push failed for {prospect.get('business_name', '?')}: {e}")
        return False


# ── Async convenience wrapper (kept for backwards compat) ─────────────────────

async def push_prospect_to_sheet(
    business_name: str,
    phone: str = "",
    location: str = "",
    niche: str = "",
    priority: str = "",
    gbp_score: float = 0,
    issues: list = None,
    website: str = "",
    maps_url: str = "",
    **_kwargs,
) -> bool:
    """Async wrapper — delegates to the synchronous gspread push."""
    prospect = {
        "business_name": business_name,
        "phone": phone,
        "location": location,
        "niche": niche,
        "priority": priority,
        "gbp_score": gbp_score,
        "gbp_issues": issues or [],
        "website": website,
        "maps_url": maps_url,
    }
    return push_prospect_sync(prospect)
