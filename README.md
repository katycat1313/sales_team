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
On inbound calls: Eric looks up caller by phone → greets known contacts by name
        ↓
Eric answers questions and sends requested details (SMS/email)
        ↓
Prospect chooses next step: callback, demo link, or payment link
        ↓
Katy joins warm transfers and closes
```

---

## Conversation Intelligence

Eric continuously analyzes every conversation for:

- **Buyer intent signals** — HIGH ("how soon can I start"), MEDIUM ("tell me more"), LOW ("just curious") to determine when to push vs. educate.
- **Emotional state detection** — frustrated, excited, skeptical, rushed, uncertain — and adapts tone and pacing accordingly.
- **Sheet enrichment** — naturally fills in missing Google Sheet fields (name, email, niche, etc.) throughout the conversation without sounding robotic or pushy.

---

## SMS & Email Outreach

Eric can send a pre-written static outreach message during calls. The templates are fully configurable via environment variables.

### Default SMS template (`OUTREACH_SMS_TEMPLATE`)
```
Hi {name}, this is Eric from Katy's AI Answering Service! We help service businesses like {business_name} capture every call and recover lost revenue — starting at just $97/month. Reply STOP to opt out.
```

### Default Email subject (`OUTREACH_EMAIL_SUBJECT`)
```
Stop Losing Customers to Missed Calls — {business_name}
```

### Default Email body (`OUTREACH_EMAIL_BODY`)
```
Hi {name},

I noticed {business_name} might be losing revenue from missed calls...
[full template is in vapi_tool.py — override with OUTREACH_EMAIL_BODY env var]
```

Placeholders: `{name}` = prospect's first name, `{business_name}` = business name.

---

## Google Sheet Caller Lookup

On every **inbound call**, Eric immediately looks up the caller's phone number:

- **Known caller** → Greets them by name and asks how their business is using the service.
- **New caller** → Introduces itself, asks for name and business name. If the niche is unclear, asks naturally — not as a survey.

Set `BUSINESS_LOOKUP_URL` to your Apps Script read endpoint (GET with `?phone=+1...`) to enable Google Sheet lookup.

---

## Compliance + Delivery Features

- DNC scrubbing before outbound calls
- Opt-out handling and internal DNC recording
- Call outcome logging and compliance logs
- In-call fulfillment tools:
  - `lookup_caller` (inbound personalization)
  - `send_outreach_message` (static SMS/email outreach)
  - `update_prospect_info` (silent mid-call sheet enrichment)
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
- SendGrid email delivery
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
# ── Voice agent (VAPI) ────────────────────────────────────────────
VAPI_API_KEY=                    # Required — your VAPI API key
VAPI_ASSISTANT_ID=               # Eric assistant ID (created via /vapi/setup)
VAPI_PHONE_NUMBER_ID=            # Twilio phone number ID in VAPI
KATY_PHONE=                      # Katy's direct phone for warm transfers
ENABLE_ERIC_CALLS=false          # Set true only when ready to go live

# ── SMS delivery (Twilio) ─────────────────────────────────────────
TWILIO_ACCOUNT_SID=              # Twilio Account SID (also accepted as TWILIO_SSID)
TWILIO_AUTH_TOKEN=               # Twilio Auth Token (also accepted as TWILIO_TOKEN)
TWILIO_FROM_NUMBER=              # Twilio outbound number (also accepted as TWILIO_PHONE_NUMBER)

# ── Email delivery (SendGrid) ─────────────────────────────────────
SENDGRID_API_KEY=                # SendGrid API key (get free at sendgrid.com)
GMAIL_ADDRESS=                   # Sender email address (From:)

# ── Static outreach message templates (optional overrides) ────────
# Placeholders: {name} and {business_name}
OUTREACH_SMS_TEMPLATE=           # Override default SMS outreach text
OUTREACH_EMAIL_SUBJECT=          # Override default email subject
OUTREACH_EMAIL_BODY=             # Override default email body

# ── Google Sheets ─────────────────────────────────────────────────
GOOGLE_SHEET_ID=                 # Spreadsheet ID (from the sheet URL)
GOOGLE_SHEETS_WEBAPP_URL=        # Apps Script web app URL for push
GOOGLE_SHEETS_WEBAPP_TOKEN=      # Auth token for the Apps Script endpoint
GOOGLE_SHEETS_DEPLOYMENT_ID=     # Deployment ID (alternative to full URL)
# For read lookups (inbound caller identification):
BUSINESS_LOOKUP_URL=             # GET endpoint: returns JSON given ?phone=+1... or ?name=...

# ── Google Service Account (fallback for Sheets / Calendar) ───────
GOOGLE_SERVICE_ACCOUNT_JSON=     # Full path to service account JSON file
GOOGLE_SERVICE_ACCOUNT_FILE=     # Alternative path variable

# ── Callback scheduling (Google Calendar) ────────────────────────
GOOGLE_CALENDAR_ID=
GOOGLE_CALENDAR_TIMEZONE=America/Los_Angeles

# ── Payments ─────────────────────────────────────────────────────
STRIPE_SECRET_KEY=

# ── LLM (Vertex AI / Gemini) ─────────────────────────────────────
VERTEX_AI_PROJECT_ID=
VERTEX_AI_LOCATION=us-central1
GEMINI_API_KEY=                  # Free-tier fallback if no Vertex AI

# ── Optional ─────────────────────────────────────────────────────
CALENDLY_LINK=
DEMO_URL=
TELEGRAM_BOT_TOKEN=
KATY_TELEGRAM_ID=
WEBHOOK_URL=                     # Public URL of this orchestrator (for VAPI callbacks)
```

---

## SMS Setup (Twilio)

1. Sign up at [twilio.com](https://www.twilio.com) and buy a phone number.
2. Copy your **Account SID** and **Auth Token** from the Twilio console.
3. Add to `.env`:
   ```env
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_FROM_NUMBER=+15551234567
   ```
4. Test: `curl -X POST http://localhost:8000/vapi/send-sms -H "Content-Type: application/json" -d '{"to_number":"+15559876543","body":"Test"}'`

---

## Email Setup (SendGrid)

1. Sign up at [sendgrid.com](https://sendgrid.com) (free — 100 emails/day).
2. Go to **Settings → API Keys → Create API Key** (Full Access).
3. Verify your sender email (Settings → Sender Authentication).
4. Add to `.env`:
   ```env
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   GMAIL_ADDRESS=you@yourdomain.com
   ```
5. Test: `curl -X POST http://localhost:8000/vapi/send-email -H "Content-Type: application/json" -d '{"to":"you@example.com","subject":"Test","body":"Hello!"}'`

---

## Google Sheet Integration

### Push (writing prospect data)

Option A — Apps Script web app (recommended, no service account needed):
1. Open your Google Sheet → Extensions → Apps Script.
2. Deploy the provided `appsscript/webhook.gs` as a Web App (Execute as: Me, Access: Anyone).
3. Copy the deployment URL.
4. Add to `.env`: `GOOGLE_SHEETS_WEBAPP_URL=https://script.google.com/macros/s/.../exec`

Option B — Service account (full API access):
1. Create a service account in GCP Console → IAM → Service Accounts.
2. Download the JSON key and share your sheet with the service account email.
3. Add to `.env`: `GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/creds.json` and `GOOGLE_SHEET_ID=your_sheet_id`

### Read (inbound caller lookup)

For Eric to greet known callers by name, expose a read endpoint from your Apps Script:

```javascript
// In your Apps Script (doGet handler)
function doGet(e) {
  var phone = e.parameter.phone || "";
  var name  = e.parameter.name  || "";
  // Search sheet for matching row, return JSON
  // {"found": true, "owner_name": "...", "business_name": "...", ...}
}
```

Set `BUSINESS_LOOKUP_URL=https://script.google.com/macros/s/.../exec` (same or separate deployment).

---

## Running Tests

```bash
cd orchestrator
pip install pytest
python -m pytest tests/ -v
```

---

## Go-Live Checklist

1. Set `ENABLE_ERIC_CALLS=true` only when phone line + compliance are validated.
2. Confirm Twilio SMS and SendGrid email both work from the tool endpoints.
3. Confirm callback scheduling creates calendar events successfully.
4. Test inbound caller lookup: call your VAPI number from a phone in the sheet — Eric should greet you by name.
5. Test the static outreach message: trigger `send_outreach_message` via the VAPI tool.
6. Run one end-to-end test call: details request, callback request, demo link, payment link.
7. Verify DNC and opt-out blocking on follow-up attempts.

