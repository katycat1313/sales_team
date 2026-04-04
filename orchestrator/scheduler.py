"""
Proactive Scheduler
-------------------
Agents wake up and work on their own — no prompting needed.
Runs as a background thread inside the orchestrator.

Schedule:
  07:00  Morning briefing — coordinator summarizes overnight findings
  09:00  Scout job hunt — searches all boards for new roles
  11:00  Outreach prep — drafts messages for new contacts scout found
  14:00  Afternoon scout — second job search pass
  17:00  End of day report — coordinator briefs Katy via Telegram
  Every 30min — check approval queue, ping Telegram if anything is waiting
"""

import asyncio
import httpx
import os
from datetime import datetime
from pathlib import Path

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KATY_TELEGRAM_ID = os.getenv("KATY_TELEGRAM_ID")

async def send_telegram(message: str):
    """Send a message to Katy via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not KATY_TELEGRAM_ID:
        print(f"[Scheduler] Telegram not configured: {message}")
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": KATY_TELEGRAM_ID, "text": message, "parse_mode": "HTML"}
            )
    except Exception as e:
        print(f"[Scheduler] Telegram error: {e}")

async def run_agent_task(agent: str, task: str) -> str:
    """Trigger an agent task via the orchestrator API"""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{ORCHESTRATOR_URL}/task",
                json={"task": task, "agent": agent}
            )
            return r.json().get("result", "")
    except Exception as e:
        print(f"[Scheduler] Task error ({agent}): {e}")
        return ""

async def morning_briefing():
    print("[Scheduler] 🌅 Morning briefing starting...")
    await send_telegram("🌅 <b>Good morning Katy!</b>\nYour agent team is starting the day. I'll update you shortly with what we find.")

    result = await run_agent_task(
        "coordinator",
        "Give Katy a morning briefing. Check memory for any jobs found yesterday, contacts identified, and tasks completed. Summarize what the team accomplished and what's planned for today. Be concise — 5 bullet points max."
    )
    if result:
        await send_telegram(f"☀️ <b>Morning Briefing</b>\n\n{result[:3000]}")

async def scout_job_hunt(label: str = "morning"):
    print(f"[Scheduler] 🔍 Scout {label} hunt starting...")
    await send_telegram(f"🔍 Scout is starting the {label} job hunt...")

    result = await run_agent_task(
        "scout",
        f"Run a thorough {label} job search for Katy. Search Wellfound, LinkedIn, Remote.co, and Contra for AI Application Developer, Solutions Implementation Specialist, and AI Product Manager roles. Filter for remote positions paying $50k+ or $35/hr+. Only report jobs not already in memory."
    )
    if result:
        await send_telegram(f"🔍 <b>Scout {label.title()} Report</b>\n\n{result[:3000]}")

async def outreach_prep():
    print("[Scheduler] ✉️ Outreach prep starting...")

    result = await run_agent_task(
        "outreach",
        "Review what Scout has found recently. Draft personalized outreach messages for any new recruiters or hiring managers identified that haven't been contacted yet. Prepare drafts — do not send anything without Katy's approval."
    )
    if result:
        await send_telegram(f"✉️ <b>Outreach Drafts Ready</b>\n\nI've prepared some outreach drafts for your review.\n\nCheck the dashboard Outbox to approve or reject.\n\n{result[:1500]}")

async def end_of_day_report():
    print("[Scheduler] 📊 End of day report starting...")

    result = await run_agent_task(
        "coordinator",
        "Give Katy an end-of-day summary. How many jobs did Scout find today? How many outreach drafts are ready? What's in the approval queue? What should she focus on tomorrow? Be direct and specific. 5-7 bullet points."
    )
    if result:
        await send_telegram(f"🌙 <b>End of Day Report</b>\n\n{result[:3000]}\n\n<i>Your agents will keep working overnight. See you tomorrow!</i>")

async def check_approvals():
    """Ping Katy if things are waiting in the approval queue"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{ORCHESTRATOR_URL}/approvals")
            items = r.json()
            if len(items) > 0:
                await send_telegram(
                    f"⏳ <b>Approval Needed</b>\n\n"
                    f"You have {len(items)} item(s) waiting for your OK.\n"
                    f"Reply /approvals to see them or check the dashboard."
                )
    except Exception as e:
        print(f"[Scheduler] Approval check error: {e}")

class ProactiveScheduler:
    def __init__(self):
        self.running = False
        self.last_approval_ping = None

    async def start(self):
        self.running = True
        print("[Scheduler] ✅ Proactive scheduler started")
        await send_telegram("🤖 <b>Agent team is online!</b>\nProactive mode activated. I'll check in throughout the day.")

        while self.running:
            now = datetime.now()
            hour = now.hour
            minute = now.minute

            # Morning briefing at 7:00
            if hour == 7 and minute == 0:
                await morning_briefing()
                await asyncio.sleep(90)

            # Morning scout at 9:00
            elif hour == 9 and minute == 0:
                await scout_job_hunt("morning")
                await asyncio.sleep(90)

            # Outreach prep at 11:00
            elif hour == 11 and minute == 0:
                await outreach_prep()
                await asyncio.sleep(90)

            # Afternoon scout at 14:00
            elif hour == 14 and minute == 0:
                await scout_job_hunt("afternoon")
                await asyncio.sleep(90)

            # End of day at 17:00
            elif hour == 17 and minute == 0:
                await end_of_day_report()
                await asyncio.sleep(90)

            # Check approvals every 30 minutes
            elif minute == 0 or minute == 30:
                # Only ping if it's been more than 25 minutes since last ping
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
