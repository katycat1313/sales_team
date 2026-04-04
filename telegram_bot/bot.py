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
        "🤖 <b>Missed-Call-Revenue Agent Team</b>\n\n"
        "<b>Find Clients</b>\n"
        "/pipeline — scan Google Maps, research, build outreach\n"
        "/linkedin — find + DM service business owners on LinkedIn\n"
        "/leadgen — find and qualify prospects\n"
        "/target [company] — deep research + pitch one specific business\n\n"
        "<b>Close Deals</b>\n"
        "/sales — pitch, objection handling, proposals\n"
        "/closer — late-stage closing + objection scripts\n"
        "/demo — book demos, follow up post-demo\n"
        "/salesops — pipeline status report\n\n"
        "<b>Outreach & Replies</b>\n"
        "/outreach — draft personalized messages\n"
        "/networking — warm up prospects before pitch\n"
        "/marketing — platform-specific messaging + content\n\n"
        "<b>Approvals</b>\n"
        "/approvals — see what's waiting\n"
        "/approve [id] — send it now\n"
        "/no [id] — cancel it\n\n"
        "<b>Strategy</b>\n"
        "/bizdev — growth opportunities + new niches\n"
        "/debrief — weekly sales debrief\n"
        "/status — team status\n\n"
        "Or just type anything — team leader handles it.",
        parse_mode="HTML"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORCHESTRATOR_URL}/status")
        d = r.json()
    mem = d.get("memory", {})
    await update.message.reply_text(
        f"📊 <b>Agent Team Status</b>\n\n"
        f"✅ Online: {d['online']}\n"
        f"📝 Events logged: {d['events_logged']}\n"
        f"⏳ Pending approvals: {d['pending_approvals']}\n"
        f"👥 Prospects in pipeline: {mem.get('prospects_total', 0)}\n"
        f"✅ Tasks today: {mem.get('tasks_today', 0)}",
        parse_mode="HTML"
    )

# ── Agent command factory ──────────────────────────────────────────────────────
def make_cmd(agent: str, default_task: str, emoji: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_katy(update): return
        task = " ".join(context.args) if context.args else default_task
        await update.message.reply_text(f"{emoji} On it...")
        try:
            result = await run_task(agent, task)
            await update.message.reply_text(
                f"{emoji} <b>{agent.replace('_',' ').title()}</b>\n\n{result[:4000]}",
                parse_mode="HTML"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    return handler

# ── Playbook shortcuts ─────────────────────────────────────────────────────────
def make_playbook_cmd(playbook_id: str, emoji: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_katy(update): return
        await update.message.reply_text(f"{emoji} Starting {playbook_id} playbook...")
        try:
            # Parse optional key=value args (niche=plumbers location="Austin TX")
            payload = {}
            for arg in (context.args or []):
                if "=" in arg:
                    k, _, v = arg.partition("=")
                    payload[k.strip()] = v.strip()
                else:
                    payload["company"] = arg  # for target-company playbook
            async with httpx.AsyncClient(timeout=180) as client:
                r = await client.post(
                    f"{ORCHESTRATOR_URL}/playbook/{playbook_id}",
                    json=payload,
                    timeout=180,
                )
                data = r.json()
            summary = data.get("summary", str(data))[:4000]
            await update.message.reply_text(f"{emoji} <b>Done</b>\n\n{summary}", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    return handler

# ── Approval commands ──────────────────────────────────────────────────────────
async def approvals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORCHESTRATOR_URL}/approvals")
        items = r.json()
    if not items:
        await update.message.reply_text("✅ No pending approvals!"); return
    msg = "⏳ <b>Pending Approvals</b>\n\n"
    for item in items:
        auto = " ⏱ auto-sends" if item.get("auto_approve") else ""
        msg += f"<b>#{item['id']}</b>: {item['agent']} → {item['action']}{auto}\n"
        details = item.get("details", {})
        preview = (
            details.get("draft_reply")
            or details.get("draft_preview")
            or details.get("preview")
            or ""
        )
        if preview:
            msg += f"<i>{str(preview)[:120]}</i>\n"
        msg += "\n"
    msg += "/approve [id]  •  /no [id]"
    await update.message.reply_text(msg, parse_mode="HTML")

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    if not context.args:
        await update.message.reply_text("Usage: /approve [id]"); return
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{ORCHESTRATOR_URL}/approvals/{context.args[0]}/approve")
        data = r.json()
    sent = data.get("sent")
    if sent is True:
        await update.message.reply_text(f"✅ Sent! (#{context.args[0]})")
    elif sent is False:
        await update.message.reply_text(f"✅ Approved #{context.args[0]} — but send failed. Check logs.")
    else:
        await update.message.reply_text(f"✅ Approved #{context.args[0]}")

async def no_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel/reject an approval — /no [id]"""
    if not is_katy(update): return
    if not context.args:
        await update.message.reply_text("Usage: /no [id]"); return
    async with httpx.AsyncClient() as client:
        await client.post(f"{ORCHESTRATOR_URL}/approvals/{context.args[0]}/reject")
    await update.message.reply_text(f"🚫 Cancelled #{context.args[0]}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_katy(update): return
    await update.message.reply_text("🧠 Thinking...")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"message": update.message.text, "agent": "team_leader"}
            )
            await update.message.reply_text(r.json()["response"][:4000])
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("status",    status))
    app.add_handler(CommandHandler("approvals", approvals_cmd))
    app.add_handler(CommandHandler("approve",   approve_cmd))
    app.add_handler(CommandHandler("reject",    no_cmd))   # alias
    app.add_handler(CommandHandler("no",        no_cmd))   # shorter, easier to type

    # Playbook shortcuts
    app.add_handler(CommandHandler("pipeline", make_playbook_cmd("client-pipeline",   "🔍")))
    app.add_handler(CommandHandler("linkedin", make_playbook_cmd("linkedin-outreach", "💼")))
    app.add_handler(CommandHandler("debrief",  make_playbook_cmd("weekly-debrief",    "📊")))
    app.add_handler(CommandHandler("funnel",   make_playbook_cmd("prospect-funnel",   "🔄")))
    app.add_handler(CommandHandler("target",   make_playbook_cmd("target-company",    "🎯")))

    # Agent commands
    commands = [
        ("leadgen",     "lead_gen",          "Find and qualify 10 HOT prospects for Missed-Call-Revenue",            "🎯"),
        ("sales",       "sales",             "Review the pipeline and write personalized pitches for warm prospects", "💰"),
        ("closer",      "closer",            "Review warm prospects and write closing messages",                      "🤝"),
        ("demo",        "demo",              "Check which prospects need a demo and draft booking messages",          "📞"),
        ("salesops",    "sales_ops",         "Give a full pipeline status report",                                    "📊"),
        ("outreach",    "outreach",          "Draft personalized cold outreach for the top HOT prospects",            "✉️"),
        ("networking",  "networking",        "Find service business owners to warm up before outreach",               "🔗"),
        ("marketing",   "marketing",         "Write a LinkedIn post about the cost of missed calls for trades businesses", "📣"),
        ("bizdev",      "biz_dev",           "What are the fastest paths to Katy's first client this week?",          "📈"),
        ("smallbiz",    "small_biz_expert",  "Analyze the missed-call pain for plumbers and HVAC businesses",         "🏪"),
        ("research",    "research",          "Research the AI answering service market — who else is selling this?",  "📚"),
        ("automations", "automations",       "What automations would help close deals faster?",                       "⚙️"),
        ("engineer",    "engineer",          "Review the codebase for issues or improvements",                        "🔧"),
    ]

    for cmd, agent, default, emoji in commands:
        app.add_handler(CommandHandler(cmd, make_cmd(agent, default, emoji)))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Telegram bot online — Missed-Call-Revenue agent team ready")
    app.run_polling()

if __name__ == "__main__":
    main()
