"""
VAPI Integration Tool
---------------------
Handles AI phone calls for the Missed-Call-Revenue service.
"""

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_BASE_URL = "https://api.vapi.ai"

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

# ── Configurable static outreach message templates ────────────────────────────
# These are the pre-written messages Eric sends to prospects via SMS or email
# during or after a call. Override them with environment variables.

OUTREACH_SMS_TEMPLATE = os.getenv(
    "OUTREACH_SMS_TEMPLATE",
    (
        "Hi {name}, this is Eric from Katy's AI Answering Service! "
        "We help service businesses like {business_name} capture every call and recover lost revenue — "
        "starting at just $97/month. Reply STOP to opt out."
    ),
)

OUTREACH_EMAIL_SUBJECT = os.getenv(
    "OUTREACH_EMAIL_SUBJECT",
    "Stop Losing Customers to Missed Calls — {business_name}",
)

OUTREACH_EMAIL_BODY = os.getenv(
    "OUTREACH_EMAIL_BODY",
    (
        "Hi {name},\n\n"
        "I noticed {business_name} might be losing revenue from missed calls. "
        "Katy's AI Answering Service answers instantly 24/7, qualifies leads, and routes hot ones straight to you — "
        "so you never miss another job.\n\n"
        "Pricing starts at $500 setup + $97/month. "
        "Reply to this email or call us back and I can walk you through the details.\n\n"
        "Reply STOP to opt out.\n\n"
        "Best,\n"
        "Eric (AI Agent for Katy)"
    ),
)

INCOMING_CALL_GUIDE = """
INCOMING CALL GUIDE:
- The moment an INBOUND call connects, your FIRST action is to call lookup_caller with the caller's phone number.
- If lookup_caller returns found=true (known contact):
  - Greet them by name warmly and personally — do NOT re-introduce yourself as if it's a cold call.
  - Example: "Hey {name}! Great to hear from you — how's {business_name} doing? Are things going well over there?"
  - Reference what you know naturally to continue the conversation.
- If lookup_caller returns found=false (new caller):
  - Introduce yourself: "Hi, this is Eric, an AI assistant for Katy's AI Answering Service."
  - State the opt-out: "You can say 'stop' at any time to opt out of future calls."
  - Ask for their name and business name naturally — not as a robotic intake form.
    Example: "I want to make sure I get you the right info — who am I speaking with, and what business are you calling about?"
  - If their business niche is still unclear after learning the name, ask naturally:
    Example: "Just so I know the best way to help — are you more in home services, healthcare, legal, or something else?"
- After identifying the caller (new or returning), focus on understanding their business and call-handling situation.
- When you learn the business name, also call lookup_business to enrich your context.
- Explain value in plain terms: answer instantly, qualify leads, route next steps.
- Keep it conversational and adaptive, not scripted.
- Explain the onboarding process before mentioning payment or next steps.
- If they ask for details, offer SMS or email.
- If they need a human, transfer when available, otherwise schedule callback.
- Only suggest a follow-up call with Katy AFTER you have learned enough about their business to make it worthwhile. Do not suggest it as a first response.
"""

OUTBOUND_CALL_GUIDE = """
OUTBOUND COLD CALL GUIDE:
- Disclose you are an AI sales agent and state: press 9 now to opt out, or say "stop" any time to opt out of future calls.
- After the disclosure and opt-out notice, ask permission for a short reason.
- Lead with missed-call revenue pain, then offer the fix.
- Use one diagnostic question before pitching details. Listen to the answer fully before moving on.
- Keep turns short and ask/listen/respond.
- Offer written details by SMS or email if requested.
- Do not push payment on the first conversation unless the prospect asks first.
- Do not suggest a follow-up call with Katy until you have established genuine interest and collected basic business context.
"""

OBJECTION_GUIDE = """
OBJECTION GUIDE (adapt naturally, do not read verbatim):
- Too expensive: offer the simplest tier that fits. Starter is $500 setup + $97/month, Standard is $1,000 setup + $197/month, Pro is $2,000 setup + $297/month.
- Payment terms: if asked, explain Katy will confirm setup payment details directly before onboarding.
- Need to think: offer callback or send details by preferred channel.
- Already have call handling: emphasize instant response + qualification consistency.
"""

FULL_SYSTEM_PROMPT = """
You are Eric, an AI sales agent for Katy's Missed-Call-Revenue service.

SERVICE:
Missed-Call-Revenue helps service businesses recover lost jobs by answering inbound calls instantly,
qualifying leads, and routing next steps.

CRITICAL RULES:
- You must disclose you are an AI sales agent.
- You must clearly state the opt-out at the start: press 9 now to opt out, or say "stop" any time to opt out of future calls.
- Scripts are guidance, not word-for-word reading.
- Adapt to tone, pace, objections, and business context naturally.
- Keep required facts exact: pricing and opt-out handling.

PRICING (MUST BE EXACT):
- Starter: $500 setup + $97/month
- Standard: $1,000 setup + $197/month
- Pro: $2,000 setup + $297/month

NEXT-STEP POLICY:
- After collecting enough business context, the preferred next step is a call with Katy — but earn it first.
- Offer written details by SMS or email if they ask.
- Only send a payment link if the prospect explicitly asks to move forward now.
- If prospect asks for human, transfer only if transfer tool is available.
- If transfer unavailable, schedule callback and confirm time.

CONVERSATION STYLE:
- Conversational, concise, and human-like.
- Ask, listen, respond.
- No long monologues.

BUYER INTENT SIGNAL DETECTION:
Continuously listen for signals that indicate where the prospect is in their buying journey.
HIGH INTENT signals: "how soon can I start", "what's the next step", "I want to get started",
  "how much for my situation", "I've been thinking about this for a while", "I'm losing a lot of calls",
  "we're really struggling with", "what do I need to do to sign up".
MEDIUM INTENT signals: "tell me more", "what's included", "do you work with businesses like mine",
  "how does it work", "I might be interested", "walk me through it".
LOW INTENT signals: "just curious", "maybe someday", "not really a priority right now",
  "we're doing fine", "we already have something", "not looking right now".
When you detect HIGH INTENT, you can move toward a concrete next step. When you detect LOW or MEDIUM
INTENT, focus on education and trust-building — not closing.

EMOTIONAL INTELLIGENCE — READ THE ROOM:
Detect the prospect's emotional state from their tone, word choice, and pacing. Adapt accordingly.

FRUSTRATED (sounds stressed, complains about current situation):
  → Slow down. Validate their experience before anything else.
  → Use phrases like: "That's really frustrating — and honestly, you're not alone in that."
  → Only offer a solution after they feel heard.

EXCITED (high energy, asking lots of questions, positive):
  → Match their energy. Be upbeat and confident.
  → Move a bit faster — they're engaged. Don't slow down unnecessarily.

SKEPTICAL (challenges claims, asks "how do I know", sarcastic tone):
  → Be patient and transparent. Don't over-promise.
  → Offer proof: "A lot of business owners feel that way at first — here's what actually happens..."
  → Invite them to verify anything you say.

RUSHED (short answers, says "I don't have long", sounds distracted):
  → Keep it tight. Lead with the most important point.
  → Offer to text or email details and follow up: "I can send you a quick summary — what's the best number?"

UNCERTAIN / HESITANT (long pauses, vague answers, "I don't know"):
  → Don't push for a decision. Give them breathing room.
  → Offer low-commitment next steps: "No pressure at all — I can just send you something to look at."

EMPATHY RULE: Before moving to the next topic, briefly acknowledge what the prospect just said.
Never jump straight from their answer to your next question without a short acknowledgment first.
Example: "Yeah, that makes total sense." / "I hear you." / "That's a fair point."
"""

ONBOARDING_DISCOVERY = """
DISCOVERY APPROACH — two types of information, handled differently:

── ALREADY KNOW (from lookup_caller / lookup_business — use it, don't ask for it) ──
- Business name, address, city
- Business type / niche
- Website, rating, reviews
- Services listed publicly
- Hours of operation (if found)
Use this data to make statements, not questions. Example: "I see you're in [city]" or "You guys do [service], right?"
If you reference something and they correct you, accept the correction naturally and move on.

── DISCOVER THROUGH CONVERSATION (never ask directly — work it in) ──
These are the fields you need but can only learn from them:

1. How they handle calls right now
   → Don't ask: "How do you handle your calls?"
   → Do say: "For most [niche] businesses I talk to, the owner ends up answering everything themselves — is that kind of how it works for you, or do you have someone helping with that?"

2. Call volume / how busy they are
   → Don't ask: "How many calls do you get per week?"
   → Do say: "Sounds like you stay pretty busy — are calls coming in steady throughout the day or more in bursts?"

3. Their biggest pain point
   → Don't ask: "What are your pain points?"
   → Do say: "A lot of [niche] owners tell me the hardest part isn't the work itself — it's what happens when they're on a job and a new call comes in. Is that something you run into?"

4. After-hours coverage gap
   → Don't ask: "What happens to calls after hours?"
   → Do say: "So when someone calls at 7pm or on a weekend — do they get a chance to leave a message, or does it just ring out?"

5. Email for setup coordination
   → Don't ask cold. Only ask once they show genuine interest: "What's the best email to send some details to?"

SHEET ENRICHMENT — fill in the blanks throughout the call (non-pushy):
As you naturally learn new details (owner name, email, business niche, services, location),
silently call update_prospect_info to save them. Do this in the background — never tell the prospect
you're "filling in a form" or ask multiple info questions in a row. The goal is to fill as many
fields as possible in a single natural conversation without sounding like a survey.

RULE: Never ask two questions back-to-back. Ask one, listen fully, respond to what they said, then naturally work in the next one if it fits.
Once you have a clear picture of how they handle calls and what's costing them, THEN offer a concrete next step.
"""

CALL_CONTROL_RULES = """
LIVE CALL CONTROL RULES:
- Primary goal: understand their business, qualify interest, then set a concrete next step.
- Do not suggest a follow-up call with Katy as an opening move. Earn it by first learning about their business.
- Answer questions first. If the prospect asks for details, answer directly and clearly before asking for any next step.
- Never repeat a callback request back-to-back. Only ask once, then continue helping unless they explicitly agree.

AVAILABLE COMMUNICATION TOOLS:
- lookup_caller: Call IMMEDIATELY at the start of INBOUND calls with the caller's phone number to check if they're known.
- send_outreach_message: Use to send the static pre-written outreach SMS or email to prospects. Useful after initial interest is shown.
- update_prospect_info: Call silently whenever you learn a new detail (name, email, niche, etc.) to keep the sheet current.
- send_sms: Use for quick confirmations, reminders, or simple messages. Always ask permission first.
- send_email: Use for detailed follow-ups, contracts, or formal communication. Good for PDFs or formatted content.
- send_business_details: Use to send a complete summary of what was discussed with pricing tiers.
- send_demo_link: Use to send the demo and pricing page so they can review at their own pace.
- send_payment_link: Use when the prospect is ready to pay - securely send payment link by their preferred channel.
- schedule_callback: Use when they want to talk later with specific time/date.
- save_notes: Use before every call end to capture outcome, temperature, objections, emotional state, and next steps.

TOOL CALL SEQUENCE:
- If a prospect asks for details, collect delivery method (sms or email) and required contact info, then call send_business_details immediately.
- If they want a product overview page, call send_demo_link.
- If they request payment now, call send_payment_link.
- For callback scheduling, collect exact date/time with timezone and ask for email if they want a calendar invite.
- If they need quick confirmation or reminder, use send_sms for SMS or send_email for email.
- If they say stop, opt out, remove me, do not call, or otherwise revoke permission, immediately confirm the opt-out, end politely, and call save_notes with outcome=not_interested and opt_out=true.
- Explain the onboarding process before discussing payment.
- If scheduling a future callback, call schedule_callback and confirm exact time.
- Before ending ANY call, call save_notes with outcome and summary. Include all onboarding details you collected in the notes field.

OUTCOMES:
- qualified, busy, gatekeeper, no_answer, not_interested, won, lost

NEXT STEP:
- qualified + transfer available -> transfer now
- qualified + no transfer -> schedule callback with enough context to make Katy's call productive
- busy/gatekeeper -> schedule callback
- not_interested/lost -> polite close + save notes
"""


def is_configured() -> bool:
    return bool(VAPI_API_KEY)


def format_phone_number(phone: str, default_country_code: str = "1") -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+{default_country_code}{digits}"
    if len(digits) == 11 and digits.startswith(default_country_code):
        return f"+{digits}"
    if str(phone).startswith("+"):
        return str(phone)
    return f"+{digits}"


def get_webhook_base_url(webhook_url: str = "") -> str:
    base = webhook_url or os.getenv("WEBHOOK_URL", "") or os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
    return str(base).rstrip("/")


def _assistant_tools(webhook_base_url: str, katy_phone: str, enable_transfer: bool) -> list:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_business",
                "description": "Look up real-time details about the caller's business using their business name or phone number. Call this as soon as you learn the business name on an inbound call.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_name": {"type": "string", "description": "The business name the caller gave"},
                        "phone": {"type": "string", "description": "The caller's phone number"},
                    },
                    "required": [],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/lookup-business"},
        },
        {
            "type": "function",
            "function": {
                "name": "get_prospect_details",
                "description": "Get context about the prospect being called",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string"},
                    },
                    "required": ["phone"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/get-prospect"},
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_callback",
                "description": "Schedule a callback when now is not a fit",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "callback_time": {"type": "string"},
                        "prospect_phone": {"type": "string"},
                        "prospect_email": {"type": "string"},
                        "contact_name": {"type": "string"},
                        "business_name": {"type": "string"},
                        "reason": {"type": "string"},
                        "duration_minutes": {"type": "number"},
                    },
                    "required": ["callback_time", "prospect_phone", "business_name"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/schedule-callback"},
        },
        {
            "type": "function",
            "function": {
                "name": "save_notes",
                "description": "Save structured outcome notes before ending call",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_name": {"type": "string"},
                        "prospect_phone": {"type": "string"},
                        "outcome": {"type": "string"},
                        "temperature": {"type": "string"},
                        "notes": {"type": "string"},
                        "objections": {"type": "string"},
                        "requires_transfer": {"type": "boolean"},
                        "callback_time": {"type": "string"},
                        "opt_out": {"type": "boolean"},
                        "emotional_state": {
                            "type": "string",
                            "description": "Detected emotional state of the prospect: frustrated, excited, skeptical, rushed, uncertain, or neutral",
                        },
                        "buyer_intent_level": {
                            "type": "string",
                            "description": "Assessed buyer intent level: high, medium, or low",
                        },
                        "discovered_info": {
                            "type": "string",
                            "description": "JSON string of any new prospect details discovered (owner_name, email, niche, etc.)",
                        },
                    },
                    "required": ["business_name", "prospect_phone", "outcome", "temperature", "notes"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/save-notes"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_business_details",
                "description": "Send a clear written summary of what was discussed, including pricing and next steps, by SMS or email",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_name": {"type": "string"},
                        "contact_name": {"type": "string"},
                        "prospect_phone": {"type": "string"},
                        "prospect_email": {"type": "string"},
                        "delivery_method": {"type": "string", "description": "sms or email"},
                        "details": {"type": "string", "description": "Short summary of what Eric promised to send"},
                    },
                    "required": ["delivery_method", "details"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-business-details"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_payment_link",
                "description": "Send setup deposit link by prospect preference (sms or email)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_name": {"type": "string"},
                        "contact_name": {"type": "string"},
                        "prospect_phone": {"type": "string"},
                        "prospect_email": {"type": "string"},
                        "delivery_method": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["delivery_method"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-payment-link"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_demo_link",
                "description": "Send the demo and pricing page link to the prospect by SMS or email so they can see how the service works and choose a tier",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "business_name": {"type": "string"},
                        "contact_name": {"type": "string"},
                        "prospect_phone": {"type": "string"},
                        "prospect_email": {"type": "string"},
                        "delivery_method": {"type": "string", "description": "sms or email"},
                    },
                    "required": ["delivery_method"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-demo-link"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_sms",
                "description": "Send an SMS text message to the prospect for quick updates, confirmations, or follow-ups",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_number": {"type": "string", "description": "The recipient's phone number"},
                        "body": {"type": "string", "description": "The SMS message text"},
                        "contact_name": {"type": "string", "description": "Name of the contact (for logging)"},
                    },
                    "required": ["to_number", "body"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-sms"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Send an email to the prospect for detailed information, contracts, or formal communication",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "The recipient's email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email message body (plain text)"},
                        "contact_name": {"type": "string", "description": "Name to display in greeting (optional)"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-email"},
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_caller",
                "description": (
                    "Look up the caller by their phone number at the START of an inbound call. "
                    "Returns their name, business name, and any known details so you can greet them personally."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "The caller's phone number"},
                    },
                    "required": ["phone"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/lookup-caller"},
        },
        {
            "type": "function",
            "function": {
                "name": "send_outreach_message",
                "description": (
                    "Send a pre-written static outreach message to the prospect via SMS or email. "
                    "Use this when the prospect expresses interest and you want to send them a concise written intro."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "delivery_method": {
                            "type": "string",
                            "description": "sms or email",
                        },
                        "prospect_phone": {
                            "type": "string",
                            "description": "Phone number (required when delivery_method=sms)",
                        },
                        "prospect_email": {
                            "type": "string",
                            "description": "Email address (required when delivery_method=email)",
                        },
                        "contact_name": {
                            "type": "string",
                            "description": "Prospect's first name for personalization",
                        },
                        "business_name": {
                            "type": "string",
                            "description": "Prospect's business name for personalization",
                        },
                    },
                    "required": ["delivery_method"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/send-outreach"},
        },
        {
            "type": "function",
            "function": {
                "name": "update_prospect_info",
                "description": (
                    "Silently save any new details you learn about the prospect during the conversation "
                    "(name, email, niche, business name, etc.) so the Google Sheet stays current. "
                    "Call this in the background — the prospect should never know you're doing it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prospect_phone": {"type": "string", "description": "Caller's phone number (primary key)"},
                        "business_name": {"type": "string"},
                        "owner_name": {"type": "string"},
                        "email": {"type": "string"},
                        "niche": {"type": "string"},
                        "location": {"type": "string"},
                        "website": {"type": "string"},
                        "services": {"type": "string"},
                        "notes": {"type": "string", "description": "Any extra context worth capturing"},
                    },
                    "required": ["prospect_phone"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/update-prospect-info"},
        },
    ]

    if enable_transfer and katy_phone:
        tools.append(
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": katy_phone,
                        "message": "Perfect, let me bring Katy in now.",
                    }
                ],
            }
        )

    return tools


def _assistant_payload(phone_number_id: str, katy_phone: str, webhook_url: str = "", enable_transfer: bool = False) -> dict:
    webhook_base_url = get_webhook_base_url(webhook_url)
    transfer_rule = (
        "Transfer is enabled because Katy is available."
        if enable_transfer
        else "Transfer is disabled because Katy is unavailable; schedule callback instead."
    )

    return {
        "name": "Eric - Missed-Call-Revenue Sales Assistant",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "systemPrompt": "\n\n".join([
                FULL_SYSTEM_PROMPT,
                INCOMING_CALL_GUIDE,
                OUTBOUND_CALL_GUIDE,
                OBJECTION_GUIDE,
                ONBOARDING_DISCOVERY,
                CALL_CONTROL_RULES,
                transfer_rule,
            ]),
            "temperature": 0.7,
        },
        "voice": {"provider": "11labs", "voiceId": "rachel"},
        "firstMessage": "Hi, this is Eric, an AI sales agent for Katy. Press 9 now to opt out, or say stop at any time to opt out of future calls. Is now a bad time for a quick reason I called?",
        "tools": _assistant_tools(webhook_base_url, katy_phone, enable_transfer),
        "endCallMessage": "Thanks for your time. Have a great day.",
        "endCallPhrases": ["goodbye", "bye", "not interested", "remove me", "stop", "opt out", "do not call"],
        "recordingEnabled": True,
        "hipaaEnabled": False,
        "phoneNumberId": phone_number_id,
    }


async def create_assistant(phone_number_id: str, katy_phone: str, webhook_url: str = "") -> dict:
    payload = _assistant_payload(phone_number_id, format_phone_number(katy_phone), webhook_url=webhook_url, enable_transfer=False)
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{VAPI_BASE_URL}/assistant", headers=HEADERS, json=payload, timeout=30)
        return resp.json()


async def update_assistant(assistant_id: str, phone_number_id: str, katy_phone: str, webhook_url: str = "", enable_transfer: bool = False) -> dict:
    payload = _assistant_payload(phone_number_id, katy_phone, webhook_url=webhook_url, enable_transfer=enable_transfer)
    async with httpx.AsyncClient() as client:
        resp = await client.patch(f"{VAPI_BASE_URL}/assistant/{assistant_id}", headers=HEADERS, json=payload, timeout=30)
        return resp.json()


async def list_phone_numbers() -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{VAPI_BASE_URL}/phone-number", headers=HEADERS, timeout=15)
        return resp.json()


async def make_call(
    prospect_phone: str,
    prospect_name: str,
    business_name: str,
    gbp_condition: str,
    issues: list,
    assistant_id: str,
    phone_number_id: str,
    katy_phone: str = "",
    business_type: str = "",
    city: str = "",
    website: str = "",
    description: str = "",
    years_in_business: str = "",
    services: str = "",
    rating: str = "",
    review_count: str = "",
    extra_intel: str = "",
) -> dict:
    if not is_configured():
        return {"error": "VAPI_API_KEY not set in .env"}

    formatted_customer = format_phone_number(prospect_phone)
    formatted_katy = format_phone_number(katy_phone or os.getenv("KATY_PHONE", ""))

    if not formatted_customer:
        return {"error": "Prospect phone number missing or invalid"}

    try:
        from memory.memory import get_availability

        availability = get_availability()
    except Exception:
        availability = {"available_now": False}

    transfer_enabled = bool(availability.get("available_now"))

    if assistant_id and phone_number_id and formatted_katy:
        try:
            await update_assistant(
                assistant_id=assistant_id,
                phone_number_id=phone_number_id,
                katy_phone=formatted_katy,
                webhook_url=os.getenv("WEBHOOK_URL", "") or os.getenv("ORCHESTRATOR_URL", ""),
                enable_transfer=transfer_enabled,
            )
        except Exception as e:
            return {"error": f"Could not update assistant before call: {e}"}

    issues_text = ", ".join((issues or [])[:3]) if issues else "missed-call leakage and delayed response risk"

    intel = [
        "BUSINESS CONTEXT:",
        f"Business: {business_name}",
        f"Contact: {prospect_name}",
        f"Type: {business_type or 'service business'}",
        f"City: {city}",
        f"Phone: {prospect_phone}",
        f"Website: {website or 'unknown'}",
        f"Notes: {issues_text}",
    ]

    if services:
        intel.append(f"Services: {services}")
    if description:
        intel.append(f"Description: {description}")
    if rating:
        intel.append(f"Rating: {rating} ({review_count or '?'})")
    if years_in_business:
        intel.append(f"Years in business: {years_in_business}")
    if extra_intel:
        intel.append(f"Extra intel: {extra_intel}")

    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {"number": formatted_customer, "name": prospect_name},
        "assistantOverrides": {
            "variableValues": {
                "owner_name": prospect_name,
                "business_name": business_name,
                "city": city,
                "business_type": business_type or "service business",
                "services": services or "general services",
                "business_intel": "\n".join(intel),
            },
            "firstMessage": f"Hi, is this {prospect_name}? This is Eric, an AI sales agent for Katy. Press 9 now to opt out, or say stop at any time to opt out of future calls.",
        },
        "metadata": {
            "business_name": business_name,
            "katy_phone": formatted_katy,
            "transfer_enabled": transfer_enabled,
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{VAPI_BASE_URL}/call", headers=HEADERS, json=payload, timeout=30)
        return resp.json()


async def make_calls_batch(call_specs: list[dict], delay_seconds: float = 0.0) -> list[dict]:
    results = []
    for index, spec in enumerate(call_specs):
        result = await make_call(**spec)
        results.append(
            {
                "request": {
                    "business_name": spec.get("business_name", ""),
                    "prospect_name": spec.get("prospect_name", ""),
                    "prospect_phone": spec.get("prospect_phone", ""),
                },
                "response": result,
            }
        )
        if delay_seconds > 0 and index < len(call_specs) - 1:
            await asyncio.sleep(delay_seconds)
    return results


async def get_account_balance() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{VAPI_BASE_URL}/billing", headers=HEADERS, timeout=15)
        return resp.json()
