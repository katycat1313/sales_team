# Katy AI Sales Team
### AI Answering-Service Cold Call Pipeline

An AI-powered outbound sales system that finds service-business prospects, researches call-handling pain points, calls them with Eric (AI voice agent), and moves qualified prospects toward demo, callback, and payment.

---

## Core Offer (Current)

### Starter — $500 setup + $97/month
- Missed-call coverage
- Message capture
- Basic FAQ responses
- No scheduling

### Standard — $1,000 setup + $197/month
- Everything in Starter
- Appointment booking
- Objection handling
- Hot lead transfer to Katy

### Pro — $2,000 setup + $297/month
- Everything in Standard
- Custom personality and tone
- Multiple call flows
- After-hours handling
- Full onboarding

---

## Team Roles

| Agent | Role |
|---|---|
| **Coordinator** | Orchestrates missions, assigns agents, and tracks outcomes. |
| **Lead Gen** | Finds local service businesses likely losing revenue from missed calls. |
| **Research Assistant / Small Biz Expert** | Enriches each lead with decision-maker and operational pain intel. |
| **Eric (VAPI AI Caller)** | Runs outbound calls, answers questions, sends details by SMS/email, handles objections, and sets callbacks. |
| **Sales / Sales Ops** | Supports close motion, logs outcomes, schedules follow-up, and triggers payment links. |
| **Outreach** | Generates approved follow-up outreach across channels. |

---

## Call Flow

```
Lead Gen + Research find qualified service businesses
        ↓
Eric places outbound calls (with opt-out disclosure)
        ↓
Eric answers questions and sends requested details (SMS/email)
        ↓
Prospect chooses next step: callback, demo link, or payment link
        ↓
Katy joins warm transfers and closes
```

---

## Compliance + Delivery Features

- DNC scrubbing before outbound calls
- Opt-out handling and internal DNC recording
- Call outcome logging and compliance logs
- In-call fulfillment tools:
  - `send_business_details`
  - `send_demo_link`
  - `send_payment_link`
  - `schedule_callback` (calendar-ready)

---

## Tech Stack

- FastAPI orchestrator (port 8000)
- Docker Compose runtime
- VAPI + ElevenLabs voice for outbound calls
- Stripe payment links
- Twilio SMS delivery
- Gmail email delivery
- Google Calendar API support for callback scheduling
- Telegram bot notifications

---

## Local URLs

```
http://localhost:8000/
http://localhost:8000/dashboard
http://localhost:8000/prospects
http://localhost:8000/compliance/logs
```

---

## Quick Start

```bash
# Start services
docker compose up -d

# Basic health check
curl http://localhost:8000/

# Trigger a lead mission
curl -X POST http://localhost:8000/task \
  -H "Content-Type: application/json" \
  -d '{"task": "Find service-business prospects in Houston TX", "agent": "lead_gen"}'

# Trigger one outbound call
curl -X POST http://localhost:8000/vapi/call \
  -H "Content-Type: application/json" \
  -d '{"prospect_phone": "+17135550000", "business_name": "Acme Plumbing"}'
```

---

## Required Environment Variables

```env
# Core runtime
VAPI_API_KEY=
VAPI_ASSISTANT_ID=
VAPI_PHONE_NUMBER_ID=
KATY_PHONE=
ENABLE_ERIC_CALLS=false

# Payments + delivery
STRIPE_SECRET_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Email delivery
GMAIL_USER=
GMAIL_APP_PASSWORD=

# Callback scheduling (Google Calendar)
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_FILE=
# or GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_CALENDAR_TIMEZONE=America/Los_Angeles

# Optional links
CALENDLY_LINK=
DEMO_URL=

# Optional notifications
TELEGRAM_BOT_TOKEN=
KATY_TELEGRAM_ID=
```

---

## Go-Live Checklist

1. Set `ENABLE_ERIC_CALLS=true` only when phone line + compliance are validated.
2. Confirm Twilio SMS and Gmail delivery both work from the tool endpoints.
3. Confirm callback scheduling creates calendar events successfully.
4. Run one end-to-end test call: details request, callback request, demo link, payment link.
5. Verify DNC and opt-out blocking on follow-up attempts.
