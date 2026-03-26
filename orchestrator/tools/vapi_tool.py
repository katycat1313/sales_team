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

INCOMING_CALL_GUIDE = """
INCOMING CALL GUIDE:
- Disclose clearly you are Eric, an AI sales agent for Katy.
- Thank them for calling and ask one quick discovery question.
- Explain value in plain terms: answer instantly, qualify leads, route next steps.
- Keep it conversational and adaptive, not scripted.
- Default next step is a short follow-up call with Katy.
- Explain the onboarding process before mentioning payment.
- If they ask for details, offer SMS or email.
- If they need a human, transfer when available, otherwise schedule callback.
"""

OUTBOUND_CALL_GUIDE = """
OUTBOUND COLD CALL GUIDE:
- Disclose you are an AI sales agent and ask permission for a short reason.
- Lead with missed-call revenue pain, then offer the fix.
- Use one diagnostic question before pitching details.
- Keep turns short and ask/listen/respond.
- Primary next step is a short follow-up call with Katy.
- Offer written details by SMS or email if requested.
- Do not push payment on the first conversation unless the prospect asks first.
"""

OBJECTION_GUIDE = """
OBJECTION GUIDE (adapt naturally, do not read verbatim):
- Too expensive: setup is $2,000 one-time + $297 monthly upkeep.
- Payment terms: 50% down ($1,000) to start, remainder at go-live.
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
- Scripts are guidance, not word-for-word reading.
- Adapt to tone, pace, objections, and business context naturally.
- Keep required facts exact: pricing, payment split, and opt-out handling.

PRICING (MUST BE EXACT):
- $2,000 one-time setup
- $297 monthly upkeep
- 50% down ($1,000) to begin custom training
- Remaining 50% due at go-live

NEXT-STEP POLICY:
- Default goal is a short follow-up call with Katy.
- Offer written details by SMS or email if they ask.
- Only send a payment link if the prospect explicitly asks to move forward now.
- If prospect asks for human, transfer only if transfer tool is available.
- If transfer unavailable, schedule callback and confirm time.

CONVERSATION STYLE:
- Conversational, concise, and human-like.
- Ask, listen, respond.
- No long monologues.
"""

CALL_CONTROL_RULES = """
LIVE CALL CONTROL RULES:
- Primary goal: qualify interest and set a concrete next step.
- Default next step is a short follow-up call with Katy.
- Explain the onboarding process before discussing payment.
- Only if the prospect explicitly asks to start now should you ask SMS or email and call send_payment_link.
- Before ending, call save_notes with outcome and summary.

OUTCOMES:
- qualified, busy, gatekeeper, no_answer, not_interested, won, lost

NEXT STEP:
- qualified + transfer available -> transfer now
- qualified + no transfer -> schedule callback
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
                        "business_name": {"type": "string"},
                        "reason": {"type": "string"},
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
                    },
                    "required": ["business_name", "prospect_phone", "outcome", "temperature", "notes"],
                },
            },
            "server": {"url": f"{webhook_base_url}/vapi/save-notes"},
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
                CALL_CONTROL_RULES,
                transfer_rule,
            ]),
            "temperature": 0.7,
        },
        "voice": {"provider": "11labs", "voiceId": "rachel"},
        "firstMessage": "Hi, this is Eric, an AI sales agent for Katy. Is now a bad time for a quick reason I called?",
        "tools": _assistant_tools(webhook_base_url, katy_phone, enable_transfer),
        "endCallMessage": "Thanks for your time. Have a great day.",
        "endCallPhrases": ["goodbye", "bye", "not interested", "remove me"],
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
            "firstMessage": f"Hi, is this {prospect_name}? This is Eric, an AI sales agent for Katy.",
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
