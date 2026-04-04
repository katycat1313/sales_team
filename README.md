# Katy Agent Team — Setup Guide

## What this is
A personal AI agent team running on your G14 that hunts jobs,
drafts outreach, preps you for interviews, and reports to you via Telegram.

## Prerequisites (already done)
- [x] Docker Desktop installed on G14
- [x] WSL2 enabled
- [x] Telegram bot created (@katyagentteam_bot)
- [x] Anthropic API key

---

## Step 1 — Get your Telegram user ID

1. In Telegram search for **@userinfobot**
2. Start it and send /start
3. It replies with your numeric ID like: `Id: 123456789`
4. Copy that number — you need it for .env

---

## Step 2 — Set up the project on the G14

Open WSL2 (search "WSL" in Windows start menu) and run:

```bash
# Clone or copy the project folder to WSL2
cd ~
mkdir agent_team
cd agent_team

# Copy katy_brief.md into memory folder
mkdir -p orchestrator/memory
cp /path/to/katy_brief.md orchestrator/memory/
```

---

## Step 3 — Fill in your .env file

Open the .env file and fill in:

```
TELEGRAM_BOT_TOKEN=8360739636:AAGhtL7OElsGvQVPdqXfTDiTnUho4XR7gRA
ANTHROPIC_API_KEY=your_anthropic_key_here        ← add this
ORCHESTRATOR_URL=http://orchestrator:8000
KATY_TELEGRAM_ID=your_telegram_id_here           ← add from Step 1
```

---

## Step 4 — Start everything

```bash
# In WSL2, inside the agent_team folder
docker-compose up --build
```

You should see:
```
agent_orchestrator  | Agent team starting up...
agent_orchestrator  | Loaded Katy's brief (XXXX chars)
agent_telegram      | Telegram bot starting...
```

---

## Step 5 — Test it

In Telegram, open your bot (@katyagentteam_bot) and send:
```
/start
```

You should see the welcome message with all commands.

Then try:
```
/status
```

If it replies with team status — everything is working!

---

## Daily commands

| Command | What it does |
|---|---|
| `/status` | Team status check |
| `/scout find AI developer jobs remote` | Scout hunts jobs |
| `/outreach draft message to ML startup recruiter` | Outreach drafts a message |
| `/coach prep me for solutions engineer interview` | Coach preps you |
| `/approvals` | See what needs your OK |
| `/approve 1` | Approve action #1 |
| `/reject 1` | Reject action #1 |
| Just type anything | Coordinator handles it |

---

## Spy dashboard (coming next)
Open your browser on the G14 or Mac and go to:
```
http://localhost:8000/events     ← live event stream
http://localhost:8000/approvals  ← pending approvals
http://localhost:8000/status     ← team status
```

The full React dashboard is the next build step.

---

## To stop the agents
```bash
docker-compose down
```

## To restart after changes
```bash
docker-compose up --build
```

## To see live logs
```bash
docker-compose logs -f
```
