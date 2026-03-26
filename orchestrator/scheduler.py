"""
Proactive Scheduler — GBP Sales Pipeline
-----------------------------------------
Agents work autonomously on their own schedule.
No prompting needed — they find prospects, research them, and queue outreach.

Daily Schedule:
  08:00  Morning prospect scan  — gbp_scout finds HOT businesses across 3 niches/cities
  09:30  Deep research pass     — gbp_researcher builds full intel on every new prospect
  11:00  Outreach queue         — outreach agent drafts + queues DMs/emails for approval
  14:00  Afternoon scout sweep  — second scan in different niches
  16:00  Research pass 2        — fill out any prospects that need more intel
  18:00  End of day report      — coordinator briefs Katy on pipeline status

  Every 30min  — check approval queue, ping Katy if anything is waiting
  On startup   — kick off an immediate prospect scan so pipeline starts filling NOW
"""

import asyncio
import httpx
import os
import random
from datetime import datetime
from pathlib import Path

from constants import PRIME_NICHES, TARGET_CITIES

ORCHESTRATOR_URL   = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KATY_TELEGRAM_ID   = os.getenv("KATY_TELEGRAM_ID")


async def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not KATY_TELEGRAM_ID:
        print(f"[Scheduler] Telegram not configured: {message[:80]}")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": KATY_TELEGRAM_ID, "text": message, "parse_mode": "HTML"}
            )
    except Exception as e:
        print(f"[Scheduler] Telegram error: {e}")


async def run_agent_task(agent: str, task: str, timeout: int = 180) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{ORCHESTRATOR_URL}/task",
                json={"task": task, "agent": agent}
            )
            return r.json().get("result", "")
    except Exception as e:
        print(f"[Scheduler] Task error ({agent}): {e}")
        return ""


async def gbp_prospect_scan(label: str = "morning"):
    """Scout scans 3 niche+city combos and saves real prospects to the database."""
    print(f"[Scheduler] 🔍 {label.title()} GBP prospect scan starting...")
    await send_telegram(f"🔍 <b>Prospect scan starting...</b>\nScanning for businesses with bad Google profiles right now.")

    # Pick 3 random niche + city combos each run (variety = more pipeline)
    combos = random.sample(
        [(n, c) for n in PRIME_NICHES[:8] for c in TARGET_CITIES[:10]],
        k=3
    )

    all_results = []
    for niche, city in combos:
        task = f"Scan for GBP prospects: {niche} in {city}. Find real businesses with missing, incomplete, or outdated Google Business Profiles. Save all HOT and WARM prospects to the database. Be thorough."
        result = await run_agent_task("gbp_scout", task, timeout=240)
        if result:
            all_results.append(f"• {niche} in {city}: {result[:200]}")
        await asyncio.sleep(5)

    summary = "\n".join(all_results)
    await send_telegram(
        f"✅ <b>{label.title()} Scan Complete</b>\n\n{summary[:2000]}\n\n"
        f"Research agent is now building intel on each prospect."
    )

    # Immediately trigger research on newly found prospects
    await asyncio.sleep(10)
    await run_research_pass()


async def run_research_pass():
    """Researcher builds full intel on every prospect that hasn't been researched yet."""
    print("[Scheduler] 🔬 Research pass starting...")

    result = await run_agent_task(
        "gbp_researcher",
        "Research ALL prospects in the database that don't have full intel yet. "
        "For each prospect find: owner name, direct phone number, business description, "
        "years in business, services offered, recent reviews, website quality, and any "
        "buyer intent signals. This intel goes directly to Eric for the sales call — "
        "make it detailed and specific so he can be personable and relevant.",
        timeout=300
    )

    if result:
        print(f"[Scheduler] Research complete: {result[:200]}")


async def run_outreach_queue():
    """Outreach agent drafts messages for researched prospects and queues for approval."""
    print("[Scheduler] ✉️ Building outreach queue...")

    result = await run_agent_task(
        "outreach",
        "Review all researched prospects in the database. For each one that hasn't been "
        "contacted yet, draft a personalized Facebook DM and email outreach message. "
        "Use the specific GBP issues found to make the message relevant. "
        "Queue everything for Katy's approval — do NOT send anything yet.",
        timeout=240
    )

    if result:
        await send_telegram(
            f"📬 <b>Outreach Queue Ready</b>\n\n"
            f"Messages drafted and waiting for your approval.\n"
            f"Check the dashboard to approve before sending.\n\n"
            f"{result[:1000]}"
        )


async def morning_briefing():
    print("[Scheduler] 🌅 Morning briefing...")
    result = await run_agent_task(
        "coordinator",
        "Give Katy a morning sales briefing. Check the prospect database and approval queue. "
        "How many HOT prospects are ready to call? How many outreach messages are pending approval? "
        "What are the top 3 most promising businesses to call today and why? "
        "Be direct, specific, and motivating. 5 bullet points max.",
        timeout=60
    )
    if result:
        await send_telegram(f"🌅 <b>Good morning Katy!</b>\n\n{result[:2000]}")


async def end_of_day_report():
    print("[Scheduler] 📊 End of day report...")
    result = await run_agent_task(
        "coordinator",
        "Give Katy an end-of-day pipeline report. How many prospects did we find today? "
        "How many have full research intel? How many outreach messages went out? "
        "Any hot leads that Eric should call tomorrow morning? "
        "What does tomorrow's pipeline look like? Keep it to 6 bullet points.",
        timeout=60
    )
    if result:
        await send_telegram(
            f"🌙 <b>End of Day Report</b>\n\n{result[:2000]}\n\n"
            f"<i>Agents are still working. Pipeline will be fuller tomorrow!</i>"
        )


async def check_approvals():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{ORCHESTRATOR_URL}/approvals")
            items = [i for i in r.json() if i.get("status") == "pending"]
            if items:
                await send_telegram(
                    f"⏳ <b>{len(items)} item(s) waiting for approval</b>\n\n"
                    f"Check the dashboard or reply /approvals to review them."
                )
    except Exception as e:
        print(f"[Scheduler] Approval check error: {e}")


class ProactiveScheduler:
    def __init__(self):
        self.running = False
        self.last_approval_ping = None
        self.startup_scan_done = False

    async def start(self):
        self.running = True
        print("[Scheduler] ✅ GBP Sales scheduler started")
        await send_telegram(
            "🤖 <b>Agent team is online!</b>\n"
            "Starting prospect scan now — I'll find businesses with bad Google profiles "
            "and build your call list. Check back in a few minutes!"
        )

        # ── Startup: kick off first scan immediately ──────────────────────────
        await asyncio.sleep(8)  # Let orchestrator finish booting
        if not self.startup_scan_done:
            self.startup_scan_done = True
            asyncio.create_task(gbp_prospect_scan("startup"))

        # ── Main loop ────────────────────────────────────────────────────────
        while self.running:
            now    = datetime.now()
            hour   = now.hour
            minute = now.minute

            if hour == 8 and minute == 0:
                await gbp_prospect_scan("morning")
                await asyncio.sleep(90)

            elif hour == 9 and minute == 30:
                await run_research_pass()
                await asyncio.sleep(90)

            elif hour == 11 and minute == 0:
                await run_outreach_queue()
                await asyncio.sleep(90)

            elif hour == 13 and minute == 0:
                await morning_briefing()
                await asyncio.sleep(90)

            elif hour == 14 and minute == 0:
                await gbp_prospect_scan("afternoon")
                await asyncio.sleep(90)

            elif hour == 16 and minute == 0:
                await run_research_pass()
                await asyncio.sleep(90)

            elif hour == 18 and minute == 0:
                await end_of_day_report()
                await asyncio.sleep(90)

            # Ping every 30 min if approvals are waiting
            elif minute in (0, 30):
                now_ts = now.timestamp()
                if not self.last_approval_ping or (now_ts - self.last_approval_ping) > 1500:
                    await check_approvals()
                    self.last_approval_ping = now_ts
                await asyncio.sleep(60)

            else:
                await asyncio.sleep(30)

    def stop(self):
        self.running = False
        print("[Scheduler] Scheduler stopped")


scheduler = ProactiveScheduler()
