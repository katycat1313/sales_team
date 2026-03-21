# iFixProfiles — AI Sales Pipeline
### Automated Google Business Profile Sales System

An AI-powered sales engine that finds local businesses with broken Google Business Profiles, researches them, and reaches out via AI phone calls, Facebook DMs, Instagram DMs, and email — then transfers warm leads directly to Katy to close.

---

## The Sales Team

| Agent | Role |
|---|---|
| **Coordinator** | Runs the operation. Delegates tasks, monitors the pipeline, and sends Katy daily briefings via Telegram. |
| **GBP Scout** | Hunts Google Maps for local businesses with missing, incomplete, or outdated Google Business Profiles. Saves real prospects with phone numbers to the database. |
| **GBP Researcher** | Digs deep on every prospect — finds owner name, services, years in business, reviews, website quality, and buyer intent signals so Eric can personalize every call. |
| **Eric (VAPI AI Caller)** | Makes outbound AI cold calls using ElevenLabs voice. Armed with full business intel, MEDDIC sales framework, and objection handlers. Transfers warm leads directly to Katy's phone the moment a prospect says yes. |
| **Outreach Agent** | Drafts and sends personalized Facebook DMs, Instagram DMs, and emails. Queues everything for Katy's approval before sending. Uses 27 proven persuasion techniques. |
| **GBP Sales Agent** | Supports Katy on the close. Knows the full pitch, pricing objections, and how to position the offer. |
| **Sales Ops** | Tracks the pipeline, logs call outcomes, schedules callbacks, and manages Stripe payment links. |
| **Small Biz Expert** | Advises on what matters most to local business owners so the pitch stays relevant and resonant. |

---

## The Service

**One-time GBP Optimization — $197**
- Full Google Business Profile audit and fix
- $99 deposit to start, $99 on completion
- Delivered same day (2–4 hours)

**Ongoing Management — $98/month**
- Monthly posts, review monitoring, updates
- Keeps clients ranked above competitors long-term

**30-day money-back guarantee on everything.**

---

## How the Pipeline Works

```
GBP Scout finds businesses with bad profiles
        ↓
GBP Researcher builds full intel dossier
        ↓
Eric calls the business (AI voice, real phone)
        ↓
Prospect shows interest → transferred to Katy
        ↓
Katy closes → Stripe payment link sent
        ↓
Work delivered same day → $98/month recurring starts
```

---

## Tech Stack

- **FastAPI** — orchestrator backend (port 8000)
- **Docker** — containerized, runs on Windows with Docker Desktop
- **VAPI** — AI outbound phone calls (Eric's voice via ElevenLabs)
- **Playwright** — browser automation for Google Maps scraping and social DMs
- **Anthropic Claude + Google Gemini** — agent intelligence
- **Stripe** — payment links and invoices
- **SendGrid** — email outreach
- **Telegram Bot** — Katy's mobile command interface

---

## Dashboard

```
http://localhost:8000/dashboard   ← full pipeline view
http://localhost:8000/prospects   ← prospect database
http://localhost:8000/approvals   ← pending outreach to approve
http://localhost:8000/vapi/calls  ← call log and outcomes
```

---

## Quick Start

```bash
# Start everything
docker compose up -d

# Check it's running
curl http://localhost:8000/health

# Trigger a prospect scan manually
curl -X POST http://localhost:8000/task \
  -H "Content-Type: application/json" \
  -d '{"task": "Scan for GBP prospects: plumbers in Houston TX", "agent": "gbp_scout"}'

# Trigger a call
curl -X POST http://localhost:8000/vapi/call \
  -H "Content-Type: application/json" \
  -d '{"prospect_phone": "+17135550000", "business_name": "Acme Plumbing"}'
```

---

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
VAPI_API_KEY=
VAPI_ASSISTANT_ID=
VAPI_PHONE_NUMBER_ID=
KATY_PHONE=3044108850
STRIPE_SECRET_KEY=
SENDGRID_API_KEY=
TELEGRAM_BOT_TOKEN=
KATY_TELEGRAM_ID=
```

---

## Automated Schedule

The scheduler runs 24/7 and handles everything autonomously:

| Time | Action |
|---|---|
| Startup | Immediate prospect scan across 3 niche/city combos |
| 8:00 AM | Morning prospect scan (3 more combos) |
| 9:30 AM | Research pass — builds intel on all new prospects |
| 11:00 AM | Outreach queue — drafts DMs and emails for approval |
| 2:00 PM | Afternoon scan — new niches and cities |
| 4:00 PM | Second research pass |
| 6:00 PM | End of day pipeline report to Katy via Telegram |
| Every 30 min | Pings Katy if anything is waiting for approval |
