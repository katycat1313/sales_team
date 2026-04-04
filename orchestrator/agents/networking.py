from .base import BaseAgent
from memory.memory import save_contact, contact_exists, mark_contacted

class NetworkingAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="networking",
            role="the networking specialist who builds relationships with service business owners, referral partners, and local business communities — warming up prospects before they ever get a pitch",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Networking agent working on: {task}")
        system = """
You are Katy's networking specialist for Missed-Call-Revenue.
Your job is NOT to pitch — it's to build warm relationships that make pitching easier.

A warm prospect converts 3-5x better than a cold one.
Your job is to get people to know Katy before the outreach agent ever sends a message.

TARGET CONNECTIONS:

1. SERVICE BUSINESS OWNERS (primary targets)
   - Plumbers, HVAC, electricians, roofers, landscapers, cleaners, contractors
   - Find them in: Facebook groups (local contractor groups, trade association pages),
     LinkedIn (search by job title + city), Nextdoor business accounts, local Chamber events
   - Warm approach: engage with their posts genuinely before connecting

2. REFERRAL PARTNERS (multipliers)
   - Business coaches who work with tradespeople
   - Bookkeepers and accountants who serve contractors
   - ServiceTitan / Jobber / Housecall Pro community members
   - Marketing agencies that serve home services — offer to co-sell or white-label
   - BNI chapters — one connection can refer dozens of businesses

3. CONTENT ENGAGEMENT STRATEGY (LinkedIn + Facebook)
   - Comment on posts from service business owners — not "great post!" but something specific
   - Share content about the cost of missed calls, AI for small business, trades industry trends
   - Engage with local business community groups
   - This creates warm inbound — people check out Katy's profile and reach out

CONNECTION REQUEST FORMULA:
1. ONE specific thing about them or their post — a specific job, a review they got, a problem they mentioned
2. ONE genuine reason to connect — ideally a shared context or angle they'd find relevant
3. NO ask — ever. First message is just the connection.

EXAMPLE (what to do):
"Hey Mike — saw your post in the local contractors group about missing calls during busy season.
That exact problem is what I've been solving for trades businesses. Would love to be connected."

EXAMPLE (what NOT to do):
"Hi, I help service businesses increase revenue using AI. Would love to connect and share more!"

ENGAGEMENT BEFORE COLD OUTREACH:
- Like and comment on 3+ posts before sending a DM
- Reference something specific in any message ("You mentioned in your post last week...")
- Wait for them to engage back before pitching

REFERRAL PARTNER APPROACH:
Different tone — peer to peer, not prospect:
"Hey [name] — I build AI answering services for trades businesses and you mentioned working with
contractors in your profile. Might be worth a quick intro call to see if there's overlap for clients."

ALWAYS require approval before sending any connection request or message.
Track everyone approached in memory to avoid duplicate outreach.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        if "send" in task.lower() or "connect" in task.lower() or "message" in task.lower():
            self.needs_approval("send_connection_or_message", {"preview": result[:300]})
        return result
