import httpx, asyncio, json

VAPI_KEY = "e1d6e9f2-432b-4663-9671-d0fc8c1cb278"
ASSISTANT_ID = "7e7f245c-0671-4fc2-ba95-d6341caf4519"
WEBHOOK = "https://lovely-grapes-tie.loca.lt"

tools = [
    {
        "type": "transferCall",
        "destinations": [{
            "type": "number",
            "number": "+13044108850",
            "transferPlan": {"mode": "blind-transfer"},
            "message": "Perfect, let me bring Katy in right now."
        }]
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_callback",
            "description": "Schedule a callback when the prospect asks to be called back later",
            "parameters": {
                "type": "object",
                "properties": {
                    "callback_time": {"type": "string", "description": "When to call back e.g. Tuesday morning, tomorrow 2pm"},
                    "prospect_phone": {"type": "string", "description": "Their phone number"},
                    "business_name": {"type": "string", "description": "The business name"},
                    "reason": {"type": "string", "description": "Why they want a callback"}
                },
                "required": ["callback_time", "prospect_phone", "business_name"]
            }
        },
        "server": {"url": f"{WEBHOOK}/vapi/schedule-callback"}
    },
    {
        "type": "function",
        "function": {
            "name": "save_call_notes",
            "description": "Save a brief summary of this call before ending. Always call this before hanging up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prospect_phone": {"type": "string"},
                    "business_name": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["transferred", "callback_scheduled", "interested_no_transfer", "not_interested", "no_answer"],
                        "description": "What happened on this call"
                    },
                    "temperature": {
                        "type": "string",
                        "enum": ["hot", "warm", "cold"],
                        "description": "How interested the prospect was"
                    },
                    "notes": {"type": "string", "description": "Brief summary - what was discussed, what they said, any important details"},
                    "objections": {"type": "string", "description": "Objections they raised and how they responded"}
                },
                "required": ["prospect_phone", "business_name", "outcome", "temperature", "notes"]
            }
        },
        "server": {"url": f"{WEBHOOK}/vapi/save-notes"}
    }
]

async def main():
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"https://api.vapi.ai/assistant/{ASSISTANT_ID}",
            headers={"Authorization": f"Bearer {VAPI_KEY}", "Content-Type": "application/json"},
            json={"tools": tools},
            timeout=30
        )
        data = resp.json()
        tool_names = [t.get("function", {}).get("name", "transferCall") for t in data.get("tools", [])]
        print(f"Status: {resp.status_code}")
        print(f"Tools added: {tool_names}")

asyncio.run(main())
