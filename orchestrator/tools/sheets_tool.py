"""
Google Sheets Sync Tool
-----------------------
Pushes prospect data to a Google Sheet via Apps Script webhook.
No API keys needed — just a Google Apps Script web app URL.

Setup:
1. Create a Google Sheet named "iFixProfiles Prospects"
2. Extensions → Apps Script → paste the doPost script
3. Deploy as web app → copy URL → add to .env as GOOGLE_SHEETS_WEBHOOK_URL
"""

import httpx
import os
import json
from typing import Optional

SHEETS_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "")


async def push_prospect_to_sheet(
    business_name: str,
    phone: str = "",
    location: str = "",
    niche: str = "",
    priority: str = "",
    gbp_score: float = 0,
    issues: list = None,
    website: str = "",
    pipeline_stage: str = "found",
    research_notes: str = "",
) -> bool:
    """
    Push a single prospect row to Google Sheets.
    Called automatically when a new prospect is saved.
    Returns True on success.
    """
    if not SHEETS_WEBHOOK_URL:
        return False

    issues_text = "; ".join(issues[:3]) if issues else ""

    payload = {
        "business_name": business_name,
        "phone": phone,
        "location": location,
        "niche": niche,
        "priority": priority,
        "gbp_score": gbp_score,
        "issues": issues_text,
        "website": website,
        "pipeline_stage": pipeline_stage,
        "research_notes": research_notes[:300] if research_notes else "",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                SHEETS_WEBHOOK_URL,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            result = r.json()
            return result.get("status") == "ok"
    except Exception as e:
        print(f"[Sheets] Push failed for {business_name}: {e}")
        return False


def push_prospect_sync(prospect: dict) -> bool:
    """
    Synchronous wrapper — call this from non-async code.
    Used in memory.py save_prospect().
    """
    import asyncio

    issues = prospect.get("gbp_issues", [])
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except Exception:
            issues = [issues]

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule as a background task — don't block the save
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    push_prospect_to_sheet(
                        business_name=prospect.get("business_name", ""),
                        phone=prospect.get("phone", ""),
                        location=prospect.get("location", ""),
                        niche=prospect.get("niche", ""),
                        priority=prospect.get("priority", ""),
                        gbp_score=prospect.get("gbp_score", 0),
                        issues=issues,
                        website=prospect.get("website", ""),
                        pipeline_stage=prospect.get("pipeline_stage", "found"),
                        research_notes=prospect.get("research_notes", ""),
                    )
                )
                return future.result(timeout=12)
        else:
            return loop.run_until_complete(
                push_prospect_to_sheet(
                    business_name=prospect.get("business_name", ""),
                    phone=prospect.get("phone", ""),
                    location=prospect.get("location", ""),
                    niche=prospect.get("niche", ""),
                    priority=prospect.get("priority", ""),
                    gbp_score=prospect.get("gbp_score", 0),
                    issues=issues,
                    website=prospect.get("website", ""),
                    pipeline_stage=prospect.get("pipeline_stage", "found"),
                    research_notes=prospect.get("research_notes", ""),
                )
            )
    except Exception as e:
        print(f"[Sheets] Sync push failed: {e}")
        return False
