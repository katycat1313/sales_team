import os
import httpx
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KATY_TELEGRAM_ID = os.getenv("KATY_TELEGRAM_ID")

def is_katy(update: Update) -> bool:
    if not KATY_TELEGRAM_ID:
        return True
    return str(update.effective_user.id) == str(KATY_TELEGRAM_ID)

async def run_task(agent: str, task: str) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{ORCHESTRATOR_URL}/task", json={"task": task, "agent": agent})
        return r.json().get("result", "No result")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    await update.message.reply_text(
        "🤖 *Katy's Agent Team — 15 Agents Online*\n\n"
        "*Job Search*\n"
        "/jobseeker — find + apply for jobs\n"
        "/scout — search job boards\n"
        "/networking — LinkedIn + connections\n"
        "/coach — interview + pitch practice\n\n"
        "*Business*\n"
        "/research — deep dive on anything\n"
        "/smallbiz — diagnose a business\n"
        "/solutions — plan a solution\n"
        "/automations — design a workflow\n"
        "/bizdev — growth opportunities\n\n"
        "*Sales*\n"
        "/leadgen — find prospects\n"
        "/sales — close a deal\n"
        "/salesops — pipeline status\n"
        "/marketing — craft messaging\n"
        "/outreach — draft messages\n\n"
        "*Support*\n"
        "/resume — tailor resume for a role\n"
        "/engineer — code help\n"
        "/approvals — pending approvals\n"
        "/approve [id] — approve action\n"
        "/reject [id] — reject action\n"
        "/status — team status\n\n"
        "Or just type anything to talk to the team leader!",
        parse_mode='Markdown'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORCHESTRATOR_URL}/status")
        d = r.json()
    mem = d.get("memory", {})
    await update.message.reply_text(
        f"📊 *Agent Team Status*\n\n"
        f"✅ Online: {d['online']}\n"
        f"📝 Events logged: {d['events_logged']}\n"
        f"⏳ Pending approvals: {d['pending_approvals']}\n"
        f"💼 Jobs in memory: {mem.get('jobs_total', 0)}\n"
        f"👥 Contacts found: {mem.get('contacts_total', 0)}\n"
        f"✅ Tasks today: {mem.get('tasks_today', 0)}",
        parse_mode='Markdown'
    )

# ── Agent command factory ──
def make_cmd(agent: str, default_task: str, emoji: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_katy(update): return
        task = " ".join(context.args) if context.args else default_task
        await update.message.reply_text(f"{emoji} On it...")
        try:
            result = await run_task(agent, task)
            await update.message.reply_text(f"{emoji} *{agent.replace('_',' ').title()}*\n\n{result[:4000]}", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    return handler

async def approvals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORCHESTRATOR_URL}/approvals")
        items = r.json()
    if not items:
        await update.message.reply_text("✅ No pending approvals!"); return
    msg = "⏳ *Pending Approvals*\n\n"
    for item in items:
        msg += f"ID {item['id']}: {item['agent']} → {item['action']}\n"
        msg += f"  _{str(item['details'])[:80]}_\n\n"
    msg += "Use /approve [id] or /reject [id]"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    if not context.args: await update.message.reply_text("Usage: /approve [id]"); return
    async with httpx.AsyncClient() as client:
        await client.post(f"{ORCHESTRATOR_URL}/approvals/{context.args[0]}/approve")
    await update.message.reply_text(f"✅ Approved #{context.args[0]}")

async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    if not context.args: await update.message.reply_text("Usage: /reject [id]"); return
    async with httpx.AsyncClient() as client:
        await client.post(f"{ORCHESTRATOR_URL}/approvals/{context.args[0]}/reject")
    await update.message.reply_text(f"❌ Rejected #{context.args[0]}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    await update.message.reply_text("🧠 Team leader thinking...")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{ORCHESTRATOR_URL}/chat", json={"message": update.message.text, "agent": "team_leader"})
            await update.message.reply_text(r.json()["response"][:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("approvals", approvals_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))

    # All 15 agents as commands
    commands = [
        ("jobseeker",   "job_seeker",         "Find the best job opportunities for Katy right now",                    "💼"),
        ("scout",       "scout",              "Search all job boards for AI developer roles remote $50k+",             "🔍"),
        ("networking",  "networking",         "Identify the best people for Katy to connect with on LinkedIn today",   "🔗"),
        ("coach",       "coach",              "Start an interview practice session",                                    "🎯"),
        ("research",    "research",           "Research the AI developer job market right now",                         "📚"),
        ("smallbiz",    "small_biz_expert",   "Identify small businesses in the Charleston WV area with intake problems","🏪"),
        ("solutions",   "solutions_architect","Design a solution for a small contractor intake problem",                "🏗️"),
        ("automations", "automations",        "Identify automation opportunities for Katy's agent team internally",    "⚙️"),
        ("bizdev",      "biz_dev",            "Identify new business opportunities Katy should pursue this week",      "📈"),
        ("leadgen",     "lead_gen",           "Find and qualify 10 prospects for Katy's services",                     "🎯"),
        ("sales",       "sales",              "Draft a pitch for Katy's AI intake form service",                       "💰"),
        ("salesops",    "sales_ops",          "Give a pipeline status report",                                         "📊"),
        ("marketing",   "marketing",          "Write a LinkedIn post showcasing CCPractice",                           "📣"),
        ("outreach",    "outreach",           "Draft cold outreach to an AI startup recruiter",                        "✉️"),
        ("resume",      "resume_builder",     "Tailor my resume for an AI developer role",                            "📄"),
        ("engineer",    "engineer",           "Review the agent pipeline code for issues",                             "🔧"),
    ]

    for cmd, agent, default, emoji in commands:
        app.add_handler(CommandHandler(cmd, make_cmd(agent, default, emoji)))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Telegram bot online — 15 agents ready")
    app.run_polling()

if __name__ == "__main__":
    main()
