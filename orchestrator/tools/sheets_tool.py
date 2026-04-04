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
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────

SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "12PoYqddT3FzQAlvL871cR4kUfk3X37M_qO10oT2V65c",
)

_webapp_url_primary = os.getenv("GOOGLE_SHEETS_WEBAPP_URL", "").strip()
_webapp_url_legacy = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "").strip()
_deployment_id = os.getenv("GOOGLE_SHEETS_DEPLOYMENT_ID", "").strip()

if not _webapp_url_primary and _deployment_id:
    _webapp_url_primary = f"https://script.google.com/macros/s/{_deployment_id}/exec"

# Final fallback uses the deployment URL provided during setup for this workspace.
SHEETS_WEBAPP_URL = (
    _webapp_url_primary
    or _webapp_url_legacy
    or "https://script.google.com/macros/s/AKfycbzmlPEdcndwHPxMjCyamglrebBe3syEGorWj4BHMRfgegyighjOwINKhGKe7R1d4LqT/exec"
)
SHEETS_WEBAPP_TOKEN = os.getenv("GOOGLE_SHEETS_WEBAPP_TOKEN", "").strip()

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
    "Buyer Intent Score",
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


def _prospect_payload(prospect: dict) -> dict:
    issues = prospect.get("gbp_issues", [])
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [issues] if issues else []
    issues_text = "; ".join(str(i) for i in issues[:3]) if issues else ""

    return {
        "business_name": prospect.get("business_name", ""),
        "phone": prospect.get("phone", ""),
        "location": prospect.get("location", ""),
        "niche": prospect.get("niche", ""),
        # Keep compatibility with older records while supporting new sales workflow naming.
        "buyer_intent_score": prospect.get("buyer_intent_score", prospect.get("gbp_score", "")),
        "priority": prospect.get("priority", ""),
        "issues": issues_text,
        "website": prospect.get("website", ""),
        "maps_url": prospect.get("maps_url", ""),
        "last_call_at": prospect.get("last_call_at", ""),
        "last_call_outcome": prospect.get("last_call_outcome", ""),
        "call_result_summary": prospect.get("call_result_summary", ""),
        "call_temperature": prospect.get("call_temperature", ""),
        "objections": prospect.get("objections", ""),
        "next_action": prospect.get("next_action", ""),
        "callback_due_at": prospect.get("callback_due_at", ""),
        "callback_reason": prospect.get("callback_reason", ""),
        "callback_status": prospect.get("callback_status", ""),
    }


def _push_via_webapp(prospect: dict) -> bool:
    if not SHEETS_WEBAPP_URL:
        return False

    payload = {
        "type": "prospect_upsert",
        "token": SHEETS_WEBAPP_TOKEN,
        "prospect": _prospect_payload(prospect),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SHEETS_WEBAPP_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if resp.status < 200 or resp.status >= 300:
                print(f"[Sheets] WebApp push failed HTTP {resp.status}: {body[:180]}")
                return False

            # Accept either plain "ok" or JSON {ok:true}
            body_l = body.strip().lower()
            if body_l in {"ok", "true", "success"}:
                print(f"[Sheets] ✓ Added via WebApp: {prospect.get('business_name', '?')}")
                return True
            try:
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {}
            ok = bool(parsed.get("ok") or parsed.get("success") or parsed.get("saved"))
            if ok:
                print(f"[Sheets] ✓ Added via WebApp: {prospect.get('business_name', '?')}")
                return True

            print(f"[Sheets] WebApp response not ok: {body[:180]}")
            return False
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(e)
        print(f"[Sheets] WebApp HTTP error {getattr(e, 'code', '?')}: {detail[:180]}")
        return False
    except Exception as e:
        print(f"[Sheets] WebApp push error: {e}")
        return False


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
    # Preferred path: Apps Script WebApp endpoint.
    if SHEETS_WEBAPP_URL and _push_via_webapp(prospect):
        return True

    # Fallback path: service account + gspread.
    creds_path = os.path.normpath(CREDS_PATH)
    if not os.path.exists(creds_path):
        print(f"[Sheets] Skipping push — credentials not found: {creds_path}")
        return False

    row_payload = _prospect_payload(prospect)
    row = [
        row_payload.get("business_name", ""),
        row_payload.get("phone", ""),
        row_payload.get("location", ""),
        row_payload.get("niche", ""),
        row_payload.get("buyer_intent_score", ""),
        row_payload.get("priority", ""),
        row_payload.get("issues", ""),
        row_payload.get("website", ""),
        row_payload.get("maps_url", ""),
        row_payload.get("last_call_at", ""),
        row_payload.get("last_call_outcome", ""),
        row_payload.get("call_result_summary", ""),
        row_payload.get("call_temperature", ""),
        row_payload.get("objections", ""),
        row_payload.get("next_action", ""),
        row_payload.get("callback_due_at", ""),
        row_payload.get("callback_reason", ""),
        row_payload.get("callback_status", ""),
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


def sheets_sync_config_status() -> dict:
    creds_path = os.path.normpath(CREDS_PATH)
    return {
        "webapp_configured": bool(SHEETS_WEBAPP_URL),
        "webapp_url": SHEETS_WEBAPP_URL,
        "webapp_token_configured": bool(SHEETS_WEBAPP_TOKEN),
        "gspread_sheet_id": SHEET_ID,
        "gspread_tab": SHEET_TAB,
        "service_account_path": creds_path,
        "service_account_exists": os.path.exists(creds_path),
    }


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
