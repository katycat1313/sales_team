"""
VAPI Integration Tool
---------------------
Handles AI phone calls for GBP sales outreach.

Flow:
1. Agent finds prospect with broken GBP
2. Dashboard shows prospect + CALL button
3. Katy clicks CALL → this tool triggers VAPI
4. VAPI calls the prospect using the pitch script
5. VAPI fetches prospect details via webhook mid-call
6. When prospect shows interest → transfers to Katy's phone
7. Katy closes the deal
"""

import os
import json
import httpx
from typing import Optional

VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_BASE_URL = "https://api.vapi.ai"

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json"
}


# ─── PITCH SCRIPTS (branch by GBP condition) ──────────────────────────────────

PITCH_SCRIPTS = {
    "NO_PROFILE": """
You're calling on behalf of Katy from iFixProfiles.
The business has NO Google Business Profile at all.

OPENER:
"Hi, is this [owner_name]? Hey [owner_name], my name is [agent_name] —
I was actually researching [business_type] businesses in [city] and when
I searched for [business_name] on Google, nothing came up at all.
You have no Google Business Profile which means right now, anyone
searching for a [business_type] near them cannot find you.
We went ahead and did a quick audit — do you have just a minute
to go over what we found?"
""",

    "INCOMPLETE_PROFILE": """
You're calling on behalf of Katy from iFixProfiles.
The business has a GBP but it's missing key information.

OPENER:
"Hi, is this [owner_name]? Hey [owner_name], my name is [agent_name] —
I came across your Google Business Profile for [business_name]
and I noticed it's missing quite a bit — specifically [missing_items].
When customers land on an incomplete profile like that, most of them
just move on to a competitor. We went ahead and did a quick audit —
do you have just a minute to go over what we found?"
""",

    "OUTDATED_PROFILE": """
You're calling on behalf of Katy from iFixProfiles.
The business has a GBP but the info is outdated.

OPENER:
"Hi, is this [owner_name]? Hey [owner_name], my name is [agent_name] —
I came across your Google Business Profile for [business_name]
and noticed some of the information looks like it hasn't been
updated in a while — things like [outdated_items].
That can send customers to the wrong place or turn them away entirely.
We did a quick audit — do you have just a minute to go over what we found?"
""",

    "INCORRECT_PROFILE": """
You're calling on behalf of Katy from iFixProfiles.
The business has incorrect info on their GBP.

OPENER:
"Hi, is this [owner_name]? Hey [owner_name], my name is [agent_name] —
I came across your Google Business Profile for [business_name]
and I actually noticed some of the information on there is incorrect —
[incorrect_items]. That's a real problem because customers trying
to reach you are getting the wrong information.
We went ahead and pull a quick audit — do you have just a minute
to go over what we found?"
"""
}

AUDIT_REVEAL = """
After they say yes to hearing the audit:
"So what we found is [specific_issues].
Now the reason that matters is — Google decides who shows up
in search results based on how complete and accurate the profile is.
Right now yours is scoring low, which means your competitors
are showing up above you every single time someone searches
for [business_type] in [city].

What we do is come in and fix all of that — get you fully optimized
so you're showing up when people are actually searching.
Most of our clients start seeing more calls within the first week.
It's $197 — we handle the whole thing — and then $98 a month
to keep it maintained so your competitors don't creep back up on you.
And if you don't see improvement within 30 days, we'll refund you.
Obviously it's completely up to you — I just wanted to make sure
you knew what was happening on your listing."
"""

OBJECTION_HANDLERS = """
OBJECTION HANDLERS — use these word for word:

"Not interested":
"Totally understand — can I share just one thing we found?
It'll take 30 seconds and honestly you can decide from there."

"Too expensive / how much is it?":
"It's $197 — we handle the whole thing — and then $98 a month
to keep it maintained so you stay ahead of competitors.
One new customer from Google pays for this twice over.
And if you don't see improvement within 30 days, we'll refund you."

"Already have someone handling it":
"That's great — when did they last update it?
Because right now it's showing [specific issue]
which is actively sending people away."

"Send me an email":
"Absolutely — what's the best address?
I'll send over the full audit we ran right now."

"Need to think about it":
"Of course, makes total sense.
What's the main thing you'd want to think through?
Maybe I can answer that right now."

"Too busy":
"That's exactly why people use us —
you don't touch a thing. We handle everything
and send you a confirmation when it's done."

HANDOFF TRIGGER:
When prospect says ANYTHING like: "okay", "how does it work",
"tell me more", "that makes sense", "how much again",
"when can you do it" — say:

"Perfect — let me get Katy on the line,
she handles all the details and can
get this taken care of for you today."

Then transfer the call.
"""

FULL_SYSTEM_PROMPT = """
You are a professional sales assistant calling on behalf of Katy from iFixProfiles.
iFixProfiles fixes Google Business Profiles for local businesses.

YOUR PERSONALITY:
- Warm, confident, conversational — not robotic or salesy
- You sound like a real person, not a script reader
- You listen more than you talk
- You use the prospect's name naturally throughout
- You give them space to respond after every point

YOUR RULES:
- Never mention more than 3 specific problems
- Always use "you/your" not "we/our" when talking about their problems
- Always explain WHY something matters with "because"
- Never pressure — always remind them it's their choice
- If they ask if you're AI, say you're Katy's assistant and redirect to their listing
- Keep responses concise — this is a phone call, not a presentation

PERSUASION PRINCIPLES:
- Lead with their pain (lost customers), not your solution
- Create curiosity before revealing audit results
- Use foot-in-the-door: get small yeses before the big ask
- Verbal affirmations: "right", "absolutely", "that makes sense"
- Reflective listening: repeat back what they say before responding

PRICING:
- $197 paid upfront — full GBP optimization, we handle everything
- $98/month ongoing management after that
  → Monthly posts, review monitoring, updates, keeps them ranking
- 30-day money back guarantee if they don't see improvement

HOW TO PRESENT PRICING:
"It's $197 — we handle the whole thing — and then $98 a month
to keep it maintained so your competitors don't creep back up.
And if you don't see improvement within 30 days, we'll refund you."

If they hesitate on price:
"One new customer from Google covers this twice over.
And most of our clients say their phone started ringing
more within the first week."

NEVER mention a deposit or split payment. It's $197, paid today, done.

CALL FUNCTION:
When you need the prospect's business details, call get_prospect_details.
When prospect shows buying interest, call transfer_to_katy.
"""


# ─── VAPI API FUNCTIONS ────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(VAPI_API_KEY)


async def create_assistant(phone_number_id: str, katy_phone: str) -> dict:
    """Create the GBP sales assistant in VAPI."""
    assistant = {
        "name": "iFixProfiles Sales Assistant",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "systemPrompt": FULL_SYSTEM_PROMPT + "\n\n" + AUDIT_REVEAL + "\n\n" + OBJECTION_HANDLERS,
            "temperature": 0.7,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "rachel",  # Professional, warm female voice
        },
        "firstMessage": "Hi, is this [owner_name]?",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_prospect_details",
                    "description": "Get the specific GBP issues found for the business being called",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone": {
                                "type": "string",
                                "description": "The phone number being called"
                            }
                        },
                        "required": ["phone"]
                    }
                },
                "server": {
                    "url": "{{WEBHOOK_URL}}/vapi/get-prospect"
                }
            },
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": katy_phone,
                        "message": "Perfect — let me get Katy on the line for you right now."
                    }
                ]
            }
        ],
        "endCallMessage": "Thanks so much for your time. Have a great day!",
        "endCallPhrases": ["goodbye", "bye", "not interested", "remove me"],
        "recordingEnabled": True,
        "hipaaEnabled": False,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{VAPI_BASE_URL}/assistant",
            headers=HEADERS,
            json=assistant,
            timeout=30
        )
        return resp.json()


async def list_phone_numbers() -> list:
    """List available phone numbers in VAPI account."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{VAPI_BASE_URL}/phone-number",
            headers=HEADERS,
            timeout=15
        )
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
    # Full research intel — everything the researcher found
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
    """
    Trigger an outbound call to a prospect.
    Katy is silently conferenced in from the start so she hears everything.
    When Alex hands off, Alex drops and Katy is already on the line.

    gbp_condition: NO_PROFILE | INCOMPLETE_PROFILE | OUTDATED_PROFILE | INCORRECT_PROFILE
    issues: list of specific problems found on their GBP
    """
    if not is_configured():
        return {"error": "VAPI_API_KEY not set in .env"}

    if not katy_phone:
        katy_phone = os.getenv("KATY_PHONE", "")

    # Format issues for the call
    issues_text = ", ".join(issues[:3]) if issues else "missing information"

    # Build full business intel briefing for Eric
    intel_lines = [
        f"BUSINESS INTEL FOR THIS CALL — study this before dialing:",
        f"Business Name: {business_name}",
        f"Owner/Contact: {prospect_name}",
        f"Business Type: {business_type or 'local business'}",
        f"City: {city}",
        f"Phone: {prospect_phone}",
        f"Website: {website or 'unknown'}",
        f"GBP Condition: {gbp_condition}",
        f"Specific GBP Problems Found: {issues_text}",
    ]
    if rating:
        intel_lines.append(f"Google Rating: {rating} stars ({review_count or '?'} reviews)")
    if years_in_business:
        intel_lines.append(f"Years in Business: {years_in_business}")
    if services:
        intel_lines.append(f"Services They Offer: {services}")
    if description:
        intel_lines.append(f"About the Business: {description}")
    if extra_intel:
        intel_lines.append(f"Additional Intel: {extra_intel}")

    intel_lines += [
        "",
        "USE THIS INTEL THROUGHOUT THE CALL:",
        "- Reference their city and business type naturally",
        "- If they have reviews, mention their rating as a strength and say their profile should match it",
        "- If you know their services, connect the GBP problems to lost customers for THOSE specific services",
        "- If they have a website but it's not on their GBP, that's an easy win to mention",
        "- Make them feel like you specifically researched THEIR business, not just any business",
    ]

    business_intel_prompt = "\n".join(intel_lines)

    # Build transfer destination — Katy is already listening so this just
    # unmutes her leg and drops Alex completely
    transfer_destination = {
        "type": "number",
        "number": f"+1{katy_phone.replace('+1','').replace('-','').replace(' ','')}",
        "transferPlan": {
            "mode": "blind-transfer",  # Alex drops immediately, no lingering
        },
        "message": "Perfect — let me bring Katy in right now."
    }

    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": prospect_phone,
            "name": prospect_name,
        },
        "assistantOverrides": {
            "variableValues": {
                "owner_name": prospect_name,
                "business_name": business_name,
                "gbp_condition": gbp_condition,
                "specific_issues": issues_text,
                "city": city,
                "business_type": business_type or "business",
                "website": website or "not found",
                "rating": rating or "unknown",
                "review_count": review_count or "0",
                "services": services or "their services",
                "years_in_business": years_in_business or "unknown",
                "business_intel": business_intel_prompt,
            },
            "firstMessage": f"Hi, is this {prospect_name}?",
        },
        "metadata": {
            "business_name": business_name,
            "gbp_condition": gbp_condition,
            "katy_phone": katy_phone,
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{VAPI_BASE_URL}/call",
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        result = resp.json()
        # Katy listens via the dashboard WebSocket (monitor.listenUrl) — no phone call needed
        return result


async def get_account_balance() -> dict:
    """Check VAPI account credits."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{VAPI_BASE_URL}/billing",
            headers=HEADERS,
            timeout=15
        )
        return resp.json()
